"""
EMPIRE V49 · COLD INBOUND DASHBOARD
=====================================
Operator dashboard at /cold-inbound showing the 5 recalculated cold inbound
dispatches with contractor contact info, match scores, and assessment status.

Wires into hub.py:
    from empire_cold_inbound_dashboard import cold_inbound_dashboard
    from hub import get_db

    @app.get("/cold-inbound", response_class=HTMLResponse)
    async def cold_inbound_route():
        return HTMLResponse(await cold_inbound_dashboard(get_db))
"""

import html
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

from empire_tokens import empire_head

log = logging.getLogger("empire.cold_inbound_dashboard")

DASHBOARD_CSS = """
.cid-wrap {
  max-width: 1200px;
  margin: 0 auto;
  padding: 40px 32px 80px;
}
.cid-hero {
  margin-bottom: 40px;
}
.cid-hero h1 {
  font-family: var(--font-display);
  font-weight: 200;
  font-size: 36px;
  letter-spacing: -0.04em;
  color: var(--empire-white);
  margin-bottom: 8px;
}
.cid-hero h1 em {
  font-style: italic;
  font-weight: 700;
  color: var(--signal-teal);
}
.cid-hero p {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--empire-fog);
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.cid-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 32px;
}
.cid-stat {
  background: var(--empire-surface);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  padding: 18px 20px;
  position: relative;
  overflow: hidden;
  transition: border-color 0.25s;
}
.cid-stat:hover {
  border-color: var(--empire-border);
}
.cid-stat-label {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.2em;
  text-transform: uppercase;
  font-weight: 600;
}
.cid-stat-value {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 28px;
  line-height: 1;
  margin-top: 8px;
  letter-spacing: -0.04em;
  color: var(--empire-white);
  font-feature-settings: 'tnum' 1;
}
.cid-stat-value.teal { color: var(--signal-teal); }
.cid-stat-value.cyan { color: var(--strike-cyan); }
.cid-stat-value.amber { color: var(--status-amber); }
.cid-stat::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 2px; height: 100%;
  background: var(--accent, var(--signal-teal));
}
.cid-stat.teal  { --accent: var(--signal-teal); }
.cid-stat.cyan  { --accent: var(--strike-cyan); }
.cid-stat.amber { --accent: var(--status-amber); }

/* ── Filter bar ─────────────────────────────────────────────────── */
.cid-filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  padding: 12px 16px;
  background: var(--empire-surface);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
}
.cid-filter-bar label {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 600;
}
.cid-filter-bar select {
  background: rgba(0,0,0,0.4);
  color: var(--empire-white);
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 8px 12px;
  outline: none;
  transition: border-color 0.2s;
}
.cid-filter-bar select:focus {
  border-color: var(--signal-teal);
}

/* ── Table ──────────────────────────────────────────────────────── */
.cid-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  background: var(--empire-surface);
}
.cid-table {
  width: 100%;
  border-collapse: collapse;
}
.cid-table th {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 600;
  padding: 14px 16px;
  border-bottom: 1px solid var(--empire-divider);
  text-align: left;
  white-space: nowrap;
  position: sticky;
  top: 0;
  background: var(--empire-surface);
  z-index: 1;
}
.cid-table td {
  padding: 14px 16px;
  border-bottom: 1px solid rgba(122, 140, 163, 0.04);
  font-size: 13px;
  color: var(--empire-silver);
  vertical-align: middle;
}
.cid-table tr:last-child td { border-bottom: none; }
.cid-table tr { transition: background 0.15s; }
.cid-table tr:hover td { background: rgba(255, 255, 255, 0.015); }
.cid-table .score-cell {
  font-family: var(--font-mono);
  font-weight: 600;
  font-feature-settings: 'tnum' 1;
}
.cid-table .score-cell.high { color: var(--signal-teal); }
.cid-table .score-cell.med  { color: var(--status-amber); }
.cid-table .score-cell.low  { color: var(--empire-mist); }
.cid-table .cell-mono {
  font-family: var(--font-mono);
  font-size: 11px;
  font-feature-settings: 'tnum' 1;
}

/* ── Badges ─────────────────────────────────────────────────────── */
.cid-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  border: 1px solid;
  border-radius: var(--radius-xs);
  font-weight: 600;
}
.cid-badge.teal  { color: var(--signal-teal); border-color: rgba(68,229,184,0.3); background: var(--signal-teal-soft); }
.cid-badge.amber { color: var(--status-amber); border-color: rgba(245,166,35,0.3); background: var(--status-amber-soft); }
.cid-badge.cyan  { color: var(--strike-cyan); border-color: rgba(90,200,250,0.3); background: var(--strike-cyan-soft); }
.cid-badge.muted { color: var(--empire-mist); border-color: var(--empire-border); }

/* ── Action buttons ─────────────────────────────────────────────── */
.cid-actions {
  display: flex;
  gap: 6px;
}
.cid-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-weight: 600;
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--empire-mist);
  cursor: pointer;
  text-decoration: none;
  transition: all 0.2s;
}
.cid-action-btn:hover {
  color: var(--empire-white);
  border-color: var(--empire-border-hi);
}
.cid-action-btn.primary {
  color: var(--signal-teal);
  border-color: rgba(68,229,184,0.3);
}
.cid-action-btn.primary:hover {
  background: var(--signal-teal-soft);
  border-color: var(--signal-teal);
}

/* ── Score bar ──────────────────────────────────────────────────── */
.cid-score-bar {
  width: 60px;
  height: 4px;
  background: rgba(10, 26, 47, 0.8);
  border-radius: 2px;
  overflow: hidden;
  display: inline-block;
  vertical-align: middle;
  margin-right: 8px;
}
.cid-score-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.6s var(--ease-out-empire);
}
.cid-score-fill.teal { background: var(--signal-teal); }
.cid-score-fill.amber { background: var(--status-amber); }
.cid-score-fill.muted { background: var(--empire-mist); }

/* ── Status dot ─────────────────────────────────────────────────── */
.cid-status-dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.cid-status-dot.green { background: var(--signal-teal); box-shadow: 0 0 8px rgba(68,229,184,0.4); }
.cid-status-dot.amber { background: var(--status-amber); box-shadow: 0 0 8px rgba(245,166,35,0.4); }
.cid-status-dot.gray  { background: var(--empire-fog); }

/* ── Footer ─────────────────────────────────────────────────────── */
.cid-foot {
  margin-top: 48px;
  padding-top: 20px;
  border-top: 1px solid var(--empire-divider);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-fog);
  letter-spacing: 0.18em;
  text-transform: uppercase;
}
.cid-foot a {
  color: var(--empire-mist);
  text-decoration: none;
  transition: color 0.2s;
}
.cid-foot a:hover { color: var(--signal-teal); }

/* ── Assessment progress section ──────────────────────────────── */
.cid-progress-section {
  margin: 32px 0;
}
.cid-progress-section h2 {
  font-family: var(--font-display);
  font-weight: 200;
  font-size: 18px;
  letter-spacing: -0.02em;
  color: var(--empire-white);
  margin-bottom: 16px;
}
.cid-progress-section h2 em {
  font-style: italic;
  font-weight: 600;
  color: var(--status-amber);
}

.cid-progress-bar-outer {
  background: rgba(10, 26, 47, 0.8);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  padding: 16px 20px;
  margin-bottom: 20px;
}
.cid-progress-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.cid-progress-header span:first-child {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--empire-mist);
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.cid-progress-header span:last-child {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
}
.cid-progress-track {
  height: 6px;
  background: rgba(122, 140, 163, 0.15);
  border-radius: 3px;
  overflow: hidden;
  display: flex;
}
.cid-progress-fill {
  height: 100%;
  transition: width 0.8s var(--ease-out-empire);
}
.cid-progress-fill.completed {
  background: var(--signal-teal);
}
.cid-progress-fill.in-progress {
  background: var(--strike-cyan);
}
.cid-progress-fill.pending {
  background: var(--status-amber);
}
.cid-progress-fill.none {
  background: var(--empire-fog);
}

.cid-progress-legend {
  display: flex;
  gap: 20px;
  margin-top: 10px;
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--empire-mist);
}
.cid-progress-legend span {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cid-progress-legend .swatch {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.cid-progress-legend .swatch.teal { background: var(--signal-teal); }
.cid-progress-legend .swatch.cyan { background: var(--strike-cyan); }
.cid-progress-legend .swatch.amber { background: var(--status-amber); }
.cid-progress-legend .swatch.gray { background: var(--empire-fog); }

/* ── Metro breakdown ───────────────────────────────────────────── */
.cid-metro-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
  margin-bottom: 24px;
}
.cid-metro-card {
  background: var(--empire-surface);
  border: 1px solid var(--empire-divider);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  transition: border-color 0.25s;
}
.cid-metro-card:hover {
  border-color: var(--empire-border);
}
.cid-metro-card .metro-name {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  color: var(--empire-white);
  margin-bottom: 6px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.cid-metro-card .metro-stat {
  display: flex;
  justify-content: space-between;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--empire-mist);
  padding: 2px 0;
}
.cid-metro-card .metro-stat .val {
  color: var(--empire-silver);
  font-weight: 600;
}
.cid-metro-card .metro-stat .val.green { color: var(--signal-teal); }
.cid-metro-card .metro-stat .val.amber { color: var(--status-amber); }
.cid-metro-card .metro-bar {
  height: 3px;
  background: rgba(122, 140, 163, 0.1);
  border-radius: 2px;
  margin-top: 8px;
  overflow: hidden;
}
.cid-metro-card .metro-bar-fill {
  height: 100%;
  background: var(--strike-cyan);
  border-radius: 2px;
  transition: width 0.6s var(--ease-out-empire);
}

/* ── Call history cell in table ────────────────────────────────── */
.cid-call-history {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  font-feature-settings: 'tnum' 1;
  cursor: default;
}
.cid-call-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 2px;
}
.cid-call-dot.made { background: var(--signal-teal); }
.cid-call-dot.none { background: var(--empire-fog); }

.cid-call-popover {
  display: none;
  position: absolute;
  top: 100%;
  left: 0;
  background: #0f1a2e;
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  min-width: 240px;
  z-index: 10;
  box-shadow: 0 8px 24px rgba(0,0,0,0.3);
}
.cid-call-history:hover .cid-call-popover {
  display: block;
}
.cid-call-popover .call-entry {
  font-size: 10px;
  color: var(--empire-silver);
  padding: 4px 0;
  border-bottom: 1px solid rgba(122, 140, 163, 0.06);
  line-height: 1.5;
}
.cid-call-popover .call-entry:last-child { border-bottom: none; }
.cid-call-popover .call-entry .ts {
  color: var(--empire-mist);
  font-size: 9px;
}

/* ── Empty state ────────────────────────────────────────────────── */
.cid-empty {
  text-align: center;
  padding: 60px 20px;
  color: var(--empire-mist);
  font-size: 13px;
}
.cid-empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

/* ── Responsive ─────────────────────────────────────────────────── */
@media (max-width: 900px) {
  .cid-stats { grid-template-columns: repeat(2, 1fr); }
  .cid-table th, .cid-table td { padding: 10px 12px; }
}
@media (max-width: 540px) {
  .cid-stats { grid-template-columns: 1fr; }
  .cid-wrap { padding: 24px 16px; }
}

/* ── Refresh button ─────────────────────────────────────────────── */
.cid-refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  font-weight: 600;
  border: 1px solid var(--signal-teal);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--signal-teal);
  cursor: pointer;
  transition: all 0.2s;
  text-decoration: none;
}
.cid-refresh-btn:hover {
  background: var(--signal-teal-soft);
  box-shadow: var(--glow-soft);
}
"""


