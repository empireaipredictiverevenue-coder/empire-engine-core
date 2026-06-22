"""
EMPIRE V49 · BUYER PROSPECTOR AGENT
====================================
Finds companies that BUY leads in each niche, using Agent-Reach
multi-channel intelligence. Complement to bots/prospector.py which
finds contractors (lead sellers).

Agent-Reach channels used per run:
  - semantic_search  — Exa web search (free, no API key)
  - github_search    — GitHub company discovery
  - hn_search        — Hacker News for startup/tech lead buyers
  - wikipedia_search — Company research and background
  - rss_fetch        — Industry news monitoring
  - jina_read        — Read company landing pages for lead-buying signals

Saves high-quality buyer prospects to the 'buyers' table in Supabase:
  - company_name, website, niche, metro
  - phone, email (when discoverable)
  - buy_signal_score (0-100), source channel
  - source_urls for audit trail

Usage:
    python3 -m bots.buyer_prospector_agent              # run all niches
    python3 -m bots.buyer_prospector_agent --niche roofing  # single niche
    python3 -m bots.buyer_prospector_agent --dry-run        # score only, no DB writes
    python3 -m bots.buyer_prospector_agent --camofox        # use camofox-browser fallback
"""

import os
import re
import sys
import json
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv("/root/.env")

sys.path.insert(0, "/root/empire-v49")

log = logging.getLogger("empire.buyer_prospector")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

