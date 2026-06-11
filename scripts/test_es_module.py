#!/usr/bin/env python3
"""Extract served JS and test as ES module (same as browser)."""
import re, subprocess, sys

import urllib.request
with urllib.request.urlopen("http://localhost:8000/command") as r:
    html = r.read().decode()

m = re.search(r'<script type="module">(.*?)</script>', html, re.DOTALL)
if not m:
    print("No module script found")
    sys.exit(1)

js = m.group(1)

# Save as .mjs (ES module)
with open("/tmp/spa_module.mjs", "w") as f:
    f.write(js)

print(f"Saved: {len(js)} chars, {js.count(chr(10))} lines")

# Test with node in module mode (same as <script type="module">)
r = subprocess.run(
    ["node", "--input-type=module", "--check", "/tmp/spa_module.mjs"],
    capture_output=True, text=True
)
if r.returncode == 0:
    print("node --input-type=module --check: PASS")
else:
    print(f"node --input-type=module --check: FAIL")
    print(f"  {r.stderr[:500]}")
    # Extract line number
    import re as re2
    err_match = re2.search(r"/(?:spa_module\.mjs):(\d+):(\d+)", r.stderr)
    if err_match:
        js_line = int(err_match.group(1))
        col = int(err_match.group(2))
        print(f"\n  Error at JS line {js_line}, col {col}")
        js_lines = js.split(chr(10))
        for i in range(max(0, js_line-3), min(len(js_lines), js_line+2)):
            marker = " <<<< ERROR" if i == js_line-1 else ""
            print(f"  {i+1}: {js_lines[i][:200]}{marker}")

# Also check for backslash-quote patterns at the error location
r2 = subprocess.run(
    ["node", "--check", "/tmp/spa_module.mjs"],
    capture_output=True, text=True
)
if r2.returncode == 0:
    print("\nnode --check (non-module): PASS")
else:
    print(f"\nnode --check (non-module): FAIL")
    print(f"  {r2.stderr[:300]}")
