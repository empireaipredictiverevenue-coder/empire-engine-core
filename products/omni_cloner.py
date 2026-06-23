"""
EMPIRE V49 · PRODUCT: OMNI CLONER
====================================
Advanced cross-platform content cloning engine. Downloads video/audio from
1000+ sites via yt-dlp, processes with ffmpeg (transcode, thumbnail, audio
extraction), transcribes via Deepgram, and syndicates across social platforms
via Zernio.

Pipeline:
    Any URL (YouTube/TikTok/IG/Twitter/FB/etc)
        → yt-dlp download + metadata extraction
        → ffmpeg transcode / thumbnail / audio extraction
        → Deepgram STT transcription
        → Zernio multi-platform syndication
        → customer_usage_ledger logging

Integration:
    cloner = OmniCloner(guard, log_usage)
    result = await cloner.clone_content(url, account_id, platforms)

Endpoints (registered via OmniClonerRoutes):
    POST /api/v6/omni/clone      — Full clone pipeline
    POST /api/v6/omni/download   — Download media only
    GET  /api/v6/omni/info       — Extract metadata from URL
    GET  /api/v6/omni/cloner/stats — Cloner stats snapshot
"""

import asyncio
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI

log = logging.getLogger("empire.product.omni_cloner")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "storm_alerts.sqlite"
MEDIA_DIR = BASE_DIR / "data" / "media"
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# ── Config from env vars ──────────────────────────────────────────────
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
DEEPGRAM_MODEL = os.environ.get("DEEPGRAM_MODEL", "nova-3")
ZERNIO_API_KEY = os.environ.get("ZERNIO_API_KEY", "")
ZERNIO_BASE_URL = os.environ.get("ZERNIO_BASE_URL", "https://zernio.com/api/v1")

# ── Supported platforms (yt-dlp covers 1000+ sites — this is for labeling) ──
PLATFORM_PATTERNS = {
    "youtube":     r"(youtube\.com|youtu\.be)",
    "tiktok":      r"(tiktok\.com)",
    "instagram":   r"(instagram\.com)",
    "twitter":     r"(twitter\.com|x\.com)",
    "facebook":    r"(facebook\.com|fb\.com)",
    "linkedin":    r"(linkedin\.com)",
    "reddit":      r"(reddit\.com)",
    "vimeo":       r"(vimeo\.com)",
    "twitch":      r"(twitch\.tv)",
    "dailymotion": r"(dailymotion\.com)",
}


def detect_platform(url: str) -> str:
    """Detect which platform a URL belongs to based on domain."""
    for platform, pattern in PLATFORM_PATTERNS.items():
        if re.search(pattern, url, re.IGNORECASE):
            return platform
    return "unknown"


