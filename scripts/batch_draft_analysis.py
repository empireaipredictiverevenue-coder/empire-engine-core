#!/usr/bin/env python3
"""
Batch Email Draft Analysis — 10 drafts per personality.
Measures: average word count, urgency level, call-to-action style.
"""
import os, sys, json, asyncio, re, logging

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

logging.basicConfig(level=logging.WARNING)

from empire_brain_personality import BrainPersonality, PERSONALITY_PROFILES
from empire_email_drafter import EmailDrafter, DRAFTER_SYSTEM
from empire_ai_router import AIRouter

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

if SUPABASE_URL and SUPABASE_KEY:
    from supabase import create_client
    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    def get_db(): return db
else:
    class _MT:
        def select(self,*c): return self
        def eq(self,c,v): return self
        def execute(self): return type("o",(object,),{"data":[]})()
    class _MD:
        def table(self,n): return _MT()
    def get_db(): return _MD()

# ── 10 varied targets ──
TARGETS = [
    {"warehouse_name": "Dallas Logistics Hub", "address": "4500 Logistics Dr, Dallas, TX 75247", "email": "ops@dallaslogistics.com", "phone": "+12145551234"},
    {"warehouse_name": "Austin Auto Service", "address": "1200 Main St, Austin, TX 78701", "email": "service@austinauto.com", "phone": "+15125552345"},
    {"warehouse_name": "Fort Worth Manufacturing", "address": "500 Factory Rd, Fort Worth, TX 76102", "email": "ops@fwmanufacturing.com"},
    {"warehouse_name": "Houston Retail Center", "address": "1 Mall Way, Houston, TX 77002", "email": "leasing@houstonretail.com", "phone": "+17135553456"},
    {"warehouse_name": "San Antonio Office Tower", "address": "100 Commerce St, San Antonio, TX 78205", "email": "info@satower.com"},
    {"warehouse_name": "Plano Data Center", "address": "8000 Tech Park, Plano, TX 75024", "email": "ops@planodc.com", "phone": "+19725556789"},
    {"warehouse_name": "Abandoned Warehouse", "address": "8900 Industrial Blvd, Houston, TX 77029"},
    {"warehouse_name": "Shopping Mall SA", "address": "1 Rivercenter, San Antonio, TX 78205", "email": "mall@rivercenter.com", "phone": "+12105559876"},
    {"warehouse_name": "Construction Site", "address": "3000 Development Dr, Austin, TX 78744", "phone": "+15125553456"},
    {"warehouse_name": "Oak Apartments", "address": "2000 Oak Ave, Houston, TX 77056", "email": "leasing@oakapts.com"},
]

ALERTS = [
    {"event": "Severe Thunderstorm — DFW Metro", "severity": "Severe", "area": "Dallas, TX"},
    {"event": "Tornado Watch — Austin", "severity": "Moderate", "area": "Austin, TX"},
    {"event": "Minor Hail — San Antonio", "severity": "Minor", "area": "San Antonio, TX"},
    {"event": "Extreme Hurricane — Gulf Coast", "severity": "Extreme", "area": "Houston/Galveston"},
    {"event": "Flash Flood — Fort Worth", "severity": "Severe", "area": "Fort Worth, TX"},
    {"event": "Winter Storm — North Texas", "severity": "Moderate", "area": "Plano/Frisco, TX"},
    {"event": "Damaging Winds — DFW", "severity": "Severe", "area": "Dallas/Fort Worth"},
    {"event": "Derecho — I-35 corridor", "severity": "Extreme", "area": "Central Texas"},
    {"event": "Lightning Storm — Central TX", "severity": "Moderate", "area": "Austin to Dallas"},
    {"event": "Heat Advisory — statewide", "severity": "Minor", "area": "All Texas"},
]


# ── Analysis helpers ──

URGENCY_KEYWORDS = {
    "high": ["immediate", "urgent", "now", "asap", "emergency", "critical", "rapid", "fast", "quickly", "prompt", "straight away"],
    "medium": ["schedule", "arrange", "book", "soon", "timely", "expedited"],
    "low": ["at your convenience", "when you have a moment", "eventually", "whenever"],
}

CTA_STYLES = {
    "direct_imperative": ["reply yes", "reply stop", "click here", "call now", "schedule now", "book now", "sign up"],
    "direct_bold": ["reply **yes**", "reply ***yes***"],
    "polite_suggestive": ["please reply", "feel free to", "you can reply", "let us know", "reach out"],
    "professional": ["we look forward", "please contact", "we welcome", "please reach out"],
}


def count_words(text: str) -> int:
    return len(text.split()) if text else 0


