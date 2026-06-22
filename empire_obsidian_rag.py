"""
Empire AI · Obsidian RAG
========================

Lightweight retrieval for the local Obsidian vault. Scans *.md files,
scores by keyword overlap, returns the top-K most relevant excerpts as
a context block the brain can prepend to its system prompt.

Why keyword matching and not embeddings?
  - The vault is small (8-20 notes, ~50KB). Embedding infra is overkill.
  - Keyword overlap is ~1ms per query, no model load, no API cost.
  - When the vault grows past ~100 notes or the user wants semantic
    search, swap _score_note() for a sentence-transformer call.

Safety:
  - Only reads *.md under OBSIDIAN_VAULT_PATH.
  - Strips frontmatter (between `---` fences) and wikilinks.
  - Skips lines containing `password|secret|token|api_key` keywords
    to avoid accidentally leaking credentials pasted into a note.
  - Caps total output at RAG_MAX_CONTEXT_CHARS (default 1500).
  - If the vault is missing/unreadable, returns "" — brain still works
    without context, just no fleet/notes awareness.
"""
import os
import re
import logging
from pathlib import Path
from typing import List, Tuple, Optional

log = logging.getLogger("empire.obsidian_rag")

OBSIDIAN_VAULT_PATH = os.environ.get(
    "OBSIDIAN_VAULT_PATH",
    "/root/empire-v49/notes",
)
RAG_MAX_CONTEXT_CHARS = int(os.environ.get("RAG_MAX_CONTEXT_CHARS", "1500"))
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", "3"))
RAG_MIN_SCORE = int(os.environ.get("RAG_MIN_SCORE", "2"))
RAG_MAX_CHARS_PER_NOTE = int(os.environ.get("RAG_MAX_CHARS_PER_NOTE", "600"))

# English stopwords + common vault-noise words. Keeps the matcher focused
# on actual signal (entity names, technical terms, action verbs).
STOPWORDS = frozenset("""
a an and are as at be been being but by did do does for from had has have
he her him his how i if in into is it its just me my of on or our she that
the their them then there these they this those to too us very was we were
what when where which who why will with would you your a's
""".split())

# Lines that look like secrets — skip the whole note if its first 500 chars
# contain these. Conservative: skips notes that *mention* these words,
# not just the lines that contain them. Reduces risk of pasting a key
# into a vault note by accident.
SECRET_HINT = re.compile(
    r"(?i)\b(api[_-]?key|secret|password|token|private[_-]?key)\b\s*[:=]\s*[\"']?[\w-]{6,}"
)

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")
_TAG_RE = re.compile(r"(?m)^#+\s+.*$")  # markdown heading line
_MULTI_NL = re.compile(r"\n{3,}")


def _tokenize(text: str) -> List[str]:
    """Lowercase, drop stopwords and short tokens. Returns term list."""
    if not text:
        return []
    tokens = re.findall(r"[a-z0-9][a-z0-9\-]{2,}", text.lower())
    return [t for t in tokens if t not in STOPWORDS]


def _strip_note(raw: str) -> str:
    """Remove frontmatter, headings, and wikilink brackets. Keep body text."""
    text = _FRONTMATTER_RE.sub("", raw, count=1)
    # Replace wikilinks with their readable text
    text = _WIKILINK_RE.sub(r"\1", text)
    # Drop markdown headings (we have filename for that)
    text = _TAG_RE.sub("", text)
    # Collapse excess whitespace
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


def _read_note(path: Path) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        log.debug(f"[rag] read {path.name} failed: {e}")
        return None


def _score_note(text: str, query_tokens: List[str]) -> int:
    """Count term overlap. Title words (lines starting with #) get +2 each."""
    if not query_tokens or not text:
        return 0
    text_lower = text.lower()
    score = 0
    for tok in query_tokens:
        # Count occurrences (cap at 3 to avoid one repeated term dominating)
        score += min(text_lower.count(tok), 3)
    return score


def _is_safe_note(raw: str) -> bool:
    """Conservative: skip notes whose head contains secret-shaped patterns."""
    return not SECRET_HINT.search(raw[:500])


def build_context(query: str, vault_path: Optional[str] = None,
                  top_k: int = RAG_TOP_K,
                  max_chars: int = RAG_MAX_CONTEXT_CHARS,
                  min_score: int = RAG_MIN_SCORE) -> str:
    """
    Return a context block (markdown) of the top-K vault notes relevant
    to *query*. Returns "" if nothing scores above min_score or vault
    is unreadable.
    """
    if not query or not query.strip():
        return ""

    vault = Path(vault_path or OBSIDIAN_VAULT_PATH)
    if not vault.exists():
        log.debug(f"[rag] vault not found: {vault}")
        return ""

    query_tokens = _tokenize(query)
    if not query_tokens:
        return ""

    # Scan all .md files (recursively), score, sort
    candidates: List[Tuple[int, Path, str]] = []
    try:
        for path in vault.rglob("*.md"):
            # Skip .obsidian config files
            if path.name.startswith(".") or ".obsidian" in path.parts:
                continue
            raw = _read_note(path)
            if not raw:
                continue
            if not _is_safe_note(raw):
                log.info(f"[rag] skipped (secret hint): {path.name}")
                continue
            clean = _strip_note(raw)
            if not clean:
                continue
            score = _score_note(clean, query_tokens)
            if score >= min_score:
                candidates.append((score, path, clean))
    except Exception as e:
        log.warning(f"[rag] vault scan failed: {e}")
        return ""

    candidates.sort(key=lambda t: (-t[0], str(t[1])))
    top = candidates[:top_k]

    if not top:
        return ""

    # Build a context block. Cap per-note excerpt and total length.
    parts = ["## Empire Obsidian context\n"]
    used = len(parts[0])
    for score, path, clean in top:
        # Excerpt: take the first max_chars_per_note chars.
        excerpt = clean[:RAG_MAX_CHARS_PER_NOTE]
        if len(clean) > RAG_MAX_CHARS_PER_NOTE:
            excerpt = excerpt.rsplit(" ", 1)[0] + " …"  # word-boundary cut

        block = f"### {path.stem} (score={score})\n{excerpt}\n\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)

    return "".join(parts).rstrip() + "\n"


# ── CLI smoke test ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: empire_obsidian_rag.py <query>")
        sys.exit(1)
    q = " ".join(sys.argv[1:])
    out = build_context(q)
    if not out:
        print("(no context — vault empty or no overlap)")
    else:
        print(out)