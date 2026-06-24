"""
EMPIRE V49 · MESH REDDIT SCOUT (HERMES PROTOCOL · SCOUTING TEAM B)
===================================================================
B2B buying-intent prospector. Scrapes targeted Reddit subreddits for
high-signal posts indicating purchase intent, then uses Ollama to
analyze each post for lead quality and fit. Drops qualified findings
as 'To-Do' tickets in the agent_task_queue for Outreach to pick up.

Based on the alpha_scout pattern from predictive-cloud with Ollama
replacing hardcoded regex for intent analysis.

Runs standalone: python3 bots/mesh_reddit_scout.py
Runs via mesh:   spawned by agent_mesh mesh_loop when a task exists

Local sovereignty: All LLM calls go through local Ollama.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, "/root/empire-v49")
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("mesh.reddit_scout")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL: str = os.environ.get("AI_MODEL_ENRICH", "llama3.2:3b")
LEAD_SCORE_THRESHOLD: int = int(os.environ.get("REDDIT_LEAD_THRESHOLD", "50"))
CYCLE_INTERVAL: int = int(os.environ.get("REDDIT_SCOUT_INTERVAL", "300"))  # 5 min default

if not SUPABASE_URL or not SUPABASE_KEY:
    log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    sys.exit(1)

_sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── B2B Subreddits (from alpha_scout.py) ──────────────────────────
B2B_SUBREDDITS: List[str] = [
    "entrepreneur", "startups", "smallbusiness", "business",
    "sales", "marketing", "agency", "consulting", "SaaS",
    "digitalnomad", "ecommerce", "growmybusiness", "b2b",
]

POST_LIMIT: int = 75  # hot posts per subreddit
NEW_LIMIT: int = 30   # new posts per subreddit

# ── Buying-intent regex pre-filter (from alpha_scout.py) ────────────
# Fast first pass before Ollama — avoids 1,000+ LLM calls per cycle
BUYING_INTENT_PATTERNS: List[str] = [
    r"\bneed.{0,25}(developer|agency|consultant|solution|platform|software|tool|engineer)\b",
    r"\blooking for.{0,25}(developer|agency|consultant|automation|integration|freelancer)\b",
    r"\bhiring.{0,25}(freelancer|agency|developer|consultant|contractor)\b",
    r"\brfp\b",
    r"\brequest for proposal\b",
    r"\bquote\b",
    r"\boutsourc\w+\b",
    r"\b(scale|scaling|scaled)\b",
    r"\b(crm|erp|saas|api|integration|automation|pipeline)\b",
    r"\b(arr|mrr|revenue|churn|ltv|cac)\b",
    r"\bpain point\b",
    r"\b(recommend|suggestion|advice).{0,20}(tool|platform|software|service|stack)\b",
    r"\bstruggling with\b",
    r"\b(wasted?|losing?).{0,20}(hours?|time|money|revenue)\b",
    r"\bbudget.{0,20}(for|of|around|under|over)\b",
    r"\bhow do (you|we|i).{0,30}(automate|handle|manage|scale)\b",
]


async def query_ollama(prompt: str, system: str = "", temperature: float = 0.2) -> str:
    """Query local Ollama for analysis."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": 512},
                },
            )
            if r.status_code == 200:
                return str(r.json().get("response", ""))
            else:
                log.warning(f"[reddit_scout] Ollama error: HTTP {r.status_code}")
                return ""
    except Exception as e:
        log.error(f"[reddit_scout] Ollama call failed: {e}")
        return ""


