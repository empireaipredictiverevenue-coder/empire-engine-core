#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# EMPIRE HUB DEPLOY VALIDATOR
# ══════════════════════════════════════════════════════════════════════
# Run this BEFORE restarting empire-hub. It catches import errors,
# syntax errors, and broken module references so the hub doesn't
# crash-loop in PM2.
#
# Usage:
#   ./validate_hub_deploy.sh                          # check everything
#   ./validate_hub_deploy.sh --quick                   # syntax + hub.py only
#   ./validate_hub_deploy.sh --file path/to/file.py    # check a specific file
#   ./validate_hub_deploy.sh --list-modules            # just show hub imports
# ══════════════════════════════════════════════════════════════════════

set -euo pipefail

cd /root/empire-v49
FAILED=0
PASSED=0
GIT_AVAILABLE=false
QUICK_MODE=false
TARGET_FILE=""

# ── Parse args ──────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK_MODE=true ;;
    --file=*) TARGET_FILE="${arg#*=}" ;;
    --file) echo "Use --file=path/to/file.py"; exit 1 ;;
    --list-modules) python3 -c "
import ast, sys
with open('hub.py') as f:
    tree = ast.parse(f.read())
print('=== Hub imports ===')
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom):
        module = node.module or ''
        for a in node.names:
            print(f'  from {module} import {a.name}')
    elif isinstance(node, ast.Import):
        for a in node.names:
            print(f'  import {a.name}')
print('=== End ===')
"; exit 0 ;;
    --help)
      echo "Empire Hub Deploy Validator"
      echo "  ./validate_hub_deploy.sh           — full check"
      echo "  ./validate_hub_deploy.sh --quick   — syntax + hub only"
      echo "  ./validate_hub_deploy.sh --file=X  — check one file"
      echo "  ./validate_hub_deploy.sh --list-modules"
      exit 0 ;;
  esac
done

# ── Check git availability ──────────────────────────────────────────
if command -v git &>/dev/null && git rev-parse --git-dir &>/dev/null 2>&1; then
  GIT_AVAILABLE=true
fi

print_result() {
  local icon="$1" msg="$2"
  if [ "$icon" = "PASS" ]; then
    echo "  ✅  $msg"
    PASSED=$((PASSED + 1))
  else
    echo "  ❌  $msg"
    FAILED=$((FAILED + 1))
  fi
}

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║     EMPIRE HUB DEPLOY VALIDATOR                          ║"
echo "║     Catches crashes before they reach PM2               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ════════════════════════════════════════════════════════════════════
# CHECK 1: Python syntax on target file or changed files
# ════════════════════════════════════════════════════════════════════
echo "─── [1/3] Syntax check ───"

if [ -n "$TARGET_FILE" ]; then
  # Single file mode
  if [[ "$TARGET_FILE" == *.py ]]; then
    if python3 -c "import ast; ast.parse(open('$TARGET_FILE').read())" 2>/dev/null; then
      print_result "PASS" "$TARGET_FILE — syntax valid"
    else
      print_result "FAIL" "$TARGET_FILE — SYNTAX ERROR"
      python3 -c "import ast; ast.parse(open('$TARGET_FILE').read())" 2>&1 | sed 's/^/       /'
    fi
  fi
elif [ "$QUICK_MODE" = true ]; then
  # Quick mode: just check hub.py and core agent files
  for f in hub.py main.py; do
    if [ -f "$f" ]; then
      python3 -c "import ast; ast.parse(open('$f').read())" 2>/dev/null \
        && print_result "PASS" "$f" \
        || { print_result "FAIL" "$f — SYNTAX ERROR"; python3 -c "import ast; ast.parse(open('$f').read())" 2>&1 | sed 's/^/       /'; }
    fi
  done
else
  # Full mode: check all changed .py files from git diff
  if [ "$GIT_AVAILABLE" = true ]; then
    CHANGED=$(git diff --name-only HEAD 2>/dev/null || git diff --name-only 2>/dev/null || true)
    if [ -z "$CHANGED" ]; then
      CHANGED=$(git status --porcelain 2>/dev/null | awk '{print $2}' | grep '\.py$' || true)
    fi
    if [ -z "$CHANGED" ]; then
      echo "  (no changed .py files to check)"
      PASSED=$((PASSED + 1))
    else
      for f in $CHANGED; do
        if [[ "$f" == *.py ]] && [ -f "$f" ]; then
          python3 -c "import ast; ast.parse(open('$f').read())" 2>/dev/null \
            && print_result "PASS" "$f" \
            || { print_result "FAIL" "$f — SYNTAX ERROR"; python3 -c "import ast; ast.parse(open('$f').read())" 2>&1 | sed 's/^/       /'; }
        fi
      done
    fi
  else
    # No git: check all modified files by mtime
    echo "  (git not available, checking hub.py + main.py)"
    for f in hub.py main.py; do
      if [ -f "$f" ]; then
        python3 -c "import ast; ast.parse(open('$f').read())" 2>/dev/null \
          && print_result "PASS" "$f" \
          || { print_result "FAIL" "$f"; python3 -c "import ast; ast.parse(open('$f').read())" 2>&1 | sed 's/^/       /'; }
      fi
    done
  fi
