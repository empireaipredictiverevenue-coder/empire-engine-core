---
tags: [rag, obsidian, brain, 2026-06-22, free-impl]
---

# Obsidian RAG Layer — Brain Vault Awareness (2026-06-22)

**Status:** Active. Every `AIRouter.generate()` + `generate_json()` call now
auto-injects relevant vault notes into the system prompt. Free. ~1ms per call.
No embeddings, no model load, no API cost.

## What it does

Before any brain call, the router runs keyword scoring against the obsidian
vault, picks the top-3 most relevant notes, and prepends them to the system
message. The brain sees its own notes as context, the same way a human
employee would skim a wiki before answering a question.

## Files

- `/root/empire-v49/empire_obsidian_rag.py` — `build_context(query, vault_path=None)` returns a markdown block. ~1ms. Caps at 1500 chars by default, top-K=3, min_score=2.
- `/root/empire-v49/empire_ai_router.py` — wires RAG into `generate()` and `generate_json()`. Fails silent if vault is missing or empty.

## How scoring works

Token overlap with stopwords removed. Filename-weighted, heading-weighted,
content-weighted equally. Top-K=3 by score. Min score=2 (a single accidental
keyword match won't fire).

Example — query "what is the brain upgrade path":
```
score 8 → Brain_MiniMax_Live_2026-06-22.md   (primary brain note)
score 8 → Parking_Lot.md                     (mentions "obsidian wiring")
```

## Safety

- Reads only `*.md` under `OBSIDIAN_VAULT_PATH` (default `/root/empire-v49/notes`).
- Strips frontmatter and wikilinks before scoring.
- Skips notes whose first 500 chars contain `api_key|secret|password|token|private_key = ...` patterns. Conservative — skips the whole note if any secret-like value appears, not just the line.
- Caps output at `RAG_MAX_CONTEXT_CHARS` (1500 default).
- Vault missing / unreadable / no matches → returns "" → brain still works without context.

## Live verification (2026-06-22 09:18 UTC)

```
q="Which AI models are wired into the brain?"
→ RAG pulled Brain_MiniMax_Live_2026-06-22.md
→ brain response quoted the provider table verbatim

q="What is the current pending fee total?"
→ RAG pulled Sessions/2026-06-22_payment_and_recovery.md
→ brain quoted $43,559 / 4 ghosting contractors

q="What is the recipe for banana bread?"
→ no relevant notes (min score not hit)
→ no context block injected
→ brain answered with a clean banana bread recipe, no prompt bloat
```

## Tunables (env)

| Var | Default | Effect |
|-----|---------|--------|
| `RAG_MAX_CONTEXT_CHARS` | 1500 | Max injected block size |
| `RAG_TOP_K` | 3 | Max notes per block |
| `RAG_MIN_SCORE` | 2 | Min keyword overlap to include a note |
| `RAG_MAX_CHARS_PER_NOTE` | 600 | Per-note excerpt cap |
| `OBSIDIAN_VAULT_PATH` | `/root/empire-v49/notes` | Vault root |

## Failure modes (handled)

- Vault deleted → returns "", brain runs without RAG, no error.
- Note file unreadable → skipped silently, no error to caller.
- Secret-shaped string in note → whole note skipped (conservative).
- All scores below threshold → returns "" (no empty-block bloat).
- Tokenizer regex fail → returns "" (no exception escapes).

## What it is NOT

- Not semantic search. Two notes that mean the same thing with different
  words won't match. Fine for an 8-50 note vault; swap to embeddings
  if the vault crosses ~100 notes.
- Not a RAGAS / retrieval eval. We trust the keyword overlap as "good enough
  for a 1M-ctx flagship" — the brain quotes 600-char excerpts and the user
  can re-prompt if the wrong note surfaced.
- Not a write path. RAG reads; obsidian notes are still edited by hand
  (or by future agents via a separate module).

## What this enables

- The brain can answer "what is the splash title?" by quoting the session
  note that says "Storm Revenue Engine".
- The brain can answer "what's pending in fees?" by quoting the
  payment-and-recovery note.
- The brain can answer "what's in the fleet?" by quoting Empire-AI-Fleet.md.

This is the "company knowledge" piece that makes a fine-tuned model
optional. Next upgrade: 1-2 day LoRA fine-tune on outbound copy + RAG
together = a brain that knows the company AND sounds like us.

## Related

- [[Brain_MiniMax_Live_2026-06-22]] — base brain upgrade
- [[Brain_Upgrade_2026-06-22]] — earlier provider work
- [[Empire-AI-Fleet]] — process map (RAG pulls this)
- [[Sessions/2026-06-22_payment_and_recovery]] — the day RAG went live