#!/usr/bin/env python3
"""Generate PDF payment status report and email to operator."""

import os
import base64
import logging
from datetime import datetime, timezone
from io import BytesIO

from dotenv import load_dotenv
from supabase import create_client
import httpx

# ReportLab
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.lib.enums import TA_CENTER

log = logging.getLogger("send_payment_report")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

load_dotenv("/root/.env")

TO_EMAIL = "philliplivesley@empire-ai.co.uk"
FROM_EMAIL = "noreply@empire-ai.co.uk"
FROM_NAME = "Empire AI Operations"


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return create_client(url, key)


def fetch_data():
    sb = _sb()
    r = sb.table("fee_events").select("*").limit(50).execute()
    fee_events = r.data or []

    # Resolve contractor names
    contractor_ids = set()
    for fe in fee_events:
        cid = fe.get("contractor_id")
        if cid:
            contractor_ids.add(cid)

    contractors = {}
    for cid in contractor_ids:
        cr = sb.table("contractors").select("id, name, email, phone").eq("id", cid).limit(1).execute()
        if cr.data:
            contractors[cid] = cr.data[0]

    rows = []
    for fe in fee_events:
        c = contractors.get(fe.get("contractor_id", ""), {})
        rows.append({
            "id": fe["id"],
            "status": fe["status"],
            "fee_amount": fe.get("fee_amount", 0),
            "claim_amount": fe.get("claim_amount", 0),
            "settled_at": str(fe.get("settled_at", ""))[:19] if fe.get("settled_at") else "",
            "contractor": c.get("name", "Unlinked"),
            "phone": c.get("phone", ""),
            "email": c.get("email", ""),
        })

    return rows


def build_pdf(rows):
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=20, textColor=colors.HexColor("#1a1a2e"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle", parent=styles["Normal"],
        fontSize=9, textColor=colors.HexColor("#666"),
        spaceAfter=20,
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"],
        fontSize=13, textColor=colors.HexColor("#1a1a2e"),
        spaceBefore=12, spaceAfter=6,
    )

    elements = []

    # ── Header ─────────────────────────────────────────────────────
    elements.append(Paragraph("Empire AI — Fee Collection Report", title_style))
    generated = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    elements.append(Paragraph(f"Generated: {generated}", subtitle_style))

    # ── Summary stats ─────────────────────────────────────────────
    pending = [r for r in rows if r["status"] == "pending"]
    paid = [r for r in rows if r["status"] in ("paid", "settled")]
    pending_total = sum(r["fee_amount"] for r in pending)
    paid_total = sum(r["fee_amount"] for r in paid)
    total_fees = pending_total + paid_total
    total_claims = sum(r["claim_amount"] for r in rows)

    summary_data = [
        ["Metric", "Value"],
        ["Total Fee Events", str(len(rows))],
        ["Pending Collection", str(len(pending))],
        ["Paid / Settled", str(len(paid))],
        ["Pending Fees (USD)", f"${pending_total:,.2f}"],
        ["Collected Fees (USD)", f"${paid_total:,.2f}"],
        ["Total Fees (USD)", f"${total_fees:,.2f}"],
        ["Total Claim Volume", f"${total_claims:,.2f}"],
        ["Fee Rate", "3.0%"],
    ]

    st = Table(summary_data, colWidths=[2.4 * inch, 2.4 * inch])
    st.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8fa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(Paragraph("Summary", section_style))
    elements.append(st)
    elements.append(Spacer(1, 16))

    # ── By Contractor ─────────────────────────────────────────────
    elements.append(Paragraph("By Contractor", section_style))

    contractor_groups = {}
    for r in rows:
        name = r["contractor"]
        if name not in contractor_groups:
            contractor_groups[name] = {"name": name, "phone": r["phone"], "email": r["email"],
                                        "pending": 0, "paid": 0, "pending_count": 0, "paid_count": 0}
        g = contractor_groups[name]
        if r["status"] == "pending":
            g["pending"] += r["fee_amount"]
            g["pending_count"] += 1
        else:
            g["paid"] += r["fee_amount"]
            g["paid_count"] += 1

    c_data = [["Contractor", "Phone", "Pending", "Collected", "Total"]]
    for g in sorted(contractor_groups.values(), key=lambda x: x["pending"] + x["paid"], reverse=True):
        total = g["pending"] + g["paid"]
        p_cnt = f" ({g['pending_count']})" if g["pending_count"] else ""
        c_data.append([
            g["name"],
            g["phone"],
            f"${g['pending']:,.2f}{p_cnt}" if g["pending"] else "—",
            f"${g['paid']:,.2f}" if g["paid"] else "—",
            f"${total:,.2f}",
        ])

    ct = Table(c_data, colWidths=[1.6 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch, 1.0 * inch])
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8fa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(ct)
    elements.append(Spacer(1, 16))

    # ── All Fee Events Table ─────────────────────────────────────
    elements.append(Paragraph("All Fee Events", section_style))

    header = ["Fee ID", "Contractor", "Claim", "Fee", "Status", "Settled"]
    table_data = [header]
    for r in rows:
        fid = r["id"][:12]
        status = r["status"].upper()
        # Color coding
        table_data.append([
            fid,
            r["contractor"][:24],
            f"${r['claim_amount']:,.0f}",
            f"${r['fee_amount']:,.2f}",
            status,
            r["settled_at"][:10] if r["settled_at"] else "—",
        ])

    col_widths = [0.8 * inch, 1.8 * inch, 0.9 * inch, 0.8 * inch, 0.7 * inch, 0.9 * inch]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ALIGN", (2, 0), (4, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f8fa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]
    # Color-code status rows
    for i, r in enumerate(rows, start=1):
        if r["status"] == "paid":
            style_cmds.append(("BACKGROUND", (4, i), (4, i), colors.HexColor("#d4edda")))
            style_cmds.append(("TEXTCOLOR", (4, i), (4, i), colors.HexColor("#155724")))
        elif r["status"] == "pending":
            style_cmds.append(("BACKGROUND", (4, i), (4, i), colors.HexColor("#fff3cd")))
            style_cmds.append(("TEXTCOLOR", (4, i), (4, i), colors.HexColor("#856404")))
        elif r["status"] == "settled":
            style_cmds.append(("BACKGROUND", (4, i), (4, i), colors.HexColor("#cce5ff")))
            style_cmds.append(("TEXTCOLOR", (4, i), (4, i), colors.HexColor("#004085")))

    t.setStyle(TableStyle(style_cmds))
    elements.append(t)

    # ── Footer ─────────────────────────────────────────────────────
    elements.append(Spacer(1, 20))
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"],
        fontSize=7, textColor=colors.HexColor("#999"),
        alignment=TA_CENTER,
    )
    elements.append(Paragraph(
        "Empire AI · empire-ai.co.uk · Vault: egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM",
        footer_style,
    ))

    doc.build(elements)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


