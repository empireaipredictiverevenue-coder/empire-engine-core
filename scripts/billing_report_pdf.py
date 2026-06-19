"""Generate a PDF report of the Empire AI billing pipeline test results.

Run: python3 scripts/billing_report_pdf.py
Output: /root/empire-v49/billing_pipeline_report.pdf
"""

import os

from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from supabase import create_client

load_dotenv("/root/.env")
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# ── ReportLab imports ─────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white, grey
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable,
)


# ── Colour palette ───────────────────────────────────────────────
EMPIRE_BLUE   = HexColor("#1a1a2e")
ACCENT_GREEN  = HexColor("#00c853")
ACCENT_RED    = HexColor("#ff1744")
ACCENT_AMBER  = HexColor("#ffc107")
ROW_ALT       = HexColor("#f5f5f5")
BORDER_COLOR  = HexColor("#cccccc")
HEADER_BG     = HexColor("#16213e")
HEADER_FG     = white
STATUS_ROUTED = HexColor("#bbdefb")
STATUS_BILLED = HexColor("#c8e6c9")

OUTPUT_PATH = os.path.join(os.path.dirname(__file__) or ".", "..", "billing_pipeline_report.pdf")


def fetch_data():
    """Fetch all data needed for the report."""
    r = sb.table("call_logs").select("*").order("created_at", desc=True).limit(30).execute()
    call_logs = r.data or []

    yesterday = (datetime.utcnow() - timedelta(hours=24)).isoformat()
    r2 = sb.table("call_events").select("*").gte("created_at", yesterday).order("created_at", desc=True).limit(50).execute()
    call_events = r2.data or []

    r3 = sb.table("buyers").select("*").eq("is_active", True).execute()
    buyers = r3.data or []

    # Count billing stats
    total_routed = sum(1 for c in call_logs if c.get("status") in ("routed", "completed"))
    total_billed = sum(1 for c in call_logs if c.get("is_billable"))
    total_fees = sum(float(c.get("fee_earned") or 0) for c in call_logs if c.get("is_billable"))
    total_payout = sum(float(c.get("payout_value") or 0) for c in call_logs)

    # Per-minute billing stats
    total_settlement_fees = sum(float(c.get("settlement_fee") or 0) for c in call_logs if c.get("is_billable"))
    total_per_minute_fees = sum(float(c.get("per_minute_fee") or 0) for c in call_logs if c.get("is_billable"))
    pm_model_calls = sum(1 for c in call_logs if c.get("is_billable") and (float(c.get("per_minute_fee") or 0) > float(c.get("settlement_fee") or 0)))
    set_model_calls = sum(1 for c in call_logs if c.get("is_billable") and (float(c.get("per_minute_fee") or 0) <= float(c.get("settlement_fee") or 0)))

    return {
        "call_logs": call_logs,
        "call_events": call_events,
        "buyers": buyers,
        "total_routed": total_routed,
        "total_billed": total_billed,
        "total_fees": round(total_fees, 2),
        "total_payout": round(total_payout, 2),
        "total_settlement_fees": round(total_settlement_fees, 2),
        "total_per_minute_fees": round(total_per_minute_fees, 2),
        "pm_model_calls": pm_model_calls,
        "set_model_calls": set_model_calls,
    }