async def analyze_post_for_intent(title: str, body: str, subreddit: str) -> Optional[Dict[str, Any]]:
    """Use Ollama to analyze a Reddit post for B2B buying intent.

    Returns a dict with intent_score, confidence, lead_tier, reasoning, and suggested_approach.
    """
    system_prompt: str = (
        "You are a B2B buying intent analyst. Analyze a Reddit post and determine if the "
        "author is expressing genuine purchase intent for business services or software.\n\n"
        "Look for signals like: budget discussions, hiring needs, vendor searches, RFP mentions, "
        "pain points, scaling challenges, requests for recommendations, or outsourcing needs.\n\n"
        "Return ONLY valid JSON with this exact schema:\n"
        '{\n'
        '  "intent_score": 0-100,\n'
        '  "confidence": 0.0-1.0,\n'
        '  "lead_tier": "hot|warm|cool|cold",\n'
        '  "buying_signals": ["signal1", "signal2"],\n'
        '  "reasoning": "brief explanation",\n'
        '  "suggested_approach": "what service/product to pitch",\n'
        '  "estimated_budget": "small|medium|large|unknown"\n'
        '}'
    )
    prompt: str = (
        f"Subreddit: r/{subreddit}\n"
        f"Title: {title[:300]}\n"
        f"Body: {body[:1000]}\n\n"
        "Assess the B2B buying intent. JSON only."
    )
    result: str = await query_ollama(prompt, system_prompt, temperature=0.2)
    if not result:
        return None

    try:
        clean: str = result.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].split("```")[0].strip()
        parsed: Any = json.loads(clean)
        assert isinstance(parsed, dict)
        return parsed
    except (json.JSONDecodeError, IndexError, AttributeError) as e:
        log.warning(f"[reddit_scout] JSON parse error: {e} | raw: {result[:100]}")
        return None


def already_captured(post_id: str) -> bool:
    """Check if a Reddit post has already been processed."""
    try:
        res = _sb.table("radar_targets").select("id").eq("storm_id", f"reddit_{post_id}").execute()
        return len(res.data) > 0
    except Exception:
        return False


def _matches_buying_intent(text: str) -> bool:
    """Fast regex pre-filter: check if text matches any buying-intent pattern.

    Returns True if at least one pattern matches, False otherwise.
    This avoids sending every post to Ollama.
    """
    import re
    text_lower: str = text.lower()
    return any(re.search(p, text_lower) for p in BUYING_INTENT_PATTERNS)


