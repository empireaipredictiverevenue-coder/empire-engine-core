#!/usr/bin/env python3
"""
check_fee_copy.py — CI guard against stale 1% fee copy in marketing strings.

When the per-claim fee was bumped from 1% to 3% (commits 2a038ef, f81f868),
the change swept code + DB + marketing copy. Future bumps should run this
guard before the commit lands. Run from /root/empire-v49/:

    python3 scripts/check_fee_copy.py
    # or via a pre-commit hook

Exit codes:
  0 — clean
  1 — at least one stale 1% fee reference found, see output for locations
  2 — config / environment error (e.g. wrong cwd)

Allow-list patterns are paths or lines that legitimately contain "1%" but
are not marketing copy. Update allow_list when a new legitimate 1% reference
appears (e.g. a calibration tolerance).
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

# Patterns that should NEVER appear in marketing code. Each is a regex
# matched against line content.
STALE_PATTERNS = [
    # The original "1% success fee" wording, with allowances
    (r'\b1\s*%\s*success\s+fee', '1% success fee'),
    (r"Empire's\s+1\s*%\s+fee", "Empire's 1% fee"),
    (r'\b1\s*%\s*fee\s+earned', '1% fee earned (funnel/landing labels)'),
    (r'\b1\s*%\s+fee\s+is\s+paid', '1% fee is paid (copy)'),
    (r"fee\s*=\s*['\"]1\s*%['\"]", 'fee = "1%" (constant)'),
    (r'Empire\s+1\s*%\s+fee', 'Empire 1% fee (copy)'),
    (r'forecasted\s+1\s*%\s+fee', 'forecasted 1% fee (docstring)'),
    (r'claim\s+settled,\s+1\s*%\s+fee', 'claim settled, 1% fee (funnel desc)'),
    (r'contractor\s+share\s+of\s+the\s+1\s*%', 'contractor share of the 1%'),
    # Numeric code defaults that should be 0.03, not 0.01
    (r'COMMISSION_RATE\s*=\s*0\.01', 'COMMISSION_RATE = 0.01 (code constant)'),
    (r'["\']fee_rate["\']\s*[:,=]\s*0\.01', 'fee_rate = 0.01 (dict/JSON key)'),
    (r'(?<![\w.])fee_rate\s*=\s*0\.01', 'fee_rate = 0.01 (bare variable)'),
    (r'\|\|\s*0\.01(?=\s*[;)])', 'JS fallback || 0.01 (code default)'),
    (r'asset_val\s*\*\s*0\.01', 'asset_val * 0.01 (code multiplier)'),
    (r'get\(["\']fee_rate["\']\s*,\s*0\.01\)', 'get("fee_rate", 0.01) (payload default)'),
]

# Files / patterns we ignore. Reasons:
#   CSS widths, hit-rate percentages, calibration tolerances, table widths,
#   and the deliberate 1% wire-amount tolerance heuristic.
ALLOW = [
    'scripts/check_fee_copy.py',  # the guard itself uses the patterns
    'empire_payouts.py:413',       # "matches within 1%" tolerance (heuristic)
    'bots/agi_revenue.py:159',     # .1% accuracy formatting
    'bots/predictive_revenue.py:383',  # revenue dipped >30% threshold
    'bots/predictive_revenue.py:869',  # >20% threshold
    'empire_command_spa.py:5358-5360', # tempMax - tempMin || 0.01 (chart scale, not fee)
    'bots/panel_court.py:83-85',   # scoring weights (40%, 30%, etc.)
    'docs/personality_comparison_report.md',  # historical 0.700 confidence scores
    'empire_brain_personality.py:93',  # "10% hit rate" example
    'empire_si_core.py:10',        # "88% success probability" example
    'scripts_archive/',            # legacy dead code
    '_to_delete_20260525-0808/',   # dead previous stack
    'node_modules/',
    '__pycache__/',
    '.git/',
    'backups/',
    'data/',
    'test-ledger/',
    'kanban.db',
    'state.db',
    'memory_store.db',
]

# File extensions we scan
SCAN_EXTS = {'.py', '.md', '.html', '.j2', '.tmpl', '.txt', '.json', '.yaml', '.yml'}

def is_allowed_path(rel: str) -> bool:
    """Return True if this file path is in the allow-list (skip whole file)."""
    for spec in ALLOW:
        if spec.endswith('/'):
            if spec in rel:
                return True
        elif ':' not in spec and spec == rel:
            return True
    return False

def is_allowed_line(rel: str, lineno: int) -> bool:
    """Return True if this (file, line) is in the allow-list (line-specific)."""
    for spec in ALLOW:
        if not spec.endswith('/') and ':' in spec:
            try:
                f, rng = spec.split(':', 1)
                if f != rel:
                    continue
                if '-' in rng:
                    lo, hi = map(int, rng.split('-'))
                    if lo <= lineno <= hi:
                        return True
                else:
                    if int(rng) == lineno:
                        return True
            except (ValueError, IndexError):
                continue
    return False

def main():
    issues = []
    files_scanned = 0
    for path in ROOT.rglob('*'):
        if not path.is_file():
            continue
        rel = str(path.relative_to(ROOT))
        if any(skip in rel for skip in ['.git/', 'node_modules/', '__pycache__/',
                                        'backups/', 'data/', 'test-ledger/',
                                        '_to_delete_']):
            continue
        if path.suffix not in SCAN_EXTS:
            continue
        if path.name in ('kanban.db', 'state.db', 'memory_store.db',
                         'sovereign_core_knowledge_base.json',
                         'master_diagnostics_suite.py'):
            continue
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        files_scanned += 1
        for lineno, line in enumerate(content.splitlines(), 1):
            rel = str(path.resolve().relative_to(ROOT.resolve()))
            if is_allowed_path(rel) or is_allowed_line(rel, lineno):
                continue
            for pattern, label in STALE_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    issues.append((rel, lineno, label, line.strip()[:120]))
                    break  # one report per line is enough

    print(f"Scanned {files_scanned} files for stale 1% fee copy.")
    if issues:
        print(f"\nFOUND {len(issues)} STALE 1% FEE REFERENCE(S):\n")
        for filepath, lineno, label, snippet in issues:
            print(f"  {filepath}:{lineno}  [{label}]")
            print(f"    {snippet}")
        print(f"\nIf these are legitimate (e.g. CSS, tolerances, examples),")
        print(f"add them to ALLOW in scripts/check_fee_copy.py.")
        sys.exit(1)
    else:
        print("Clean — no stale 1% fee copy found.")
        sys.exit(0)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"check_fee_copy.py error: {e}", file=sys.stderr)
        sys.exit(2)
