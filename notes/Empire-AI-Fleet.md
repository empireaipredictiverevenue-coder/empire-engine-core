---
tags: [fleet, inventory, 2026-06-13]
---

# Empire-AI Fleet (as of 2026-06-13)

## PM2 (10 online)

| pm_id | name                        | exec                                            |
|-------|-----------------------------|-------------------------------------------------|
| 8     | empire-mesh                 | /root/empire-v49/main.py                        |
| 17    | contractor-sniper           | /root/empire-v49/bots/contractor_sniper.py      |
| 23    | empire-hub                  | /root/empire-v49/hub.py :8001                   |
| 25    | empire-chrome               | /root/empire-v49/scripts/chrome_headless.sh     |
| 26    | empire-pulse-cron           | /root/empire-v49/scripts/pulse_refresh_cron.py  |
| 27    | empire-matrix-agi           | /root/empire-v49/matrix/sovereign_agi_matrix.py |
| 28    | empire-matrix-strategy      | /root/empire-v49/strategy/roi_marketing_matrix.py |
| 29    | empire-matrix-landing       | /root/empire-v49/landing/landing_matrix.py      |
| 30    | empire-matrix-universal     | /root/empire-v49/universal/universal_matrix.py  |
| 31    | empire-ppc-inbound          | /root/empire-v49/matrix/main.py                 |

## Uvicorn (external-listening)

- hub `:8001` (empire-v49 hub, public)
- synthetic_brain `:8005` → see [[Empire_AI_Brain]]
- agent_orchestrator `:8042`
- hook_analytics `:8046`

## Internal-only matrix services (127.0.0.1)

- `:8010` empire-matrix-agi
- `:8020` empire-matrix-strategy
- `:8030` empire-matrix-landing
- `:8040` empire-matrix-universal
- `:8045` empire-ppc-inbound

## Other

- ollama `:11434` (llama3.2:3b, qwen2.5-coder:14b)
- chrome devtools `:9222` (visual QA)
- hermes dashboard `:9119`
- nginx `:80/:443` (empire-ai.co.uk)

## Related

- [[Empire_AI_Brain]] — predictive cloud
- [[Parking_Lot]] — deferred ideas
- [[Vonage]] — live-call wiring
