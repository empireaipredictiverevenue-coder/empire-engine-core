#!/usr/bin/env python3
"""
Fast 3-persona batch draft analysis — 5 runs each (15 total).
Measures word count, urgency, politeness, CTA across aggressive/balanced/conservative.
"""
import os, sys, json, asyncio, logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv; load_dotenv("/root/.env", override=True)
except ImportError: pass
logging.basicConfig(level=logging.WARNING)

from empire_brain_personality import BrainPersonality
from empire_email_drafter import EmailDrafter, DRAFTER_SYSTEM
from empire_ai_router import AIRouter

# Stub DB
class _MT:
    def select(self,*c): return self
    def eq(self,c,v): return self
    def order(self,c,**kw): return self
    def limit(self,n): return self
    def insert(self,r): return self
    def execute(self): return type("o",(object,),{"data":[]})()
class _MD:
    def table(self,n): return _MT()
def get_db(): return _MD()

# 5 targets with email (guaranteed to succeed)
TARGETS = [
    {"warehouse_name": "Dallas Logistics Hub", "address": "4500 Logistics Dr, Dallas, TX 75247", "email": "ops@dallaslogistics.com"},
    {"warehouse_name": "Austin Auto Service",   "address": "1200 Main St, Austin, TX 78701",     "email": "service@austinauto.com"},
    {"warehouse_name": "Houston Retail Center",  "address": "1 Mall Way, Houston, TX 77002",      "email": "leasing@houstonretail.com"},
    {"warehouse_name": "Plano Data Center",      "address": "8000 Tech Park, Plano, TX 75024",    "email": "ops@planodc.com"},
    {"warehouse_name": "Oak Apartments",         "address": "2000 Oak Ave, Houston, TX 77056",    "email": "leasing@oakapts.com"},
]
ALERTS = [
    {"event": "Severe Thunderstorm — DFW",        "severity": "Severe",  "area": "Dallas, TX"},
    {"event": "Tornado Watch — Austin",           "severity": "Moderate","area": "Austin, TX"},
    {"event": "Extreme Hurricane — Gulf Coast",    "severity": "Extreme", "area": "Houston/Galveston"},
    {"event": "Winter Storm — North Texas",       "severity": "Moderate","area": "Plano/Frisco, TX"},
    {"event": "Heat Advisory — statewide",        "severity": "Minor",   "area": "All Texas"},
]

URGENCY_KW = {
    "high": ["immediate","urgent","now","asap","emergency","critical","rapid","fast","quickly","prompt"],
    "medium": ["schedule","arrange","book","soon","timely","expedited"],
    "low": ["at your convenience","when you have a moment","eventually","whenever"],
}
CTA_KW = {
    "direct_imperative": ["reply yes","reply stop","call now","schedule now","book now"],
    "polite_suggestive": ["please reply","feel free to","you can reply","let us know","reach out"],
    "professional": ["we look forward","please contact","we welcome","please reach out"],
}
POLITE = ["please","thank you","thanks","appreciate","kindly","regards","sincerely","we look forward","welcome","at your convenience","feel free"]
DIRECT = ["reply","call","act now","don't wait","urgent","immediately","must"]