async def _query_cold_inbound_data(get_db):
    """Shared query: returns (rows, total, total_pending, total_in_progress,
    total_completed, total_calls_made, avg_score) from cold inbound claims.

    Each row dict includes assessment + call_log data for both the
    dashboard HTML and the API endpoint.
    """
    rows = []
    total_pending = 0
    total_in_progress = 0
    total_completed = 0
    total_calls_made = 0
    avg_score = 0.0

    try:
        db = get_db()

        r = db.table("carrier_claims").select("*").execute()
        all_claims = r.data or []
        cold_claims = [
            c for c in all_claims
            if "cold inbound" in (c.get("loss_description", "") or "").lower()
        ]

        score_sum = 0.0
        for c in cold_claims:
            claim_id = c["id"]
            dsp_id = c.get("dispatch_id", "") or ""

            dispatch_data = None
            contractor_data = None
            assessment = {}
            call_log = []

            if dsp_id:
                rd = db.table("dispatches").select("*").eq("id", dsp_id).limit(1).execute()
                if rd.data:
                    dispatch_data = rd.data[0]
                    meta = dispatch_data.get("meta", {})
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except Exception:
                            meta = {}
                    if isinstance(meta, dict):
                        assessment = meta.get("assessment_worksheet", {}) or {}
                        call_log = meta.get("call_log", []) or []
                        if isinstance(call_log, str):
                            try:
                                call_log = json.loads(call_log)
                            except Exception:
                                call_log = []

                    ctr_id = dispatch_data.get("contractor_id", "")
                    if ctr_id:
                        rc = db.table("contractors").select(
                            "id,name,phone,email,metro,specialties,trust_score"
                        ).eq("id", ctr_id).limit(1).execute()
                        if rc.data:
                            contractor_data = rc.data[0]

            score = dispatch_data.get("match_score") if dispatch_data else None
            if score is not None:
                score_sum += float(score)

            assess_status = assessment.get("status", "none") if assessment else "none"
            fields = assessment.get("fields", {}) if assessment else {}
            fields_filled = sum(1 for v in fields.values() if v is not None) if isinstance(fields, dict) else 0
            fields_total = len(fields) if isinstance(fields, dict) else 5
            calls = len(call_log) if isinstance(call_log, list) else 0
            total_calls_made += calls

            if assess_status == "pending":
                total_pending += 1
            elif assess_status == "in_progress":
                total_in_progress += 1
            elif assess_status == "completed":
                total_completed += 1

            rows.append({
                "claim_id": claim_id[:8],
                "claim_id_full": claim_id,
                "created_at": str(c.get("created_at", ""))[:19],
                "claim_status": c.get("status", "?"),
                "asset_value": float(c.get("asset_value", 0) or 0),
                "dispatch_id": dsp_id[:8] if dsp_id else "—",
                "dispatch_id_full": dsp_id,
                "dispatch_status": dispatch_data.get("status", "?") if dispatch_data else "?",
                "match_score": score,
                "match_components": (dispatch_data.get("match_components", {})
                                     if dispatch_data else {}),
                "contractor_name": (contractor_data.get("name", "?")
                                    if contractor_data else "Unknown"),
                "contractor_id": contractor_data.get("id", "") if contractor_data else "",
                "contractor_phone": (contractor_data.get("phone", "")
                                     if contractor_data else ""),
                "contractor_email": (contractor_data.get("email", "")
                                     if contractor_data else ""),
                "contractor_metro": (contractor_data.get("metro", "")
                                     if contractor_data else ""),
                "contractor_specialties": (contractor_data.get("specialties", [])
                                           if contractor_data else []),
                "contractor_trust_score": (contractor_data.get("trust_score", "?")
                                           if contractor_data else "?"),
                "assessment_status": assess_status,
                "assessment_fields": fields,
                "assessment_fields_filled": fields_filled,
                "assessment_fields_total": fields_total,
                "assessment_notes": (assessment.get("notes", "")[:120]
                                     if assessment else ""),
                "call_log": call_log,
                "call_count": calls,
            })

        if rows:
            avg_score = round(score_sum / len(rows), 3)

    except Exception as e:
        log.error(f"[_query_cold_inbound_data] failed: {e}")
        rows = []

    return rows, len(rows), total_pending, total_in_progress, total_completed, total_calls_made, avg_score


