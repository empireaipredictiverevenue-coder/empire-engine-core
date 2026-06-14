# log.md — chronological wiki ingest log

Append-only. Use a consistent prefix for greppability. The pattern
is `## [YYYY-MM-DD] ingest | <title>` or `## [YYYY-MM-DD] edit | <page>`.

```bash
# Show the last 5 entries
grep "^## \[" log.md | tail -5
```

## [2026-06-14] scaffold | empire-ai wiki

Initial scaffold. Created `/root/empire-v49/wiki/` with:

- `AGENTS.md` — schema + operations (ingest, query, lint) +
  security note on prompt-injection risk from karpathy's gist.
- `index.md` — content catalog with 11 page stubs covering
  architecture, pipeline, contractors, QC, operators, compliance,
  lanes, conventions.
- `log.md` — this file.
- `architecture.md` — what empire-ai is, the funnel, the 3
  services (splash, contractor, fee).
- `locked-directive.md` — the 4-step definition of "done" and the
  current score (2/4 as of 2026-06-14).
- `dispatcher.md` — the runtime SMS dispatcher, the v1/v2 A/B
  split, the 422 counter (commit 0e0b6a1), the send-time DNC
  gate (commit ff27c69).

Pattern: karpathy's `llm-wiki` gist (April 2026, 5000+ stars).
LLM-driven persistent markdown that compounds as the project
evolves. Obsidian is one tool to host this; we're using a
plain git-tracked directory + markdown because the box is headless.

The wiki's purpose: re-orient after a break, and let the next
operator session not re-derive everything from scratch.

Future ingests should follow `AGENTS.md` operations: drop a source
in `raw/`, append an entry here, update affected pages, update
`index.md`.
