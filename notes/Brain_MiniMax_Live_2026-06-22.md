---
tags: [brain, minimax, upgrade, 2026-06-22, provider, online]
---

# Synthetic Brain Upgrade — MiniMax-M3 LIVE (2026-06-22)

**Status:** Active. User supplied `MINIMAX_API_KEY` (token-based, monthly plan).
Empire brain proxy now serves real MiniMax responses. Multiple bugs surfaced
during activation (see "Bugs fixed" below).

## Wired provider (empire_ai_router.py)

`/api/v1/brain/chat` and the AIRouter dispatch now supports 4 providers:

| Provider  | Env key                  | Models | When to use |
|-----------|--------------------------|--------|-------------|
| **minimax** | `MINIMAX_API_KEY`     | MiniMax-M3, M2.7, M2.5, M2.1 | Primary brain (this user) |
| zhipu      | `ZAI_API_KEY`            | GLM 5.2 etc. | Long-horizon planning, 1M ctx |
| anthropic  | `ANTHROPIC_API_KEY`      | Claude Sonnet 4/4.5 | Reasoning, structured output |
| ollama     | (always available)       | llama3.2, qwen2.5-coder | Local fallback, no key needed |

Provider auto-selected by model name prefix (`minimax-`, `MiniMax-`, `glm-`,
`claude-`, etc.). Falls through to ollama if no key set for the chosen provider.

## Activated routing (`/root/.env`)

```
AI_DEFAULT_MODEL    = MiniMax-M3    (brain.proxy + general)
AI_MODEL_DECIDE     = MiniMax-M3    (brain.decide)
AI_MODEL_QUALIFY    = MiniMax-M2.1  (reply.qualify)
AI_MODEL_ENRICH     = MiniMax-M2.1  (enricher.extract)
AI_MODEL_NARRATE    = MiniMax-M2.5  (narrate.event)
AI_MODEL_DRAFT      = MiniMax-M2.5  (email.draft)
AI_MODEL_BRIEFING   = MiniMax-M2.7  (mission.briefing)
```

## Latency / cost profile (probed live on the user's key)

| model          | latency | use case |
|----------------|--------:|---|
| MiniMax-M3     | 1.4s   | flagship reasoning |
| MiniMax-M2.7   | 2.0s   | step-down strong |
| MiniMax-M2.5   | 0.8s   | fast email/narrate |
| MiniMax-M2.1   | 0.8s   | cheap qualify/enrich |
| MiniMax-M2     | 1.0s   | oldest, fallback |

All models emit `<think>...</think>` reasoning by default. The router strips it
and exposes it via `reasoning_content` for callers that want it.

## Bugs fixed during activation

1. **Module-level env capture** — `MINIMAX_API_KEY` was set at import time,
   before hub.py loaded `/root/.env`. Dispatcher re-reads `os.environ.get()`
   per call now.

2. **TokenProxy wrap bypass** — `empire_token_proxy.wrap_router()` captured
   `original_generate._ollama_call` (legacy Ollama-only path). The wrap now
   calls the full `original_generate()` so the dispatch runs.

3. **TASK_MODEL computed at import** — Per-task routing defaults are now
   re-evaluated in `AIRouter.__init__` so post-import env loads are picked up.

4. **brain.proxy not in TASK_MODEL** — `AI_DEFAULT_MODEL=MiniMax-M3` makes
   the brain_chat endpoint default to MiniMax when no model override.

## Verified live

```
$ curl -X POST .../api/v1/brain/chat -d '{"prompt":"Capital of France? One word."}'
{"response":"Paris","model":"MiniMax-M3",...}

$ curl ... -d '{"model":"MiniMax-M2.1","prompt":"2+2?"}'
{"response":"2 + 2 = 4",...}

$ curl ... -d '{"model":"MiniMax-M2.5","prompt":"2+2?"}'
{"response":"2 + 2 = 4",...}
```

## File diff summary

- `/root/empire-v49/empire_ai_router.py` — added `_call_minimax()`,
  `_provider_for_model()` accepts `minimax-*` / `MiniMax-*` prefixes,
  dispatchers re-read env, `__init__` re-evaluates task routing.
- `/root/empire-v49/empire_token_proxy.py` — wrap calls the full
  `original_generate()` instead of the legacy `_ollama_call` snapshot.
- `/root/empire-v49/hub.py` — `/api/v1/brain/chat` accepts `model` override
  (added in earlier session).
- `/root/.env` — `MINIMAX_API_KEY`, `MINIMAX_MODEL`, `MINIMAX_BASE_URL`
  + all 6 `AI_MODEL_*` task routes set to MiniMax.

## Related

- [[Brain_Upgrade_2026-06-22]] — earlier work adding Z.ai + Anthropic providers
- [[Empire-AI-Fleet]] — process map
- [[STARTING_POINT]] — locked directive unchanged