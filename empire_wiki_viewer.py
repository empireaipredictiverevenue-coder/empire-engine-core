"""
Empire AI - /wiki route. Visual index of the project wiki.

GET /wiki          - lists all .md files in /root/empire-v49/wiki/ with
                     their first heading as a one-line summary.
GET /wiki/<name>   - renders a single .md file as basic HTML
                     (preserves code blocks, escapes everything else,
                     no markdown parser required).
"""
import os
import re
import html
from pathlib import Path
from fastapi.responses import HTMLResponse

WIKI_DIR = Path("/root/empire-v49/wiki")


def _list_pages() -> list:
    """Return [(name, first_heading, mtime)] for every .md in WIKI_DIR,
    newest first. raw/ is excluded.
    """
    pages = []
    if not WIKI_DIR.is_dir():
        return pages
    for p in sorted(WIKI_DIR.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        # Extract the first H1 (or first H2 if no H1)
        h1 = re.search(r"^# (.+)$", text, re.MULTILINE)
        if h1:
            title = h1.group(1).strip()
        else:
            h2 = re.search(r"^## (.+)$", text, re.MULTILINE)
            title = h2.group(1).strip() if h2 else p.stem
        # strip the trailing " - what is it" / " - the metric" style suffix
        # by keeping the title as-is
        mtime = p.stat().st_mtime
        pages.append((p.stem, title, mtime))
    pages.sort(key=lambda x: -x[2])
    return pages


def _read_page(name: str) -> str | None:
    """Read a wiki page by name (no path traversal)."""
    if "/" in name or ".." in name or name.startswith("."):
        return None
    path = WIKI_DIR / f"{name}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def _md_to_html(md: str) -> str:
    """Minimal markdown -> HTML for the wiki viewer.

    Handles:
      - H1 / H2 / H3
      - fenced code blocks (```)
      - inline code (`)
      - bold (**...**)
      - links [text](url) -- escapes but renders
      - lists (- bullet, 1. ordered)
      - paragraphs

    Does NOT handle nested lists, tables, or images. That's fine
    for the wiki style.
    """
    out = []
    in_code = False
    code_buf = []
    code_lang = ""
    in_list = False
    list_kind = None  # 'ul' or 'ol'

    def flush_list():
        nonlocal in_list, list_kind
        if in_list:
            out.append(f"</{list_kind}>")
            in_list = False
            list_kind = None

    def flush_paragraph(buf):
        if not buf:
            return
        text = " ".join(buf).strip()
        if not text:
            return
        # inline formatting
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        # links: [text](url) -- escape the text and href
        def link_repl(m):
            t = html.escape(m.group(1))
            u = html.escape(m.group(2))
            return f'<a href="{u}">{t}</a>'
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, text)
        out.append(f"<p>{text}</p>")

    para_buf = []
    for line in md.split("\n"):
        if line.strip().startswith("```"):
            if in_code:
                out.append(f'<pre><code class="language-{code_lang}">{html.escape(chr(10).join(code_buf))}</code></pre>')
                code_buf = []
                code_lang = ""
                in_code = False
            else:
                flush_list()
                flush_paragraph(para_buf); para_buf = []
                in_code = True
                code_lang = line.strip().lstrip("`").strip() or "text"
            continue
        if in_code:
            code_buf.append(line)
            continue
        if line.startswith("# "):
            flush_list()
            flush_paragraph(para_buf); para_buf = []
            out.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            flush_list()
            flush_paragraph(para_buf); para_buf = []
            out.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("### "):
            flush_list()
            flush_paragraph(para_buf); para_buf = []
            out.append(f"<h3>{html.escape(line[4:].strip())}</h3>")
        elif line.startswith("- "):
            if not in_list or list_kind != "ul":
                flush_list()
                flush_paragraph(para_buf); para_buf = []
                out.append("<ul>")
                in_list = True
                list_kind = "ul"
            out.append(f"<li>{html.escape(line[2:].strip())}</li>")
        elif re.match(r"^\d+\. ", line):
            if not in_list or list_kind != "ol":
                flush_list()
                flush_paragraph(para_buf); para_buf = []
                out.append("<ol>")
                in_list = True
                list_kind = "ol"
            num_re = re.compile(r"^\d+\. ")
            li_text = num_re.sub("", line).strip()
            out.append(f"<li>{html.escape(li_text)}</li>")
        elif line.strip() == "":
            flush_list()
            flush_paragraph(para_buf); para_buf = []
        else:
            para_buf.append(line)
    flush_list()
    flush_paragraph(para_buf)
    return "\n".join(out)


