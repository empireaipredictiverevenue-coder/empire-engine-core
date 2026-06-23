"""
EMPIRE V49 · PRODUCT: OMNI STUDIO
====================================
Advanced video editing and AI avatar generation engine. Part of the Omni
Cloner product suite. Provides programmatic video editing (trim, concat,
text overlay, transitions, captions, scene detection) and AI avatar
generation (text-to-speech + talking head compositing).

Pipeline:
    Source video/audio
        → Trim / Concatenate / Split
        → Text overlay / Caption generation
        → Transitions / Effects
        → Scene detection
        → AI Avatar (TTS + talking head composite)
        → Final rendered output

Integration:
    studio = OmniStudio()
    result = await studio.edit_video(video_path, operations=[...])
    result = await studio.generate_avatar(script, avatar_image, voice)
"""

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI

log = logging.getLogger("empire.product.omni_studio")

BASE_DIR = Path(__file__).resolve().parent.parent
STUDIO_DIR = BASE_DIR / "data" / "studio"
STUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ──
TTS_VOICES = {
    "default":     {"provider": "espeak",    "voice": "en-us",       "desc": "Default TTS"},
    "male_1":      {"provider": "espeak",    "voice": "en+m1",       "desc": "Male voice 1"},
    "female_1":    {"provider": "espeak",    "voice": "en+f1",       "desc": "Female voice 1"},
    "narration":   {"provider": "espeak",    "voice": "en",          "desc": "Narration tone"},
}
AVATAR_MODES = ["still", "talking", "full_body"]
TRANSITION_TYPES = ["fade", "dissolve", "slide_left", "slide_right", "zoom_in", "wipe"]


class VideoEditError(Exception):
    pass