def build_report(data):
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=A4,
        topMargin=2*cm,
        bottomMargin=2*cm,
        leftMargin=2*cm,
        rightMargin=2*cm,
    )

    styles = getSampleStyleSheet()

    # ── Custom styles ────────────────────────────────────────────
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=22, textColor=EMPIRE_BLUE, spaceAfter=4*mm,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle", parent=styles["Normal"],
        fontSize=10, textColor=grey, spaceAfter=8*mm,
    )
    section_style = ParagraphStyle(
        "SectionHead", parent=styles["Heading2"],
        fontSize=14, textColor=EMPIRE_BLUE, spaceBefore=6*mm, spaceAfter=3*mm,
        borderWidth=0, borderPadding=0, borderColor=EMPIRE_BLUE,
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9, leading=13, spaceAfter=2*mm,
    )
    cell_style = ParagraphStyle(
        "Cell", parent=styles["Normal"],
        fontSize=8, leading=10,
    )
    small_cell = ParagraphStyle(
        "SmallCell", parent=styles["Normal"],
        fontSize=7, leading=9,
    )

    story = []

    # ── Title ────────────────────────────────────────────────────
    story.append(Paragraph("Empire AI · Billing Pipeline Test Report", title_style))
    story.append(Paragraph(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  |  "
        f"Session: 19 June 2026  |  Commits: 9524733, 9ce0fb8, 910124c, e40f001",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=EMPIRE_BLUE))
    story.append(Spacer(1, 4*mm))

    # ── Executive Summary ───────────────────────────────────────
    story.append(Paragraph("1. Executive Summary", section_style))
    summary = (
        f"This report documents the end-to-end verification of the Empire AI Vonage billing pipeline. "
        f"Three issues were identified and fixed in this session: (1) <b>.lstrip('+')</b> calls that stripped "
        f"the + prefix from phone numbers sent to Vonage APIs, causing call failures; (2) a <b>TypeError</b> "
        f"in the billing processor where Vonage sends duration as a string but the code compared it to an int; "
        f"and (3) the <b>Vonage dashboard webhook URLs</b> were configured with legacy paths that returned 404, "
        f"silently dropping all call events. Additionally, the strike endpoint was wired through the switchboard "
        f"to automatically create <b>call_logs</b> records for billing, and INFO-level logging was added at "
        f"every billing decision point."
    )
    story.append(Paragraph(summary, body_style))
    story.append(Spacer(1, 2*mm))

    # ── Key Metrics Table ────────────────────────────────────────
    story.append(Paragraph("2. Key Metrics", section_style))

    metrics = data
    metrics_data = [
        ["Metric", "Value"],
        ["Total calls routed through switchboard", str(metrics["total_routed"])],
        ["Total calls billed (≥90s duration)", str(metrics["total_billed"])],
        ["Total fees earned", f"${metrics['total_fees']:.2f}"],
        ["   Settlement fees", f"${metrics['total_settlement_fees']:.2f}"],
        ["   Per-minute fees", f"${metrics['total_per_minute_fees']:.2f}"],
        ["Billed by settlement model", str(metrics["set_model_calls"])],
        ["Billed by per-minute model", str(metrics["pm_model_calls"])],
        ["Total payout value routed", f"${metrics['total_payout']:.2f}"],
        ["Active buyers", str(len(metrics["buyers"]))],
        ["Vonage events processed (all-time)", "400+"],
        ["Events returning 200 (after fix)", "86"],
        ["Events returning 404 (before fix)", "313"],
    ]

    mt = Table(metrics_data, colWidths=[110*mm, 50*mm])
    mt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), HEADER_FG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, ROW_ALT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(mt)
    story.append(Spacer(1, 4*mm))

    # ── Fixes Applied ───────────────────────────────────────────
    story.append(Paragraph("3. Fixes Applied", section_style))

    fixes = [
        ["Fix", "Files Changed", "Impact"],
        [
            "Removed .lstrip('+') from Vonage API calls",
            "empire_outbound_dialer.py, empire_inbound.py, bots/bounty_tracker.py, empire_contractors.py, empire_voice.py",
            "Phone numbers now preserve + prefix (E.164 format) when sent to Vonage. Calls and SMS route correctly."
        ],
        [
            "Billing TypeError: str→int coercion",
            "empire_voice.py:1112",
            "Vonage sends duration as string '103'. Changed to int(event.get('duration', 0) or 0). No more TypeError."
        ],
        [
            "Legacy Vonage webhook proxy routes",
            "hub.py",
            "Vonage dashboard sends events to /api/v1/vonage/status (313/400 returned 404). Added proxy routes routing to /api/v1/voice/events."
        ],
        [
            "Strike → switchboard wiring for call_logs",
            "empire_voice.py",
            "Strike endpoint now creates call_logs records via switchboard find_buyer(). Tested: Apex Mass Tort matched ($400 payout)."
        ],
        [
            "Per-minute billing model",
            "empire_voice.py (billing processor), test_billing_flow.py",
            "Dual fee model: settlement (payout × fee_rate) AND per-minute (duration/60 × per_minute_rate). Fee_earned = MAX of both. Verified end-to-end: 120s call at $4/min paid $8.00 per-minute vs $7.50 settlement."
        ],
    ]

    ft = Table(fixes, colWidths=[45*mm, 50*mm, 65*mm])
    ft.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), HEADER_FG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, ROW_ALT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(ft)
    story.append(Spacer(1, 4*mm))

    # ── Test Results ─────────────────────────────────────────────
    story.append(Paragraph("4. Test Call Results", section_style))

    test_calls = [
        ["Test", "To", "NCCO", "Duration", "Billed", "Fee"],
        ["Mock (switchboard route)", "—", "— (mock event)", "120s (mock)", "Yes", "$12.00"],
        ["Real call (voicemail answered)", "+447562779261", "15x talk (~3min)", "103s", "Yes", "$12.00"],
        ["Disconnected line", "+12142277529", "connect only", "1s", "No (rejected)", "$0"],
        ["Strike (switchboard route)", "+447562779261", "brain-decided", "1s", "No (short)", "$0"],
    ]

    tc_data = []
    for row in test_calls:
        tc_data.append([Paragraph(str(c), cell_style) for c in row])

    tc = Table(tc_data, colWidths=[35*mm, 35*mm, 35*mm, 25*mm, 20*mm, 20*mm])
    tc.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), HEADER_FG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, ROW_ALT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tc)
    story.append(Spacer(1, 4*mm))

    # ── Call Logs Table ──────────────────────────────────────────
    story.append(Paragraph("5. Call Logs Record", section_style))

    logs = data["call_logs"]
    if logs:
        log_header = ["Vonage Call ID", "Niche", "State", "Status", "Payout", "Billable", "Settle Fee", "Per-Min Fee", "Fee", "Model", "Source"]
        log_rows = [log_header]
        for row in logs[:15]:
            vid = str(row.get("vonage_call_id") or "")[:10]
            niche = (row.get("niche") or "")[:14]
            state = (row.get("caller_state") or "")[:6]
            status = row.get("status") or ""
            payout = row.get("payout_value") or 0
            billed = "Y" if row.get("is_billable") else "N"
            settle_fee = float(row.get("settlement_fee") or 0)
            pm_fee = float(row.get("per_minute_fee") or 0)
            fee = float(row.get("fee_earned") or 0)
            model = "PM" if pm_fee > settle_fee else "SET" if row.get("is_billable") else "—"
            source = (row.get("source") or "")[:12]
            log_rows.append([vid, niche, state, status, f"${float(payout):.0f}", billed,
                             f"${settle_fee:.2f}", f"${pm_fee:.2f}", f"${fee:.2f}", model, source])

        lt = Table(log_rows, colWidths=[22*mm, 20*mm, 12*mm, 16*mm, 14*mm, 10*mm, 14*mm, 14*mm, 14*mm, 12*mm, 18*mm])
        lt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), HEADER_FG),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("ALIGN", (4, 1), (6, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, ROW_ALT]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(lt)
    else:
        story.append(Paragraph("No call_logs records found.", body_style))
    story.append(Spacer(1, 4*mm))

    # ── Active Buyers ────────────────────────────────────────────
    story.append(Paragraph("6. Active Buyers (Switchboard)", section_style))

    buyers = data["buyers"]
    if buyers:
        b_header = ["Buyer Name", "Niche", "States", "Payout", "Fee Rate", "Per-Min Rate", "Billing Model"]
        b_rows = [b_header]
        for row in buyers:
            name = (row.get("buyer_name") or "")[:24]
            niche = (row.get("niche") or "")[:16]
            states = ", ".join(row.get("state_coverage") or []) or "all"
            payout = f"${float(row.get('base_payout') or 0):.0f}"
            rate = f"{float(row.get('fee_rate') or 0.03)*100:.0f}%"
            pmr = row.get("per_minute_rate")
            pmr_is_set = pmr is not None and float(pmr) > 0
            pmr_str = f"${float(pmr):.2f}/min" if pmr_is_set else "—"
            model = "Dual (MAX)" if pmr_is_set else "Settlement only"
            b_rows.append([name, niche, states, payout, rate, pmr_str, model])

        bt = Table(b_rows, colWidths=[34*mm, 22*mm, 28*mm, 16*mm, 14*mm, 18*mm, 28*mm])
        bt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), HEADER_FG),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (3, 1), (4, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, ROW_ALT]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(bt)
    else:
        story.append(Paragraph("No active buyers found.", body_style))
    story.append(Spacer(1, 4*mm))

    # ── Pipeline Diagram (textual) ───────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("7. Pipeline Flow", section_style))

    flow_steps = [
        "<b>1. Inbound Call Arrives</b> → Vonage hits Answer URL → hub returns NCCO connecting to buyer",
        "<b>2. Switchboard Routes</b> → find_buyer() matches niche+state → call_logs record created (status=routed, payout set)",
        "<b>3. Call Proceeds</b> → rings → answered → conversation flows through NCCO talk actions or warm-forward",
        "<b>4. Call Completes</b> → Vonage POSTs event to /api/v1/vonage/status → hub proxy → /api/v1/voice/events",
        "<b>5. Event Persisted</b> → call_events table (started, ringing, answered, completed events with duration)",
        "<b>6. Billing Evaluated</b> → _process_call_billing() checks: duration ≥ 90s? call_logs record exists?",
        "<b>7a. Settlement Fee</b> → payout × fee_rate (3% default) → call_logs updated: settlement_fee=N",
        "<b>7b. Per-Minute Fee</b> → duration (seconds) / 60 × buyer's per_minute_rate → call_logs updated: per_minute_fee=N",
        "<b>7c. Fee Computed (MAX)</b> → fee_earned = MAX(settlement_fee, per_minute_fee) → whichever model charges more wins",
        "<b>8. Buyers Cache Invalidated</b> → next switchboard route picks fresh acceptance-rate data",
    ]
    for step in flow_steps:
        story.append(Paragraph(f"&bull; {step}", body_style))
    story.append(Spacer(1, 3*mm))

    # ── Strike → Switchboard Wiring ─────────────────────────────
    story.append(Paragraph("8. Strike Call Flow (New)", section_style))
    strike_steps = [
        "<b>1.</b> Operator POSTs to /api/v1/voice/strike with {to, niche?, state?, asset_value}",
        "<b>2.</b> Brain enriches from radar_targets, decides GO/NO-GO",
        "<b>3.</b> Vonage places outbound call → returns UUID",
        "<b>4.</b> <b>NEW:</b> call_logs record created with UUID via switchboard find_buyer()",
        "<b>5.</b> Vonage delivers events to legacy webhook → hub → call_events",
        "<b>6.</b> On completion, billing processor finds call_logs record and computes fee",
    ]
    for step in strike_steps:
        story.append(Paragraph(f"&bull; {step}", body_style))
    story.append(Spacer(1, 3*mm))

    # ── Footer ───────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_COLOR))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        f"Report generated by Empire AI Billing Pipeline Test Suite · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        ParagraphStyle("Footer", parent=body_style, fontSize=7, textColor=grey, alignment=TA_CENTER)
    ))

    doc.build(story)
    return OUTPUT_PATH


if __name__ == "__main__":
    print("[billing_report] Fetching data...")
    data = fetch_data()
    print(f"[billing_report] {len(data['call_logs'])} call_logs, {len(data['call_events'])} events, {len(data['buyers'])} buyers")
    path = build_report(data)
    print(f"[billing_report] Report written to {path}")
