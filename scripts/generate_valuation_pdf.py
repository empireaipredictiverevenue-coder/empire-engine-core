#!/usr/bin/env python3
"""Generate a professional PDF from EMPIRE_VALUATION.md for investor distribution.

Uses markdown → HTML → WeasyPrint to produce a styled, print-ready PDF.

Usage:
    python3 scripts/generate_valuation_pdf.py
    python3 scripts/generate_valuation_pdf.py --output /tmp/empire_valuation.pdf
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from markdown import Markdown
from weasyprint import HTML

MD_PATH = REPO / "EMPIRE_VALUATION.md"
OUTPUT_PATH = REPO / "EMPIRE_VALUATION.pdf"

# ── Professional CSS for investor-grade PDF ─────────────────────────────────

CSS = """
@page {
    size: A4;
    margin: 2.2cm 2cm 2.2cm 2cm;
    @bottom-center {
        content: "Empire AI v49 — Confidential";
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 8pt;
        color: #999;
    }
    @top-right {
        content: "Page " counter(page) " of " counter(pages);
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 8pt;
        color: #999;
    }
}

@page :first {
    @top-right {
        content: none;
    }
    @bottom-center {
        content: "Empire AI v49 — Confidential";
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 8pt;
        color: #999;
    }
}

body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.6;
    color: #1a1a2e;
    max-width: 100%;
}

/* ── Cover / Title ── */
h1 {
    font-size: 28pt;
    font-weight: 800;
    color: #0f0f23;
    border-bottom: 3px solid #2563eb;
    padding-bottom: 12pt;
    margin-top: 0;
    margin-bottom: 6pt;
    letter-spacing: -0.5pt;
}

h1 + blockquote {
    margin-top: 8pt;
}

blockquote {
    border-left: 4px solid #2563eb;
    padding: 8pt 14pt;
    margin: 10pt 0 16pt 0;
    background: #f0f4ff;
    color: #374151;
    font-size: 9.5pt;
    border-radius: 0 4px 4px 0;
}

blockquote p {
    margin: 2pt 0;
}

/* ── Section Headers ── */
h2 {
    font-size: 16pt;
    font-weight: 700;
    color: #2563eb;
    border-bottom: 1.5px solid #d1d5db;
    padding-bottom: 6pt;
    margin-top: 28pt;
    margin-bottom: 10pt;
    page-break-after: avoid;
}

h3 {
    font-size: 12pt;
    font-weight: 600;
    color: #1e3a5f;
    margin-top: 18pt;
    margin-bottom: 8pt;
}

/* ── Tables ── */
table {
    width: 100%;
    border-collapse: collapse;
    margin: 12pt 0 16pt 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}

thead {
    background: #2563eb;
    color: white;
}

th {
    padding: 7pt 10pt;
    text-align: left;
    font-weight: 600;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.3pt;
}

td {
    padding: 6pt 10pt;
    border-bottom: 1px solid #e5e7eb;
}

tr:nth-child(even) td {
    background: #f9fafb;
}

tr:last-child td {
    border-bottom: 2px solid #2563eb;
}

/* ── Code / Pipeline ── */
code {
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    font-size: 9pt;
    background: #f3f4f6;
    padding: 2pt 5pt;
    border-radius: 3px;
    color: #1e3a5f;
}

pre {
    background: #1a1a2e;
    color: #e2e8f0;
    padding: 12pt 14pt;
    border-radius: 6px;
    font-size: 8.5pt;
    line-height: 1.5;
    overflow-x: auto;
    page-break-inside: avoid;
}

pre code {
    background: none;
    color: inherit;
    padding: 0;
    font-size: 8.5pt;
}

/* ── Horizontal Rule ── */
hr {
    border: none;
    border-top: 1px solid #d1d5db;
    margin: 20pt 0;
}

/* ── Strong / Emphasis ── */
strong {
    font-weight: 700;
    color: #0f0f23;
}

/* ── Lists ── */
ul, ol {
    padding-left: 20pt;
    margin: 8pt 0;
}

li {
    margin: 3pt 0;
}

/* ── Cover Page Extra Styling ── */
body::before {
    display: block;
    content: "";
    height: 20pt;
}

/* ── Links (print-safe) ── */
a {
    color: #2563eb;
    text-decoration: none;
}

/* ── Last-section spacing ── */
p:last-child {
    margin-bottom: 0;
}
"""


def build_html(md_text: str) -> str:
    """Convert Markdown to a full HTML document with styling."""
    md = Markdown(extensions=["extra", "tables", "fenced_code", "codehilite", "toc"])
    body_html = md.convert(md_text)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Empire AI v49 — System Valuation</title>
    <style>{CSS}</style>
</head>
<body>
{body_html}
</body>
</html>"""
    return html


def main():
    import argparse
    p = argparse.ArgumentParser(description="Generate Empire AI valuation PDF")
    p.add_argument("--output", default=str(OUTPUT_PATH),
                   help=f"Output PDF path (default: {OUTPUT_PATH})")
    args = p.parse_args()

    if not MD_PATH.exists():
        print(f"ERROR: {MD_PATH} not found", file=sys.stderr)
        sys.exit(1)

    md_text = MD_PATH.read_text()

    print(f"[pdf] Converting {MD_PATH} ({len(md_text)} chars) → HTML")
    html = build_html(md_text)

    output = Path(args.output)
    print(f"[pdf] Rendering → {output}")
    HTML(string=html).write_pdf(str(output))

    size_kb = output.stat().st_size / 1024
    print(f"[pdf] Done — {output} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
