import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client

load_dotenv("/root/.env")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

# Base job values (USD) — industry-standard ballpark for restoration leads
BASE_VALUE = {
    "storm damage": 9000, "water damage": 9000, "hail damage": 9000, "roof damage": 9000,
    "solar": 25000, "solar installation": 25000,
    "general repair": 4000, "roof repair": 4000, "repair": 4000, "restoration": 9000,
    "multi-niche": 6000, "multi": 6000, "insurance claim": 9000,
    "default": 6000,
}
COMMISSION_RATE = 0.01  # 1% whale fee
COMMISSION_RATE = 0.01  # 1% whale fee

def get_close_rate():
    """Real probability-to-close from brain_memory outcomes."""
    try:
        res = sb.table("brain_memory").select("outcome").execute()
        rows = res.data or []
        if len(rows) < 10:
            return 0.15  # not enough data — conservative default
        closed = sum(1 for r in rows if (r.get("outcome") or "").lower() in ("won","closed","converted"))
        return max(0.05, min(0.6, closed / len(rows)))
    except Exception:
        return 0.15

def base_for(keyword):
    if not keyword:
        return BASE_VALUE["default"]
    k = keyword.lower()
    for key, val in BASE_VALUE.items():
        if key in k:
            return val
    return BASE_VALUE["default"]

def score_lead(lead, close_rate=None):
    """Returns lead enriched with estimated_value + forecasted_revenue."""
    if close_rate is None:
        close_rate = get_close_rate()
    tcv = base_for(lead.get("damage_severity") or (lead.get("meta") or {}).get("keyword") or (lead.get("meta") or {}).get("keyword_matched"))
    intent = lead.get("urgency_score", 5) or 5
    intent_norm = intent / 10.0                       # 0.1 to 1.0
    fee = tcv * COMMISSION_RATE * intent_norm * close_rate
    lead["tcv"] = round(tcv, 2)
    lead["forecasted_fee"] = round(fee, 2)
    lead["close_rate_used"] = round(close_rate, 3)
    return lead

def pipeline_forecast():
    """Aggregate TCV + forecasted 1% fee across today's open leads. Logs to pipeline_health."""
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        res = sb.table("radar_targets").select("damage_severity,urgency_score,meta").gte("created_at", today).execute()
        rows = res.data or []
        cr = get_close_rate()
        total_tcv = 0
        total_fee = 0
        for r in rows:
            scored = score_lead(dict(r), cr)
            total_tcv += scored["tcv"]
            total_fee += scored["forecasted_fee"]
        result = {
            "lead_count": len(rows),
            "close_rate": round(cr, 3),
            "total_tcv": round(total_tcv, 2),
            "total_forecasted_fee": round(total_fee, 2),
        }
        try:
            sb.table("pipeline_health").insert({
                "total_tcv": result["total_tcv"],
                "total_forecasted_fee": result["total_forecasted_fee"],
                "lead_count": result["lead_count"],
                "close_rate": result["close_rate"],
                "created_at": datetime.now(timezone.utc).isoformat()
            }).execute()
        except Exception as e:
            print(f"[REVENUE] pipeline_health log error: {e}")
        return result
    except Exception as e:
        return {"error": str(e), "lead_count": 0, "total_tcv": 0, "total_forecasted_fee": 0}


if __name__ == "__main__":
    import json
    print(json.dumps(pipeline_forecast(), indent=2))