# ── Niche → lead buyer search queries ──────────────────────────────
# Each niche maps to search terms that find companies buying leads
# in that vertical. These are used as Agent-Reach search queries.
BUYER_QUERIES: Dict[str, List[str]] = {
    "roofing": [
        "roofing company that buys leads",
        "residential roofing lead purchaser",
        "storm restoration roofing leads buyer",
        "roofing contractor lead generation buyer",
    ],
    "restoration": [
        "water damage restoration company buys leads",
        "fire restoration lead purchasing company",
        "restoration contractor lead buyer",
        "emergency restoration services lead acquisition",
    ],
    "water mitigation": [
        "water mitigation company buys leads",
        "flood restoration lead purchaser",
        "water damage remediation lead buyer",
    ],
    "general contractor": [
        "general contractor buys leads",
        "remodeling contractor lead purchaser",
        "home renovation company lead buyer",
    ],
    "hvac": [
        "HVAC company that buys leads",
        "heating and cooling lead purchaser",
        "AC repair lead generation buyer",
        "HVAC contractor lead buyer",
    ],
    "gutter": [
        "gutter company buys leads",
        "gutter installation lead purchaser",
        "seamless gutter lead buyer",
    ],
    "solar": [
        "solar company buys leads",
        "solar installation lead purchaser",
        "residential solar lead generation buyer",
    ],
    "solar installer": [
        "solar panel installer buys leads",
        "solar energy contractor lead purchaser",
    ],
    "commercial solar": [
        "commercial solar developer buys leads",
        "C&I solar lead purchaser",
        "commercial solar installer lead buyer",
    ],
    "commercial roofing": [
        "commercial roofing company buys leads",
        "flat roofing contractor lead purchaser",
        "commercial roof repair lead buyer",
    ],
    "tree removal": [
        "tree service company buys leads",
        "tree removal contractor lead purchaser",
        "arborist lead generation buyer",
    ],
    "emergency services": [
        "emergency service company buys leads",
        "24/7 restoration service lead purchaser",
        "emergency response contractor lead buyer",
    ],
    "public insurance adjuster": [
        "public adjuster firm buys leads",
        "independent insurance adjuster lead purchaser",
        "claims adjuster lead generation buyer",
    ],
    "personal injury lawyer": [
        "personal injury law firm buys leads",
        "PI attorney lead purchaser",
        "injury lawyer lead generation buyer",
        "plaintiff lawyer lead buyer",
    ],
    "mass tort lawyer": [
        "mass tort law firm buys leads",
        "class action attorney lead purchaser",
        "pharma litigation lead buyer",
        "product liability lawyer lead generation buyer",
    ],
    "class action lawyer": [
        "class action law firm buys leads",
        "securities litigation attorney lead purchaser",
    ],
    "workers comp lawyer": [
        "workers compensation attorney buys leads",
        "workers comp lawyer lead purchaser",
    ],
    "medical malpractice lawyer": [
        "medical malpractice law firm buys leads",
        "med mal attorney lead purchaser",
    ],
    "medicare advantage agent": [
        "medicare advantage agent buys leads",
        "medicare broker lead purchaser",
        "senior health insurance lead buyer",
    ],
    "life insurance agent": [
        "life insurance agent buys leads",
        "life insurance broker lead purchaser",
        "final expense lead buyer",
    ],
    "final expense insurance": [
        "final expense agent buys leads",
        "burial insurance lead purchaser",
        "senior life insurance lead buyer",
    ],
    "debt consolidation": [
        "debt consolidation company buys leads",
        "debt relief lead purchaser",
        "credit card debt settlement lead buyer",
    ],
    "debt relief": [
        "debt settlement company buys leads",
        "debt relief lead generation buyer",
        "consumer debt lead purchaser",
    ],
    "business loan broker": [
        "business loan broker buys leads",
        "SBA loan lead purchaser",
        "commercial financing lead buyer",
        "small business loan lead generation",
    ],
    "mortgage broker": [
        "mortgage broker buys leads",
        "home loan lead purchaser",
        "refinance lead generation buyer",
        "mortgage lender lead buyer",
    ],
    "assisted living": [
        "assisted living facility buys leads",
        "senior living lead purchaser",
        "memory care lead generation buyer",
    ],
    "home health agency": [
        "home health care agency buys leads",
        "home care lead purchaser",
        "elderly care lead generation buyer",
    ],
    "addiction treatment center": [
        "addiction treatment center buys leads",
        "rehab facility lead purchaser",
        "substance abuse treatment lead buyer",
    ],
    "mental health clinic": [
        "mental health clinic buys leads",
        "psychiatry practice lead purchaser",
        "therapy center lead generation buyer",
    ],
    "medical alert system": [
        "medical alert company buys leads",
        "senior safety device lead purchaser",
        "PERS lead generation buyer",
    ],
    "cdl truck driving school": [
        "CDL truck driving school buys leads",
        "truck driver training lead purchaser",
        "commercial driving school lead buyer",
    ],
    "nursing school": [
        "nursing school buys leads",
        "RN program lead purchaser",
        "nursing education lead generation buyer",
    ],
    "managed it": [
        "managed IT services company buys leads",
        "MSP lead purchaser",
        "IT support company lead generation buyer",
    ],
    "staffing": [
        "staffing agency buys leads",
        "employment agency lead purchaser",
        "temp staffing lead generation buyer",
    ],
    "auto_insurance": [
        "auto insurance agent buys leads",
        "car insurance lead purchaser",
        "auto insurance broker lead buyer",
    ],
    "medical_claims": [
        "medical claims buyer",
        "medical lien purchaser",
        "healthcare receivables lead buyer",
        "medical claims management company",
    ],
    "electrical": [
        "electrical contractor buys leads",
        "electrician lead purchaser",
        "electrical services lead generation buyer",
    ],
    "plumbing": [
        "plumbing company buys leads",
        "plumber lead purchaser",
        "plumbing services lead generation buyer",
    ],
    "paving": [
        "paving company buys leads",
        "asphalt contractor lead purchaser",
        "parking lot paving lead buyer",
    ],
}

# ── Agent-Reach channels to use for buyer discovery ────────────────
BUYER_CHANNELS = [
    "semantic_search",
    "github_search",
    "hn_search",
    "wikipedia_search",
    "jina_read",
    "wayback_fetch",
]

# ── Supabase helper ────────────────────────────────────────────────
_SB = None


def _get_sb():
    global _SB
    if _SB is None:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
        _SB = create_client(url, key)
    return _SB


# ── Buyer scoring ──────────────────────────────────────────────────


