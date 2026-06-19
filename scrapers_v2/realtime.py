from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
import asyncio
import json

app = FastAPI()

html = """
<!DOCTYPE html>
<html>
<head><title>Elite Scraper v2 - Live</title></head>
<body style="background:#0A1A2F;color:#E0E0E0;font-family:sans-serif">
<h2>🚀 Elite Scraper v2 - Live Feed</h2>
<div id="leads"></div>
<script>
var ws = new WebSocket("ws://localhost:8003/ws");
ws.onmessage = function(event) {
    var lead = JSON.parse(event.data);
    var div = document.createElement("div");
    div.innerHTML = lead.vertical + " | " + lead.source + " | Score: " + lead.meta.predicted_score;
    document.getElementById("leads").appendChild(div);
};
</script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        # Simulate new lead every 3 seconds
        await asyncio.sleep(3)
        lead = {
            "vertical": "Public Adjuster",
            "source": "bbb",
            "meta": {"predicted_score": 87}
        }
        await websocket.send_text(json.dumps(lead))