def score_urgency(body: str, subject: str) -> dict:
    """Score urgency based on keyword density."""
    text = (body + " " + subject).lower()
    scores = {"high": 0, "medium": 0, "low": 0}
    for level, words in URGENCY_KEYWORDS.items():
        for w in words:
            scores[level] += text.count(w.lower())
    total = sum(scores.values())
    if total == 0:
        return {"score": 0, "level": "neutral", "breakdown": scores}
    weighted = (scores["high"] * 3 + scores["medium"] * 2 + scores["low"] * 1) / total
    if weighted >= 2.5:
        level = "high"
    elif weighted >= 1.5:
        level = "medium"
    else:
        level = "low"
    return {"score": round(weighted, 2), "level": level, "breakdown": scores}


def classify_cta(body: str) -> dict:
    """Classify the CTA style used in the email."""
    text = body.lower()
    styles = {}
    for style, keywords in CTA_STYLES.items():
        found = [kw for kw in keywords if kw in text]
        if found:
            styles[style] = found
    if not styles:
        styles["unclear"] = ["no recognizable CTA pattern"]
    return styles


def estimate_politeness(body: str) -> float:
    """Estimate politeness on a 0-1 scale based on linguistic markers."""
    polite_markers = ["please", "thank you", "thanks", "appreciate", "kindly", "regards", "sincerely",
                      "we look forward", "welcome", "at your convenience", "feel free"]
    direct_markers = ["reply", "call", "act now", "don't wait", "urgent", "immediately", "must"]
    text = body.lower()
    polite_count = sum(1 for m in polite_markers if m in text)
    direct_count = sum(1 for m in direct_markers if m in text)
    total = polite_count + direct_count
    if total == 0:
        return 0.5
    return round(polite_count / total, 2)


