"""Re-shoot one URL into a fixed file."""
import json, urllib.request, urllib.parse, base64, time, os
import websocket

CHROME = 'http://127.0.0.1:9222'
url = 'http://127.0.0.1:8000/contractors/signup'
out = '/tmp/dashboards/hub_contractors_v2.png'

quoted = urllib.parse.quote(url, safe=':/?&=')
tab = json.loads(urllib.request.urlopen(
    urllib.request.Request(f'{CHROME}/json/new?{quoted}', method='PUT'),
    timeout=5).read())
ws = websocket.create_connection(tab['webSocketDebuggerUrl'], timeout=10)
ws.send(json.dumps({'id': 1, 'method': 'Page.navigate', 'params': {'url': url}}))
ws.recv()
time.sleep(4)
ws.send(json.dumps({'id': 2, 'method': 'Page.captureScreenshot',
                    'params': {'format': 'png', 'captureBeyondViewport': True}}))
result = json.loads(ws.recv())
ws.close()
with open(out, 'wb') as f:
    f.write(base64.b64decode(result['result']['data']))
print(f'saved {out} {os.path.getsize(out)} bytes')
