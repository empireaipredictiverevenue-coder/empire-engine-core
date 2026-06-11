#!/usr/bin/env python3
"""CDP diagnostic: enable Runtime BEFORE navigation to catch module errors."""
import json, time, urllib.request, sys

CHROME_URL = "http://127.0.0.1:9222"
TARGET_URL = "http://localhost:8000/command"

try:
    import websocket
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "websocket-client", "-q"], check=True)
    import websocket

# Create blank tab (don't navigate yet)
req = urllib.request.Request(f"{CHROME_URL}/json/new", method="PUT")
resp = urllib.request.urlopen(req, timeout=5)
tab = json.loads(resp.read())
print(f"Tab: {tab['id']}")

# Connect WebSocket BEFORE navigating
ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=10, suppress_origin=True)

# Enable domains
for dom in ["Runtime", "Console", "Network"]:
    ws.send(json.dumps({"id": 1, "method": f"{dom}.enable"}))
    time.sleep(0.3)

# Drain initial responses
try:
    ws.settimeout(0.2)
    while True: ws.recv()
except: pass

# NOW navigate
print("Navigating...")
ws.send(json.dumps({"id": 5, "method": "Page.navigate", "params": {"url": TARGET_URL}}))
time.sleep(2)

# Wait for page load
print("Waiting 15s for page + CDN...")
time.sleep(15)

# Collect ALL accumulated events
print("\n=== COLLECTING EVENTS ===")
events = []
for _ in range(50):
    try:
        ws.settimeout(0.3)
        events.append(json.loads(ws.recv()))
    except:
        break

# Analyze
exceptions = []
console_msgs = []
network_fails = []

for data in events:
    method = data.get("method", "")
    params = data.get("params", {})
    
    if method == "Runtime.exceptionThrown":
        exc = params.get("exceptionDetails", {})
        exceptions.append(exc)
        print(f"\n❌ EXCEPTION:")
        print(f"   text: {exc.get('text', '')}")
        print(f"   url: {exc.get('url', '')}")
        print(f"   line: {exc.get('lineNumber', 0)}:{exc.get('columnNumber', 0)}")
        desc = exc.get('exception', {}).get('description', '')
        print(f"   desc: {desc[:500]}")
        # Stack trace
        for frame in exc.get("stackTrace", {}).get("callFrames", [])[:3]:
            fn = frame.get("functionName", "(anon)")
            f_url = frame.get("url", "?")
            f_ln = frame.get("lineNumber", 0)
            print(f"      at {fn} ({f_url}:{f_ln})")
    
    elif method == "Console.messageAdded":
        msg = params.get("message", {})
        if msg.get("level") in ("error", "warning"):
            console_msgs.append(msg)
            print(f"\n📋 [{msg['level'].upper()}] {msg.get('text','')[:300]}")
    
    elif method == "Network.loadingFailed":
        url = params.get("url", "")
        err = params.get("errorText", "")
        if "esm.sh" in url or "localhost" in url:
            network_fails.append(params)
            print(f"\n🌐 NET FAIL: {err} — {url[:80]}")

# Page state check
print("\n=== PAGE STATE ===")
ws.send(json.dumps({"id": 10, "method": "Runtime.evaluate", "params": {
    "expression": "JSON.stringify({rootChildren: (document.getElementById('root')||{}).children?.length||0, title: document.title, bodyLen: document.body?.innerHTML?.length||0, moduleScripts: document.querySelectorAll('script[type=module]').length, importMap: !!document.querySelector('script[type=importmap]')})",
    "returnByValue": True
}}))
time.sleep(1)
try:
    ws.settimeout(2)
    while True:
        resp = ws.recv()
        data = json.loads(resp)
        result = data.get("result", {})
        if "result" in result:
            val = result.get("result", {}).get("value", "")
            state = json.loads(val)
            print(f"   {val}")
            if state.get("rootChildren", 0) > 0:
                print("✅ REACT MOUNTED!")
            else:
                print("❌ React did not mount")
            break
except Exception as e:
    print(f"   Failed: {e}")

print(f"\n=== SUMMARY ===")
print(f"Exceptions: {len(exceptions)}")
print(f"Console errors: {len(console_msgs)}")
print(f"Network failures: {len(network_fails)}")

# Close
ws.close()
try:
    urllib.request.urlopen(urllib.request.Request(f"{CHROME_URL}/json/close/{tab['id']}", method="POST"), timeout=5)
except:
    pass