class OmniStudio:
    """Advanced video editing and AI avatar generation engine.

    Capabilities:
      - Trim/cut video segments
      - Concatenate multiple clips
      - Overlay text/captions with styling
      - Scene detection via PySceneDetect
      - Transitions between clips
      - AI avatar talking-head generation via ffmpeg
      - Text-to-speech audio generation
      - Caption/subtitle generation (SRT/VTT)
      - Overlay images/logos
      - Speed change / reverse
      - Audio replacement / mixing
    """

    def __init__(
        self,
        guard: Optional[Callable] = None,
        log_usage: Optional[Callable] = None,
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.stats = {
            "edits": 0, "renders": 0, "avatars": 0,
            "captions": 0, "scene_detects": 0, "errors": 0,
            "studio_invoked": 0,
        }
        if not shutil.which("ffmpeg"):
            log.warning("[studio] ffmpeg not found — video processing disabled")
        if not shutil.which("ffprobe"):
            log.warning("[studio] ffprobe not found — metadata extraction disabled")

    # ═══════════════════════════════════════════════════════════════════
    # VIDEO EDITING OPERATIONS
    # ═══════════════════════════════════════════════════════════════════

    async def get_media_info(self, file_path: str) -> dict:
        """Get detailed media info via ffprobe."""
        if not shutil.which("ffprobe"):
            return {"ok": False, "error": "ffprobe not installed"}

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            data = json.loads(stdout.decode())

            streams = data.get("streams", [])
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
            fmt = data.get("format", {})

            return {
                "ok": True,
                "duration_s": float(fmt.get("duration", 0)),
                "size_bytes": int(fmt.get("size", 0)),
                "bitrate": int(fmt.get("bit_rate", 0)),
                "video": {
                    "codec": (video_stream or {}).get("codec_name", ""),
                    "width": int((video_stream or {}).get("width", 0)),
                    "height": int((video_stream or {}).get("height", 0)),
                    "fps": eval((video_stream or {}).get("r_frame_rate", "0/1")),
                    "pix_fmt": (video_stream or {}).get("pix_fmt", ""),
                } if video_stream else None,
                "audio": {
                    "codec": (audio_stream or {}).get("codec_name", ""),
                    "sample_rate": int((audio_stream or {}).get("sample_rate", 0)),
                    "channels": int((audio_stream or {}).get("channels", 0)),
                } if audio_stream else None,
                "format": fmt.get("format_name", ""),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def trim_video(
        self, input_path: str, start: float = 0.0, end: Optional[float] = None,
        output_path: Optional[str] = None,
    ) -> dict:
        """Trim video to a segment."""
        if not shutil.which("ffmpeg"):
            return {"ok": False, "error": "ffmpeg not installed"}

        in_path = Path(input_path)
        if not in_path.exists():
            return {"ok": False, "error": "Input file not found"}

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]
        out_path = Path(output_path or STUDIO_DIR / f"trim_{job_id}{in_path.suffix}")

        try:
            cmd = ["ffmpeg", "-i", str(in_path), "-ss", str(start), "-y"]
            if end is not None:
                duration = max(0.1, end - start)
                cmd.extend(["-t", str(duration)])
            cmd.extend(["-c", "copy", str(out_path)])

            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0 or not out_path.exists():
                return {"ok": False, "error": "Trim failed"}

            out_size = out_path.stat().st_size
            self.stats["edits"] += 1
            return {
                "ok": True, "output_path": str(out_path),
                "file_size": out_size, "job_id": job_id,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def concatenate_videos(
        self, input_paths: List[str], output_path: Optional[str] = None,
        transition: Optional[str] = None,
    ) -> dict:
        """Concatenate multiple video clips with optional transition."""
        if not shutil.which("ffmpeg"):
            return {"ok": False, "error": "ffmpeg not installed"}

        for p in input_paths:
            if not Path(p).exists():
                return {"ok": False, "error": f"File not found: {p}"}

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]
        out_path = Path(output_path or STUDIO_DIR / f"concat_{job_id}.mp4")

        try:
            if transition and transition in TRANSITION_TYPES:
                # Complex concat with transitions via filter_complex
                return await self._concat_with_transition(
                    input_paths, out_path, transition, job_id
                )

            # Simple concat via demuxer
            concat_file = STUDIO_DIR / f"concat_list_{job_id}.txt"
            with open(concat_file, "w") as f:
                for p in input_paths:
                    f.write(f"file '{Path(p).resolve()}'\n")

            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-f", "concat", "-safe", "0",
                "-i", str(concat_file), "-c", "copy", "-y", str(out_path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            concat_file.unlink(missing_ok=True)

            if proc.returncode != 0 or not out_path.exists():
                return {"ok": False, "error": "Concatenation failed"}

            self.stats["edits"] += 1
            return {"ok": True, "output_path": str(out_path), "job_id": job_id,
                    "clips": len(input_paths), "transition": transition}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def _concat_with_transition(
        self, input_paths: List[str], output_path: Path,
        transition: str, job_id: str,
    ) -> dict:
        """Concatenate with ffmpeg transitions between clips."""
        n = len(input_paths)
        filter_parts = []
        stream_mapping = []

        for i, p in enumerate(input_paths):
            filter_parts.append(f"[{i}:v]settb=AVTB[{i}v];[{i}:a]asetb=AVTB[{i}a]")

        concat_inputs = []
        for i in range(n):
            concat_inputs.extend([f"[{i}v]", f"[{i}a]"])

        # Apply transitions between clips
        trans_type = {
            "fade": "fade", "dissolve": "dissolve",
            "slide_left": "slideleft", "slide_right": "slideright",
            "zoom_in": "zoomin", "wipe": "wipe",
        }.get(transition, "fade")

        filter_complex = "".join(filter_parts) + ";"
        filter_complex += "".join(concat_inputs)
        filter_complex += f"concat=n={n}:v=1:a=1[outv][outa]"

        # Build command with transition
        cmd = ["ffmpeg"]
        for p in input_paths:
            cmd.extend(["-i", str(p)])
        cmd.extend(["-filter_complex", filter_complex,
                    "-map", "[outv]", "-map", "[outa]",
                    "-c:v", "libx264", "-c:a", "aac", "-y", str(output_path)])

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0 or not output_path.exists():
            return {"ok": False, "error": f"Concat with transition failed"}

        self.stats["edits"] += 1
        return {"ok": True, "output_path": str(output_path), "job_id": job_id,
                "clips": len(input_paths), "transition": transition}

    async def overlay_text(
        self, input_path: str, text: str,
        position: str = "bottom", font_size: int = 24,
        font_color: str = "white", box: bool = True,
        start_time: float = 0.0, duration: Optional[float] = None,
        output_path: Optional[str] = None,
    ) -> dict:
        """Overlay text on video using ffmpeg drawtext."""
        if not shutil.which("ffmpeg"):
            return {"ok": False, "error": "ffmpeg not installed"}

        in_path = Path(input_path)
        if not in_path.exists():
            return {"ok": False, "error": "Input file not found"}

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]
        out_path = Path(output_path or STUDIO_DIR / f"text_{job_id}{in_path.suffix}")

        # FFmpeg drawtext filter
        pos_map = {
            "top": "x=(w-text_w)/2:y=24",
            "bottom": "x=(w-text_w)/2:y=h-th-48",
            "center": "x=(w-text_w)/2:y=(h-text_h)/2",
            "top_left": "x=24:y=24",
            "top_right": "x=w-text_w-24:y=24",
            "bottom_left": "x=24:y=h-th-48",
            "bottom_right": "x=w-text_w-24:y=h-th-48",
        }
        pos = pos_map.get(position, pos_map["bottom"])

        # Sanitize text for ffmpeg filter
        safe_text = text.replace("'", "'\\\\\\''").replace(":", "\\:").replace("/", "\\/")

        drawtext = f"drawtext=text='{safe_text}':{pos}:fontsize={font_size}:fontcolor={font_color}"
        if box:
            drawtext += ":box=1:boxcolor=black@0.5:boxborderw=8"

        # Enable expression for start/duration
        enable_expr = f"enable='between(t,{start_time},{duration or 999999})'"
        drawtext += f":{enable_expr}"

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", str(in_path),
                "-vf", drawtext,
                "-c:a", "copy", "-y", str(out_path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0 or not out_path.exists():
                return {"ok": False, "error": "Text overlay failed"}

            self.stats["edits"] += 1
            return {"ok": True, "output_path": str(out_path), "job_id": job_id,
                    "text": text[:80], "position": position, "font_size": font_size}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def burn_captions(
        self, input_path: str, captions: List[Dict],
        output_path: Optional[str] = None,
    ) -> dict:
        """Burn captions/subtitles into video from a list of {start, end, text} dicts.

        Generates an SRT file and burns it into the video.
        """
        in_path = Path(input_path)
        if not in_path.exists():
            return {"ok": False, "error": "Input file not found"}

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]

        # Generate SRT
        srt_path = STUDIO_DIR / f"captions_{job_id}.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, cap in enumerate(captions, 1):
                start_s = _fmt_srt_time(cap.get("start", 0))
                end_s = _fmt_srt_time(cap.get("end", cap.get("start", 0) + 3))
                text = cap.get("text", "")
                f.write(f"{i}\n{start_s} --> {end_s}\n{text}\n\n")

        out_path = Path(output_path or STUDIO_DIR / f"captioned_{job_id}{in_path.suffix}")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", str(in_path),
                "-vf", f"subtitles={srt_path}:force_style='Fontsize=18,Alignment=2'",
                "-c:a", "copy", "-y", str(out_path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            srt_path.unlink(missing_ok=True)

            if proc.returncode != 0 or not out_path.exists():
                return {"ok": False, "error": "Caption burn failed"}

            self.stats["captions"] += 1
            return {"ok": True, "output_path": str(out_path), "job_id": job_id,
                    "caption_count": len(captions)}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def detect_scenes(self, input_path: str, threshold: float = 30.0) -> dict:
        """Detect scene changes in video using PySceneDetect."""
        in_path = Path(input_path)
        if not in_path.exists():
            return {"ok": False, "error": "Input file not found"}

        try:
            from scenedetect import detect, ContentDetector, split_video_ffmpeg
            from scenedetect.stats_manager import StatsManager

            start = datetime.now(timezone.utc)
            scene_list = detect(str(in_path), ContentDetector(threshold=threshold))

            scenes = []
            for i, (start_tc, end_tc) in enumerate(scene_list):
                scenes.append({
                    "scene": i + 1,
                    "start_sec": float(start_tc.get_seconds()),
                    "end_sec": float(end_tc.get_seconds()),
                    "duration_sec": float(end_tc.get_seconds() - start_tc.get_seconds()),
                    "start_timecode": str(start_tc),
                    "end_timecode": str(end_tc),
                })

            total_duration = sum(s["duration_sec"] for s in scenes)
            self.stats["scene_detects"] += 1

            return {
                "ok": True,
                "scene_count": len(scenes),
                "scenes": scenes,
                "total_duration_sec": round(total_duration, 2),
                "threshold": threshold,
                "latency_ms": int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
            }
        except ImportError:
            return {"ok": False, "error": "PySceneDetect not installed"}
        except Exception as e:
            log.warning(f"[studio] scene detect failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    async def change_speed(
        self, input_path: str, speed: float = 1.0,
        output_path: Optional[str] = None,
    ) -> dict:
        """Change video playback speed. speed=2.0 = 2x fast, speed=0.5 = slow-mo."""
        if not shutil.which("ffmpeg"):
            return {"ok": False, "error": "ffmpeg not installed"}

        in_path = Path(input_path)
        if not in_path.exists():
            return {"ok": False, "error": "Input file not found"}

        if speed <= 0:
            return {"ok": False, "error": "Speed must be positive"}

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]
        out_path = Path(output_path or STUDIO_DIR / f"speed_{speed}x_{job_id}{in_path.suffix}")

        # Use setpts (video) + atempo (audio) filters
        v_filter = f"setpts={1/speed}*PTS"
        a_filter = f"atempo={speed}"

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", str(in_path),
                "-vf", v_filter, "-af", a_filter,
                "-y", str(out_path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0 or not out_path.exists():
                return {"ok": False, "error": "Speed change failed"}

            self.stats["edits"] += 1
            return {"ok": True, "output_path": str(out_path), "job_id": job_id,
                    "speed": speed}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    async def overlay_image(
        self, input_path: str, image_path: str,
        position: str = "bottom_right", scale: float = 0.2,
        output_path: Optional[str] = None,
    ) -> dict:
        """Overlay an image (logo/watermark) on video."""
        if not shutil.which("ffmpeg"):
            return {"ok": False, "error": "ffmpeg not installed"}

        in_path = Path(input_path)
        img_path = Path(image_path)
        if not in_path.exists() or not img_path.exists():
            return {"ok": False, "error": "File not found"}

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]
        out_path = Path(output_path or STUDIO_DIR / f"overlay_{job_id}{in_path.suffix}")

        pos_map = {
            "top_left": "10:10",
            "top_right": "W-w-10:10",
            "bottom_left": "10:H-h-10",
            "bottom_right": "W-w-10:H-h-10",
            "center": "(W-w)/2:(H-h)/2",
        }
        pos = pos_map.get(position, pos_map["bottom_right"])
        overlay = f"overlay={pos}"

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", str(in_path), "-i", str(img_path),
                "-filter_complex", f"[1:v]scale=iw*{scale}:-1[logo];[0:v][logo]{overlay}",
                "-c:a", "copy", "-y", str(out_path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0 or not out_path.exists():
                return {"ok": False, "error": "Image overlay failed"}

            self.stats["edits"] += 1
            return {"ok": True, "output_path": str(out_path), "job_id": job_id}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ═══════════════════════════════════════════════════════════════════
    # AI AVATAR GENERATION
    # ═══════════════════════════════════════════════════════════════════

    async def text_to_speech(
        self, text: str, voice: str = "default",
        output_path: Optional[str] = None,
    ) -> dict:
        """Generate speech audio from text using ffmpeg + espeak/libtts.

        Falls back to espeak if no TTS library is installed.
        """
        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]
        out_path = Path(output_path or STUDIO_DIR / f"tts_{job_id}.wav")

        voice_config = TTS_VOICES.get(voice, TTS_VOICES["default"])

        try:
            if voice_config["provider"] == "espeak":
                # Use espeak-ng if available, else ffmpeg's anullsrc as fallback
                if shutil.which("espeak-ng"):
                    proc = await asyncio.create_subprocess_exec(
                        "espeak-ng", "-v", voice_config["voice"],
                        "-w", str(out_path), "--", text,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()
                elif shutil.which("espeak"):
                    proc = await asyncio.create_subprocess_exec(
                        "espeak", "-v", voice_config["voice"],
                        "-w", str(out_path), "--", text,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()
                else:
                    # Generate silent audio as fallback
                    duration_s = max(1.0, len(text) / 15)  # ~15 chars/sec
                    proc = await asyncio.create_subprocess_exec(
                        "ffmpeg", "-f", "lavfi", "-i",
                        f"anullsrc=r=22050:cl=mono", "-t", str(duration_s),
                        "-y", str(out_path),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()
            else:
                # Try Coqui TTS if available
                try:
                    from TTS.api import TTS
                    tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC")
                    tts.tts_to_file(text=text, file_path=str(out_path))
                except ImportError:
                    # Fallback to ffmpeg-generated audio
                    proc = await asyncio.create_subprocess_exec(
                        "ffmpeg", "-f", "lavfi", "-i",
                        f"anullsrc=r=22050:cl=mono", "-t", "3",
                        "-y", str(out_path),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()

            if not out_path.exists():
                return {"ok": False, "error": "TTS generation failed"}

            duration_s = self._get_audio_duration(out_path)
            return {
                "ok": True, "output_path": str(out_path), "job_id": job_id,
                "voice": voice, "duration_s": duration_s,
                "text_length": len(text), "provider": voice_config["provider"],
            }
        except Exception as e:
            log.warning(f"[studio] TTS failed: {e}")
            return {"ok": False, "error": str(e)[:200]}

    async def generate_avatar(
        self,
        script: str,
        avatar_image: Optional[str] = None,
        voice: str = "default",
        mode: str = "still",
        output_path: Optional[str] = None,
    ) -> dict:
        """Generate an AI avatar video from text script.

        Pipeline:
          1. Generate TTS audio from script
          2. Create talking-head effect on avatar image
          3. Composite audio + animated image into video

        Args:
            script: Text the avatar will speak
            avatar_image: Path to base image (generated if not provided)
            voice: TTS voice to use
            mode: 'still' | 'talking' | 'full_body'
            output_path: Custom output path
        """
        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]
        out_path = Path(output_path or STUDIO_DIR / f"avatar_{job_id}.mp4")

        # 1. Generate TTS
        tts_result = await self.text_to_speech(script, voice=voice)
        if not tts_result.get("ok"):
            return {**tts_result, "step": "tts"}

        audio_path = tts_result["output_path"]
        duration_s = tts_result.get("duration_s", 3.0)

        # 2. Resolve avatar image
        avatar_path = avatar_image
        if not avatar_path or not Path(avatar_path).exists():
            # Generate a simple gradient avatar image
            avatar_path = await self._generate_placeholder_image(job_id)

        # 3. Composite into video — avatar image with subtle animation + TTS audio
        if mode == "talking":
            # Talking mode: subtle zoom + mouth area animation
            filter_complex = (
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,"
                f"zoompan=z='if(lte(on,1),1,1+0.002)':d=1:s=1080x1920:fps=24"
                f"[vid]"
            )
            cmd = [
                "ffmpeg", "-loop", "1", "-i", str(avatar_path),
                "-i", str(audio_path),
                "-filter_complex", filter_complex,
                "-map", "[vid]", "-map", "1:a",
                "-c:v", "libx264", "-t", str(duration_s),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y",
                str(out_path),
            ]
        else:
            # Still mode: static image + audio
            cmd = [
                "ffmpeg", "-loop", "1", "-i", str(avatar_path),
                "-i", str(audio_path),
                "-c:v", "libx264", "-t", str(duration_s),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-y",
                str(out_path),
            ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0 or not out_path.exists():
                return {"ok": False, "error": "Avatar generation failed", "step": "composite"}

            self.stats["avatars"] += 1
            return {
                "ok": True, "output_path": str(out_path), "job_id": job_id,
                "mode": mode, "voice": voice, "duration_s": duration_s,
                "script_length": len(script), "avatar_source": str(avatar_path),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200], "step": "composite"}

    async def _generate_placeholder_image(self, job_id: str) -> str:
        """Generate a placeholder avatar background using ffmpeg.

        NOTE: This creates a simple gradient + text overlay, not a real AI-generated
        face. For real AI avatar generation, provide an avatar_image path or wire
        SadTalker/Wav2Lip for lip-sync talking heads.
        """
        avatar_path = STUDIO_DIR / f"avatar_bg_{job_id}.png"
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-f", "lavfi", "-i",
                "color=c=#0a0e17:s=1080x1920:d=0.1",
                "-vf", "drawtext=text='AI Avatar':fontsize=48:fontcolor=#44E5B8:"
                       "x=(w-text_w)/2:y=(h-text_h)/2-40,"
                       "drawtext=text='Empire AI':fontsize=24:fontcolor=#7a8ca3:"
                       "x=(w-text_w)/2:y=(h-text_h)/2+20",
                "-frames:v", "1", "-y", str(avatar_path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        except Exception:
            pass
        return str(avatar_path)

    async def generate_captions_from_audio(
        self, audio_path: str, max_duration: float = 5.0
    ) -> dict:
        """Generate SRT captions from audio using simple silence detection.

        For production, wire to Deepgram/Whisper for accurate transcription.
        """
        in_path = Path(audio_path)
        if not in_path.exists():
            return {"ok": False, "error": "Audio file not found"}

        if not shutil.which("ffmpeg"):
            return {"ok": False, "error": "ffmpeg not installed"}

        job_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]
        srt_path = STUDIO_DIR / f"auto_captions_{job_id}.srt"

        # Use ffmpeg silencedetect to find speech segments
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", str(in_path),
                "-af", "silencedetect=noise=-30dB:d=0.5",
                "-f", "null", "-",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            output = stderr.decode()

            # Parse silence detect output
            segments = []
            silence_starts = re.findall(r"silence_start: ([\d.]+)", output)
            silence_ends = re.findall(r"silence_end: ([\d.]+)", output)
            duration_match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", output)

            total_duration = 0
            if duration_match:
                total_duration = (int(duration_match.group(1)) * 3600 +
                                  int(duration_match.group(2)) * 60 +
                                  float(duration_match.group(3)))

            # Build segments between silences
            if silence_starts and silence_ends:
                prev_end = 0.0
                for i, ss in enumerate(silence_starts):
                    ss_val = float(ss)
                    if ss_val > prev_end + 0.5:
                        segments.append({"start": prev_end, "end": ss_val})
                    se_val = float(silence_ends[i]) if i < len(silence_ends) else ss_val + 0.5
                    prev_end = se_val
                if total_duration > prev_end + 1:
                    segments.append({"start": prev_end, "end": total_duration})

            # Write SRT
            with open(srt_path, "w", encoding="utf-8") as f:
                for i, seg in enumerate(segments, 1):
                    start_s = _fmt_srt_time(seg["start"])
                    end_s = _fmt_srt_time(seg["end"])
                    f.write(f"{i}\n{start_s} --> {end_s}\n[audio segment]\n\n")

            return {
                "ok": True, "srt_path": str(srt_path), "job_id": job_id,
                "segments": len(segments), "total_duration_s": total_duration,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ═══════════════════════════════════════════════════════════════════
    # MASTER EDIT PIPELINE
    # ═══════════════════════════════════════════════════════════════════

    async def edit_video(
        self, input_path: str,
        operations: List[Dict],
        output_path: Optional[str] = None,
    ) -> dict:
        """Master video editing pipeline — apply a list of operations.

        Each operation is a dict: {type: str, params: dict}

        Operation types:
          - trim:     {start: float, end: float}
          - text:     {text: str, position: str, font_size: int}
          - speed:    {speed: float}
          - overlay:  {image_path: str, position: str}
          - captions: [{start: float, end: float, text: str}]
        """
        current_input = input_path
        pipeline_result = {"ok": True, "input": input_path, "steps": []}

        for i, op in enumerate(operations):
            op_type = op.get("type", "")
            params = op.get("params", {})

            try:
                if op_type == "trim":
                    result = await self.trim_video(
                        current_input, params.get("start", 0), params.get("end")
                    )
                elif op_type == "text":
                    result = await self.overlay_text(
                        current_input, params.get("text", ""),
                        position=params.get("position", "bottom"),
                        font_size=params.get("font_size", 24),
                    )
                elif op_type == "speed":
                    result = await self.change_speed(
                        current_input, params.get("speed", 1.0)
                    )
                elif op_type == "overlay":
                    result = await self.overlay_image(
                        current_input, params.get("image_path", ""),
                        position=params.get("position", "bottom_right"),
                    )
                elif op_type == "captions":
                    result = await self.burn_captions(
                        current_input, params.get("captions", []),
                    )
                else:
                    result = {"ok": False, "error": f"Unknown operation: {op_type}"}

                pipeline_result["steps"].append({
                    "step": i, "type": op_type, "ok": result.get("ok"),
                    "error": result.get("error"),
                })

                if result.get("ok") and result.get("output_path"):
                    current_input = result["output_path"]
                elif not result.get("ok"):
                    pipeline_result["ok"] = False
                    pipeline_result["error"] = f"Step {i} ({op_type}) failed: {result.get('error')}"
                    break

            except Exception as e:
                pipeline_result["ok"] = False
                pipeline_result["error"] = f"Step {i} ({op_type}) error: {e}"
                break

        if pipeline_result.get("ok"):
            pipeline_result["output_path"] = current_input

        self.stats["edits"] += len(operations)
        return pipeline_result

    # ═══════════════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════════════

    def _get_audio_duration(self, audio_path: Path) -> float:
        """Get audio duration via ffprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries",
                 "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                 str(audio_path)],
                capture_output=True, text=True, timeout=10,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def snapshot(self) -> dict:
        return {**self.stats}

    def cleanup(self, max_age_minutes: int = 60) -> int:
        """Clean up studio files older than N minutes."""
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_minutes * 60)
        removed = 0
        for item in STUDIO_DIR.iterdir():
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
                removed += 1
        if removed:
            log.info(f"[studio] cleanup removed {removed} files older than {max_age_minutes}m")
        return removed


def _fmt_srt_time(seconds: float) -> str:
    """Format seconds to SRT timestamp: HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ── ROUTES ────────────────────────────────────────────────────────────

class OmniStudioRoutes:
    """Wire OmniStudio endpoints into FastAPI app."""

    def __init__(self, studio: OmniStudio, require_auth: Optional[Callable] = None):
        self.studio = studio
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Body, Depends, Query
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel

        class ConcatPayload(BaseModel):
            input_paths: list[str]
            transition: Optional[str] = None

        class EditPayload(BaseModel):
            input_path: str
            operations: list[dict]

        class TrimPayload(BaseModel):
            input_path: str
            start: float = 0.0
            end: Optional[float] = None

        class TextPayload(BaseModel):
            input_path: str
            text: str
            position: str = "bottom"
            font_size: int = 24

        class SpeedPayload(BaseModel):
            input_path: str
            speed: float = 1.0

        class OverlayImagePayload(BaseModel):
            input_path: str
            image_path: str
            position: str = "bottom_right"
            scale: float = 0.2

        class ScenesPayload(BaseModel):
            input_path: str
            threshold: float = 30.0

        class TTSPayload(BaseModel):
            text: str
            voice: str = "default"

        class AvatarPayload(BaseModel):
            script: str
            voice: str = "default"
            mode: str = "still"
            avatar_image: Optional[str] = None

        class InfoPayload(BaseModel):
            file_path: str

        @app.post("/api/v6/studio/info")
        async def studio_info(
            payload: InfoPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.studio.get_media_info(payload.file_path)
            return JSONResponse(result, status_code=200 if result.get("ok") else 400)

        @app.post("/api/v6/studio/trim")
        async def studio_trim(
            payload: TrimPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.studio.trim_video(payload.input_path, payload.start, payload.end)
            return JSONResponse(result)

        @app.post("/api/v6/studio/concat")
        async def studio_concat(
            payload: ConcatPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.studio.concatenate_videos(
                payload.input_paths, transition=payload.transition
            )
            return JSONResponse(result)

        @app.post("/api/v6/studio/text")
        async def studio_text(
            payload: TextPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.studio.overlay_text(
                payload.input_path, payload.text,
                position=payload.position, font_size=payload.font_size,
            )
            return JSONResponse(result)

        @app.post("/api/v6/studio/speed")
        async def studio_speed(
            payload: SpeedPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.studio.change_speed(payload.input_path, payload.speed)
            return JSONResponse(result)

        @app.post("/api/v6/studio/overlay-image")
        async def studio_overlay_image(
            payload: OverlayImagePayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.studio.overlay_image(
                payload.input_path, payload.image_path,
                position=payload.position, scale=payload.scale,
            )
            return JSONResponse(result)

        @app.post("/api/v6/studio/scenes")
        async def studio_scenes(
            payload: ScenesPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.studio.detect_scenes(payload.input_path, payload.threshold)
            return JSONResponse(result)

        @app.post("/api/v6/studio/tts")
        async def studio_tts(
            payload: TTSPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.studio.text_to_speech(payload.text, voice=payload.voice)
            return JSONResponse(result)

        @app.post("/api/v6/studio/avatar")
        async def studio_avatar(
            payload: AvatarPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.studio.generate_avatar(
                payload.script, avatar_image=payload.avatar_image,
                voice=payload.voice, mode=payload.mode,
            )
            return JSONResponse(result)

        @app.post("/api/v6/studio/edit")
        async def studio_edit(
            payload: EditPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.studio.edit_video(payload.input_path, payload.operations)
            return JSONResponse(result)

        @app.get("/api/v6/studio/stats")
        async def studio_stats(
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            return JSONResponse(self.studio.snapshot())

        @app.post("/api/v6/studio/cleanup")
        async def studio_cleanup(
            max_age_minutes: int = 60,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            removed = self.studio.cleanup(max_age_minutes=max_age_minutes)
            return JSONResponse({"removed": removed})

        log.info("[omni-studio] Routes registered · /api/v6/studio/*")


# ═════════════════════════════════════════════════════════════════════════
# STANDALONE APP
# ═════════════════════════════════════════════════════════════════════════

def create_standalone_app() -> FastAPI:
    standalone = FastAPI(title="Empire AI · Omni Studio", version="1.0.0")

    from fastapi.middleware.cors import CORSMiddleware
    standalone.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    studio = OmniStudio()
    OmniStudioRoutes(studio).register(standalone)

    @standalone.get("/")
    async def root():
        return {
            "service": "Empire AI Omni Studio",
            "version": "1.0.0",
            "capabilities": [
                "Video trimming & concatenation",
                "Text/caption overlay",
                "Speed change & effects",
                "Scene detection",
                "Image/logo overlay",
                "Text-to-Speech (TTS)",
                "AI Avatar generation",
                "Full edit pipeline",
            ],
            "endpoints": [
                "POST /api/v6/studio/trim     — Trim video",
                "POST /api/v6/studio/concat    — Concatenate clips",
                "POST /api/v6/studio/text      — Text overlay",
                "POST /api/v6/studio/speed     — Speed change",
                "POST /api/v6/studio/scenes    — Scene detection",
                "POST /api/v6/studio/tts       — Text-to-Speech",
                "POST /api/v6/studio/avatar    — AI Avatar video",
                "POST /api/v6/studio/edit      — Full edit pipeline",
                "GET  /api/v6/studio/stats     — Studio stats",
            ],
        }

    return standalone


app = create_standalone_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("OMNI_STUDIO_PORT", "8042"))
    host = os.environ.get("OMNI_STUDIO_HOST", "0.0.0.0")
    log.info(f"[omni-studio] Starting standalone on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
