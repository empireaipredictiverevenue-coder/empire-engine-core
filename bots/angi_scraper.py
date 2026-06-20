import os, time, random
from datetime import datetime, timezone
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from supabase import create_client

load_dotenv("/root/.env")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36"
]

CATEGORIES = ["roofing", "storm-damage", "water-damage", "restoration"]
URGENCY = ["emergency","urgent","asap","insurance","storm","hail","flood","damage","leak","collapse"]

def score_intent(text):
    text = text.lower()
    return min(sum(2 for w in URGENCY if w in text), 10)

def already_captured(url):
    res = sb.table("radar_targets").select("id").eq("source_url", url).execute()
    return len(res.data) > 0

def scrape_angi():
    leads = 0
    for category in CATEGORIES:
        url = f"https://www.angi.com/companylist/{category}.htm"
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        try:
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.content, 'html.parser')
            for card in soup.find_all(['div','article'], class_=lambda c: c and any(x in c for x in ['listing','company','result','card'])):
                title = card.get_text(separator=' ', strip=True)[:200]
                link = card.find('a')
                href = f"https://www.angi.com{link['href']}" if link and link.get('href','').startswith('/') else (link['href'] if link else url)
                score = score_intent(title)
                if score >= 2 and not already_captured(href):
                    sb.table("radar_targets").insert({
                        "city": "Unknown",
                        "status": "new",

                        "source_url": href,
                        "meta": {"source":"angi_scraper","title":title[:200],"keyword":category},

                        "urgency_score": score,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }).execute()
                    leads += 1
                    print(f"[ANGI] Lead: {title[:60]} score={score}")
        except Exception as e:
            print(f"[ANGI] Error {category}: {e}")
        time.sleep(3)
    return leads

def heartbeat(leads):
    sb.table("agent_registry").upsert({
        "agent_name": "angi",
        "role_name": "b2b_lead_scraper",
        "status": "ACTIVE",
        "leads_today": leads,
        "last_ping": datetime.now(timezone.utc).isoformat(),
        "enabled": True
    }, on_conflict="agent_name").execute()

def run():
    print("[ANGI] Scraper starting...")
    total = 0
    while True:
        total += scrape_angi()
        heartbeat(total)
        print(f"[ANGI] Cycle done. Total leads: {total}")
        time.sleep(1800)


_run_once_total = 0

def run_once():
    """Single cycle for agent_runner loop mode."""
    global _run_once_total
    print("[ANGI] Scraper cycle...")
    count = scrape_angi()
    _run_once_total += count
    heartbeat(_run_once_total)
    print(f"[ANGI] Cycle done. Leads this cycle: {count}, total: {_run_once_total}")
    return {"status": "ok", "leads_found": count, "total": _run_once_total}


if __name__ == "__main__":
    run()