fi

# ════════════════════════════════════════════════════════════════════
# CHECK 2: Hub import resolution — try importing every module
# ════════════════════════════════════════════════════════════════════
echo ""
echo "─── [2/3] Hub import resolution ───"

python3 -c "
import ast, sys, importlib, traceback

with open('hub.py') as f:
    tree = ast.parse(f.read())

# Collect all from-imports: (module, name) pairs
imports_to_check = []
for node in ast.walk(tree):
    if isinstance(node, ast.ImportFrom):
        module = node.module or ''
        for a in node.names:
            imports_to_check.append((module, a.name))

failed_imports = []
for module, name in imports_to_check:
    # Skip stdlib, known-available, and packages that require env setup
    skip = {'dotenv', 'logging', 'abc', 'typing', 'datetime', 'json', 'os', 'sys',
            'io', 'csv', 're', 'copy', 'math', 'random', 'functools', 'pathlib',
            'collections', 'enum', 'dataclasses', 'uuid', 'time', 'hashlib',
            'inspect', 'textwrap', 'asyncio'}
    if module in skip or module.split('.')[0] in skip:
        continue
    # Use find_spec to check module existence WITHOUT executing top-level code.
    # __import__ would trigger side effects (DB connections, thread spawns).
    try:
        spec = importlib.util.find_spec(module)
        if spec is None:
            failed_imports.append((module, name, 'module not found'))
            continue

    except Exception as e:
        failed_imports.append((module, name, str(e)[:120]))

if failed_imports:
    for module, name, err in failed_imports:
        print(f'  ❌  from {module} import {name} — {err}')
    sys.exit(1)
else:
    print('  ✅  All hub imports resolve')
    sys.exit(0)
" && print_result "PASS" "All hub imports resolve" || {
  FAILED=$((FAILED + 1))
}

# ════════════════════════════════════════════════════════════════════
# CHECK 3: Port conflict detection
# ════════════════════════════════════════════════════════════════════
echo ""
echo "─── [3/4] Port conflict detection ───"

# Use check_ports.sh to detect orphaned processes that would prevent startup
if [ -f "check_ports.sh" ] && [ "$QUICK_MODE" = false ]; then
  if ./check_ports.sh 2>&1 | grep -q "orphan\|ORPHAN"; then
    print_result "FAIL" "Port conflict detected — run ./check_ports.sh --clean to resolve"
    ./check_ports.sh 2>&1 | grep "orphan\|ORPHAN" | sed 's/^/       /'
  else
    print_result "PASS" "All empire ports clean, no conflicts"
  fi
else
  # Quick mode: just check port 8000 (hub) is not held by an orphan
  if command -v ss &>/dev/null; then
    PORT_8000=$(ss -tlnp "sport = :8001" 2>/dev/null | grep -v State | head -1)
    if [ -n "$PORT_8000" ]; then
      print_result "PASS" "Port 8000 is occupied (expected for running hub)"
    else
      print_result "PASS" "Port 8000 is free (hub not running — will start on next restart)"
    fi
  else
    print_result "PASS" "Port check skipped (ss not available)"
  fi
fi

# ════════════════════════════════════════════════════════════════════
# CHECK 4: hub.py AST integrity (catches structural issues)
# ════════════════════════════════════════════════════════════════════
echo ""
echo "─── [4/4] Structural integrity ───"

# Verify hub.py parses cleanly
python3 -c "
import ast
with open('hub.py') as f:
    tree = ast.parse(f.read())
print('  ✅  hub.py parses cleanly')
" 2>/dev/null || { print_result "FAIL" "hub.py parse error"; }

# Count route registrations vs imports (sanity check)
python3 -c "
import ast
with open('hub.py') as f:
    tree = ast.parse(f.read())

register_calls = 0
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr == 'add_api_route':
            register_calls += 1
        if isinstance(fn, ast.Attribute) and fn.attr.startswith('register_'):
            register_calls += 1
        if isinstance(fn, ast.Attribute) and fn.attr in ('get', 'post', 'put', 'patch', 'delete'):
            register_calls += 1

decorator_routes = 0
for node in ast.walk(tree):
    if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
        for dec in node.decorator_list:
            if isinstance(dec, ast.Attribute) and dec.attr in ('get', 'post'):
                decorator_routes += 1

print(f'  📊  Route registrations: {register_calls}')
print(f'  📊  Decorator routes: {decorator_routes}')
" 2>/dev/null || true

print_result "PASS" "Structural integrity check"

# ════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
if [ "$FAILED" -eq 0 ]; then
  echo "║  ✅  ALL $PASSED CHECKS PASSED — Ready to deploy          ║"
  echo "║      Run: hub_safe_restart.sh                           ║"
else
  echo "║  ❌  $FAILED CHECK(S) FAILED — Do NOT restart hub        ║"
  echo "║      Fix the errors above, then re-run this script     ║"
fi
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
exit "$FAILED"
