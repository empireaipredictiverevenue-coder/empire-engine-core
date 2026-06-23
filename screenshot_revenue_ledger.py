#!/usr/bin/env python3
"""Screenshot the Revenue Ledger SPA via Chrome DevTools Protocol."""
import json, base64, time, subprocess

# Ensure websocket-client is available
subprocess.run(["pip3", "install", "-q", "websocket-client"], capture_output=True)
import websocket

# List existing pages to find one we can reuse
resp = subprocess.run(["curl", "-s", "http://localhost:9222/json"], capture_output=True, text=True)
pages = json.loads(resp.stdout)
print(f"Found {len(pages)} existing pages")

# Try to create a new tab
resp = subprocess.run(
    ["curl", "-s", "-X", "PUT", "http://localhost:9222/json/new?about:blank"],
    capture_output=True, text=True
)
if resp.stdout.strip():
    tab = json.loads(resp.stdout)
    ws_url = tab["webSocketDebuggerUrl"]
    print(f"Created new tab: {tab['id']}")
else:
    # Fall back to first existing page
    tab = pages[0]
    ws_url = tab["webSocketDebuggerUrl"]
    print(f"Using existing tab: {tab['id']}")

ws = websocket.create_connection(ws_url, timeout=15)

_cdp_id = [0]
def send_cdp(ws, method, params=None):
    _cdp_id[0] += 1
    msg_id = _cdp_id[0]
    msg = json.dumps({"id": msg_id, "method": method, "params": params or {}})
    ws.send(msg)
    # Keep receiving until we get a response with matching id
    for _ in range(20):
        raw = ws.recv()
        resp = json.loads(raw)
        if resp.get("id") == msg_id:
            return resp
        # Otherwise it's an event - ignore and continue
    return {"error": "no matching response after 20 messages"}

# Enable domains
send_cdp(ws, "Page.enable")
send_cdp(ws, "Runtime.enable")

# Inject auth token before any page script runs
send_cdp(ws, "Page.addScriptToEvaluateOnNewDocument", {
    "source": "localStorage.setItem('hub_token', 'Jaykub20*');"
})
print("Pre-navigation script registered")

# Navigate to the SPA with #/ledger hash
send_cdp(ws, "Page.navigate", {"url": "http://localhost:8001/command#/ledger"})

# Poll for document.readyState
for i in range(20):
    time.sleep(0.5)
    result = send_cdp(ws, "Runtime.evaluate", {
        "expression": "document.readyState"
    })
    state = (result.get('result', {}).get('result', {}).get('value', 'loading'))
    if i % 3 == 0:
        print(f"  [{i*0.5:.0f}s] readyState: {state}")
    if state == "complete":
        break

# Wait for React to render + API calls to complete
print("Waiting for React + API calls...")
time.sleep(5)

# --- CHECK PAGE STATE ---
result = send_cdp(ws, "Runtime.evaluate", {
    "expression": """JSON.stringify({
        title: document.title,
        hash: window.location.hash,
        tokenSet: !!localStorage.getItem('hub_token'),
        hasNav: !!document.querySelector('.nav'),
        hasSectionTitle: !!document.querySelector('.section-title'),
        sectionTitleText: (document.querySelector('.section-title') || {}).innerText || '',
        statCards: document.querySelectorAll('.stat-card').length,
        statLabels: Array.from(document.querySelectorAll('.stat-label')).map(e => e.innerText).slice(0, 8),
        panelTitles: Array.from(document.querySelectorAll('.panel-title')).map(e => e.innerText).slice(0, 6),
        hasTables: !!document.querySelector('table.tbl'),
        loadingText: (document.querySelector('.psy-loading') || {}).innerText || '',
        errorText: (document.querySelector('.psy-error') || {}).innerText || '',
        bodyText: document.body.innerText.substring(0, 800)
    })"""
})
page_state_raw = result.get('result', {}).get('result', {}).get('value', 'NO JSON')
try:
    page_state = json.loads(page_state_raw) if isinstance(page_state_raw, str) else page_state_raw
    print(f"\n=== PAGE STATE ===")
    for k, v in page_state.items():
        if k == 'bodyText':
            print(f"  {k}: {str(v)[:200]}...")
        else:
            print(f"  {k}: {v}")
except Exception:
    print(f"State parse failed: {str(page_state_raw)[:500]}")

# --- TAKE SCREENSHOT ---
result = send_cdp(ws, "Page.captureScreenshot", {"format": "png", "fromSurface": True})
if "result" in result and "data" in result["result"]:
    img_data = base64.b64decode(result["result"]["data"])
    path = "/root/empire-v49/tmp_revenue_ledger.png"
    with open(path, "wb") as f:
        f.write(img_data)
    print(f"\nScreenshot saved to {path} ({len(img_data)} bytes)")
else:
    print(f"\nScreenshot failed: {str(result)[:300]}")

ws.close()
print("Done")