async def _process_post(
    post: Any,
    subreddit: str,
    post_type: str = "hot",
    dry_run: bool = False,
) -> bool:
    """Analyze a single Reddit post and save if qualified.

    Steps:
    1. Fast regex pre-filter (avoids Ollama on irrelevant posts)
    2. Ollama intent analysis (only if regex matches)
    3. Save to radar_targets if score >= threshold

    Returns True if the post was saved as a lead.
    """
    text: str = f"{post.title} {post.selftext[:1000] if post.selftext else ''}"

    # Phase 1: Fast regex pre-filter
    if not _matches_buying_intent(text):
        return False

    if already_captured(post.id):
        return False

    # Phase 2: Ollama intent analysis (only for regex-matched posts)
    analysis = await analyze_post_for_intent(
        title=post.title,
        body=post.selftext[:1000] if post.selftext else "",
        subreddit=subreddit,
    )
    if not analysis:
        return False

    intent_score: int = int(analysis.get("intent_score", 0) or 0)
    if intent_score < LEAD_SCORE_THRESHOLD:
        return False

    lead_tier: str = str(analysis.get("lead_tier", "cold") or "cold")
    buying_signals: List[str] = analysis.get("buying_signals", []) or []
    suggested_approach: str = str(analysis.get("suggested_approach", "") or "")
    estimated_budget: str = str(analysis.get("estimated_budget", "unknown") or "unknown")
    reasoning: str = str(analysis.get("reasoning", "") or "")

    url: str = f"https://reddit.com{post.permalink}"
    author: str = post.author.name if post.author else "unknown"

    if dry_run:
        log.info(
            f"[reddit_scout] DRY RUN: would save r/{subreddit}: "
            f"{post.title[:50]} score={intent_score} tier={lead_tier}"
        )
        return True

    meta = {
        "source": "reddit_b2b_scout",
        "author": author,
        "title": post.title[:200],
        "buying_signals": buying_signals,
        "suggested_approach": suggested_approach,
        "estimated_budget": estimated_budget,
        "reasoning": reasoning,
        "url": url,
        "post_type": post_type,
    }

    targets_data = {
        "post_id": post.id,
        "subreddit": subreddit,
        "title": post.title[:200],
        "score": post.score,
        "comments": post.num_comments,
        "author": author,
        "created_utc": post.created_utc,
        "analysis": analysis,
        "post_type": post_type,
    }

    try:
        _sb.table("radar_targets").insert({
            "storm_id": f"reddit_{post.id}",
            "storm_event": "b2b_intent",
            "address": f"r/{subreddit}",
            "city": subreddit,
            "state": "",
            "lat": 0,
            "lon": 0,
            "damage_severity": lead_tier,
            "urgency_score": intent_score,
            "status": "new",
            "source_url": url,
            "targets_json": json.dumps(targets_data),
            "meta": json.dumps(meta),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        log.info(
            f"[reddit_scout] ✅ r/{subreddit} ({post_type}): {post.title[:50]} "
            f"score={intent_score} tier={lead_tier} budget={estimated_budget}"
        )
        return True
    except Exception as e:
        log.warning(f"[reddit_scout] DB insert error: {e}")
        return False


async def process_subreddit(
    subreddit: str,
    praw_reddit: Any,
    dry_run: bool = False,
) -> int:
    """Process a single subreddit: fetch posts, analyze with Ollama, save qualified leads.

    Uses a two-phase approach:
    1. Fast regex pre-filter (avoids Ollama on irrelevant posts)
    2. Ollama intent analysis on regex-matched posts only

    Returns the count of new leads found in this subreddit.
    """
    local_leads: int = 0
    try:
        # Fetch hot posts (high engagement)
        for post in praw_reddit.subreddit(subreddit).hot(limit=POST_LIMIT):
            if post.stickied:
                continue
            if post.score < 3:
                continue
            if await _process_post(post, subreddit, post_type="hot", dry_run=dry_run):
                local_leads += 1
            await asyncio.sleep(1)  # Rate limit

        # Also check new posts for freshness
        for post in praw_reddit.subreddit(subreddit).new(limit=NEW_LIMIT):
            if post.stickied or post.score < 3:
                continue
            if await _process_post(post, subreddit, post_type="new", dry_run=dry_run):
                local_leads += 1
            await asyncio.sleep(1)  # Rate limit

    except Exception as e:
        log.error(f"[reddit_scout] error processing r/{subreddit}: {e}")

    return local_leads


async def run_scout_cycle(dry_run: bool = False) -> Dict[str, Any]:
    """Run one full Reddit B2B scouting cycle.

    1. Scrape all 13 B2B subreddits
    2. Analyze each post with Ollama
    3. Save qualified leads to radar_targets
    4. Create outreach tasks in agent_task_queue for hot leads

    Returns summary dict with counts.
    """
    try:
        import praw
    except ImportError:
        log.error("[reddit_scout] praw not installed — run 'pip install praw'")
        return {"error": "praw not installed", "leads_found": 0}

    reddit = praw.Reddit(
        client_id=os.environ.get("REDDIT_CLIENT_ID", ""),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
        username=os.environ.get("REDDIT_USERNAME", ""),
        password=os.getenv("REDDIT_PASSWORD", ""),
        user_agent=os.environ.get("REDDIT_USER_AGENT", "EmpireAI/2.0"),
    )

    total_leads: int = 0
    errors: int = 0

    for sub in B2B_SUBREDDITS:
        try:
            leads = await process_subreddit(sub, reddit, dry_run=dry_run)
            total_leads += leads
            log.info(f"[reddit_scout] r/{sub}: {leads} new leads")
        except Exception as e:
            errors += 1
            log.warning(f"[reddit_scout] r/{sub} failed: {e}")
        await asyncio.sleep(2)  # Rate limit between subreddits

    log.info(
        f"[reddit_scout] cycle complete: {total_leads} leads across {len(B2B_SUBREDDITS)} subreddits"
    )

    return {
        "leads_found": total_leads,
        "subreddits_scouted": len(B2B_SUBREDDITS),
        "errors": errors,
    }


async def run_loop(interval_sec: int = CYCLE_INTERVAL):
    """Run the Reddit scout in a background loop."""
    log.info(f"[reddit_scout] starting background loop (interval={interval_sec}s)")
    while True:
        try:
            results = await run_scout_cycle()
            log.info(f"[reddit_scout] cycle complete: {results}")
        except Exception as e:
            log.error(f"[reddit_scout] cycle error: {e}")

        # Heartbeat to agent_registry
        try:
            _sb.table("agent_registry").upsert({
                "agent_name": "reddit_b2b_scout",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "meta": json.dumps({"interval_sec": interval_sec}),
            }, on_conflict="agent_name").execute()
        except Exception as e:
            log.debug(f"[reddit_scout] heartbeat error: {e}")

        await asyncio.sleep(interval_sec)


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if "--loop" in sys.argv:
        asyncio.run(run_loop())
    else:
        results = asyncio.run(run_scout_cycle(dry_run=dry_run))
        print(json.dumps(results, indent=2))
