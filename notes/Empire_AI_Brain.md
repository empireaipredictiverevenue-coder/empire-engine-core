---
tags: [brain, predictive-cloud, port-8005]
---

# Empire AI Synthetic Brain

The "predictive cloud" of Empire-AI. Lives on the Hetzner box (5.78.148.141),
bound to 127.0.0.1:8005, served by uvicorn as `synthetic_brain:app`.

## What it actually is

Not a weather/lead-scoring engine. It's a **real-time voice + video
synthesis server** for outbound phone calls.

- `POST /api/v1/synthetic/register_stream` — script + Kokoro voice
  (`am_michael` | `af_sarah`) → returns `voice_id`, HMAC `signature`, and
  a `ws://` URL that Vonage patches into the live call.
- `POST /api/v1/synthetic/run` — `AGICommand{objective}` → renders a
  video file at `/root/empire-v49/builds/production_vault/<id>/rendered_output.mp4`.

## Auth

- Both endpoints require `X-API-Key: <SYNTHETIC_BRAIN_API_KEY>`.
- Current key (dev): `test-key-please-change-in-production`
- Stream HMAC reuses the same secret.
- Bound 127.0.0.1 only — not externally reachable. [[Vonage]] calls it
  over a same-host websocket.

## Related

- See [[Vonage]] for the live-call wiring.
- See [[Empire-AI-Fleet]] for the full process map.
- Predictive revenue routing lives separately in `empire-matrix-agi`
  (port 8010), NOT in this service.
