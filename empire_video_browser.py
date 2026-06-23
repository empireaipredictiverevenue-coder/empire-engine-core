"""
EMPIRE V49 · VIDEO ASSET BROWSER
==============================================
Interactive gallery of rendered YouTube Shorts at /videos.
Scans youtube_shorts_output/ for MP4 files, generates thumbnails
on-the-fly via ffmpeg, and displays them in a visual grid with
keyframe previews, metadata, and inline playback.

API:
  GET /api/v1/videos/assets  — JSON list of all videos with metadata

Routes:
  GET /videos  — Visual asset browser page

Static:
  /videos/media/...  — Serves rendered MP4s and thumbnails
"""

import asyncio
import json
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI

log = logging.getLogger("empire.video_browser")

REPO = Path(__file__).resolve().parent
SHORTS_DIR = REPO / "youtube_shorts_output"
THUMBS_DIR = SHORTS_DIR / ".thumbs"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)

# ── Supported video extensions ──
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}


def scan_videos() -> list[dict]:
    """Scan the shorts output directory for rendered videos.

    Returns a list of dicts with: filename, title, file_path, file_size,
    duration_s, thumbnail, keyframes, has_keyframes, created_at.
    """
    videos = []
    for f in sorted(SHORTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.suffix.lower() not in VIDEO_EXTS or f.name.startswith("."):
            continue

        # Parse title from filename — extract meaningful name
        title = _title_from_filename(f.stem)

        # Look for associated keyframes directory
        keyframe_dir = SHORTS_DIR / f"{f.stem}_keyframes"
        keyframes = sorted(keyframe_dir.glob("thumb_*.jpg")) if keyframe_dir.exists() else []

        # Generate thumbnail if not cached
        thumb_path = THUMBS_DIR / f"{f.stem}.jpg"
        if not thumb_path.exists():
            _generate_thumbnail(f, thumb_path)

        # Get video duration via ffprobe
        duration_s = _get_duration(f)

        stat = f.stat()
        videos.append({
            "filename": f.name,
            "title": title,
            "file_path": f"media/{f.name}",
            "file_size": stat.st_size,
            "file_size_display": _format_bytes(stat.st_size),
            "duration_s": duration_s,
            "duration_display": _format_duration(duration_s),
            "thumbnail": f"thumbs/{f.stem}.jpg",
            "keyframes": [f"keyframes/{f.stem}_keyframes/{k.name}" for k in keyframes],
            "has_keyframes": len(keyframes) > 0,
            "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })

    return videos


def _title_from_filename(stem: str) -> str:
    """Extract a readable title from the filename stem."""
    # Remove leading "short_" prefix
    name = stem
    if name.startswith("short_"):
        name = name[6:]
    # Remove trailing timestamp (_YYYYMMDD_HHMMSS)
    name = re.sub(r"_\d{8}_\d{6}$", "", name)
    # Replace underscores with spaces
    name = name.replace("_", " ")
    # Capitalize words
    name = " ".join(w.capitalize() for w in name.split())
    return name.strip() or stem


def _generate_thumbnail(video_path: Path, thumb_path: Path) -> None:
    """Generate a thumbnail at the 2-second mark via ffmpeg."""
    try:
        subprocess.run(
            ["ffmpeg", "-ss", "00:00:02", "-i", str(video_path),
             "-vframes", "1", "-q:v", "3", "-y", str(thumb_path)],
            capture_output=True, timeout=30,
        )
    except Exception as e:
        log.debug(f"[video-browser] thumbnail failed for {video_path.name}: {e}")


def _get_duration(video_path: Path) -> float:
    """Get video duration via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=15,
        )
        return round(float(r.stdout.strip()), 1) if r.stdout.strip() else 0
    except Exception:
        return 0


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.1f} MB"
    else:
        return f"{size / 1024 ** 3:.2f} GB"


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


# ── PAGE HTML ──

_VIDEO_CSS = """
html, body {
  min-height: 100vh;
  background: var(--empire-black);
  color: var(--empire-white);
}

body {
  display: flex;
  flex-direction: column;
  padding-bottom: 48px;
}

/* ── HEADER ── */
.vb-header {
  padding: 32px 24px 24px;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}

.vb-header-left h1 {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: clamp(24px, 4vw, 36px);
  letter-spacing: -0.03em;
  margin-bottom: 4px;
}

.vb-header-left h1 em {
  color: var(--signal-teal);
  font-style: normal;
}

.vb-header-left p {
  font-size: 13px;
  color: var(--empire-silver);
  margin: 0;
}

.vb-header-count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--empire-mist);
  letter-spacing: 0.08em;
  padding: 8px 16px;
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-sm);
}