async def cold_inbound_assessment_progress(get_db) -> dict:
    """Return structured JSON of assessment progress for the API.

    Used by GET /api/v1/cold-inbound/assessment-progress.
    """
    rows, total, total_pending, total_in_progress, total_completed, total_calls_made, avg_score = (
        await _query_cold_inbound_data(get_db)
    )

    # ── Group by metro ──
    by_metro: dict = {}
    for r_ in rows:
        metro = r_["contractor_metro"] or "Unknown"
        if metro not in by_metro:
            by_metro[metro] = {
                "metro": metro,
                "total": 0,
                "pending": 0,
                "in_progress": 0,
                "completed": 0,
                "no_worksheet": 0,
                "calls_made": 0,
            }
        by_metro[metro]["total"] += 1
        if r_["assessment_status"] == "pending":
            by_metro[metro]["pending"] += 1
        elif r_["assessment_status"] == "in_progress":
            by_metro[metro]["in_progress"] += 1
        elif r_["assessment_status"] == "completed":
            by_metro[metro]["completed"] += 1
        else:
            by_metro[metro]["no_worksheet"] += 1
        by_metro[metro]["calls_made"] += r_["call_count"]

    return {
        "summary": {
            "total_leads": total,
            "no_worksheet": total - total_pending - total_in_progress - total_completed,
            "pending": total_pending,
            "in_progress": total_in_progress,
            "completed": total_completed,
            "calls_made": total_calls_made,
            "avg_score": avg_score,
            "worksheet_completion_pct": round(
                ((total_in_progress + total_completed) / max(total, 1)) * 100, 1
            ),
        },
        "by_metro": sorted(by_metro.values(), key=lambda x: x["total"], reverse=True),
        "leads": [
            {
                "contractor_name": r_["contractor_name"],
                "metro": r_["contractor_metro"],
                "assessment_status": r_["assessment_status"],
                "fields_filled": r_["assessment_fields_filled"],
                "fields_total": r_["assessment_fields_total"],
                "call_count": r_["call_count"],
                "claim_status": r_["claim_status"],
                "match_score": r_["match_score"],
                "claim_id": r_["claim_id"],
                "dispatch_id": r_["dispatch_id"],
            }
            for r_ in rows
        ],
    }


