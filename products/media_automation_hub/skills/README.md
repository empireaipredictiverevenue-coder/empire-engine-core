# Media Automation Hub — Pipeline Skills

These skills teach AI coding assistants how to use the media automation hub.
Modeled after OpenMontage's skill system: each skill is a markdown file that
describes how to execute a specific stage or use a specific tool.

## Pipeline Stage Director Skills

Each pipeline has a directory under `pipelines/<pipeline-name>/` with
one skill file per stage. The orchestrator reads the pipeline YAML to
determine which stages to run and in what order.

### Short-Form Pipeline Skills

- `short-form/research.md` — Research trending topics and hooks
- `short-form/script.md` — Generate short-form scripts
- `short-form/render.md` — Compose and render vertical video
- `short-form/publish.md` — Upload to platforms with SEO metadata

## Tool Skills

Each tool has a skill file describing how to use it effectively.
These are optional but help AI assistants make better tool choices.

## Meta Skills

- `onboarding.md` — First-time setup and discovery flow
- `self-review.md` — Post-render quality checklist
