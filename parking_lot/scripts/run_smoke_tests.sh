#!/usr/bin/env bash
# =============================================================================
# EMPIRE V49 · SMOKE TEST RUNNER
# =============================================================================
# Runs all standalone smoke tests in sequence. Designed for both local dev
# and CI pipeline use.
#
# Usage:
#   ./scripts/run_smoke_tests.sh              # Run all smoke tests
#   ./scripts/run_smoke_tests.sh --quick      # Skip slow network tests
#   ./scripts/run_smoke_tests.sh --spa        # Only the SPA smoke test
#   ./scripts/run_smoke_tests.sh --imports    # Only the import-safety test
#   ./scripts/run_smoke_tests.sh --syntax     # Only the Python syntax check
#
# Exit codes:
#   0 — all tests passed
#   1 — one or more tests failed
# =============================================================================

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0
FAILED_NAMES=""

# ── Parse arguments ─────────────────────────────────────────────────────────
RUN_ALL=true
RUN_SPA=false
RUN_IMPORTS=false
RUN_SYNTAX=false
RUN_PIPELINE=false

if [[ $# -gt 0 ]]; then
    RUN_ALL=false
    for arg in "$@"; do
        case "$arg" in
            --quick)        RUN_SYNTAX=true; RUN_IMPORTS=true ;;
            --spa)          RUN_SPA=true ;;
            --imports)      RUN_IMPORTS=true ;;
            --syntax)       RUN_SYNTAX=true ;;
            --pipeline)     RUN_PIPELINE=true ;;
            *)              echo "Unknown option: $arg"; exit 2 ;;
        esac
    done
fi

if $RUN_ALL; then
    RUN_SYNTAX=true
    RUN_IMPORTS=true
    RUN_SPA=true
    RUN_PIPELINE=true
fi

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

pass()   { PASS=$((PASS + 1)); echo -e "  ${GREEN}✅ PASS${NC}  $1"; }
fail()   { FAIL=$((FAIL + 1)); FAILED_NAMES="$FAILED_NAMES  - $1\n"; echo -e "  ${RED}❌ FAIL${NC}  $1"; }
skip()   { echo -e "  ${YELLOW}⏭  SKIP${NC}  $1"; }
header() { echo -e "\n${BOLD}─── $1 ───${NC}"; }

# ════════════════════════════════════════════════════════════════════════════
# Python version check
# ════════════════════════════════════════════════════════════════════════════
header "Environment"
echo "  Python : $(python3 --version 2>&1)"
echo "  Project: $REPO_ROOT"
echo "  Node   : $(node --version 2>&1 || echo 'not found')"
echo "  Chrome : $(google-chrome --version 2>&1 || echo 'not found (will skip SPA smoke test)')"

# ════════════════════════════════════════════════════════════════════════════
# 1. Python syntax check on all .py files
# ════════════════════════════════════════════════════════════════════════════
if $RUN_SYNTAX; then
    header "1. Python Syntax Check (all .py files)"

    SYNTAX_ERRORS=0
    SYNTAX_ERROR_FILES=""

    # Use git-tracked files for speed, fall back to find for full scan
    if git rev-parse --git-dir >/dev/null 2>&1; then
        PY_FILES=$(git ls-files '*.py' 2>/dev/null || find . -name '*.py' -not -path './.git/*' -not -path './node_modules/*' -not -path './scripts_archive/*' -not -path './_to_delete_*')
    else
        PY_FILES=$(find . -name '*.py' -not -path './.git/*' -not -path './node_modules/*' -not -path './scripts_archive/*' -not -path './_to_delete_*')
    fi

    TOTAL_FILES=0
    for f in $PY_FILES; do
        TOTAL_FILES=$((TOTAL_FILES + 1))
        if ! python3 -m py_compile "$f" 2>/dev/null; then
            SYNTAX_ERRORS=$((SYNTAX_ERRORS + 1))
            SYNTAX_ERROR_FILES="$SYNTAX_ERROR_FILES  - $f\n"
        fi
    done

    if [ "$SYNTAX_ERRORS" -eq 0 ]; then
        pass "All $TOTAL_FILES Python files pass syntax check"
    else
        fail "$SYNTAX_ERRORS / $TOTAL_FILES Python files have syntax errors:"
        echo -e "$SYNTAX_ERROR_FILES"
    fi
fi

# ════════════════════════════════════════════════════════════════════════════
# 2. Import-safety test (pytest subset)
# ════════════════════════════════════════════════════════════════════════════
if $RUN_IMPORTS; then
    header "2. Import-Safety Test (test_imports.py)"

    export EMPIRE_TESTING=1
    export SUPABASE_URL="https://test.placeholder.supabase.co"
    export SUPABASE_ANON_KEY="test-anon-key-placeholder"
    export SUPABASE_SERVICE_KEY="test-service-key-placeholder"

    if python3 -m pytest tests/test_imports.py -v --tb=short 2>&1; then
        pass "All modules import safely with EMPIRE_TESTING=1"
    else
        fail "Import-safety test failed (see above for details)"
    fi
fi

# ════════════════════════════════════════════════════════════════════════════
# 3. Pipeline smoke test (requires network — Open-Meteo)
# ════════════════════════════════════════════════════════════════════════════
if $RUN_PIPELINE; then
    header "3. Pipeline Smoke Test (smoke_test.py)"

    if python3 smoke_test.py 2>&1; then
        pass "Pipeline smoke test passed"
    else
        fail "Pipeline smoke test failed (check Open-Meteo connectivity)"
    fi
fi

# ════════════════════════════════════════════════════════════════════════════
# 4. Fee copy guard (runs against the full repo)
# ════════════════════════════════════════════════════════════════════════════
if $RUN_ALL; then
    header "4. Fee Copy Guard (check_fee_copy.py)"

    if python3 scripts/check_fee_copy.py 2>&1; then
        pass "No stale 1% fee copy found"
    else
        fail "Fee copy guard found stale references"
    fi
fi

# ════════════════════════════════════════════════════════════════════════════
# ── Summary ─────────────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  SMOKE TEST SUMMARY${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    echo -e "\n${RED}Failed tests:${NC}"
    echo -e "$FAILED_NAMES"
    echo -e "${BOLD}Result: ${RED}FAILED${NC}"
    exit 1
else
    echo -e "  ${BOLD}Result: ${GREEN}ALL PASSED${NC}"
    exit 0
fi
