---
tags: [vonage, voice, telco, partial-blocked]
status: creds-rotated-routes-missing
last_diag: 2026-06-13
---

# Vonage

Live-call voice wiring for Empire-AI.

## Identity (current in /root/.env, 2026-06-13)

- Number: `+12142277528`
- Auth: JWT, private key at `/root/vonage_private.key` (sha256: `2e95316d...71a4`)
- Application ID: `231873a5-68d1-4028-8ffb-000853072332` (renamed `Empire-AI_Voice`)
- API key: `f1e9d2a1` (legacy rest.nexmo.com auth)
- API secret: set (10 chars)
- Working endpoint host: `api.nexmo.com` (NOT `api.vonage.com`)

## Status - CREDS FIXED, ROUTES MISSING (2026-06-13)

Credentials were rotated this session after the old private key was
compromised via a chat paste. New app created in dashboard with fresh
keypair; on-disk public key matches the dashboards stored public key.

### Auth probes (POST-rotation)

| probe                                            | result | meaning                              |
|--------------------------------------------------|--------|--------------------------------------|
| rest.nexmo.com /account/get-balance (key:secret) | 200    | balance 9.73 EUR - account healthy   |
| api.nexmo.com /v1/applications/{id} (key:secret) | 200    | app retrievable                      |

The pre-rotation 401s on the JWT path may have been a red herring - once
the account creds are valid, the app-level JWT path may also work. Not
re-verified this session; defer to next.

### Vonage app voice webhooks (per /v1/applications/{id} response)

  - `answer_url` -> `https://empire-ai.co.uk/webhook/vonage-answer` (POST)
  - `event_url`  -> `https://empire-ai.co.uk/webhook/vonage-event` (POST)

### NEXT BLOCKER - the hub has no routes for these

`grep` of hub.py: only `/webhook/lead` is registered. `/webhook/vonage-answer`
and `/webhook/vonage-event` are 404. Until those routes exist, every
inbound vonage call is a 404 -> `sip_status=502` -> failed.

The vonage webhook log earlier today showed hundreds of:
  `GET /webhooks/answer?status=failed&sip_status=502` from 216.147.2.x
confirming every inbound call was rejected.

### Building the routes (next session)

- `empire_voice.py` already has `ncco_dynamic_inbound`, `ncco_dynamic_outbound`,
  and `VoiceRouter`. They just need to be wired into hub routes.
- Answer route must return NCCO JSON. Event route is informational only
  (logs call status, durations, etc.).
- Reference: the dashboard already points the right URLs at the right
  paths - only the server side is missing.

## Related

- [[Empire_AI_Brain]] - synthesis server (online, key rotated 2026-06-13)
- [[Empire-AI-Fleet]] - port map
- [[Parking_Lot]] - outreach agent runtime is parked, blocked on:
  (a) these missing webhook routes, (b) 1 real lead, (c) 1 real contractor.
