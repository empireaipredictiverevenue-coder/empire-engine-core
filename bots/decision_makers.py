"""
EMPIRE V49 - DECISION MAKER ENRICHMENT (legitimate)
Two clean sources:
  1. ingest_csv(path)        - merge a Sales Navigator / data-provider CSV export
  2. enrich_from_websites()  - read each prospect's PUBLIC company website for owner names
Does NOT scrape LinkedIn. Public business info + sanctioned CSV only.
"""
import os, re, csv, asyncio, logging
from dotenv import load_dotenv

load_dotenv("/root/.env")
from supabase import create_client
import httpx

log = logging.getLogger("empire.decision_makers")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

DECISION_TITLES = ["owner","founder","president","ceo","principal","partner",
                   "general manager","vice president","vp","director","managing","proprietor"]

def looks_like_decision_maker(title):
    if not title: return False
    t = title.lower()
    return any(k in t for k in DECISION_TITLES)

def ingest_csv(path):
    if not os.path.exists(path):
        print(f"[DM] CSV not found: {path}"); return 0
    merged = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            r = {k.strip().lower(): (v or "").strip() for k,v in row.items()}
            company = r.get("company") or r.get("company name") or r.get("account") or r.get("organization")
            name = r.get("name") or " ".join(filter(None,[r.get("first name"),r.get("last name")])).strip()
            title = r.get("title") or r.get("position") or r.get("job title")
            if not company: continue
            try:
                existing = sb.table("prospects").select("id,business_name").execute()
                match = None
                for p in (existing.data or []):
                    bn = (p.get("business_name") or "").lower()
                    if bn and (bn in company.lower() or company.lower() in bn):
                        match = p; break
                update = {"contact_name": name or None, "contact_title": title or None, "contact_source":"sales_navigator_csv"}
                if match:
                    sb.table("prospects").update(update).eq("id", match["id"]).execute()
                else:
                    sb.table("prospects").insert({"business_name":company,"niche":"roofing",
                        "contact_name":name or None,"contact_title":title or None,
                        "contact_source":"sales_navigator_csv","phone":r.get("phone"),
                        "website":r.get("website"),"status":"new"}).execute()
                merged += 1
            except Exception as e:
                log.error(f"[DM] csv merge error: {e}")
    print(f"[DM] CSV merge complete: {merged} prospects updated/added")
    return merged

NAME_TITLE_PATTERNS = [
    re.compile(r"([A-Z][a-z]+ [A-Z][a-z]+)\s*[,\-]\s*(owner|founder|president|ceo|principal|general manager)", re.I),
    re.compile(r"(owner|founder|president|ceo|principal)\s*[:\-]?\s*([A-Z][a-z]+ [A-Z][a-z]+)", re.I),
]

async def _scrape_public_site(client, url):
    if not url: return None, None
    if not url.startswith("http"): url = "https://" + url
    candidates = [url, url.rstrip("/")+"/about", url.rstrip("/")+"/about-us", url.rstrip("/")+"/team"]
    for u in candidates:
        try:
            r = await client.get(u, timeout=12, follow_redirects=True, headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code != 200: continue
            text = re.sub(r"<[^>]+>"," ", r.text)
            text = re.sub(r"\s+"," ", text)
            for pat in NAME_TITLE_PATTERNS:
                m = pat.search(text)
                if m:
                    g = m.groups()
                    if looks_like_decision_maker(g[0]): return g[1], g[0]
                    else: return g[0], g[1]
        except Exception:
            continue
    return None, None

async def enrich_from_websites(limit=20):
    try:
        res = (sb.table("prospects").select("id,business_name,website,contact_name")
               .is_("contact_name","null").limit(limit).execute())
        rows = [r for r in (res.data or []) if r.get("website")]
        if not rows:
            print("[DM] No prospects with websites needing enrichment"); return 0
        found = 0
        async with httpx.AsyncClient() as client:
            for p in rows:
                name, title = await _scrape_public_site(client, p["website"])
                if name:
                    sb.table("prospects").update({"contact_name":name,"contact_title":title or "listed",
                        "contact_source":"public_website"}).eq("id", p["id"]).execute()
                    found += 1
                    print(f"[DM] {p['business_name']}: {name} ({title or 'listed'})")
                await asyncio.sleep(1)
        print(f"[DM] Website enrichment complete: {found} contacts found")
        return found
    except Exception as e:
        log.error(f"[DM] enrich error: {e}"); return 0

def show_contactable(metro="Wichita"):
    try:
        res = (sb.table("prospects").select("*").eq("metro", metro)
               .order("buy_signal_score", desc=True).execute())
        rows = res.data or []
        named = [r for r in rows if r.get("contact_name")]
        print(f"\n=== CONTACTABLE ({metro}): {len(named)}/{len(rows)} have a named contact ===")
        for r in rows:
            tag = f"{r['contact_name']} ({r.get('contact_title','')})" if r.get("contact_name") else "no name yet"
            print(f"- {r['business_name']} | {tag} | {r.get('phone') or 'no-phone'}")
        return named
    except Exception as e:
        print(f"[DM] show error: {e}"); return []

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "csv":
        ingest_csv(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "web":
        asyncio.run(enrich_from_websites())
    else:
        show_contactable("Wichita")