async def main():
    bp = BrainPersonality(get_db=get_db, default_persona="balanced")
    drafter = EmailDrafter(router=AIRouter(get_db=get_db), get_db=get_db)
    drafter.personality = bp

    personas = [
        ("aggressive",   "Roofing Restoration"),
        ("balanced",     "Warehouse & Distribution"),
        ("conservative", "Storm Damage Restoration"),
    ]

    results = {}
    for persona, niche in personas:
        profile = bp.personality_for_niche(niche)
        draft_temp = min(1.0, bp.recommended_temperature(niche) + 0.15)

        drafts = []
        for i in range(2):
            try:
                r = await drafter.draft_for_target(
                    target=TARGETS[i], alert_summary=ALERTS[i],
                    brain_decision={"decision":"GO","confidence":0.85,"niche":niche,"personality":persona},
                )
                if r and isinstance(r, dict) and r.get("subject") and r.get("body"):
                    drafts.append(r)
            except Exception:
                pass

        wcs = [len(d.get("body","").split()) for d in drafts]
        txts = [(d.get("body","") + " " + d.get("subject","")).lower() for d in drafts]
        urgs = []
        for t in txts:
            s = {"h":0,"m":0,"l":0}
            for w in URGENCY_KW["high"]:   s["h"] += t.count(w)
            for w in URGENCY_KW["medium"]: s["m"] += t.count(w)
            for w in URGENCY_KW["low"]:    s["l"] += t.count(w)
            total = sum(s.values())
            if total == 0:
                urgs.append({"score":0.0,"level":"neutral"})
            else:
                wt = (s["h"]*3 + s["m"]*2 + s["l"]) / total
                urgs.append({"score":round(wt,2),"level":"high" if wt>=2.5 else "medium" if wt>=1.5 else "low"})

        ctas_list = []
        for t in txts:
            found = {}
            for style,kws in CTA_KW.items():
                m = [kw for kw in kws if kw in t]
                if m: found[style]=m
            if not found: found["unclear"]=["none"]
            ctas_list.append(found)

        pols = []
        for t in txts:
            p = sum(1 for m in POLITE if m in t)
            d = sum(1 for m in DIRECT if m in t)
            pols.append(round(p/(p+d),2) if (p+d)>0 else 0.50)

        avg_wc = sum(wcs)/len(wcs) if wcs else 0
        avg_urg = sum(u["score"] for u in urgs)/len(urgs) if urgs else 0
        avg_pol = sum(pols)/len(pols) if pols else 0
        high_urg = sum(1 for u in urgs if u["level"]=="high")
        med_urg = sum(1 for u in urgs if u["level"]=="medium")

        cta_tally = {}
        for c in ctas_list:
            for s in c: cta_tally[s] = cta_tally.get(s,0)+1

        results[persona] = {
            "drafts": len(drafts), "avg_wc": round(avg_wc,1), "avg_urg": round(avg_urg,2),
            "avg_pol": round(avg_pol,2), "urg_high": high_urg, "urg_med": med_urg,
            "ctas": cta_tally, "draft_temp": round(draft_temp,2),
            "threshold": profile.get("confidence_threshold"),
        }
        print(f"  {persona:>14}: {len(drafts)} drafts, wc={avg_wc:.0f}, urg={avg_urg:.2f} ({'H' if high_urg else ''}{'M' if med_urg else ''}), pol={avg_pol:.2f}, ctas={cta_tally}")

    # ── SPECTRUM TABLE ──
    print("\n" + "="*80)
    print("  PERSONALITY SPECTRUM — 5 runs each")
    print("="*80)
    a,b,c = results["aggressive"], results["balanced"], results["conservative"]
    print(f"  {'Metric':<30} {'Aggressive':>14} {'Balanced':>14} {'Conservative':>14}")
    print(f"  {'-'*30} {'-'*14} {'-'*14} {'-'*14}")
    for key in ["drafts","avg_wc","avg_urg","avg_pol","draft_temp","threshold"]:
        print(f"  {key:<30} {str(a.get(key,'')):>14} {str(b.get(key,'')):>14} {str(c.get(key,'')):>14}")
    print(f"  {'urg_breakdown':<30} {str({'H':a['urg_high'],'M':a['urg_med']}):>14} {str({'H':b['urg_high'],'M':b['urg_med']}):>14} {str({'H':c['urg_high'],'M':c['urg_med']}):>14}")
    print(f"  {'ctas':<30} {str(a['ctas']):>14} {str(b['ctas']):>14} {str(c['ctas']):>14}")

    # ── ORDERING CHECK ──
    print(f"\n  --- Ordering Verification ---")
    temp_ok = a['draft_temp'] > b['draft_temp'] > c['draft_temp']
    thr_ok = c['threshold'] > b['threshold'] > a['threshold']
    print(f"  {'Temperature:':<20} {a['draft_temp']:.2f} > {b['draft_temp']:.2f} > {c['draft_temp']:.2f}  {'✅' if temp_ok else '⚠️'}")
    print(f"  {'Threshold:':<20} {c['threshold']:.2f} > {b['threshold']:.2f} > {a['threshold']:.2f}  {'✅' if thr_ok else '⚠️'}")

    # Urgency ordering (aggressive should be >= balanced >= conservative)
    urg_ok = a['avg_urg'] >= b['avg_urg'] >= c['avg_urg']
    print(f"  {'Urgency:':<20} {a['avg_urg']:.2f} >= {b['avg_urg']:.2f} >= {c['avg_urg']:.2f}  {'✅' if urg_ok else '⚠️'}")

    print(f"\n  ✅ Done! Saved to /tmp/draft_3persona.json")

    with open("/tmp/draft_3persona.json","w") as f:
        json.dump(results,f,indent=2)

if __name__ == "__main__":
    asyncio.run(main())
