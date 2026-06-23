"""Skip-trace via camofox CLI, called directly (not via subprocess)."""
import os
import sys
import re
import time
import urllib.parse
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path("/root/.env"))

sys.path.insert(0, "/root/empire-v49")
from supabase import create_client
from empire_vonage_email import _smtp_validate

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# Patterns to try
EMAIL_PATTERNS = ["info", "contact", "office", "hello", "sales", "team", "admin"]


def camofox_open(url):
    """Open a URL, return tabId. CLI returns plain text 'tabId: <uuid>'."""
    import subprocess, re
    r = subprocess.run(["camofox-browser", "open", url], capture_output=True, text=True, timeout=60)
    m = re.search(r"tabId[:\s]+([a-f0-9-]{36})", r.stdout)
    return m.group(1) if m else None


def camofox_get_text(tab_id):
    import subprocess
    r = subprocess.run(["camofox-browser", "get-text", tab_id], capture_output=True, text=True, timeout=30)
    return r.stdout


def camofox_close(tab_id):
    import subprocess
    subprocess.run(["camofox-browser", "close", tab_id], capture_output=True, text=True, timeout=10)


def bbb_search(name, city):
    q = urllib.parse.quote(name)
    c = urllib.parse.quote(city)
    url = f"https://www.bbb.org/search?find_text={q}&find_loc={c}&find_type=Category"
    tab = camofox_open(url)
    if not tab:
        return ""
    time.sleep(4)  # give BBB JS time to render results
    text = camofox_get_text(tab)
    camofox_close(tab)
    return text


def extract_profiles(text, business_name):
    urls = re.findall(r"/us/[a-z]{2}/[a-z\-]+/[a-z\-]+/[a-z0-9\-]+-\d+", text)
    biz_words = set(w.lower() for w in re.findall(r"[a-z]{4,}", business_name.lower()) if len(w) > 3)
    matches = []
    for u in urls[:20]:
        slug = u.split("/")[-1].rsplit("-", 1)[0].replace("-", " ").lower()
        slug_words = set(slug.split())
        overlap = biz_words & slug_words
        if overlap:
            matches.append((len(overlap), "https://www.bbb.org" + u))
    matches.sort(reverse=True)
    return [u for _, u in matches[:3]]


def extract_website(text):
    patterns = [
        r"Website[:\s]+(https?://[^\s]+)",
        r"Business Website[:\s]+(https?://[^\s]+)",
        r"Visit Website\s*([^\s]+)",
    ]
    for p in patterns:
        for m in re.finditer(p, text, re.I):
            url = m.group(1).rstrip(".,;:")
            if any(x in url for x in ["bbb.org", "facebook.com", "twitter.com", "linkedin.com", "youtube.com"]):
                continue
            if url.startswith("http"):
                return url
            elif "." in url and " " not in url:
                return "http://" + url
    return ""


def get_domain(url):
    m = re.search(r"(?:https?://)?(?:www\.)?([^/]+)", url)
    return m.group(1) if m else ""


def try_emails(domain):
    for pat in EMAIL_PATTERNS:
        c = f"{pat}@{domain}"
        if _smtp_validate(c):
            return c
    return ""


def skip_trace_one(contractor):
    name = contractor.get("name", "")
    metro = contractor.get("metro", "")
    city = metro.split("-")[0].strip() if metro else ""
    if not name or not city:
        return None
    text = bbb_search(name, city)
    if not text or len(text) < 100:
        return None
    profiles = extract_profiles(text, name)
    for url in profiles[:2]:
        tab = camofox_open(url)
        if not tab:
            continue
        time.sleep(3)
        ptext = camofox_get_text(tab)
        camofox_close(tab)
        site = extract_website(ptext)
        if site:
            dom = get_domain(site)
            if dom:
                email = try_emails(dom)
                if email:
                    return {"id": contractor["id"], "email": email, "domain": dom, "profile": url}
    return None


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    r = sb.table("contractors").select("id,name,phone,metro,email").eq("active", True).is_("email", "null").limit(limit).execute()
    rows = r.data or []
    print(f"processing {len(rows)} contractors via BBB", flush=True)
    found = 0
    t0 = time.time()
    for i, c in enumerate(rows):
        try:
            res = skip_trace_one(c)
            if res:
                sb.table("contractors").update({"email": res["email"]}).eq("id", c["id"]).execute()
                found += 1
                print(f"  [{i+1}/{len(rows)}] {c['name'][:50]:50}  -> {res['email']} (via {res['domain']})", flush=True)
            else:
                print(f"  [{i+1}/{len(rows)}] {c['name'][:50]:50}  no match", flush=True)
        except Exception as e:
            print(f"  [{i+1}] ERR: {type(e).__name__}: {e}", flush=True)
    print(f"\nDONE: scanned={len(rows)} found={found} in {time.time()-t0:.0f}s")