/* ── SEARCH / FILTER BAR ── */
.vb-toolbar {
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  padding: 0 24px 20px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.vb-search {
  flex: 1;
  min-width: 200px;
  padding: 10px 16px;
  background: var(--empire-glass);
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-sm);
  color: var(--empire-white);
  font-family: var(--font-mono);
  font-size: 12px;
  outline: none;
  transition: all 0.2s ease;
}

.vb-search:focus {
  border-color: var(--signal-teal);
  box-shadow: 0 0 0 1px var(--signal-teal);
}

.vb-search::placeholder {
  color: var(--empire-fog);
}

.vb-filter-btn {
  padding: 8px 16px;
  background: transparent;
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-sm);
  color: var(--empire-silver);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  cursor: pointer;
  transition: all 0.2s ease;
}

.vb-filter-btn:hover,
.vb-filter-btn.active {
  border-color: var(--signal-teal);
  color: var(--signal-teal);
}

/* ── VIDEO GRID ── */
.vb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  padding: 0 24px;
}

.vb-card {
  background: var(--empire-glass);
  border: 1px solid var(--empire-border);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: all 0.3s var(--ease-out-empire);
  cursor: pointer;
  animation: empire-fade-up 0.5s var(--ease-out-empire) both;
}

.vb-card:hover {
  border-color: rgba(68, 229, 184, 0.25);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3), var(--glow-soft);
  transform: translateY(-2px);
}

.vb-card:nth-child(1) { animation-delay: 0.05s; }
.vb-card:nth-child(2) { animation-delay: 0.08s; }
.vb-card:nth-child(3) { animation-delay: 0.11s; }
.vb-card:nth-child(4) { animation-delay: 0.14s; }
.vb-card:nth-child(5) { animation-delay: 0.17s; }
.vb-card:nth-child(6) { animation-delay: 0.20s; }
.vb-card:nth-child(7) { animation-delay: 0.23s; }
.vb-card:nth-child(8) { animation-delay: 0.26s; }
.vb-card:nth-child(9) { animation-delay: 0.29s; }
.vb-card:nth-child(10) { animation-delay: 0.32s; }

.vb-thumb {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #111;
  overflow: hidden;
}

.vb-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.4s ease;
}

.vb-card:hover .vb-thumb img {
  transform: scale(1.05);
}

.vb-thumb-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  opacity: 0;
  transition: opacity 0.3s ease;
}

.vb-card:hover .vb-thumb-overlay {
  opacity: 1;
}

.vb-play-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: rgba(68, 229, 184, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #000;
  transition: transform 0.2s ease;
}

.vb-card:hover .vb-play-icon {
  transform: scale(1.1);
}

.vb-thumb-duration {
  position: absolute;
  bottom: 8px;
  right: 8px;
  padding: 3px 8px;
  background: rgba(0, 0, 0, 0.8);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: #fff;
  letter-spacing: 0.04em;
}

.vb-card-body {
  padding: 14px 16px;
}

.vb-card-title {
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 500;
  color: var(--empire-white);
  line-height: 1.4;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.vb-card-meta {
  display: flex;
  gap: 12px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--empire-mist);
  letter-spacing: 0.04em;
}

.vb-card-meta span {
  color: var(--signal-teal);
}

/* ── KEYFRAMES STRIP ── */
.vb-keyframes {
  display: flex;
  gap: 4px;
  padding: 8px 16px 14px;
  overflow-x: auto;
  scrollbar-width: none;
}

.vb-keyframes::-webkit-scrollbar {
  display: none;
}

.vb-keyframe {
  flex-shrink: 0;
  width: 72px;
  height: 40px;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.06);
  cursor: pointer;
  transition: all 0.2s ease;
}

.vb-keyframe:hover {
  border-color: var(--signal-teal);
  transform: scale(1.08);
}

.vb-keyframe img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* ── MODAL / PLAYER ── */
.vb-modal {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.9);
  backdrop-filter: blur(20px);
  align-items: center;
  justify-content: center;
}

.vb-modal.open {
  display: flex;
  animation: empire-fade-in 0.2s ease;
}

.vb-modal-close {
  position: absolute;
  top: 20px;
  right: 24px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  border: none;
  color: #fff;
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  z-index: 10;
}

.vb-modal-close:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: scale(1.1);
}