def buyer_score(result: Dict[str, Any]) -> int:
    """Score a potential lead buyer company. 0-100.

    Signals:
      - Has a website URL in result: 30 pts
      - Has a company description (from semantic/github): 25 pts
      - Has GitHub presence (developer/tech buyer signal): 20 pts
      - Mentioned in news/RSS context: 15 pts
      - Has contact info (phone/email pattern in snippets): 10 pts
    """
    score = 0
    data = result.get("data") or result
    channel = result.get("channel", "")

    if isinstance(data, dict):
        # Website presence
        url = data.get("url") or data.get("website") or data.get("link") or ""
        if url and url.startswith("http"):
            score += 30

        # Description/content indicates lead buying intent
        text = json.dumps(data).lower()
        for signal in ["buy", "lead", "purchas", "acquisition", "partner", "client"]:
            if signal in text:
                score += 5
                break

        # Company name presence
        title = data.get("title") or data.get("name") or ""
        snippet = data.get("snippet") or data.get("description") or ""
        if title and len(title) > 3:
            score += 10
        if snippet and len(snippet) > 50:
            score += 15

        # Phone/email in content
        phone_match = re.search(r'[\+\d][\d\s\.\-\(\)]{7,}\d', text[:5000])
        email_match = re.search(r'[\w\.\-]+@[\w\.\-]+\.\w{2,}', text[:5000])
        if phone_match:
            score += 5
        if email_match:
            score += 5

    # Channel bonus — some channels are stronger signals
    if channel == "semantic_search":
        score += 5  # semantic relevance bonus
    elif channel == "github_search":
        score += 10  # GitHub = real company with engineering team

    return min(score, 100)


# ── Company extraction from Agent-Reach results ───────────────────


def extract_companies(result: Dict[str, Any], niche: str) -> List[Dict[str, Any]]:
    """Extract company prospects from a single Agent-Reach channel result."""
    companies: List[Dict[str, Any]] = []
    seen: set = set()
    channel = result.get("channel", "unknown")
    data = result.get("data")

    if not data or not result.get("ok"):
        return companies

    # semantic_search returns items with title/url/snippet
    if isinstance(data, dict):
        items = data.get("results") or data.get("items") or data.get("papers") or []
        if isinstance(items, list):
            for item in items:
                title = item.get("title") or item.get("name") or ""
                url = item.get("url") or item.get("link") or item.get("wayback_url") or ""
                snippet = item.get("snippet") or item.get("description") or item.get("summary") or ""

                # Skip non-companies
                if not title:
                    continue
                low = title.lower()
                if any(skip in low for skip in ["reddit", "forum", "blog", "article", "news"]):
                    continue
                if len(title) < 3:
                    continue

                key = title.lower().strip()[:40]
                if key in seen:
                    continue
                seen.add(key)

                # Score this buyer
                place = {"data": item, "channel": channel}
                score = buyer_score(place)

                companies.append({
                    "company_name": title.strip()[:200],
                    "website": (url or "").strip()[:500],
                    "niche": niche,
                    "snippet": (snippet or "")[:500],
                    "buy_signal_score": score,
                    "source": f"agent-reach/{channel}",
                    "source_url": (url or "")[:500],
                    "status": "new",
                    "phone": None,
                    "email": None,
                })

        # Single URL results (jina_read, wayback_fetch)
        if not items:
            url = data.get("url") or ""
            text = data.get("text") or data.get("content") or data.get("snapshot") or ""
            if url:
                title = data.get("title") or extract_title_from_text(text)
                key = f"{title}_{url}".lower().strip()[:60]
                if key not in seen:
                    seen.add(key)
                    place = {"data": data, "channel": channel}
                    score = buyer_score(place)

                    # Extract phone/email from page text
                    phone = None
                    email = None
                    text_sample = (text or "")[:10000]
                    phone_match = re.search(r'[\+\d][\d\s\.\-\(\)]{7,}\d', text_sample)
                    email_match = re.search(r'[\w\.\-]+@[\w\.\-]+\.\w{2,}', text_sample)
                    if phone_match:
                        phone = phone_match.group(0).strip()
                    if email_match:
                        email = email_match.group(0).strip()

                    companies.append({
                        "company_name": (title or url.split("/")[2] if "://" in url else url)[:200],
                        "website": url[:500],
                        "niche": niche,
                        "snippet": (text or "")[:500] if text else "",
                        "buy_signal_score": score,
                        "source": f"agent-reach/{channel}",
                        "source_url": url[:500],
                        "status": "new",
                        "phone": phone,
                        "email": email,
                    })

    return companies


