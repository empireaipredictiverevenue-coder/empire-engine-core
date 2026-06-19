#!/usr/bin/env python3
"""Extract JS from the served /command page and node --check it."""
import re, subprocess, sys, urllib.request

# Fetch from local server
resp = urllib.request.urlopen("http://localhost:8001/command")
html = resp.read().decode()

# Extract script type="module" content
m = re.search(r'<script type="module">(.*?)</script>', html, re.DOTALL)
if not m:
    print("ERROR: Could not find <script type='module'> tag")
    sys.exit(1)

js = m.group(1).strip()
with open("/tmp/served_spa.js", "w") as f:
    f.write(js)

print(f"Extracted {len(js)} chars, {len(js.split(chr(10)))} lines")

# node --check
result = subprocess.run(["node", "--check", "/tmp/served_spa.js"], capture_output=True, text=True)
if result.returncode == 0:
    print("node --check: PASSED")
else:
    print("node --check: FAILED")
    print(result.stderr[:2000])
sys.exit(result.returncode)