.vb-modal-content {
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.vb-modal video {
  max-width: 100%;
  max-height: 80vh;
  border-radius: var(--radius-md);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.vb-modal-title {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 500;
  color: var(--empire-white);
  margin-top: 16px;
  text-align: center;
}

/* ── EMPTY STATE ── */
.vb-empty {
  grid-column: 1 / -1;
  text-align: center;
  padding: 64px 24px;
  border: 1px dashed var(--empire-border);
  border-radius: var(--radius-md);
}

.vb-empty-icon {
  margin-bottom: 16px;
  opacity: 0.4;
}

.vb-empty-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--empire-white);
  margin-bottom: 8px;
}

.vb-empty-desc {
  font-size: 13px;
  color: var(--empire-mist);
  line-height: 1.6;
  max-width: 400px;
  margin: 0 auto;
}

.vb-empty-desc code {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--signal-teal);
  background: rgba(68,229,184,0.06);
  padding: 2px 6px;
  border-radius: 3px;
}

/* ── RESPONSIVE ── */
@media (max-width: 640px) {
  .vb-grid {
    grid-template-columns: 1fr;
    gap: 14px;
    padding: 0 16px;
  }
  .vb-header {
    padding: 24px 16px 16px;
  }
  .vb-toolbar {
    padding: 0 16px 16px;
  }
}
"""

_VIDEO_PAGE_SCRIPT = """
(function() {
  var videos = [];
  var filtered = [];
  var searchEl = document.getElementById('vb-search');
  var gridEl = document.getElementById('vb-grid');
  var countEl = document.getElementById('vb-count');

  // ── Fetch video list ──
  fetch('/api/v1/videos/assets')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      videos = data.videos || [];
      countEl.textContent = videos.length + ' video' + (videos.length !== 1 ? 's' : '');
      filtered = videos;
      renderGrid(filtered);
    })
    .catch(function(err) {
      gridEl.innerHTML =
        '<div class="vb-empty">' +
        '<div class="vb-empty-icon"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#44E5B8" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div>' +
        '<div class="vb-empty-title">Could not load videos</div>' +
        '<div class="vb-empty-desc">The video scanner encountered an error. Ensure <code>youtube_shorts_output/</code> exists and has rendered MP4 files.</div>' +
        '</div>';
    });

  // ── Render grid ──
  function renderGrid(list) {
    if (!list.length) {
      gridEl.innerHTML =
        '<div class="vb-empty">' +
        '<div class="vb-empty-icon"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#44E5B8" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg></div>' +
        '<div class="vb-empty-title">No videos found</div>' +
        '<div class="vb-empty-desc">No rendered Shorts detected. Run the YouTube Shorts pipeline to generate videos, or place MP4 files in <code>youtube_shorts_output/</code>.</div>' +
        '</div>';
      return;
    }

    var html = '';
    list.forEach(function(v, i) {
      var keyframeHtml = '';
      if (v.keyframes && v.keyframes.length) {
        keyframeHtml = '<div class="vb-keyframes">';
        v.keyframes.forEach(function(kf) {
          keyframeHtml += '<div class="vb-keyframe" onclick="event.stopPropagation();document.getElementById(\\'vb-modal\\').classList.add(\\'open\\');document.getElementById(\\'vb-player\\').src=\\'/videos/media/' + v.filename + '?t=' + kf.match(/_(\\\\d+)\\\\./)?.[1] || \\'\\' + '\\'"><img src="/videos/media/' + kf + '" loading="lazy" alt="Keyframe"></div>';
        });
        keyframeHtml += '</div>';
      }

      html +=
        '<div class="vb-card" data-title="' + escapeAttr(v.title).toLowerCase() + '" onclick="openPlayer(\\'' + escapeAttr(v.filename) + '\\', \\'' + escapeAttr(v.title) + '\\')">' +
        '<div class="vb-thumb">' +
        '<img src="/videos/media/' + escapeAttr(v.thumbnail) + '" loading="lazy" alt="' + escapeAttr(v.title) + '">' +
        '<div class="vb-thumb-overlay"><div class="vb-play-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg></div></div>' +
        '<div class="vb-thumb-duration">' + v.duration_display + '</div>' +
        '</div>' +
        '<div class="vb-card-body">' +
        '<div class="vb-card-title">' + escapeHtml(v.title) + '</div>' +
        '<div class="vb-card-meta"><span>' + escapeHtml(v.file_size_display) + '</span> · ' + escapeHtml(v.created_at.slice(0, 10)) + '</div>' +
        '</div>' +
        (keyframeHtml ? keyframeHtml : '') +
        '</div>';
    });
    gridEl.innerHTML = html;
  }

  // ── Search filter ──
  searchEl.addEventListener('input', function() {
    var q = this.value.toLowerCase().trim();
    filtered = q ? videos.filter(function(v) { return v.title.toLowerCase().indexOf(q) !== -1; }) : videos;
    countEl.textContent = filtered.length + ' of ' + videos.length + ' videos';
    renderGrid(filtered);
  });

  // ── Modal player ──
  window.openPlayer = function(filename, title) {
    var modal = document.getElementById('vb-modal');
    var player = document.getElementById('vb-player');
    var titleEl = document.getElementById('vb-modal-title');
    player.src = '/videos/media/' + filename;
    player.load();
    titleEl.textContent = title;
    modal.classList.add('open');
    player.play().catch(function() {});
  };

  // ── Close modal ──
  document.getElementById('vb-modal-close').addEventListener('click', function() {
    var modal = document.getElementById('vb-modal');
    var player = document.getElementById('vb-player');
    player.pause();
    player.src = '';
    modal.classList.remove('open');
  });

  document.getElementById('vb-modal').addEventListener('click', function(e) {
    if (e.target === this) {
      document.getElementById('vb-modal-close').click();
    }
  });

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      document.getElementById('vb-modal-close').click();
    }
  });

  // ── Helpers ──
  function escapeHtml(str) {
    if (!str) return '';
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  function escapeAttr(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
})();
"""


def video_browser_page() -> str:
    """Return the video asset browser HTML page."""

    from empire_tokens import empire_head
    from empire_structured_data import webpage_jsonld

    head = empire_head(
        title="Video Assets · Empire AI",
        extra=_VIDEO_CSS,
        page="videos",
        meta_html=webpage_jsonld(
            "Empire AI Video Assets",
            "Browse rendered YouTube Shorts and video assets from Empire AI's content generation pipeline. Preview, play, and download MP4 videos with keyframe thumbnails.",
            "https://empire-ai.co.uk/videos",
        ),
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<!-- ═══════════════ MODAL PLAYER ═══════════════ -->
<div class="vb-modal" id="vb-modal">
  <button class="vb-modal-close" id="vb-modal-close" aria-label="Close">&times;</button>
  <div class="vb-modal-content">
    <video id="vb-player" controls playsinline preload="metadata"></video>
    <div class="vb-modal-title" id="vb-modal-title"></div>
  </div>
</div>

<!-- ═══════════════ HEADER ═══════════════ -->
<header class="vb-header">
  <div class="vb-header-left">
    <h1>Video <em>Assets</em></h1>
    <p>Rendered Shorts from the Empire AI content pipeline</p>
  </div>
  <div class="vb-header-count" id="vb-count">Loading...</div>
</header>

<!-- ═══════════════ TOOLBAR ═══════════════ -->
<div class="vb-toolbar">
  <input class="vb-search" id="vb-search" type="text" placeholder="Search videos by title..." autocomplete="off">
</div>

<!-- ═══════════════ GRID ═══════════════ -->
<div class="vb-grid" id="vb-grid">
  <div class="vb-empty">
    <div class="vb-empty-icon"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#44E5B8" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg></div>
    <div class="vb-empty-title">Loading assets...</div>
    <div class="vb-empty-desc">Scanning rendered Shorts from <code>youtube_shorts_output/</code></div>
  </div>
</div>

<script>{_VIDEO_PAGE_SCRIPT}</script>
</body>
</html>"""


# ── FASTAPI ROUTE REGISTRATION ──────────────────────────────────────
def register_video_routes(app):
    """Wire video browser routes into a FastAPI app.

    Registers:
      GET  /videos              — Asset browser page
      GET  /api/v1/videos/assets — JSON video list
      /videos/media/...          — Static file serving for MP4s + thumbs
    """
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    # ── Static file server for videos, thumbs, keyframes ──
    if not any(
        r.path == "/videos/media" for r in app.routes
        if hasattr(r, "path")
    ):
        app.mount(
            "/videos/media",
            StaticFiles(directory=str(SHORTS_DIR)),
            name="video_media",
        )

    # ── JSON API ──
    @app.get("/api/v1/videos/assets")
    async def video_assets():
        """Return JSON list of all rendered videos with metadata."""
        videos = scan_videos()
        return JSONResponse({
            "ok": True,
            "videos": videos,
            "count": len(videos),
            "shorts_dir": str(SHORTS_DIR),
        })

    # ── HTML page ──
    @app.get("/videos", response_class=HTMLResponse)
    async def video_browser():
        """Video asset browser page."""
        return HTMLResponse(video_browser_page())

    log.info("[video-browser] Routes registered: GET /videos, GET /api/v1/videos/assets, /videos/media/...")
