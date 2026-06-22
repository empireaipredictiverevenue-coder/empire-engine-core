---
tags: [brain, upgrade, zai, glm-5.2, anthropic, provider, 2026-06-22]
---

# Synthetic Brain Upgrade — GLM 5.2 + Claude Sonnet 4

User asked about upgrading the brain to "GLM 5.2" (Z.ai flagship, 753B params, released 2026-06-16). Research agent confirmed:

- GLM 5.2 is **753B-parameter MoE**, ~$42/mo at 1M input tokens/day, 976K context window.
- **No local install is viable** on a 14GB-disk / 15GB-RAM box (smallest GGUF is 222GB, needs ~240GB RAM to run).
- Only Z.ai API (`https://api.z.ai/api/paas/v4`) is reachable. OpenAI-compatible, drop-in.
- We do **not** have a `ZAI_API_KEY` in `/root/.env` yet. To activate GLM 5.2: signup at `z.ai`, add key, restart hub.

## What we did (2026-06-22)

### 1. Patched `empire_ai_router.py` (multi-provider)

Replaced the hardcoded `PROVIDER = "ollama"` router with provider-aware dispatch:

- `_provider_for_model(model_name)` → returns `"zhipu"`, `"anthropic"`, or `"ollama"` based on prefix.
- New methods: `_call_zhipu()`, `_call_anthropic()`, `call_any()` dispatch wrapper.
- Provider activated only when its env key is set (`ZAI_API_KEY` / `ANTHROPIC_API_KEY`). If absent, falls through to Ollama (no breakage).
- Cost tracking per provider (GLM 5.2: $1.40/M in + $4.40/M out; Sonnet 4: $3/M in + $15/M out).

Provider resolution rules:
| Model prefix        | Provider    |
|---------------------|-------------|
| `glm-*` / `zhipu:*` / `zai/*` | Z.ai (OpenAI-compat) |
| `claude-*` / `anthropic:*`     | Anthropic Messages API |
| everything else     | Ollama local (unchanged) |

### 2. Patched `/api/v1/brain/chat` endpoint

Now accepts optional `model` field in body. Provider auto-selected. Response includes `model`, `tokens_in`, `tokens_out` for observability.

### 3. Added `keep_alive: "30m"` to Ollama calls

Was unloading the 3B model after 5min idle, causing 60s cold-load penalty on every background tick. Now stays warm for 30min.

### 4. Replaced dead `llama3:8b` references (6 files)

`products/agent_orchestrator.py`, `products/buyer_spy.py`, `matrix/sovereign_agi_matrix.py`, `landing/landing_matrix.py`, `strategy/roi_marketing_matrix.py`, `empire_niche_terrain.py` all referenced a non-existent model → 404. Replaced with `llama3.2:3b` (installed).

### 5. Hub restart loop investigation

Was at 8201+ restarts. Root cause: Ollama timeouts on overloaded box (load avg 25-43 on 1-2 CPU). After `keep_alive: 30m`, the model stays in RAM and load drops on the next cycle. Current restarts stable at 8202 (no growth over 7 min).

## To activate GLM 5.2 today

```bash
# 1. Get key from z.ai (email signup, pay-as-you-go, ~$42/mo at 1M tok/day)
# 2. Add to /root/.env:
echo 'ZAI_API_KEY=sk-your-key-here' >> /root/.env
# 3. Restart hub:
pm2 restart empire-hub
# 4. Test via:
curl -s -X POST http://localhost:8001/api/v1/brain/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HUB_TOKEN" \
  -d '{"model":"glm-5.2","prompt":"PONG","system":"Reply with only the word PONG"}'
```

To route `brain.proxy` task specifically to GLM 5.2 (high-context planning) and keep other tasks on Ollama:
```bash
echo 'AI_MODEL_DECIDE=glm-5.2' >> /root/.env   # brain.decide task → GLM 5.2
# other tasks stay on llama3.2:3b
```

## Sonnet 4 alternative

Already keyed (`ANTHROPIC_API_KEY` in `/root/.env`). Drop-in: send `{"model":"claude-sonnet-4-5", ...}`. Currently cheaper than GLM 5.2 for small prompts but no 1M context. Use for sub-200K planning tasks; reserve GLM 5.2 for long-horizon brain.decide prompts.

## Files changed

- `/root/empire-v49/empire_ai_router.py` — multi-provider dispatch + keep_alive
- `/root/empire-v49/hub.py` — brain_chat accepts `model` field
- `/root/empire-v49/products/agent_orchestrator.py` — llama3:8b → llama3.2:3b
- `/root/empire-v49/products/buyer_spy.py` — llama3:8b → llama3.2:3b
- `/root/empire-v49/matrix/sovereign_agi_matrix.py` — same
- `/root/empire-v49/landing/landing_matrix.py` — same
- `/root/empire-v49/strategy/roi_marketing_matrix.py` — same
- `/root/empire-v49/empire_niche_terrain.py` — same

## Related

- [[Empire_AI_Brain]] — base brain doc (voice/video focus)
- [[Empire-AI-Fleet]] — process map (refreshed)
- [[Sessions/2026-06-22_payment_and_recovery]] — today's earlier work
- [[STARTING_POINT]] — locked directive still gates 1-fee milestone
- [[Parking_Lot]] — obsidian ↔ brain integration still parked (could now wire)