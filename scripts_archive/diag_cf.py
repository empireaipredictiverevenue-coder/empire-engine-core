#!/usr/bin/env python3
"""Compare JS served directly vs through Cloudflare."""
import re
import subprocess
import urllib.request

# Fetch from direct server
with urllib.request.urlopen("http://localhost:8000/command") as resp:
    direct_html = resp.read().decode()

# Fetch through Cloudflare  
req = urllib.request.Request("https://empire-ai.co.uk/command")
with urllib.request.urlopen(req) as resp:
    cf_html = resp.read().decode()

# Extract JS from both
def extract_js(html):
    m = re.search(r'<script type="module">(.*?)</script>', html, re.DOTALL)
    if m:
        return m.group(1)
    return None

direct_js = extract_js(direct_html)
cf_js = extract_js(cf_html)

print(f"Direct: {len(direct_html)} chars HTML, JS={len(direct_js) if direct_js else 'NOT FOUND'} chars")
print(f"CF:     {len(cf_html)} chars HTML, JS={len(cf_js) if cf_js else 'NOT FOUND'} chars")

if direct_js and cf_js:
    if len(direct_js) == len(cf_js):
        print("\n✓ JS sizes MATCH - Cloudflare is NOT modifying the JS")
    else:
        print(f"\n✗ JS sizes DIFFER! Direct={len(direct_js)} vs CF={len(cf_js)}")
        print(f"  Difference: {len(cf_js) - len(direct_js)} chars")
        # Show first difference
        for i, (a, b) in enumerate(zip(direct_js, cf_js)):
            if a != b:
                print(f"  First diff at char {i}: direct={repr(a)} cf={repr(b)}")
                print(f"  Direct context: ...{direct_js[max(0,i-20):i+20]}...")
                print(f"  CF context:     ...{cf_js[max(0,i-20):i+20]}...")
                break
elif direct_js and not cf_js:
    print("\nCould not extract JS from Cloudflare response")
    # Show what's different about CF HTML
    if 'script' in cf_html:
        print("Cloudflare HTML contains 'script' keyword")
        for m in re.finditer(r'<script[^>]*>', cf_html):
            print(f"  Script tag: {m.group()[:100]}")

# Run node --check on both
if direct_js:
    with open("/tmp/spa_direct.js", "w") as f:
        f.write(direct_js)
    r = subprocess.run(["node", "--check", "/tmp/spa_direct.js"], capture_output=True, text=True)
    print(f"\nnode --check direct: {'PASS' if r.returncode == 0 else 'FAIL'}")
    if r.returncode != 0:
        print(f"  {r.stderr[:500]}")

if cf_js:
    with open("/tmp/spa_cf.js", "w") as f:
        f.write(cf_js)
    r = subprocess.run(["node", "--check", "/tmp/spa_cf.js"], capture_output=True, text=True)
    print(f"node --check CF:     {'PASS' if r.returncode == 0 else 'FAIL'}")
    if r.returncode != 0:
        print(f"  {r.stderr[:500]}")
