import os, time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/root/.env")

def run():
    print("[REDDIT] Agent Alpha starting...")
    try:
        import praw
    except ImportError:
        print("[REDDIT] praw not installed, exiting")
        return

    from supabase import create_client
    sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        username=os.getenv("REDDIT_USERNAME"),
        password=os.getenv("REDDIT_PASSWORD"),
        user_agent=os.getenv("REDDIT_USER_AGENT","EmpireAI/1.0")
    )

    SUBREDDITS = ["HomeImprovement","Roofing","Insurance","homeowners","DIY","weather"]
    KEYWORDS = ["roof damage","storm damage","insurance claim","hail damage","water damage","restoration","roof repair","storm hit"]

    def intent_score(text):
        text = text.lower()
        score = sum(2 for k in KEYWORDS if k in text)
        if any(w in text for w in ["budget","quote","estimate","cost","hire","urgent","emergency"]):
            score += 3
        return min(score, 10)

    def already_captured(url):
        try:
            res = sb.table("radar_targets").select("id").eq("source_url", url).execute()
            return len(res.data) > 0
        except:
            return False

    leads_today = 0
    while True:
        try:
            for sub in SUBREDDITS:
                for post in reddit.subreddit(sub).new(limit=25):
                    text = f"{post.title} {post.selftext}".lower()
                    matched = next((k for k in KEYWORDS if k in text), None)
                    if matched:
                        url = f"https://reddit.com{post.permalink}"
                        if not already_captured(url):
                            score = intent_score(text)
                            if score >= 2:
                                try:
                                    sb.table("radar_targets").insert({
                                        "city": "unknown",
                                        "source_url": url,
                                        "urgency_score": score,
                                        "damage_severity": matched,
                                        "status": "new",
                                        "meta": {"source":"reddit_alpha","author":post.author.name if post.author else "unknown","title":post.title[:200],"keyword_matched":matched},
                                        "created_at": datetime.now(timezone.utc).isoformat()
                                    }).execute()
                                    leads_today += 1
                                    print(f"[REDDIT] Lead: {post.title[:60]} score={score}")
                                except Exception as e:
                                    print(f"[REDDIT] Save error: {e}")
                time.sleep(2)
            try:
                sb.table("agent_registry").upsert({
                    "agent_name": "reddit", "status": "ACTIVE",
                    "leads_today": leads_today,
                    "last_ping": datetime.now(timezone.utc).isoformat(),
                    "enabled": True
                }, on_conflict="agent_name").execute()
            except Exception as e:
                print(f"[REDDIT] Heartbeat error: {e}")
            print(f"[REDDIT] Cycle complete. Leads today: {leads_today}")
            time.sleep(300)
        except Exception as e:
            print(f"[REDDIT] Loop error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run()