def extract_title_from_text(text: str) -> str:
    """Heuristic: find the first <title> or <h1> or significant line."""
    if not text:
        return ""
    m = re.search(r'<title[^>]*>(.*?)</title>', text, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()[:100]
    for line in text.split("\n")[:20]:
        line = line.strip()
        if line and len(line) > 10 and len(line) < 120:
            return line[:100]
    return text[:100].strip()


# ── Deduplication ──────────────────────────────────────────────────


def deduplicate(companies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Dedup by company_name (case-insensitive), keep highest score."""
    seen: Dict[str, Dict[str, Any]] = {}
    for c in companies:
        key = c["company_name"].lower().strip()
        if key not in seen or c["buy_signal_score"] > seen[key]["buy_signal_score"]:
            seen[key] = c
    return sorted(seen.values(), key=lambda x: x["buy_signal_score"], reverse=True)


# ── Database operations ───────────────────────────────────────────


def save_buyers(companies: List[Dict[str, Any]], dry_run: bool = False) -> int:
    """Insert buyer prospects into the 'buyers' table, dedup by company_name + niche."""
    if dry_run:
        return 0
    sb = _get_sb()
    saved = 0
    for c in companies:
        try:
            existing = (
                sb.table("buyers")
                .select("id")
                .eq("company_name", c["company_name"])
                .eq("niche", c["niche"])
                .execute()
            )
            if existing.data:
                continue
            sb.table("buyers").insert(c).execute()
            saved += 1
        except Exception as e:
            log.error(f"[buyer_prospector] save error: {e}")
    return saved


# ── Core discovery ────────────────────────────────────────────────


async def discover_buyers(
    niche: str = "roofing",
    max_results: int = 10,
    use_camofox: bool = False,
) -> List[Dict[str, Any]]:
    """Discover companies buying leads in a given niche using Agent-Reach channels.

    Args:
        niche: Niche to search for lead buyers.
        max_results: Max results per Agent-Reach channel.
        use_camofox: If True, also attempt camofox-browser scraping as a fallback.

    Returns:
        Deduplicated, scored list of buyer prospects sorted by score descending.
    """
    queries = BUYER_QUERIES.get(niche, [f"{niche} company buys leads"])
    print(f"[buyer_prospector] Discovering {niche} lead buyers ({len(queries)} queries)...")

    all_companies: List[Dict[str, Any]] = []

    # Create the enricher once per niche (not once per query)
    from products.agent_reach_enrichment import AgentReachEnricher

    def _get_db():
        return _get_sb()

    enricher = AgentReachEnricher(get_db=_get_db)

    for query in queries:
        print(f"[buyer_prospector]  Search: \"{query}\"")

        # Run Agent-Reach enrichment across channels
        try:
            result = await enricher.enrich(
                query=query,
                channels=BUYER_CHANNELS,
                max_results=max_results,
                tier="SCRAPER_PRO",
                save_to_db=True,
                metadata={"source": "buyer_prospector", "niche": niche},
            )
        except Exception as e:
            print(f"[buyer_prospector]  ⚠ Enrichment exception: {e}")
            await asyncio.sleep(1.0)
            continue

        if not result.get("ok"):
            print(f"[buyer_prospector]  ⚠ Enrichment failed: {result.get('error', 'unknown')}")
            await asyncio.sleep(1.0)
            continue

        channels_used = result.get("channels_used", [])
        channel_results = result.get("results", {})
        print(f"[buyer_prospector]  Channels used: {len(channels_used)} — {', '.join(channels_used[:5])}...")

        # Extract companies from each channel result
        for channel in channels_used:
            channel_result = channel_results.get(channel, {})
            companies = extract_companies(channel_result, niche)
            all_companies.extend(companies)
            if companies:
                print(f"[buyer_prospector]    {channel}: {len(companies)} companies")

        # Rate limit between queries
        await asyncio.sleep(1.0)

    # Deduplicate and score
    all_companies = deduplicate(all_companies)

    # Try camofox-browser as a fallback enrichment source
    if use_camofox and not all_companies:
        print(f"[buyer_prospector] Agent-Reach returned no results — trying camofox-browser...")
        try:
            from bots.predictive_camofox_scraper import PredictiveCamofoxScraper

            scraper = PredictiveCamofoxScraper()
            opportunities = await scraper.scrape_niche(niche, "texas", max_results=20)
            for opp in opportunities:
                name = opp.get("name") or opp.get("business_name") or ""
                if not name:
                    continue
                url = opp.get("url") or opp.get("domain") or ""
                score = 25 if url else 10  # camofox gives us less signal
                all_companies.append({
                    "company_name": name[:200],
                    "website": url[:500],
                    "niche": niche,
                    "snippet": f"Found via camofox-browser (source: {opp.get('source', 'camofox')})",
                    "buy_signal_score": score,
                    "source": opp.get("source", "camofox-browser"),
                    "source_url": url[:500],
                    "status": "new",
                    "phone": None,
                    "email": None,
                })
            all_companies = deduplicate(all_companies)
        except Exception as e:
            print(f"[buyer_prospector]  ⚠ Camofox fallback failed: {e}")

    print(f"[buyer_prospector] Total unique buyer prospects for {niche}: {len(all_companies)}")
    return all_companies


# ── Multi-niche runner ────────────────────────────────────────────


async def run_all(
    niches: Optional[List[str]] = None,
    max_per_niche: int = 10,
    dry_run: bool = False,
    use_camofox: bool = False,
) -> Dict[str, Any]:
    """Run buyer discovery across multiple niches."""
    if niches is None:
        niches = list(BUYER_QUERIES.keys())

    summary: Dict[str, Any] = {
        "total_found": 0,
        "total_saved": 0,
        "by_niche": {},
        "niches_scanned": len(niches),
        "dry_run": dry_run,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    for niche in niches:
        companies = await discover_buyers(
            niche=niche,
            max_results=max_per_niche,
            use_camofox=use_camofox,
        )
        summary["by_niche"][niche] = len(companies)
        summary["total_found"] += len(companies)

        if companies:
            saved = save_buyers(companies, dry_run=dry_run)
            summary["total_saved"] += saved
            print(f"[buyer_prospector] {niche}: {len(companies)} found, {saved} saved")
            print(f"[buyer_prospector]   Top 3:")
            for c in companies[:3]:
                src = c.get('source', '?')[:25]
                print(f"     {c['buy_signal_score']:3d}  {c['company_name'][:60]:60s}  {c.get('website', '')[:40]}  [{src}]")
        else:
            print(f"[buyer_prospector] {niche}: 0 found")

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    return summary


# ── CLI entry point ───────────────────────────────────────────────


def main():
    import argparse

    p = argparse.ArgumentParser(description="Empire AI Buyer Prospector Agent")
    p.add_argument("--niche", type=str, default="", help="Single niche to scan (default: all)")
    p.add_argument("--max", type=int, default=10, help="Max results per channel per niche")
    p.add_argument("--dry-run", action="store_true", help="Score and report, don't write to DB")
    p.add_argument("--camofox", action="store_true", help="Enable camofox-browser fallback")
    p.add_argument("--json", action="store_true", help="Output results as JSON")
    args = p.parse_args()

    niches = [args.niche] if args.niche else None

    summary = asyncio.run(run_all(
        niches=niches,
        max_per_niche=args.max,
        dry_run=args.dry_run,
        use_camofox=args.camofox,
    ))

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        print(f"\n=== BUYER PROSPECTOR COMPLETE ===")
        print(f"Niches scanned: {summary['niches_scanned']}")
        print(f"Total found:    {summary['total_found']}")
        if not args.dry_run:
            print(f"Total saved:    {summary['total_saved']}")
        print(f"Dry run:        {summary['dry_run']}")


if __name__ == "__main__":
    main()
