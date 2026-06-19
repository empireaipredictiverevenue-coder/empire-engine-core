"""
Take screenshots of the Empire-AI dashboards using Chrome DevTools Protocol.

Uses the Chrome instance already running on 127.0.0.1:9222 (PID 3451971,
started by scripts/chrome_headless.sh). For each URL: opens a new tab,
navigates, waits for network idle + 2s for React hydration, captures
full-page PNG to /tmp/dashboards/<safe-name>.png.

Then the operator sends them to Phil via the Telegram bot using
`hermes send --to telegram --file <path>`.
"""

import json
import os
import sys
import time
import urllib.request
import websocket  # pip install websocket-client (need to check if available)

CHROME = "http://127.0.0.1:9222"
OUTDIR = "/tmp/dashboards"

URLS = [
    ("hub",        "http://127.0.0.1:8001/"),
    ("hub_command","http://127.0.0.1:8001/command"),
    ("hub_contractors", "http://127.0.0.1:8001/contractors/signup"),
    ("hermes",     "http://127.0.0.1:9119/"),
    ("hermes_sessions", "http://127.0.0.1:9119/sessions"),
    ("brain",      "http://127.0.0.1:8005/"),
    ("orchestrator","http://127.0.0.1:8042/docs"),
]

os.makedirs(OUTDIR, exist_ok=True)

def http_json(url, method=None):
    req = urllib.request.Request(url, method=method) if method else urllib.request.Request(url)
    return json.loads(urllib.request.urlopen(req, timeout=5).read())

def new_tab(url):
    """Create a new tab and return its wsUrl."""
    return http_json(f"{CHROME}/json/new?{urllib.parse.quote(url, safe=':/?&=')}", method="PUT")

import urllib.parse  # late import so the script header stays clean

results = []
for name, url in URLS:
    print(f"\n=== {name}  {url} ===", flush=True)
    try:
        tab = new_tab(url)
    except Exception as e:
        print(f"  create tab failed: {e}")
        results.append((name, url, None, str(e)))
        continue
    ws_url = tab.get("webSocketDebuggerUrl")
    tab_id = tab.get("id")
    print(f"  tab id={tab_id[:8]}  ws={ws_url[:60]}...")
    if not ws_url:
        results.append((name, url, None, "no ws url"))
        continue

    # Connect CDP
    try:
        ws = websocket.create_connection(ws_url, timeout=10)
    except Exception as e:
        print(f"  ws connect failed: {e}")
        results.append((name, url, None, str(e)))
        continue

    msg_id = [0]
    def send(method, params=None):
        msg_id[0] += 1
        ws.send(json.dumps({"id": msg_id[0], "method": method, "params": params or {}}))
        # Read until matching id
        while True:
            raw = ws.recv()
            data = json.loads(raw)
            if data.get("id") == msg_id[0]:
                return data

    # Wait for load (Chrome opened the tab and started navigating; Page.navigate
    # isn't needed since the tab was opened with the URL as initial).
    # Instead, poll Page.frameStoppedLoading or just wait 5s.
    time.sleep(5.0)

    # Capture full page screenshot
    try:
        result = send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
        ws.close()
        if "result" in result and "data" in result["result"]:
            png = result["result"]["data"]
            import base64
            out = f"{OUTDIR}/{name}.png"
            with open(out, "wb") as f:
                f.write(base64.b64decode(png))
            size = os.path.getsize(out)
            print(f"  saved {out}  ({size//1024} KB)")
            results.append((name, url, out, None))
        else:
            print(f"  capture failed: {result}")
            results.append((name, url, None, json.dumps(result)[:200]))
    except Exception as e:
        print(f"  screenshot error: {e}")
        try: ws.close()
        except: pass
        results.append((name, url, None, str(e)))

print("\n\n=== summary ===")
for name, url, out, err in results:
    if out:
        print(f"  OK    {name:18s}  {out}")
    else:
        print(f"  FAIL  {name:18s}  {err}")
