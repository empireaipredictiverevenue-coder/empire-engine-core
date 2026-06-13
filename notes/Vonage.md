---
tags: [vonage, voice, telco, status-blocked]
status: needs-dashboard-rotation
last_diag: 2026-06-13
---

# Vonage

Live-call voice wiring for Empire-AI.

## Identity (current in /root/.env)

- Number: `+12142277528`
- Auth: JWT, private key at `/root/vonage_private.key`
- Application ID: `f0fb5906-a75d-4a2c-90ad-981cce01cd7f`
- API key: `f1e9d2a1` (legacy rest.nexmo.com auth)
- Working endpoint host: `api.nexmo.com` (NOT `api.vonage.com` —
  that one returns 403 from an unrelated AWS load balancer)

## Status — BLOCKED, dashboard-side rotation required (2026-06-13)

Both auth methods return 401 from the live API:

| probe                                  | result | meaning                                     |
|----------------------------------------|--------|---------------------------------------------|
| api.nexmo.com Basic (key:secret)       | 401    | key+secret pair rejected                    |
| api.nexmo.com JWT (RS256 from priv)    | 401    | private key + app id pair rejected          |
| rest.nexmo.com key+secret query        | 401    | same on legacy endpoint                     |
| api.nexmo.com /v2/applications/.../oauth-keys JWT | 401 | same                                   |

The `private.key` was committed to the repo or exposed in logs at some
point — see `docs/KEY_ROTATION.md` ("Emergency Rotation: Vonage Private
Key"). The 401 is the dashboard telling us the app or key has been
revoked/rotated server-side.

## Unblock procedure (from docs/KEY_ROTATION.md)

1. `openssl genrsa -out private_new.key 2048`
2. Dashboard: https://dashboard.nexmo.com/applications → Create new app
   → upload new public key → enable Voice capability → copy new app id
3. `cp private_new.key /root/vonage_private.key && chmod 600`
4. Update `VONAGE_APPLICATION_ID` in `/root/.env`
5. `pm2 restart empire-hub` (so it picks up the new key)
6. `pm2 restart synthetic_brain` (so the brain's HMAC sig path re-checks)
7. Smoke: `python3 -c "from empire_outbound_dialer import OutboundDialer; print('OK')"`
8. Delete the old app from the dashboard

## Per-call flow (when unblocked)

1. Vonage dials the lead.
2. Call audio is patched via websocket to [[Empire_AI_Brain]]
   (`synthetic_brain:app` on port 8005).
3. Brain renders live Kokoro TTS (voice_id + HMAC signature from
   `POST /api/v1/synthetic/register_stream`).
4. Streamed back into the call in real time.

## Related

- [[Empire_AI_Brain]] — synthesis server (now online with rotated key
  after 2026-06-13, see note there)
- [[Empire-AI-Fleet]] — port map
- [[Parking_Lot]] — outreach agent runtime is parked, blocked on
  this Vonage 401 + 1 real lead + 1 real contractor.
