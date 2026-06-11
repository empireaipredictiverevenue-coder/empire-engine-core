#!/usr/bin/env python3
"""Diagnose SPA JS syntax errors by extracting and testing the served JS."""
import re
import subprocess
import sys

from empire_command_spa import command_spa_page

html = command_spa_page()
lines = html.split("\n")

# 1. Find ALL script tags in the HTML
print("=" * 60)
print("ALL SCRIPT TAGS IN HTML")
print("=" * 60)
for i, m in enumerate(re.finditer(r'<script[^>]*>(.*?)</script>', html, re.DOTALL), 1):
    tag = m.group(0)[:120]
    line_num = html[:m.start()].count("\n") + 1
    content_len = len(m.group(1))
    print(f"Script {i} at line {line_num}: {tag}... ({content_len} chars)")

# 2. Find the main module script
m = re.search(r'<script type="module">(.*?)</script>', html, re.DOTALL)
if not m:
    print("\nERROR: No module script tag found!")
    sys.exit(1)

js = m.group(1)
js_lines = js.split("\n")
print(f"\n{'=' * 60}")
print(f"MAIN SCRIPT: {len(js_lines)} lines, {len(js)} chars")
print("=" * 60)

# 3. Backtick balance check
backtick_count = js.count("`")
print(f"\nBacktick count: {backtick_count} (should be even: {backtick_count % 2 == 0})")

# 4. Track html` ... ` pairs
open_positions = []
unclosed_starts = []
for i, ch in enumerate(js):
    if ch == "`":
        if open_positions:
            open_positions.pop()
        else:
            open_positions.append(i)
    # Track html` starts
    if ch == "`" and i >= 4 and js[i-4:i] == "html":
        unclosed_starts.append(i)

if open_positions:
    pos = open_positions[0]
    print(f"\nWARNING: Unclosed backtick at position {pos}")
    # Show context around the unclosed backtick
    line_start = js.rfind("\n", 0, pos) + 1
    line_end = js.find("\n", pos)
    line_num = js[:pos].count("\n") + 1
    print(f"  Line {line_num}: {js[line_start:line_end][:200]}")
else:
    print("All backticks are balanced. ✓")

# 5. Try parsing with node
print(f"\n{'=' * 60}")
print("NODE PARSER CHECK")
print("=" * 60)
with open("/tmp/spa_diag.js", "w") as f:
    f.write(js)

result = subprocess.run(["node", "--check", "/tmp/spa_diag.js"], capture_output=True, text=True)
if result.returncode == 0:
    print("node --check: PASSED ✓")
else:
    print(f"node --check: FAILED (exit {result.returncode})")
    print(f"  stderr: {result.stderr[:500]}")

# 6. Check for backslash-quote patterns in template literals
bs_quote_lines = []
for i, line in enumerate(js_lines, 1):
    if '\\"' in line:
        bs_quote_lines.append((i, line.strip()[:150]))
if bs_quote_lines:
    print(f"\n{'=' * 60}")
    print(f"BACKSLASH-QUOTE PATTERNS: {len(bs_quote_lines)} lines")
    print("=" * 60)
    for ln, text in bs_quote_lines[:20]:
        print(f"  Line {ln}: {text}")
    if len(bs_quote_lines) > 20:
        print(f"  ... and {len(bs_quote_lines) - 20} more")

# 7. Show lines around where class appears unexpectedly
# Check for 'class' that appears outside template literals
print(f"\n{'=' * 60}")
print(f"'class' OUTSIDE TEMPLATE LITERALS CHECK")
print("=" * 60)
# Basic check: find 'class' occurrences and check if they're inside backticks
in_backtick = False
class_outside = []
for i, line in enumerate(js_lines, 1):
    if 'class' in line:
        # Crude check: check if the line is inside a template literal
        # This is a simplification but helps find obvious issues
        # Count backticks before this line
        preceding_text = "\n".join(js_lines[:i-1])
        backticks_before = preceding_text.count("`")
        if backticks_before % 2 == 0:
            # Even number of backticks before = outside template literal
            # But 'class' could be in a JS string or comment
            if not line.strip().startswith("//"):
                class_outside.append((i, line.strip()[:150]))

if class_outside:
    print(f"Found {len(class_outside)} lines with 'class' potentially outside template literals:")
    for ln, text in class_outside[:20]:
        print(f"  Line {ln}: {text}")
    if len(class_outside) > 20:
        print(f"  ... and {len(class_outside) - 20} more")
else:
    print("All 'class' occurrences appear inside template literals. ✓")

print(f"\n{'=' * 60}")
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
