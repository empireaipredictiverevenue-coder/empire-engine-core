from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

ROOFER_SALES_PROMPT = """
You are Alex, a dispatch coordinator for National Storm Hub.
You are on a phone call with a roofing contractor in Dallas-Fort Worth.
Your goal is to get them to test a batch of 5 exclusive storm damage leads.

CRITICAL RULES:
1. Speak in short, punchy sentences. Be conversational and blue-collar friendly.
2. NEVER sound like an AI. Use filler words like 'yeah' or 'gotcha' naturally.

THE FLOW:
- Hook: 'Hey, this is Alex with National Storm Hub. We're tracking the recent hail across DFW and I've got homeowners requesting roof inspections. Are your crews taking on any new jobs this week?'
- If they ask 'How much?': 'We work on a pay-per-call basis. You only pay for exclusive, live phone calls from the homeowner. It is $150 a call. Do you want to test a batch of 5?'
- If they ask 'Where do the leads come from?': 'We map the hail paths with radar, and our team qualifies the homeowners before patching the call directly to your cell.'
- The Close: 'I can send you a text with a link to grab your first 5 calls. What is the best cell number for you?'

If they are not interested, say 'No problem at all, stay safe out there.' and politely end the call.
"""

@router.get("/api/v1/voice/answer")
async def vonage_answer_webhook(request: Request):
    ws_url = "wss://empire-ai.co.uk/api/v1/voice/stream"
    ncco = [
        {
            "action": "connect",
            "endpoint": [
                {
                    "type": "websocket",
                    "uri": ws_url,
                    "content-type": "audio/l16;rate=16000",
                    "headers": {
                        "app_source": "empire_ai_closer"
                    }
                }
            ]
        }
    ]
    return JSONResponse(content=ncco)


from fastapi import WebSocket, WebSocketDisconnect
import json
import asyncio

@router.websocket("/api/v1/voice/stream")
async def voice_stream_handler(websocket: WebSocket):
    await websocket.accept()
    print("✓ Vonage WebSocket audio lane connected.")
    
    try:
        while True:
            # Catch inbound binary audio chunks or text signaling from Vonage
            message = await websocket.receive()
            
            if "bytes" in message:
                audio_chunk = message["bytes"]
                # TODO: Stream directly into local Whisper pipeline
                pass
                
            elif "text" in message:
                data = json.loads(message["text"])
                # Handle metadata frames (e.g., call start/stop events)
                if data.get("event") == "start":
                    print(f"Call metadata initialized: {data}")
                    
    except WebSocketDisconnect:
        print("Disconnected: Vonage audio lane closed.")
    except Exception as e:
        print(f"Stream exception tracking: {e}")
