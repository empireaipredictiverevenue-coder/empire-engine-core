#!/usr/bin/env python3
"""
Extract ALL script blocks from the rendered SPA and validate syntax.
"""
import sys, re, os, subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from empire_command_spa import command_spa_page

html = command_spa_page()

# Find all script blocks
blocks = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
print(f"Found {len(blocks)} script blocks")
for i, js in enumerate(blocks):
    print(f"  Block {i}: {len(js)} chars, starts with: {js[:60].strip()}")

# The second <script type="module"> block is the main SPA JS
if len(blocks) >= 2:
    js = blocks[1].strip()
else:
    js = blocks[0].strip() if blocks else ""

print(f"\nModule JS length: {len(js)} chars")

# Write module JS to temp file and check with node
tmpfile = "/tmp/spa_check.mjs"
with open(tmpfile, "w") as f:
    f.write(js)

# Node.js syntax check
try:
    result = subprocess.run(
        ["node", "--check", tmpfile],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode == 0:
        print("PASS: Node.js syntax check OK")
    else:
        print(f"FAIL: Node.js syntax error")
        print(f"  {result.stderr.strip()}")
        sys.exit(1)
except FileNotFoundError:
    print("WARN: Node.js not available, skipping syntax check")
except Exception as e:
    print(f"WARN: Node check failed: {e}")

# Verify key components
checks = [
    ("function Personality", "Personality component"),
    ("Per-Operator", "Per-Operator tab"),
    ('type="range"', "Range slider input"),
    ("apiFetch('/api/brain/personality/snapshot')", "Snapshot API call"),
    ("apiFetch('/api/brain/personality/operator/set'", "Operator set API call"),
    ("apiFetch('/api/brain/personality/operator/remove'", "Operator remove API call"),
    ("operator_id", "operator_id usage"),
    ("onInput=${", "Slider event handler"),
    ("Confidence Threshold", "Confidence Threshold label"),
    ("Temperature", "Temperature label"),
    ("Urgency Floor", "Urgency Floor label"),
    ("Set Global Override", "Global override button"),
    ("Set Niche Override", "Niche override button"),
    ("Active Overrides", "Active Overrides section"),
]

print("\n=== COMPONENT VERIFICATION ===")
all_pass = True
for pattern, name in checks:
    found = pattern in js
    if not found:
        all_pass = False
    print(f"  {'[PASS]' if found else '[FAIL]'} {name}")

if all_pass:
    print(f"\n✅ All {len(checks)} checks passed!")
else:
    print(f"\n❌ Some checks failed")
    sys.exit(1)

# Clean up
if os.path.exists(tmpfile):
    os.unlink(tmpfile)
