"""Probe schemas for panel_court_decisions and seo_genome_history."""
import os, json, urllib.request, sys
sys.path.insert(0, "/root/empire-v49")
from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

URL = os.environ["SUPABASE_URL"].rstrip("/")
KEY = os.environ["SUPABASE_SERVICE_KEY"]

req = urllib.request.Request(
    f"{URL}/rest/v1/?apikey={KEY}",
    headers={"Authorization": f"Bearer {KEY}"}
)
with urllib.request.urlopen(req, timeout=15) as resp:
    spec = json.loads(resp.read())

for path, defn in spec.get("definitions", {}).items():
    name = path.split("/")[-1] if "/" in path else path
    if name in ("panel_court_decisions", "seo_genome_history"):
        print(f"\n=== {name} ===")
        props = defn.get("properties", {})
        for col, info in sorted(props.items()):
            fmt = info.get("format", "")
            typ = info.get("type", "?")
            print(f"  {col:30s}  {typ}{' (' + fmt + ')' if fmt else ''}")