def send_email(pdf_bytes, rows):
    resend_key = os.getenv("RESEND_API_KEY", "")
    if not resend_key:
        log.error("RESEND_API_KEY not set")
        return False

    pending = [r for r in rows if r["status"] == "pending"]
    paid = [r for r in rows if r["status"] in ("paid", "settled")]
    pending_total = sum(r["fee_amount"] for r in pending)
    paid_total = sum(r["fee_amount"] for r in paid)

    subject = f"Empire AI — Payment Status Report: ${pending_total:,.0f} Pending / ${paid_total:,.0f} Collected"
    html_body = f"""
    <div style="font-family:-apple-system,system-ui,sans-serif;max-width:600px;margin:0 auto;padding:32px;">
      <h2 style="color:#1a1a2e;margin:0 0 4px;">Fee Collection Report</h2>
      <p style="color:#666;font-size:13px;margin:0 0 24px;">
        Generated {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M')} UTC
      </p>

      <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
        <tr><td style="padding:8px 12px;background:#1a1a2e;color:#fff;font-weight:600;border-radius:4px 4px 0 0;" colspan="2">Summary</td></tr>
        <tr><td style="padding:6px 12px;border-bottom:1px solid #eee;">Total Fee Events</td><td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;font-weight:600;">{len(rows)}</td></tr>
        <tr><td style="padding:6px 12px;border-bottom:1px solid #eee;">Pending Collection</td><td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;color:#856404;font-weight:600;">{len(pending)} (${pending_total:,.2f})</td></tr>
        <tr><td style="padding:6px 12px;border-bottom:1px solid #eee;">Paid / Settled</td><td style="padding:6px 12px;border-bottom:1px solid #eee;text-align:right;color:#155724;font-weight:600;">{len(paid)} (${paid_total:,.2f})</td></tr>
        <tr><td style="padding:6px 12px;border-radius:0 0 4px 4px;">Total Fee Revenue</td><td style="padding:6px 12px;border-radius:0 0 4px 4px;text-align:right;font-weight:700;">${pending_total + paid_total:,.2f}</td></tr>
      </table>

      <p style="color:#666;font-size:12px;">Full details are attached as a PDF.</p>
    </div>
    """

    pdf_b64 = base64.b64encode(pdf_bytes).decode()

    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {resend_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"{FROM_NAME} <{FROM_EMAIL}>",
                "to": [TO_EMAIL],
                "subject": subject,
                "html": html_body,
                "attachments": [
                    {
                        "filename": f"empire_fee_report_{datetime.now().strftime('%Y%m%d')}.pdf",
                        "content": pdf_b64,
                    }
                ],
            },
            timeout=30,
        )
        if r.status_code < 300:
            data = r.json()
            log.info(f"Email sent: {data.get('id', '?')}")
            return True
        else:
            log.error(f"Resend error {r.status_code}: {r.text[:300]}")
            return False
    except Exception as e:
        log.error(f"Failed to send email: {e}")
        return False


def main():
    log.info("Fetching fee event data...")
    rows = fetch_data()
    log.info(f"Found {len(rows)} fee events")

    log.info("Generating PDF...")
    pdf_bytes = build_pdf(rows)
    log.info(f"PDF generated: {len(pdf_bytes):,} bytes")

    log.info(f"Sending email to {TO_EMAIL}...")
    ok = send_email(pdf_bytes, rows)
    if ok:
        log.info("✅ Email sent successfully!")
    else:
        log.error("❌ Email failed")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