def _shell(content: str, title: str = "Empire AI · Wiki") -> str:
    """Wrap content in a styled HTML page."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#0A1A2F">
<title>{html.escape(title)}</title>
<style>
  :root {{ --bg: #0A1A2F; --panel: #0F1E2F; --text: #E8EEF6;
          --muted: #94A3B8; --accent: #4FD1C5; --border: rgba(232,238,246,0.10); }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         line-height: 1.6; }}
  .wrap {{ max-width: 880px; margin: 0 auto; padding: 32px 20px 80px; }}
  .topbar {{ display: flex; justify-content: space-between; align-items: center;
            padding: 0 0 24px; border-bottom: 1px solid var(--border); margin-bottom: 24px; }}
  .brand {{ font-weight: 700; letter-spacing: 0.04em; font-size: 14px;
            color: var(--accent); text-decoration: none; }}
  .toplink {{ color: var(--muted); font-size: 12px; text-decoration: none; }}
  .toplink:hover {{ color: var(--accent); }}
  h1 {{ font-size: 32px; line-height: 1.15; font-weight: 800;
        margin: 24px 0 16px; color: #FFFFFF; }}
  h2 {{ font-size: 22px; line-height: 1.2; font-weight: 700;
        margin: 32px 0 12px; color: #FFFFFF; border-bottom: 1px solid var(--border);
        padding-bottom: 6px; }}
  h3 {{ font-size: 17px; line-height: 1.25; font-weight: 600;
        margin: 20px 0 8px; color: #FFFFFF; }}
  p  {{ margin: 0 0 12px; color: #B8C5D6; }}
  ul, ol {{ margin: 0 0 12px; padding-left: 24px; color: #B8C5D6; }}
  li {{ margin: 0 0 4px; }}
  a  {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  code {{ background: rgba(0,0,0,0.30); border-radius: 4px;
          padding: 1px 5px; font-size: 13px;
          font-family: ui-monospace, "SF Mono", Menlo, monospace;
          color: #E8EEF6; }}
  pre {{ background: rgba(0,0,0,0.30); border-radius: 8px;
         padding: 14px 18px; overflow-x: auto; margin: 0 0 12px; }}
  pre code {{ background: transparent; padding: 0; }}
  .page-list {{ list-style: none; padding: 0; margin: 0; }}
  .page-list li {{ background: var(--panel); border: 1px solid var(--border);
                  border-radius: 10px; padding: 18px 22px; margin: 0 0 12px; }}
  .page-list a {{ font-size: 17px; font-weight: 700; color: #FFFFFF; }}
  .page-list a:hover {{ color: var(--accent); text-decoration: none; }}
  .page-list .meta {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
  .page-list .desc {{ font-size: 14px; color: #B8C5D6; margin-top: 8px; }}
  .topbar .nav {{ display: flex; gap: 16px; font-size: 13px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <a class="brand" href="/wiki">EMPIRE <span style="color: #4FD1C5">AI</span> · Wiki</a>
    <div class="nav">
      <a class="toplink" href="/">splash</a>
      <a class="toplink" href="/contractors">/contractors</a>
      <a class="toplink" href="/demo">/demo</a>
      <a class="toplink" href="/command">/command</a>
    </div>
  </div>
{content}
</div>
</body>
</html>"""


def wiki_index() -> str:
    """GET /wiki -- the catalog page."""
    pages = _list_pages()
    if not pages:
        return _shell("<p>No wiki pages found at <code>/root/empire-v49/wiki/</code>.</p>")
    items = []
    for name, title, mtime in pages:
        # one-line summary: first non-heading, non-empty line after the title
        md = _read_page(name) or ""
        summary = ""
        for line in md.split("\n"):
            ls = line.strip()
            if not ls or ls.startswith("#") or ls.startswith("```") or ls.startswith("- "):
                continue
            summary = ls[:200]
            break
        import datetime
        try:
            when = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            when = "?"
        items.append(
            f'<li><a href="/wiki/{html.escape(name)}">{html.escape(title)}</a>'
            f'<div class="meta">{html.escape(name)}.md · updated {when}</div>'
            f'<div class="desc">{html.escape(summary)}</div></li>'
        )
    body = f"""
  <h1>Wiki</h1>
  <p>LLM-driven persistent markdown that compounds as the project
  evolves. {len(pages)} page{"s" if len(pages) != 1 else ""}. Pattern:
  karpathy's <a href="https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f">llm-wiki</a>
  gist (April 2026).</p>
  <p style="font-size: 13px; color: #94A3B8;">See <a href="/wiki/AGENTS">AGENTS.md</a> for the schema (operations, conventions, security note). The wiki's source is at <code>/root/empire-v49/wiki/</code> on the box.</p>
  <ul class="page-list">{"".join(items)}</ul>
"""
    return _shell(body)


def wiki_page(name: str) -> str:
    """GET /wiki/<name> -- render a single page."""
    md = _read_page(name)
    if md is None:
        return _shell(f"<h1>Not found</h1><p>No wiki page named <code>{html.escape(name)}</code>.</p><p><a href=\"/wiki\">back to index</a></p>")
    body = _md_to_html(md)
    nav = f'<p style="margin-top: 32px;"><a href="/wiki">← back to wiki index</a></p>'
    return _shell(body, title=f"Empire AI · Wiki · {name}")


def register_wiki_routes(app):
    app.add_api_route(
        "/wiki",
        lambda: HTMLResponse(wiki_index()),
        methods=["GET"],
    )
    app.add_api_route(
        "/wiki/{name}",
        lambda name: HTMLResponse(wiki_page(name)),
        methods=["GET"],
    )
    # /wiki/ with trailing slash -> redirect to /wiki
    from starlette.responses import RedirectResponse
    app.add_api_route(
        "/wiki/",
        lambda: RedirectResponse("/wiki", status_code=302),
        methods=["GET"],
    )