async def cold_inbound_dashboard(get_db) -> str:
    """Return the full /cold-inbound dashboard HTML page.

    Queries Supabase live to show the cold inbound dispatches with
    contractor contact info, match scores, assessment worksheet
    status, and call history.
    """
    now = datetime.now(timezone.utc)

    rows, total, total_pending, total_in_progress, total_completed, total_calls_made, avg_score = (
        await _query_cold_inbound_data(get_db)
    )
    total_no_worksheet = total - total_pending - total_in_progress - total_completed
    total_assessed = total_completed  # alias used by stat cards below
    worksheet_completion_pct = round(
        ((total_in_progress + total_completed) / max(total, 1)) * 100, 1
    )

    # ── Build HTML ────────────────────────────────────────────

    def _score_cell(score):
        if score is None:
            return '<span class="cid-badge muted">unscored</span>'
        s = float(score)
        pct = int(s * 100)
        cls = "high" if s >= 0.5 else "med" if s >= 0.35 else "low"
        fill_cls = "teal" if s >= 0.5 else "amber" if s >= 0.35 else "muted"
        return (
            f'<span class="score-cell {cls}">'
            f'<span class="cid-score-bar"><span class="cid-score-fill {fill_cls}" '
            f'style="width:{pct}%"></span></span>'
            f'{s:.3f}</span>'
        )

    def _badge(text, variant="muted"):
        return f'<span class="cid-badge {variant}">{text}</span>'

    def _status_dot(status):
        if status == "pending":
            return f'<span><span class="cid-status-dot amber"></span>Pending</span>'
        elif status == "in_progress":
            return f'<span><span class="cid-status-dot green"></span>In Progress</span>'
        elif status == "completed":
            return f'<span><span class="cid-status-dot green"></span>Complete</span>'
        else:
            return f'<span><span class="cid-status-dot gray"></span>No Worksheet</span>'

    rows_html = ""
    for r_ in rows:
        # Score
        score_cell = _score_cell(r_["match_score"])

        # Assessment status
        status_cell = _status_dot(r_["assessment_status"])

        # Fields
        ft = r_["assessment_fields_total"]
        fields_cell = (
            f'<span class="cell-mono">{r_["assessment_fields_filled"]}/{ft}</span>'
        )

        # Phone as clickable link
        phone = r_["contractor_phone"]
        phone_display = phone if phone else "—"
        phone_link = f'<a href="tel:{phone}" style="color:var(--signal-teal);text-decoration:none;font-family:var(--font-mono);font-size:11px">{phone_display}</a>' if phone else phone_display

        # Email
        email = r_["contractor_email"]
        email_display = email if email else "—"

        # Metro badge
        metro = r_["contractor_metro"]
        metro_badge = _badge(metro, "cyan") if metro else _badge("—", "muted")

        # Score components breakdown as tooltip
        components = r_.get("match_components", {})
        if isinstance(components, str):
            try:
                components = json.loads(components)
            except Exception:
                components = {}
        comp_parts = []
        if isinstance(components, dict):
            for k, v in sorted(components.items()):
                if isinstance(v, (int, float)):
                    comp_parts.append(f"{k}={v:.3f}")
        comp_tip = " | ".join(comp_parts) if comp_parts else ""

        # Call history
        call_count = r_["call_count"]
        call_log_entries = r_["call_log"]
        if call_count > 0 and isinstance(call_log_entries, list):
            popover_entries = ""
            for entry in call_log_entries:
                ts = entry.get("timestamp", "") or entry.get("time", "") or ""
                if len(ts) > 16:
                    ts = ts[:16]
                note = entry.get("note", "") or entry.get("notes", "") or entry.get("summary", "") or ""
                note_safe = html.escape(note[:80])
                popover_entries += f'<div class="call-entry"><span class="ts">{ts}</span> {note_safe}</div>'
            calls_cell = f'<span class="cid-call-history">'
            for _ in range(min(call_count, 5)):
                calls_cell += '<span class="cid-call-dot made"></span>'
            calls_cell += f'<span class="cell-mono" style="margin-left:2px">{call_count}</span>'
            if popover_entries:
                calls_cell += f'<div class="cid-call-popover">{popover_entries}</div>'
            calls_cell += "</span>"
        else:
            calls_cell = '<span class="cid-call-history"><span class="cid-call-dot none"></span><span class="cell-mono" style="color:var(--empire-fog)">0</span></span>'

        rows_html += f"""
    <tr>
      <td><strong style="color:var(--empire-white);font-weight:500">{r_["contractor_name"]}</strong></td>
      <td>{phone_link}</td>
      <td style="font-size:11px;color:var(--empire-mist);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{email_display}</td>
      <td>{metro_badge}</td>
      <td class="cell-mono">{r_["dispatch_status"]}</td>
      <td{(' title="' + comp_tip + '"') if comp_tip else ''}>{score_cell}</td>
      <td>{status_cell}</td>
      <td>{fields_cell}</td>
      <td>{calls_cell}</td>
      <td>
        <div class="cid-actions">
          <a href="tel:{r_['contractor_phone']}" class="cid-action-btn primary">📞 Call</a>
          <a href="/command#/dispatch" class="cid-action-btn">Dispatch</a>
        </div>
      </td>
    </tr>"""

    if not rows_html:
        rows_html = """
    <tr>
      <td colspan="10">
        <div class="cid-empty">
          <div class="cid-empty-icon">📭</div>
          <p>No cold inbound leads found.</p>
          <p style="font-size:11px;margin-top:8px;color:var(--empire-fog)">Cold inbound leads appear when a contractor signs up and is dispatched without an existing storm claim.</p>
        </div>
      </td>
    </tr>"""

    stat_val = (
        f'<span class="cid-stat-value teal">{total}</span>'
        if total > 0 else
        f'<span class="cid-stat-value">0</span>'
    )
    pending_val = (
        f'<span class="cid-stat-value amber">{total_pending}</span>'
        if total_pending > 0 else
        f'<span class="cid-stat-value">0</span>'
    )
    assessed_val = (
        f'<span class="cid-stat-value cyan">{total_assessed}</span>'
        if total_assessed > 0 else
        f'<span class="cid-stat-value">0</span>'
    )
    score_val = (
        f'<span class="cid-stat-value teal">{avg_score:.3f}</span>'
        if avg_score > 0 else
        f'<span class="cid-stat-value">—</span>'
    )
    no_ws_val = (
        f'<span class="cid-stat-value" style="color:var(--empire-fog)">{total_no_worksheet}</span>'
        if total_no_worksheet > 0 else
        f'<span class="cid-stat-value" style="color:var(--empire-fog)">0</span>'
    )
    in_prog_val = (
        f'<span class="cid-stat-value cyan">{total_in_progress}</span>'
        if total_in_progress > 0 else
        f'<span class="cid-stat-value">0</span>'
    )
    calls_val = (
        f'<span class="cid-stat-value teal">{total_calls_made}</span>'
        if total_calls_made > 0 else
        f'<span class="cid-stat-value" style="color:var(--empire-fog)">0</span>'
    )

    # ── Metro breakdown ──
    metro_data = defaultdict(lambda: {"total": 0, "pending": 0, "in_progress": 0, "completed": 0, "no_worksheet": 0, "calls": 0})
    for r_ in rows:
        m = r_["contractor_metro"] or "Unknown"
        metro_data[m]["total"] += 1
        s = r_["assessment_status"]
        if s == "pending":
            metro_data[m]["pending"] += 1
        elif s == "in_progress":
            metro_data[m]["in_progress"] += 1
        elif s == "completed":
            metro_data[m]["completed"] += 1
        else:
            metro_data[m]["no_worksheet"] += 1
        metro_data[m]["calls"] += r_["call_count"]

    metro_cards_html = ""
    for metro, md in sorted(metro_data.items(), key=lambda x: x[1]["total"], reverse=True):
        metro = metro if metro else "Unknown"
        assessable = max(md["total"], 1)
        pct = round(((md["in_progress"] + md["completed"]) / assessable) * 100)
        metro_cards_html += f"""
    <div class="cid-metro-card">
      <div class="metro-name">{metro}</div>
      <div class="metro-stat"><span>Leads</span><span class="val">{md['total']}</span></div>
      <div class="metro-stat"><span>Assessed</span><span class="val green">{md['in_progress'] + md['completed']}</span></div>
      <div class="metro-stat"><span>Calls</span><span class="val">{md['calls']}</span></div>
      <div class="metro-stat"><span>Pending</span><span class="val amber">{md['pending']}</span></div>
      <div class="metro-bar"><div class="metro-bar-fill" style="width:{pct}%"></div></div>
    </div>"""

    # ── Progress bar weights ──
    c_total = max(total, 1)
    c_none_pct = round((total_no_worksheet / c_total) * 100)
    c_pending_pct = round((total_pending / c_total) * 100)
    c_inprog_pct = round((total_in_progress / c_total) * 100)
    c_completed_pct = 100 - c_none_pct - c_pending_pct - c_inprog_pct

    head = empire_head(
        title="Cold Inbound Leads · Empire AI",
        extra=DASHBOARD_CSS,
        page="cold_inbound",
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="cid-wrap">

  <div class="cid-hero">
    <h1>Cold Inbound <em>Leads</em></h1>
    <p>{now.strftime('%B %d, %Y at %H:%M UTC')} · Assessment progress tracker</p>
  </div>

  {'' if total == 0 else f'''
  <div class="cid-progress-section">
    <h2>Assessment <em>Progress</em></h2>

    <div class="cid-progress-bar-outer">
      <div class="cid-progress-header">
        <span>Worksheet Completion</span>
        <span style="color:var(--signal-teal)">{worksheet_completion_pct}%</span>
      </div>
      <div class="cid-progress-track">
        <div class="cid-progress-fill completed" style="width:{c_completed_pct}%"></div>
        <div class="cid-progress-fill in-progress" style="width:{c_inprog_pct}%"></div>
        <div class="cid-progress-fill pending" style="width:{c_pending_pct}%"></div>
        <div class="cid-progress-fill none" style="width:{c_none_pct}%"></div>
      </div>
      <div class="cid-progress-legend">
        <span><span class="swatch teal"></span>Completed</span>
        <span><span class="swatch cyan"></span>In Progress</span>
        <span><span class="swatch amber"></span>Pending</span>
        <span><span class="swatch gray"></span>No Worksheet</span>
        <span>|</span>
        <span>Calls made: {total_calls_made}</span>
      </div>
    </div>

    <h2 style="margin-top:24px;font-size:14px;color:var(--empire-mist)">
      By <em style="font-style:italic;font-weight:600;color:var(--strike-cyan)">Metro</em>
    </h2>
    <div class="cid-metro-grid">{metro_cards_html}</div>

    <div class="cid-stats" style="grid-template-columns:repeat(4,1fr)">
      <div class="cid-stat" style="--accent:var(--empire-fog)">
        <div class="cid-stat-label">No Worksheet</div>
        {no_ws_val}
      </div>
      <div class="cid-stat cyan">
        <div class="cid-stat-label">In Progress</div>
        {in_prog_val}
      </div>
      <div class="cid-stat teal">
        <div class="cid-stat-label">Calls Made</div>
        {calls_val}
      </div>
      <div class="cid-stat teal">
        <div class="cid-stat-label">Avg Match Score</div>
        {score_val}
      </div>
    </div>
  </div>
  '''}

  <div class="cid-stats">
    <div class="cid-stat teal">
      <div class="cid-stat-label">Total Leads</div>
      {stat_val}
    </div>
    <div class="cid-stat amber">
      <div class="cid-stat-label">Pending Assessment</div>
      {pending_val}
    </div>
    <div class="cid-stat cyan">
      <div class="cid-stat-label">Assessed</div>
      {assessed_val}
    </div>
    <div class="cid-stat teal">
      <div class="cid-stat-label">Avg Match Score</div>
      {score_val}
    </div>
  </div>

  <div class="cid-filter-bar">
    <label>Filter</label>
    <select onchange="filterTable(this.value)">
      <option value="all">All Leads</option>
      <option value="pending">Pending Assessment</option>
      <option value="in_progress">In Progress</option>
      <option value="no_worksheet">No Worksheet</option>
      <option value="called">Has Calls</option>
      <option value="scored">Score > 0.4</option>
      <option value="high">Score > 0.5</option>
    </select>
    <div style="flex:1"></div>
    <a href="/cold-inbound" class="cid-refresh-btn">↻ Refresh</a>
  </div>

  <div class="cid-table-wrap">
    <table class="cid-table" id="cid-table">
      <thead>
        <tr>
          <th>Contractor</th>
          <th>Phone</th>
          <th>Email</th>
          <th>Metro</th>
          <th>Dispatch</th>
          <th>Score</th>
          <th>Assessment</th>
          <th>Fields</th>
          <th>Calls</th>
          <th style="min-width:110px">Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

  <div class="cid-foot">
    <span>
      <a href="/command">Command Deck</a>
      <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
      <a href="/command#/dispatch">Dispatch Console</a>
      <span style="padding:0 8px;color:var(--empire-shadow)">·</span>
      <a href="/api/v1/cold-inbound/assessment-progress" style="color:var(--strike-cyan)">API → JSON</a>
    </span>
    <span>Empire AI · Assessment Progress Tracker</span>
  </div>

</div>

<script>
function filterTable(val) {{
  var rows = document.querySelectorAll('#cid-table tbody tr');
  rows.forEach(function(row) {{
    if (val === 'all') {{
      row.style.display = '';
      return;
    }}
    var scoreText = row.querySelector('.score-cell');
    var statusDot = row.querySelector('.cid-status-dot');
    var callDots = row.querySelectorAll('.cid-call-dot');
    var show = false;
    if (val === 'pending' && statusDot && statusDot.classList.contains('amber')) {{
      show = true;
    }}
    if (val === 'in_progress' && statusDot && statusDot.classList.contains('green')) {{
      // Check if it's the smaller solid green dot (in_progress) not the glowing one (completed)
      var statusCell = statusDot.closest('span');
      if (statusCell && !statusCell.textContent.includes('Complete')) {{
        show = true;
      }}
    }}
    if (val === 'no_worksheet' && statusDot && statusDot.classList.contains('gray')) {{
      show = true;
    }}
    if (val === 'called' && callDots.length > 0) {{
      for (var i = 0; i < callDots.length; i++) {{
        if (callDots[i].classList.contains('made')) {{
          show = true;
          break;
        }}
      }}
    }}
    if (val === 'scored' && scoreText) {{
      var match = scoreText.textContent.trim().match(/[\d.]+/);
      if (match && parseFloat(match[0]) > 0.4) show = true;
    }}
    if (val === 'high' && scoreText) {{
      var match = scoreText.textContent.trim().match(/[\d.]+/);
      if (match && parseFloat(match[0]) > 0.5) show = true;
    }}
    row.style.display = show ? '' : 'none';
  }});
}}

// Keyboard shortcut: R to refresh
document.addEventListener('keydown', function(e) {{
  if (e.key === 'r' && !e.ctrlKey && !e.metaKey && !e.target.closest('input,textarea,select')) {{
    window.location.href = '/cold-inbound';
  }}
}});
</script>

</body>
</html>"""