class OmniCloner:
    """Advanced cross-platform content cloning engine.

    Capabilities:
      - Download video/audio from 1000+ sites via yt-dlp
      - Extract metadata without downloading
      - Transcode video formats via ffmpeg
      - Extract audio tracks for transcription
      - Generate thumbnails
      - Transcribe via Deepgram (or simulation)
      - Syndicate across social platforms via Zernio
      - Clone entire channels (playlist/channel download)
    """

    def __init__(
        self,
        guard: Optional[Callable] = None,
        log_usage: Optional[Callable] = None,
        studio: Optional[object] = None,
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.studio = studio
        self.stats = {
            "downloads": 0, "transcodes": 0, "transcriptions": 0,
            "syndications": 0, "channel_clones": 0, "errors": 0,
            "bytes_downloaded": 0, "media_count": 0,
        }

        try:
            import yt_dlp as _yt
            self._ydl_version = getattr(_yt, "__version__", "unknown")
        except ImportError:
            self._ydl_version = "not_installed"
            log.warning("[cloner] yt-dlp not installed — downloading disabled")

        if not shutil.which("ffmpeg"):
            log.warning("[cloner] ffmpeg not found — video processing disabled")
        if not DEEPGRAM_API_KEY:
            log.warning("[cloner] DEEPGRAM_API_KEY not set — transcription simulated")
        if not ZERNIO_API_KEY:
            log.warning("[cloner] ZERNIO_API_KEY not set — syndication disabled")

    # ── ENTITLEMENT ────────────────────────────────────────────────────

    async def check_entitlement(self, account_id: str) -> dict:
        """Verify account has the omni_cloner feature enabled."""
        if not self.guard:
            return {"ok": False, "error": "No guard configured"}
        return self.guard(account_id, "omni_cloner")

    # ── STEP 1: EXTRACT INFO (metadata without download) ────────────────

    def extract_info(self, url: str) -> dict:
        """Extract rich metadata from a URL without downloading.

        Returns title, description, duration, uploader, view_count,
        thumbnails, formats available, platform, and more.
        """
        import yt_dlp
        start = datetime.now(timezone.utc)
        try:
            with yt_dlp.YoutubeDL({
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
            }) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return {"ok": False, "error": "No info extracted"}

                # Build clean metadata response
                thumbnails = info.get("thumbnails") or []
                best_thumb = ""
                if thumbnails:
                    # Prefer highest resolution
                    sorted_thumbs = sorted(
                        [t for t in thumbnails if t.get("url")],
                        key=lambda t: (t.get("width", 0) or 0) * (t.get("height", 0) or 0),
                        reverse=True,
                    )
                    best_thumb = sorted_thumbs[0].get("url", "") if sorted_thumbs else ""

                formats = info.get("formats") or []
                best_video = next(
                    (f for f in formats if f.get("vcodec") and f.get("acodec") and f.get("height")),
                    formats[0] if formats else None,
                )

                # Detect age-restricted or private content
                availability = info.get("availability", "public")
                if availability in ("needs_auth", "private", "unlisted"):
                    log.warning(f"[cloner] content restricted: {availability}")

                return {
                    "ok": True,
                    "title": info.get("title", ""),
                    "description": (info.get("description") or "")[:2000],
                    "duration_s": info.get("duration") or 0,
                    "uploader": info.get("uploader") or info.get("channel") or "",
                    "uploader_url": info.get("uploader_url") or info.get("channel_url") or "",
                    "view_count": info.get("view_count") or 0,
                    "like_count": info.get("like_count") or 0,
                    "comment_count": info.get("comment_count") or 0,
                    "upload_date": info.get("upload_date") or "",
                    "platform": detect_platform(url),
                    "platform_label": info.get("extractor", "unknown"),
                    "thumbnail": best_thumb,
                    "duration_display": _format_duration(info.get("duration") or 0),
                    "availability": availability,
                    "age_limit": info.get("age_limit") or 0,
                    "tags": (info.get("tags") or [])[:20],
                    "categories": (info.get("categories") or [])[:10],
                    "formats_available": len(formats),
                    "best_format": {
                        "height": (best_video or {}).get("height", 0),
                        "width": (best_video or {}).get("width", 0),
                        "fps": (best_video or {}).get("fps", 0),
                        "vcodec": (best_video or {}).get("vcodec", ""),
                        "acodec": (best_video or {}).get("acodec", ""),
                        "filesize": (best_video or {}).get("filesize", 0),
                        "ext": (best_video or {}).get("ext", ""),
                        "tbr": (best_video or {}).get("tbr", 0),
                    } if best_video else None,
                    "is_live": info.get("is_live", False),
                    "was_live": info.get("was_live", False),
                    "playlist": info.get("playlist_title") or "",
                    "playlist_count": info.get("playlist_count") or 0,
                    "extractor": info.get("extractor_key", ""),
                    "extracted_at": datetime.now(timezone.utc).isoformat(),
                    "latency_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
                }
        except Exception as e:
            log.warning(f"[cloner] extract_info failed: {e}")
            return {"ok": False, "error": str(e)[:200], "url": url}

    # ── STEP 2: DOWNLOAD MEDIA ──────────────────────────────────────

    async def download_media(
        self,
        url: str,
        output_template: Optional[str] = None,
        format_spec: str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        extract_audio: bool = False,
    ) -> dict:
        """Download media from any supported URL.

        Args:
            url: Source URL (YouTube, TikTok, IG, etc.)
            output_template: Custom output path template
            format_spec: yt-dlp format specification
            extract_audio: If True, download audio-only

        Returns:
            dict with file path, metadata, platform info
        """
        import yt_dlp
        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]
        out_dir = MEDIA_DIR / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        if output_template:
            out_tmpl = str(MEDIA_DIR / output_template)
        else:
            out_tmpl = str(out_dir / "%(title).100s_%(id)s.%(ext)s")

        ydl_opts = {
            "format": format_spec if not extract_audio else "bestaudio/best",
            "outtmpl": out_tmpl,
            "quiet": True,
            "no_warnings": True,
            "writethumbnail": True,
            "embedthumbnail": True,
            "embedmetadata": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en"],
            "postprocessor_args": [],
            "max_filesize": 500000000,  # 500MB limit — prevents disk exhaustion
        }

        if extract_audio:
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._download_sync, url, ydl_opts, job_id, out_dir, extract_audio)
            return result
        except Exception as e:
            log.warning(f"[cloner] download failed: {e}")
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)[:200]}

    def _download_sync(
        self, url: str, ydl_opts: dict, job_id: str, out_dir: Path, extract_audio: bool
    ) -> dict:
        """Synchronous download wrapper for thread pool execution."""
        import yt_dlp
        start = datetime.now(timezone.utc)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
            except Exception as e:
                self.stats["errors"] += 1
                return {"ok": False, "error": f"Download failed: {str(e)[:200]}"}

            if not info:
                return {"ok": False, "error": "No data returned from extractor"}

            # Find the downloaded file
            downloaded_files = list(out_dir.iterdir())
            video_file = None
            audio_file = None
            thumbnail_file = None
            subtitle_files = []

            for f in downloaded_files:
                ext = f.suffix.lower()
                if ext in (".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4a", ".m4v"):
                    if extract_audio:
                        audio_file = str(f)
                    else:
                        video_file = str(f)
                elif ext in (".mp3", ".wav", ".ogg", ".aac", ".opus", ".m4a"):
                    audio_file = str(f)
                elif ext in (".jpg", ".jpeg", ".png", ".webp"):
                    thumbnail_file = str(f)
                elif ext in (".vtt", ".srt", ".ass", ".sbv"):
                    subtitle_files.append(str(f))

            # Fallback: find via yt-dlp's info dict
            if not video_file and not audio_file:
                requested_downloads = info.get("requested_downloads") or []
                for rd in requested_downloads:
                    fp = rd.get("filepath", "")
                    if fp and os.path.exists(fp):
                        ext = os.path.splitext(fp)[1].lower()
                        if ext in (".mp4", ".webm", ".mkv"):
                            video_file = fp
                        else:
                            audio_file = fp

            file_path = video_file or audio_file or ""
            file_size = os.path.getsize(file_path) if file_path and os.path.exists(file_path) else 0

            # Get subtitle content if available
            subtitle_text = ""
            for sf in subtitle_files:
                try:
                    with open(sf, "r", encoding="utf-8") as f:
                        subtitle_text += f.read()[:5000] + "\n"
                except Exception:
                    pass

            # Update stats
            self.stats["downloads"] += 1
            self.stats["bytes_downloaded"] += file_size
            self.stats["media_count"] += 1

            duration_s = info.get("duration") or 0

            return {
                "ok": True,
                "job_id": job_id,
                "title": info.get("title", ""),
                "file_path": file_path,
                "file_size": file_size,
                "file_size_display": _format_bytes(file_size),
                "video_file": video_file or "",
                "audio_file": audio_file or "",
                "thumbnail_file": thumbnail_file or "",
                "subtitle_files": subtitle_files,
                "subtitle_text_preview": subtitle_text[:2000],
                "has_subs": len(subtitle_files) > 0,
                "duration_s": duration_s,
                "duration_display": _format_duration(duration_s),
                "platform": detect_platform(url),
                "extractor": info.get("extractor_key", ""),
                "view_count": info.get("view_count") or 0,
                "uploader": info.get("uploader") or info.get("channel") or "",
                "format": info.get("format", ""),
                "width": info.get("width", 0),
                "height": info.get("height", 0),
                "fps": info.get("fps", 0),
                "vcodec": info.get("vcodec", ""),
                "acodec": info.get("acodec", ""),
                "is_live": info.get("is_live", False),
                "availability": info.get("availability", "public"),
                "latency_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
                "output_dir": str(out_dir),
            }

    # ── STEP 2b: DOWNLOAD CHANNEL / PLAYLIST ──────────────────────────

    async def download_channel(
        self,
        url: str,
        max_count: int = 10,
        format_spec: str = "bestvideo[height<=720]+bestaudio/best[height<=720]",
    ) -> dict:
        """Download multiple videos from a channel or playlist.

        Supports YouTube channels, TikTok profiles, Instagram users, etc.
        Uses yt-dlp's playlist/channel extraction.
        """
        import yt_dlp
        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]
        out_dir = MEDIA_DIR / f"channel_{job_id}"
        out_dir.mkdir(parents=True, exist_ok=True)

        ydl_opts = {
            "format": format_spec,
            # Flat output — no subdirectory per playlist to prevent path traversal
            "outtmpl": str(out_dir / f"ch_{job_id[:12]}_%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "max_downloads": max_count,
            "extract_flat": "in_playlist",
            "writethumbnail": True,
            "max_filesize": 500000000,
        }

        start = datetime.now(timezone.utc)
        try:
            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))

            if not info:
                return {"ok": False, "error": "No data returned"}

            # Collect downloaded files
            entries = info.get("entries") or []
            if not entries and info.get("_type") == "playlist":
                entries = info.get("entries") or []

            downloaded = []
            total_size = 0
            for entry in (entries if entries else [info]):
                if not entry:
                    continue
                req_dl = entry.get("requested_downloads") or []
                for rd in req_dl:
                    fp = rd.get("filepath", "")
                    if fp and os.path.exists(fp):
                        sz = os.path.getsize(fp)
                        total_size += sz
                        downloaded.append({
                            "title": entry.get("title", ""),
                            "file_path": fp,
                            "file_size": sz,
                            "duration": entry.get("duration", 0),
                        })

            self.stats["channel_clones"] += 1
            self.stats["downloads"] += len(downloaded)
            self.stats["bytes_downloaded"] += total_size
            self.stats["media_count"] += len(downloaded)

            return {
                "ok": True,
                "job_id": job_id,
                "channel_title": info.get("title") or info.get("channel", ""),
                "channel_url": info.get("channel_url") or info.get("uploader_url", ""),
                "playlist_count": info.get("playlist_count") or len(entries),
                "downloaded_count": len(downloaded),
                "downloaded": downloaded,
                "total_bytes": total_size,
                "total_duration_s": sum(d.get("duration", 0) for d in downloaded),
                "output_dir": str(out_dir),
                "latency_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
            }
        except Exception as e:
            log.warning(f"[cloner] channel download failed: {e}")
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)[:200]}

    # ── STEP 3: TRANSCODE (ffmpeg) ──────────────────────────────────

    async def transcode(
        self,
        input_path: str,
        output_format: str = "mp4",
        resolution: Optional[str] = None,
        bitrate: Optional[str] = None,
        fps: Optional[int] = None,
    ) -> dict:
        """Transcode a video file to a different format/resolution using ffmpeg.

        Args:
            input_path: Path to input video file
            output_format: Target format (mp4, webm, mov, avi, gif)
            resolution: Target resolution (e.g., "720", "1080", "480")
            bitrate: Target video bitrate (e.g., "2M", "1M")
            fps: Target frame rate

        Returns:
            dict with output path, size info, duration
        """
        if not shutil.which("ffmpeg"):
            return {"ok": False, "error": "ffmpeg not installed"}

        input_path = Path(input_path)
        if not input_path.exists():
            return {"ok": False, "error": "Input file not found"}

        ext_map = {
            "mp4": ".mp4", "webm": ".webm", "mov": ".mov",
            "avi": ".avi", "gif": ".gif", "mkv": ".mkv",
        }
        ext = ext_map.get(output_format, ".mp4")

        # Build output path
        stem = input_path.stem[:80]
        out_name = f"{stem}_transcoded{ext}"
        output_path = input_path.parent / out_name

        import subprocess
        cmd = ["ffmpeg", "-i", str(input_path), "-y"]

        # Resolution scaling
        if resolution:
            try:
                res_val = int(resolution)
                # Maintain aspect ratio, fit within resolution vertically
                cmd.extend(["-vf", f"scale=-2:{res_val}"])
            except ValueError:
                pass

        # Bitrate control
        if bitrate:
            cmd.extend(["-b:v", bitrate])

        # FPS control
        if fps:
            cmd.extend(["-r", str(fps)])

        # Codec selection
        if output_format == "mp4":
            cmd.extend(["-c:v", "libx264", "-c:a", "aac", "-pix_fmt", "yuv420p"])
        elif output_format == "webm":
            cmd.extend(["-c:v", "libvpx-vp9", "-c:a", "libopus"])
        elif output_format == "gif":
            cmd.extend(["-vf", "fps=10,scale=640:-1:flags=lanczos", "-loop", "0"])
        else:
            cmd.extend(["-c:v", "libx264", "-c:a", "aac"])

        cmd.append(str(output_path))

        try:
            start = datetime.now(timezone.utc)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                err_msg = stderr.decode()[-200:] if stderr else f"ffmpeg exit code {proc.returncode}"
                self.stats["errors"] += 1
                return {"ok": False, "error": err_msg}

            out_size = output_path.stat().st_size if output_path.exists() else 0
            self.stats["transcodes"] += 1

            return {
                "ok": True,
                "input_path": str(input_path),
                "output_path": str(output_path),
                "output_format": output_format,
                "file_size": out_size,
                "file_size_display": _format_bytes(out_size),
                "resolution": resolution or "original",
                "latency_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
            }
        except Exception as e:
            log.warning(f"[cloner] transcode failed: {e}")
            self.stats["errors"] += 1
            return {"ok": False, "error": str(e)[:200]}

    # ── STEP 4: GENERATE THUMBNAIL ──────────────────────────────────

    async def generate_thumbnail(
        self, video_path: str, time_offset: str = "00:00:05", size: str = "1280x720"
    ) -> dict:
        """Generate a thumbnail from a video at a specific timestamp."""
        if not shutil.which("ffmpeg"):
            return {"ok": False, "error": "ffmpeg not installed"}

        video_path = Path(video_path)
        if not video_path.exists():
            return {"ok": False, "error": "Video file not found"}

        thumb_path = video_path.parent / f"{video_path.stem[:70]}_thumb.jpg"

        try:
            start = datetime.now(timezone.utc)
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-ss", time_offset, "-i", str(video_path),
                "-vframes", "1", "-s", size, "-q:v", "2",
                "-y", str(thumb_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0 or not thumb_path.exists():
                return {"ok": False, "error": "Thumbnail generation failed"}

            return {
                "ok": True,
                "thumbnail_path": str(thumb_path),
                "file_size": thumb_path.stat().st_size,
                "size": size,
                "time_offset": time_offset,
                "latency_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ── STEP 5: TRANSCRIBE AUDIO ────────────────────────────────────

    async def transcribe_video(self, video_path: str) -> dict:
        """Extract audio from video and transcribe via Deepgram.

        Falls back to simulated transcript if Deepgram API key not set
        or if audio extraction is not possible.
        """
        video_path = Path(video_path)
        if not video_path.exists():
            return {"ok": False, "error": "Video file not found"}

        # Extract audio to WAV using ffmpeg
        audio_path = video_path.parent / f"{video_path.stem[:70]}_audio.wav"
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", str(video_path),
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                "-y", str(audio_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if not audio_path.exists():
                return {"ok": False, "error": "Audio extraction failed"}
        except Exception as e:
            return {"ok": False, "error": f"Audio extraction error: {e}"}

        # Transcribe the audio — upload binary to Deepgram (file:// URLs not supported)
        transcript = await self._transcribe_file(audio_path)

        # Clean up temp audio file
        try:
            audio_path.unlink(missing_ok=True)
        except Exception:
            pass

        return transcript

    async def _transcribe_file(self, audio_path: Path) -> dict:
        """Upload audio binary to Deepgram for transcription.

        Uses multipart upload (not URL reference) since Deepgram does not
        accept file:// or local paths.
        """
        if not DEEPGRAM_API_KEY:
            log.info("[cloner] Deepgram API key not set — simulated transcript")
            self.stats["transcriptions"] += 1
            return {
                "ok": True,
                "transcript": "This is a simulated transcript. Set DEEPGRAM_API_KEY for real transcription.",
                "simulated": True,
                "duration_s": 0,
                "words": [],
            }

        if not audio_path or not audio_path.exists():
            return {"ok": False, "error": "Audio file not found", "transcript": ""}

        try:
            import httpx
            start = datetime.now(timezone.utc)
            audio_bytes = audio_path.read_bytes()
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"https://api.deepgram.com/v1/listen?model={DEEPGRAM_MODEL}&"
                    f"smart_format=true&punctuate=true&diarize=true",
                    headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
                    content=audio_bytes,
                    # Deepgram accepts raw audio binary in the body
                )
                if response.status_code >= 300:
                    return {"ok": False, "error": f"Deepgram error {response.status_code}"}

                data = response.json()
                channels = data.get("results", {}).get("channels", [])
                if channels:
                    alt = channels[0].get("alternatives", [])
                    if alt:
                        transcript = alt[0].get("transcript", "")
                        words = alt[0].get("words", [])
                        duration = data.get("metadata", {}).get("duration", 0)
                        self.stats["transcriptions"] += 1
                        return {
                            "ok": True,
                            "transcript": transcript,
                            "words": words,
                            "word_count": len(words),
                            "duration_s": duration,
                            "simulated": False,
                            "latency_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
                        }

                return {"ok": False, "error": "No transcript returned", "transcript": ""}
        except Exception as e:
            log.warning(f"[cloner] Deepgram request failed: {e}")
            return {"ok": False, "error": str(e)[:200], "transcript": ""}

    # ── STEP 6: POST TO ZERNIO ──────────────────────────────────────

    async def syndicate_to_zernio(
        self, content_text: str, media_paths: Optional[List[str]] = None
    ) -> dict:
        """Post content (with optional media attachments) to Zernio.

        Creates a draft post. Actual platform delivery requires
        connected social accounts in Zernio.
        """
        result = {"posted": False, "channels_hit": 0}

        if not ZERNIO_API_KEY:
            self.stats["errors"] += 1
            return result

        import httpx
        headers = {
            "Authorization": f"Bearer {ZERNIO_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {"content": content_text}

        # If we have media files, note them (Zernio may support media upload)
        if media_paths:
            payload["_media"] = media_paths[:5]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{ZERNIO_BASE_URL}/posts",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code < 300:
                    self.stats["syndications"] += 1
                    result["posted"] = True
                    return result
                else:
                    body = resp.text[:200]
                    log.warning(f"[cloner] Zernio error {resp.status_code}: {body}")
                    self.stats["errors"] += 1
                    return result
        except Exception as e:
            log.warning(f"[cloner] Zernio POST failed: {e}")
            self.stats["errors"] += 1
            return result

    # ── PIPELINE: FULL CLONE ────────────────────────────────────────

    async def clone_content(
        self,
        url: str,
        account_id: str,
        platforms: Optional[List[str]] = None,
        transcode_format: Optional[str] = None,
        resolution: Optional[str] = None,
        studio_ops: Optional[List[Dict]] = None,
        generate_avatar: bool = False,
        avatar_voice: str = "default",
        studio: Optional[object] = None,  # Override injected studio from constructor
    ) -> dict:
        """End-to-end clone pipeline: info → download → transcode → transcribe → syndicate.

        Args:
            url: Source URL to clone from
            account_id: Account for entitlement/metering
            platforms: Target platforms for syndication
            transcode_format: Optional output format (mp4, webm, etc.)
            resolution: Optional output resolution
            studio_ops: Optional OmniStudio video editing operations (trim, text, speed, overlay, captions)
            generate_avatar: If True, generate AI avatar video from transcript
            avatar_voice: TTS voice for avatar (default, male_1, female_1, narration)
            studio: OmniStudio instance for video editing/avatar generation

        Returns:
            dict with full pipeline results
        """
        pipeline_start = datetime.now(timezone.utc)
        pipeline_result = {
            "ok": False,
            "url": url,
            "steps": {},
            "total_latency_ms": 0,
        }

        # 1. Entitlement
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["errors"] += 1
            return {**pipeline_result, "error": entitlement.get("error", "Access denied"),
                    "step": "entitlement", "account_id": account_id}

        # 2. Extract info (in thread pool to avoid blocking event loop)
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, self.extract_info, url)
        pipeline_result["steps"]["info"] = info
        if not info.get("ok"):
            return {**pipeline_result, "error": info.get("error", "Info extraction failed"),
                    "step": "info_extraction"}

        # 3. Download
        download_result = await self.download_media(url)
        pipeline_result["steps"]["download"] = download_result
        if not download_result.get("ok"):
            return {**pipeline_result, "error": download_result.get("error", "Download failed"),
                    "step": "download"}

        video_path = download_result.get("file_path", "")
        thumbnail_path = download_result.get("thumbnail_file", "")

        # 4. Generate thumbnail (if not auto-downloaded)
        if not thumbnail_path and video_path:
            thumb_result = await self.generate_thumbnail(video_path)
            pipeline_result["steps"]["thumbnail"] = thumb_result
            if thumb_result.get("ok"):
                thumbnail_path = thumb_result.get("thumbnail_path", "")
        else:
            pipeline_result["steps"]["thumbnail"] = {"ok": True, "source": "auto_downloaded"}

        # 5. Optional transcode
        if transcode_format and video_path:
            transcode_result = await self.transcode(
                video_path, output_format=transcode_format, resolution=resolution
            )
            pipeline_result["steps"]["transcode"] = transcode_result
            if transcode_result.get("ok"):
                video_path = transcode_result.get("output_path", video_path)

        # 6. Transcribe
        if video_path:
            transcribe_result = await self.transcribe_video(video_path)
            pipeline_result["steps"]["transcribe"] = transcribe_result

        # Resolve studio (constructor-injected or explicitly passed)
        resolved_studio = studio or self.studio

        # 7. OmniStudio video editing (optional) — trim, text overlay, speed, captions, etc.
        if studio_ops and resolved_studio and video_path:
            edit_result = await resolved_studio.edit_video(video_path, studio_ops)
            pipeline_result["steps"]["studio_edit"] = edit_result
            if edit_result.get("ok") and edit_result.get("output_path"):
                video_path = edit_result["output_path"]
                self.stats["media_count"] += len(studio_ops)

        # 8. AI Avatar generation (optional)
        if generate_avatar and resolved_studio:
            transcript_text = pipeline_result.get("steps", {}).get("transcribe", {}).get("transcript", "")
            avatar_script = transcript_text or info.get("title", "Cloned content")
            avatar_result = await resolved_studio.generate_avatar(
                avatar_script, voice=avatar_voice, mode="still"
            )
            pipeline_result["steps"]["avatar"] = avatar_result

        # 9. Syndicate
        if platforms:
            # Build content from transcript + metadata
            title = info.get("title", "Cloned content")
            transcript = pipeline_result.get("steps", {}).get("transcribe", {}).get("transcript", "")
            syndication_text = (
                f"📦 CLONED: {title}\n\n"
                f"Source: {url}\n"
                f"Platform: {info.get('platform', 'unknown')}\n"
                f"Uploader: {info.get('uploader', 'unknown')}\n"
                f"Views: {info.get('view_count', 0):,}\n"
            )
            if transcript and not pipeline_result.get("steps", {}).get("transcribe", {}).get("simulated"):
                syndication_text += f"\n📝 Transcript:\n{transcript[:500]}\n"

            media_for_syndication = [p for p in [video_path, thumbnail_path] if p]
            syndicate_result = await self.syndicate_to_zernio(
                syndication_text, media_paths=media_for_syndication
            )
            pipeline_result["steps"]["syndicate"] = syndicate_result

        # 10. Log usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "omni_cloner", "clone_pipeline",
                               quantity=1, metadata={
                                   "url": url[:100],
                                   "platform": info.get("platform", ""),
                                   "title": info.get("title", "")[:100],
                                   "platforms": platforms or [],
                               })
            except Exception:
                pass

        # 11. Log to ledger
        self._log_ledger(account_id, url, info.get("platform", ""))

        elapsed = int((datetime.now(timezone.utc) - pipeline_start).total_seconds() * 1000)
        pipeline_result["ok"] = True
        pipeline_result["total_latency_ms"] = elapsed
        return pipeline_result

    # ── LEDGER LOGGING ──────────────────────────────────────────────

    def _log_ledger(self, account_id: str, url: str, platform: str):
        """Insert a row into the customer_usage_ledger table."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute(
                """INSERT INTO customer_usage_ledger
                   (transaction_id, customer_account_id, api_endpoint_accessed,
                    computed_raw_cost, client_billed_amount, metadata)
                   VALUES (hex(randomblob(16)), ?, '/api/v6/omni/clone', ?, ?, ?)""",
                (
                    account_id,
                    0.005,  # raw cost per clone pipeline
                    0.15,   # flat $0.15 per clone
                    json.dumps({"url": url[:100], "platform": platform}),
                ),
            )
            conn.commit()
        except Exception as e:
            log.debug(f"[cloner] ledger log skipped: {e}")
        finally:
            conn.close()

    # ── STATS ───────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            **self.stats,
            "yt_dlp_version": self._ydl_version,
            "ffmpeg_available": bool(shutil.which("ffmpeg")),
            "deepgram_configured": bool(DEEPGRAM_API_KEY),
            "zernio_configured": bool(ZERNIO_API_KEY),
            "media_directory": str(MEDIA_DIR),
            "media_directory_size": _dir_size(MEDIA_DIR),
        }

    def cleanup(self, max_age_hours: int = 24) -> int:
        """Remove downloaded media older than max_age_hours. Returns count removed."""
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        removed = 0
        for item in MEDIA_DIR.iterdir():
            if item.is_dir():
                # Check directory modification time
                mtime = item.stat().st_mtime
                if mtime < cutoff:
                    shutil.rmtree(item, ignore_errors=True)
                    removed += 1
            elif item.is_file():
                mtime = item.stat().st_mtime
                if mtime < cutoff:
                    item.unlink(missing_ok=True)
                    removed += 1
        if removed:
            log.info(f"[cloner] cleanup removed {removed} items older than {max_age_hours}h")
        return removed


# ── ROUTES ────────────────────────────────────────────────────────────

class OmniClonerRoutes:
    """Wire OmniCloner endpoints into the FastAPI app."""

    def __init__(self, cloner: OmniCloner, require_auth: Optional[Callable] = None):
        self.cloner = cloner
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Query
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel

        class ClonePayload(BaseModel):
            url: str
            account_id: str
            platforms: Optional[list[str]] = None
            transcode_format: Optional[str] = None
            resolution: Optional[str] = None
            studio_ops: Optional[list[dict]] = None
            generate_avatar: Optional[bool] = False
            avatar_voice: Optional[str] = "default"

        class DownloadPayload(BaseModel):
            url: str
            account_id: str
            extract_audio: bool = False
            format_spec: Optional[str] = None

        @app.post("/api/v6/omni/clone")
        async def clone_endpoint(
            payload: ClonePayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """End-to-end clone: download → transcode → transcribe → syndicate.

            Body: {
                url: "https://www.youtube.com/watch?v=...",
                account_id: "client_alpha",
                platforms?: ["twitter", "linkedin"],
                transcode_format?: "mp4",
                resolution?: "720"
            }
            """
            result = await self.cloner.clone_content(
                url=payload.url.strip(),
                account_id=payload.account_id.strip(),
                platforms=payload.platforms,
                transcode_format=payload.transcode_format,
                resolution=payload.resolution,
                studio_ops=payload.studio_ops,
                generate_avatar=payload.generate_avatar,
                avatar_voice=payload.avatar_voice,
            )
            status = 200 if result.get("ok") else 400
            return JSONResponse(result, status_code=status)

        @app.post("/api/v6/omni/download")
        async def download_endpoint(
            payload: DownloadPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Download media from URL. Returns file info and metadata.

            Body: {
                url: "https://www.tiktok.com/@user/video/...",
                account_id: "client_alpha",
                extract_audio?: false,
                format_spec?: "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
            }
            """
            result = await self.cloner.download_media(
                url=payload.url.strip(),
                format_spec=payload.format_spec or "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
                extract_audio=payload.extract_audio,
            )
            status = 200 if result.get("ok") else 400
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/omni/info")
        async def info_endpoint(
            url: str = Query(..., description="Source URL to extract metadata from"),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Extract rich metadata from a URL without downloading.

            Returns: title, description, duration, uploader, view_count,
            thumbnails, formats, platform detection, and more.
            """
            # Run in thread pool to not block the event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self.cloner.extract_info, url.strip())
            status = 200 if result.get("ok") else 400
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/omni/cloner/stats")
        async def cloner_stats(
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """OmniCloner pipeline stats."""
            return JSONResponse(self.cloner.snapshot())

        @app.post("/api/v6/omni/cloner/cleanup")
        async def cloner_cleanup(
            max_age_hours: int = 24,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Clean up downloaded media older than N hours."""
            removed = self.cloner.cleanup(max_age_hours=max_age_hours)
            return JSONResponse({"removed": removed, "max_age_hours": max_age_hours})

        log.info("[omni-cloner] Routes registered · /api/v6/omni/clone*")


# ── HELPERS ───────────────────────────────────────────────────────────

def _format_bytes(size: int) -> str:
    """Format bytes to human-readable string."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 ** 3:
        return f"{size / 1024 ** 2:.1f} MB"
    else:
        return f"{size / 1024 ** 3:.2f} GB"


def _format_duration(seconds: int) -> str:
    """Format seconds to HH:MM:SS or MM:SS."""
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _dir_size(path: Path) -> str:
    """Calculate total size of a directory."""
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return _format_bytes(total)


# ═════════════════════════════════════════════════════════════════════════
# STANDALONE APP (uvicorn port 8040)
# ═════════════════════════════════════════════════════════════════════════


def create_standalone_app() -> FastAPI:
    """Create a standalone FastAPI app with the cloner routes."""
    standalone = FastAPI(title="Empire AI · Omni Cloner", version="1.0.0")

    from fastapi.middleware.cors import CORSMiddleware
    standalone.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    cloner = OmniCloner()
    OmniClonerRoutes(cloner).register(standalone)

    @standalone.get("/")
    async def root():
        return {
            "service": "Empire AI Omni Cloner",
            "version": "1.0.0",
            "capabilities": [
                "Download video/audio from 1000+ sites",
                "Channel/playlist cloning",
                "Video transcoding (ffmpeg)",
                "Thumbnail generation",
                "Audio transcription (Deepgram)",
                "Cross-platform syndication (Zernio)",
            ],
            "endpoints": [
                "POST /api/v6/omni/clone       — Full clone pipeline",
                "POST /api/v6/omni/download     — Download media only",
                "GET  /api/v6/omni/info          — Extract metadata",
                "GET  /api/v6/omni/cloner/stats  — Cloner stats",
                "POST /api/v6/omni/cloner/cleanup — Cleanup old media",
            ],
        }

    return standalone


app = create_standalone_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("OMNI_CLONER_PORT", "8041"))
    host = os.environ.get("OMNI_CLONER_HOST", "0.0.0.0")
    log.info(f"[omni-cloner] Starting standalone on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
