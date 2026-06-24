"""
Empire AI · Mass Tort Lane (Firecrawl-based)
============================================

Scrapes FDA recall listings + extracts potential mass tort plaintiff leads.
Writes to prospects table with niche='mass_tort'.

Data source: https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts
Free tier limits: 500 credits/month (Firecrawl). ~10 credits per scrape.

Usage:
    python3 scripts/mass_tort_lane.py            # one-shot scrape
    python3 scripts/mass_tort_lane.py --loop     # loop every 6h

Env:
    FIRECRAWL_API_KEY    — required
"""
import os, sys, re, json, time, argparse
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import urllib.request, urllib.error
from supabase import create_client

FIRE_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
FIRE_BASE = "https://api.firecrawl.dev/v1"

FDA_RECALLS_URL = "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts"


def _scrape(url: str, formats: list = None) -> dict:
    """Firecrawl v1 scrape. Defaults to markdown; pass formats=['markdown','rawHtml'] for HTML parsing."""
    fmts = formats or ["markdown"]
    req = urllib.request.Request(
        f"{FIRE_BASE}/scrape",
        data=json.dumps({"url": url, "formats": fmts}).encode(),
        headers={"Authorization": f"Bearer {FIRE_KEY}", "Content-Type": "application/json", "User-Agent": "Empire-AI/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"http_{e.code}", "body": e.read().decode()[:200]}
    except Exception as e:
        return {"error": str(e)}


def fetch_fda_recalls() -> list:
    """Pull FDA recall listing page; extract recall links + summaries."""
    out = []
    r = _scrape(FDA_RECALLS_URL)
    if r.get("error"):
        print(f"  firecrawl error: {r['error']}")
        return out
    content = (r.get("data") or {}).get("markdown", "")
    # Each recall has a title + date + link
    # Pattern matches <h3><a>Title</a></h3> structure or list items
    # Match table-row format: | 06/22/2026 | [Brand](https://www.fda.gov/...) | ...
    pattern = re.compile(r'\|\s*(\d{2}/\d{2}/\d{4})\s*\|\s*\[([^\]]+)\]\((https://www\.fda\.gov/safety/recalls[^)]+)\)', re.M)
    seen = set()
    for m in pattern.finditer(content):
        date, title, link = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        year = date.split("/")[-1] if "/" in date else ""
        if not link.startswith("http"):
            link = "https://www.fda.gov" + link
        if "recalls" not in link.lower() and "/safety/" not in link.lower():
            continue
        if "search" in link or "form" in link:
            continue
        key = (title[:50], link)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "name": title[:200],
            "url": link,
            "year": year,
            "niche": "mass_tort",
            "source": "fda_recalls_firecrawl",
        })
    return out


def fetch_class_action_docket(target_court: str = "S.D.N.Y.") -> list:
    """Scrape courtlistener for recent class-action / mass tort dockets.

    Note: Firecrawl's markdown conversion drops <a> link URLs inside <h3>
    result titles, so we parse the raw HTML and extract each <article> title
    anchor.
    """
    out = []
    url = "https://www.courtlistener.com/?q=mass+tort+class+action&type=o&order_by=dateFiled+desc"
    r = _scrape(url, formats=["markdown", "rawHtml"])
    if r.get("error"):
        return out
    data = r.get("data") or {}
    html = data.get("rawHtml") or data.get("html") or ""
    md = data.get("markdown") or ""
    # 1) primary: rawHtml article anchors (preserves URLs)
    art_pat = re.compile(
        r'<article[^>]*>\s*<h3[^>]*>\s*<a[^>]+href="(https?://www\.courtlistener\.com/opinion/\d+/[^"]+?/?)"[^>]*>\s*(.+?)\s*</a>',
        re.S,
    )
    seen = set()
    for m in art_pat.finditer(html):
        href, txt = m.group(1), m.group(2)
        clean_url = re.sub(r"\?[^/]*$", "", href).rstrip("/")
        clean_txt = txt.replace("&nbsp;", " ").replace("\xa0", " ")
        clean_txt = re.sub(r"<[^>]+>", " ", clean_txt)
        clean_txt = re.sub(r"\s+", " ", clean_txt).strip()
        if not clean_url or clean_url in seen:
            continue
        seen.add(clean_url)
        out.append({
            "name": f"{clean_txt[:160]} (court opinion)",
            "url": clean_url,
            "niche": "mass_tort",
            "source": "courtlistener_firecrawl",
        })
    # 2) fallback: markdown regex (in case rawHtml isn't returned)
    if not out and md:
        md_pat = re.compile(r'\[([^\]]{10,150})\]\((https?://www\.courtlistener\.com/opinion/\d+/[^)]+)\)', re.M)
        for m in md_pat.finditer(md):
            name, link = m.group(1).strip(), m.group(2).strip()
            link = re.sub(r"\?[^/]*$", "", link).rstrip("/")
            if link in seen:
                continue
            seen.add(link)
            out.append({
                "name": f"{name[:120]} (court opinion)",
                "url": link,
                "niche": "mass_tort",
                "source": "courtlistener_firecrawl",
            })
    return out




def upsert_prospects(prospects: list) -> int:
    """Insert/update prospects (dedup by url)."""
    if not prospects:
        return 0
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    inserted = 0
    for p in prospects:
        try:
            r = sb.table("prospects").select("id").eq("website", p["url"]).execute().data
            if r:
                continue
            sb.table("prospects").insert({
                "business_name": p["name"],
                "website": p["url"],
                "niche": p["niche"],
                "metro": "NATIONAL",
                "notes": p["url"],
                "buy_signal_score": 50,
                "contact_source": p["source"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            inserted += 1
        except Exception as e:
            print(f"  insert err {p['url'][:60]}: {e}")
    return inserted


def run_once() -> dict:
    print(f"[{datetime.now(timezone.utc).isoformat()}] mass_tort_lane scrape")
    recalls = fetch_fda_recalls()
    print(f"  FDA recalls: {len(recalls)}")
    opinions = fetch_class_action_docket()
    print(f"  Courtlistener opinions: {len(opinions)}")
    all_p = recalls + opinions
    ins = upsert_prospects(all_p)
    print(f"  inserted: {ins}")
    return {"recalls": len(recalls), "opinions": len(opinions), "inserted": ins}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--loop", action="store_true", help="loop every 6h")
    args = p.parse_args()
    if args.loop:
        while True:
            run_once()
            time.sleep(6 * 3600)
    else:
        run_once()