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

# Words that look like names but aren't. Anything in this set is
# rejected as a "name" match. Cities/states/generic English.
_NAME_STOPWORDS = {
    # cities we already search
    "wichita", "dallas", "houston", "austin", "san antonio", "oklahoma city",
    "tulsa", "kansas city", "denver", "phoenix", "atlanta", "chicago",
    "nashville", "charlotte", "tampa", "new orleans", "st louis",
    # states
    "texas", "kansas", "oklahoma", "colorado", "missouri", "arizona",
    "georgia", "illinois", "tennessee", "north carolina", "florida",
    "louisiana", "kentucky", "alabama", "mississippi", "nebraska",
    # generic / common false positives from real websites
    "and", "of", "the", "this", "that", "from", "with", "for",
    "contact", "about", "team", "staff", "service", "services",
    "call", "click", "learn", "more", "read", "see", "view",
    "home", "page", "site", "company", "business", "office",
    "native", "response", "look", "can", "our", "your", "their",
    "first", "last", "next", "best", "top", "all", "any",
    "colorado", "california", "wyoming", "nevada", "oregon",
    "new", "old", "north", "south", "east", "west",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    # placeholder / example names
    "john doe", "jane doe", "your name",
    "co", "inc", "llc", "ltd", "corp",
    # second-batch false positives observed on real contractor sites
    "standing", "together", "needing", "roof", "personally", "calls",
    "lays", "his", "her", "him", "them", "we", "us", "i", "me",
    "most", "trusted", "reliable", "professional", "quality", "expert",
    "free", "estimate", "quotes", "licensed", "insured", "bonded",
    # third-batch false positives
    "qualified", "supervises", "every", "ial", "set", "out",
    "ensuring", "ensures", "committed", "dedicated", "passionate",
    "years", "experience", "team", "ready", "help", "today",
    "need", "want", "make", "get", "go", "let", "ask",
    # fourth-batch: marketing verbs / adverbs that aren't names
    "drives", "started", "starting", "informed", "allows", "allow",
    "bringing", "brings", "loved", "trust", "trusted", "rely",
    "relying", "dependable", "depend", "growing", "built", "building",
    "based", "operated", "operates", "serving", "served", "serves",
    "reaches", "reached", "covering", "covers", "covered", "cover",
    "founded", "founds", "established", "establishes", "delivers",
    "delivered", "providing", "provides", "provided", "offering",
    "offers", "offered", "creates", "created", "create", "building",
    "gained", "gains", "known", "shows", "showed", "shown", "show",
    "comes", "came", "come", "goes", "went", "gone", "goes",
    "tells", "told", "telling", "says", "said", "saying",
    "looks", "looked", "looking", "sees", "saw", "seen",
    "finds", "found", "finding", "keeps", "kept", "keeping",
    "takes", "took", "taken", "taking", "gives", "gave", "given",
    "works", "worked", "working", "plays", "played", "playing",
    "runs", "ran", "running", "moves", "moved", "moving",
    "lives", "lived", "living", "grows", "grew", "grown", "growing",
    "stands", "stood", "standing", "sits", "sat", "sitting",
    "speaks", "spoke", "spoken", "speaking", "talks", "talked", "talking",
    "writes", "wrote", "written", "writing", "reads", "read", "reading",
    "tries", "tried", "trying", "wants", "wanted", "wanting",
    "needs", "needed", "needing", "helps", "helped", "helping",
    "starts", "started", "starting", "stops", "stopped", "stopping",
    "ends", "ended", "ending", "leaves", "left", "leaving",
    "sends", "sent", "sending", "calls", "called", "calling",
    "meets", "met", "meeting", "joins", "joined", "joining",
    "feels", "felt", "feeling", "seems", "seemed", "seeming",
    "becomes", "became", "becoming", "remains", "remained", "remaining",
    "appears", "appeared", "appearing", "happens", "happened", "happening",
    "begins", "began", "begun", "beginning", "continues", "continued",
    "decides", "decided", "deciding", "expects", "expected", "expecting",
    "includes", "included", "including", "requires", "required", "requiring",
    # adjectives that show up in marketing copy
    "best", "top", "leading", "premier", "premium", "elite", "expert",
    "quality", "professional", "certified", "licensed", "insured",
    "affordable", "reliable", "trusted", "dependable", "honest",
    "experienced", "knowledgeable", "skilled", "qualified",
    "ultimate", "aware", "customer", "client", "customers", "clients",
    "goal", "goals", "mission", "vision", "values", "principles",
    "story", "stories", "journey", "experience", "experiences",
    "owner", "owners", "founder", "founders",  # titles, not names
}


def _looks_like_real_name(s: str) -> bool:
    """Filter false-positive "names" from the regex output."""
    if not s:
        return False
    parts = s.lower().split()
    if len(parts) != 2:
        return False
    for p in parts:
        if p in _NAME_STOPWORDS or len(p) < 3:
            return False
        # real names don't have all-caps or all-consonants
        if not any(c in "aeiou" for c in p):
            return False
    return True


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
                    candidate_name, candidate_title = g[0], g[1]
                    # Identify which group is the name vs the title
                    if looks_like_decision_maker(candidate_name):
                        name, title = candidate_title, candidate_name
                    else:
                        name, title = candidate_name, candidate_title
                    # Final filter: must look like a real human name
                    if _looks_like_real_name(name):
                        return name, title
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
        # one-shot batch run: takes a limit arg, defaults to 100
        lim = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        asyncio.run(enrich_from_websites(limit=lim))
    else:
        show_contactable("Wichita")
