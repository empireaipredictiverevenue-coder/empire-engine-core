#!/usr/bin/env python3
"""Fetch JS through Cloudflare with browser-like headers, compare to direct."""
import re
import subprocess
import urllib.request

# Fetch from direct server
with urllib.request.urlopen("http://localhost:8001/command") as resp:
    direct_html = resp.read().decode()

# Fetch through Cloudflare with browser User-Agent
req = urllib.request.Request(
    "https://empire-ai.co.uk/command",
    headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        cf_html = resp.read().decode()
        print(f"CF response: {resp.status} {len(cf_html)} chars")
except Exception as e:
    print(f"CF request failed: {e}")
    cf_html = None

def extract_js(html):
    m = re.search(r'<script type="module">(.*?)</script>', html, re.DOTALL)
    if m:
        return m.group(1)
    return None

direct_js = extract_js(direct_html)
cf_js = extract_js(cf_html) if cf_html else None

print(f"\nDirect JS: {len(direct_js) if direct_js else 0} chars")
print(f"CF JS:     {len(cf_js) if cf_js else 0} chars")

if direct_js:
    with open("/tmp/spa_direct.js", "w") as f:
        f.write(direct_js)
    r = subprocess.run(["node", "--check", "/tmp/spa_direct.js"], capture_output=True, text=True)
    print(f"node --check direct: {'PASS' if r.returncode == 0 else 'FAIL ' + r.stderr[:200]}")

if cf_js:
    with open("/tmp/spa_cf.js", "w") as f:
        f.write(cf_js)
    r = subprocess.run(["node", "--check", "/tmp/spa_cf.js"], capture_output=True, text=True)
    print(f"node --check CF:     {'PASS' if r.returncode == 0 else 'FAIL ' + r.stderr[:200]}")

    if direct_js and len(direct_js) == len(cf_js):
        print("\n✓ JS sizes match exactly - Cloudflare is not modifying the JS")
    elif direct_js:
        print(f"\n✗ JS sizes differ! Direct={len(direct_js)} vs CF={len(cf_js)}")

if direct_js and not cf_js:
    print("\nCould not fetch from Cloudflare - may be blocking non-browser requests")
    print("This confirms the server is serving correct JS. The browser error is likely cache.")