async def main():
    print("=" * 72)
    print("  BATCH EMAIL DRAFT ANALYSIS — 10 drafts per personality")
    print("=" * 72)

    # Setup
    bp = BrainPersonality(get_db=get_db, default_persona="balanced")
    ai_router = AIRouter(get_db=get_db)
    drafter = EmailDrafter(router=ai_router, get_db=get_db)
    drafter.personality = bp

    results = {}
    for persona, niche in [("aggressive", "Roofing Restoration"), ("balanced", "Warehouse & Distribution"), ("conservative", "Storm Damage Restoration")]:
        profile = bp.personality_for_niche(niche)
        temp = bp.recommended_temperature(niche)
        draft_temp = min(1.0, temp + 0.15)

        print(f"\n  ── Generating 10 {persona.upper()} drafts (temp={draft_temp:.2f}) ──")

        drafts = []
        for i in range(10):
            target = TARGETS[i]
            alert = ALERTS[i]
            brain_dec = {"decision": "GO", "confidence": 0.85, "niche": niche, "personality": persona}

            try:
                result = await drafter.draft_for_target(
                    target=target, alert_summary=alert, brain_decision=brain_dec,
                )
                if result and isinstance(result, dict):
                    drafts.append(result)
                    subj = result.get("subject", "—")[:60]
                    body = result.get("body", "")
                    wc = count_words(body)
                    urg = score_urgency(body, subj)
                    print(f"    Run {i+1:2d}: wc={wc:3d}  urgency={urg['level']:8s}  subj=\"{subj}\"")
                else:
                    print(f"    Run {i+1:2d}: (no draft returned)")
            except Exception as e:
                print(f"    Run {i+1:2d}: ERROR — {e}")

        # Analyze
        word_counts = [count_words(d.get("body", "")) for d in drafts]
        urgencies = [score_urgency(d.get("body", ""), d.get("subject", "")) for d in drafts]
        cta_styles = [classify_cta(d.get("body", "")) for d in drafts]
        politeness = [estimate_politeness(d.get("body", "")) for d in drafts]

        avg_wc = sum(word_counts) / len(word_counts) if word_counts else 0
        avg_urg = sum(u["score"] for u in urgencies) / len(urgencies) if urgencies else 0
        high_urg = sum(1 for u in urgencies if u["level"] == "high")
        med_urg = sum(1 for u in urgencies if u["level"] == "medium")
        low_urg = sum(1 for u in urgencies if u["level"] == "low")
        avg_polite = sum(politeness) / len(politeness) if politeness else 0

        # CTA style breakdown
        cta_tally = {}
        for cta in cta_styles:
            for style in cta:
                cta_tally[style] = cta_tally.get(style, 0) + 1

        results[persona] = {
            "persona": persona,
            "niche": niche,
            "drafts_generated": len(drafts),
            "avg_word_count": round(avg_wc, 1),
            "word_counts": word_counts,
            "avg_urgency_score": round(avg_urg, 2),
            "urgency_breakdown": {"high": high_urg, "medium": med_urg, "low": low_urg},
            "avg_politeness": round(avg_polite, 2),
            "cta_styles": cta_tally,
            "drafting_temp": draft_temp,
            "threshold": profile.get("confidence_threshold"),
        }

        print(f"    ──")
        print(f"    Avg word count: {avg_wc:.1f}")
        print(f"    Urgency: high={high_urg} med={med_urg} low={low_urg} (score={avg_urg:.2f})")
        print(f"    Politeness: {avg_polite:.2f}")
        print(f"    CTA styles: {cta_tally}")

    # ── SUMMARY TABLE ──
    print()
    print("=" * 72)
    print("  RESULTS SUMMARY")
    print("=" * 72)
    print(f"  {'Metric':<40} {'Aggressive':>16} {'Balanced':>16} {'Conservative':>16}")
    print(f"  {'─'*40} {'─'*16} {'─'*16} {'─'*16}")

    for key in ["drafts_generated", "avg_word_count", "avg_urgency_score", "drafting_temp", "threshold"]:
        a = results["aggressive"].get(key, "—")
        b = results["balanced"].get(key, "—")
        c = results["conservative"].get(key, "—")
        print(f"  {key:<40} {str(a):>16} {str(b):>16} {str(c):>16}")

    print(f"  {'urgency_breakdown':<40} {str(results['aggressive']['urgency_breakdown']):>16} {str(results['balanced']['urgency_breakdown']):>16} {str(results['conservative']['urgency_breakdown']):>16}")
    print(f"  {'avg_politeness':<40} {results['aggressive']['avg_politeness']:>16.2f} {results['balanced']['avg_politeness']:>16.2f} {results['conservative']['avg_politeness']:>16.2f}")
    print(f"  {'cta_styles':<40} {str(results['aggressive']['cta_styles']):>16} {str(results['balanced']['cta_styles']):>16} {str(results['conservative']['cta_styles']):>16}")

    # ── SPECTRUM COMPARISON ──
    print()
    print("=" * 72)
    print("  SPECTRUM COMPARISON — 3 Personalities")
    print("=" * 72)
    a = results["aggressive"]
    b = results["balanced"]
    c = results["conservative"]

    # Temperature spectrum (should be aggressive > balanced > conservative)
    print(f"  • Temperature spectrum:  {a['drafting_temp']:.2f} (agg)  →  {b['drafting_temp']:.2f} (bal)  →  {c['drafting_temp']:.2f} (con)")
    if a['drafting_temp'] > b['drafting_temp'] > c['drafting_temp']:
        print(f"    ✅ Strict ordering: aggressive > balanced > conservative")
    else:
        print(f"    ⚠️  Not strictly ordered")

    # Threshold spectrum (should be conservative > balanced > aggressive)
    print(f"  • Threshold spectrum:   {a['threshold']:.2f} (agg)  →  {b['threshold']:.2f} (bal)  →  {c['threshold']:.2f} (con)")
    if c['threshold'] > b['threshold'] > a['threshold']:
        print(f"    ✅ Strict ordering: conservative > balanced > aggressive")
    else:
        print(f"    ⚠️  Not strictly ordered")

    # Word count spectrum
    print(f"  • Word count spectrum:  {a['avg_word_count']:.0f} (agg)  →  {b['avg_word_count']:.0f} (bal)  →  {c['avg_word_count']:.0f} (con)")

    # Urgency spectrum
    print(f"  • Urgency spectrum:     {a['avg_urgency_score']:.2f} (agg)  →  {b['avg_urgency_score']:.2f} (bal)  →  {c['avg_urgency_score']:.2f} (con)")

    # Politeness spectrum
    print(f"  • Politeness spectrum:  {a['avg_politeness']:.2f} (agg)  →  {b['avg_politeness']:.2f} (bal)  →  {c['avg_politeness']:.2f} (con)")

    # CTA style comparison (3-way)
    print(f"  • CTA styles:")
    all_styles = set(list(a['cta_styles'].keys()) + list(b['cta_styles'].keys()) + list(c['cta_styles'].keys()))
    for style in sorted(all_styles):
        ac = a['cta_styles'].get(style, 0)
        bc = b['cta_styles'].get(style, 0)
        cc = c['cta_styles'].get(style, 0)
        print(f"    {style:<25} agg={ac}  bal={bc}  con={cc}")

    print()
    print("  Done! ✅")

    # Save to JSON
    with open("/tmp/draft_analysis.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Full results saved to /tmp/draft_analysis.json")


if __name__ == "__main__":
    asyncio.run(main())
