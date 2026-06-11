# scripts_archive/

One-off diagnostic / fixup / debug scripts from earlier sessions. These are
NOT part of the regular dev/test workflow — they were written to chase a
specific bug then left behind. Kept for historical reference in case the
same bug resurfaces; feel free to delete this entire directory if disk
space matters more than the audit trail.

Naming convention matches the original scripts/ dir:
  analyze_*.py  — one-off code analyses (template depth, line counts, etc.)
  check_*.py    — ad-hoc linter / template-balance / served-JS probes
  debug_*.py    — bug-specific debug scripts
  diag_*.py     — diagnostic runners (CDP, coldfusion, SPA, etc.)
  fix_*.py      — one-shot fixup scripts for specific issues
  find_*.py     — grep-like finders for unclosed tags / broken sections
  transform_*.py — AST transforms applied once
  refactor_*.py  — one-off refactors
  validate_*.py  — ad-hoc validators
  patch_*.py     — surgical patches for specific issues
  apply_*.py     — orchestration of multiple fixes

If a script is needed again in active development, move it back to scripts/.

## Date

Archived: 2026-06-11 (session cleanup)
