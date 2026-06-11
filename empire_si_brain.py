"""
EMPIRE V49 · SYNTHETIC INTELLIGENCE BRAIN
===========================================
End-to-end autonomous media pipeline:

   [Operator Command] → [Local LLM Brain] → [System Directory Audit]
        ^                                            |
        |              (Self-Correction)             v
   [Validation Log] ← [FFmpeg / Kokoro Rendering Engine]

Wire-up in hub.py:
    from empire_si_brain import SyntheticBrain, register_synthetic_routes
    synthetic_brain = SyntheticBrain(router=ai_router, base_dir=BASE_DIR)
    register_synthetic_routes(app, brain=synthetic_brain, require_auth=require_auth)

Dependencies:
    - kokoro_onnx (Kokoro TTS, ONNX runtime)
    - soundfile (WAV I/O)
    - ffmpeg (system binary)
    - Ollama running on localhost:11434 (via existing AIRouter)
"""

import os
import json
import asyncio
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger("empire.si.brain")


# ─────────────────────────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────────────────────────
class AGICommand(BaseModel):
    objective: str  # e.g., "Build a high-impact roofing ad for Atlanta. Use +18885551234."


# ─────────────────────────────────────────────────────────────────────
# SYNTHETIC BRAIN
# ─────────────────────────────────────────────────────────────────────
class SyntheticBrain:
    """
    Orchestrates the full autonomous media pipeline:
      1. Audit system assets (video templates on disk)
      2. Query local LLM for execution strategy
      3. Synthesize voiceover via Kokoro-ONNX TTS
      4. Assemble final video via native FFmpeg
      5. Self-correct: LLM quality-control pass on the output
    """

    def __init__(
        self,
        *,
        router=None,               # AIRouter instance
        base_dir: str = "",
        ffmpeg_bin: str = "ffmpeg",
        kokoro_model_path: str = "",
        kokoro_voices_path: str = "",
        max_correction_loops: int = 3,
    ):
        self.router = router          # AIRouter (Ollama dispatcher)
        self.ffmpeg_bin = ffmpeg_bin
        self.max_correction_loops = max_correction_loops

        base = Path(base_dir) if base_dir else Path(__file__).resolve().parent
        self.templates_dir = base / "templates" / "videos"
        self.output_dir = base / "builds" / "production_vault"

        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.kokoro_model_path = kokoro_model_path or str(base / "kokoro-v1.0.onnx")
        self.kokoro_voices_path = kokoro_voices_path or str(base / "voices-v1.0.bin")

        self.stats = {"runs": 0, "completed": 0, "failed": 0, "last_run_ts": None}

    # ── 1. SYSTEM DIRECTORY AUDIT ────────────────────────────────────
    def audit_assets(self) -> List[str]:
        """Scan local media templates so the brain knows what it can use."""
        assets = [f.name for f in self.templates_dir.glob("*.mp4")]
        log.info(f"[si.brain] asset audit: {len(assets)} templates found")
        return assets

    # ── 2. LOCAL LLM: FORMULATE STRATEGY ─────────────────────────────
    async def formulate_strategy(self, objective: str, available_assets: List[str], dream_wisdom: str = "") -> Dict[str, Any]:
        """Query the local LLM to produce an execution strategy from the objective + assets."""
        system = (
            "You are the Core Synthetic Brain for Empire AI. You analyze a business objective "
            "alongside available server assets, then output a strict execution strategy plan. "
            "Your response must be standard JSON containing exactly these keys: "
            "script_copy (max 3 punchy sentences), chosen_template (must pick from available assets list), "
            "target_phone, voice_profile ('am_michael' or 'af_sarah'), "
            "text_overlay_color ('yellow' or 'white'), canvas_format ('vertical', 'square', or 'widescreen')."
        )
        if dream_wisdom:
            system += f"\n\n{dream_wisdom}"
        prompt = (
            f"Objective: {objective}\n"
            f"Available System Templates: {json.dumps(available_assets)}"
        )

        if self.router:
            result = await self.router.generate_json(
                prompt=prompt,
                task="si.brain",
                system=system,
                temperature=0.3,
                max_tokens=300,
                context={"objective": objective[:100]},
            )
        else:
            # Fallback: direct Ollama chat via HTTP
            result = await self._ollama_chat_json(system, prompt)

        return result

    async def _ollama_chat_json(self, system: str, prompt: str) -> Dict[str, Any]:
        """Direct Ollama chat fallback when no AIRouter is wired."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": "llama3.2:3b",
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "format": "json",
                    },
                )
                r.raise_for_status()
                data = r.json()
                return json.loads(data["message"]["content"])
        except Exception as e:
            log.error(f"[si.brain] LLM chat failed: {e}")
            return {"_error": str(e), "script_copy": "Call us today for your properties needs."}

    # ── 3. KOKORO TTS: VOICEOVER SYNTHESIS ──────────────────────────
    def synthesize_voiceover(
        self, script: str, output_path: str, voice: str = "am_michael", speed: float = 1.1
    ) -> tuple[int, int]:
        """
        Generate WAV voiceover via Kokoro-ONNX.
        Returns (sample_count, sample_rate).
        """
        try:
            import soundfile as sf
            from kokoro_onnx import Kokoro

            kokoro = Kokoro(self.kokoro_model_path, self.kokoro_voices_path)
            samples, sample_rate = kokoro.create(script, voice=voice, speed=speed, lang="en-us")
            sf.write(output_path, samples, sample_rate)
            log.info(f"[si.brain] voiceover synthesized: {len(samples)} samples @ {sample_rate}Hz → {output_path}")
            return len(samples), sample_rate
        except ImportError as e:
            raise RuntimeError(f"Missing dependency: {e}. Install kokoro_onnx and soundfile.")
        except Exception as e:
            raise RuntimeError(f"Voice synthesis failed: {e}")

    # ── 4. FFMPEG: VIDEO ASSEMBLY ────────────────────────────────────
    def render_video(
        self,
        template_path: str,
        audio_path: str,
        output_path: str,
        phone: str = "Contact Us Now",
        color: str = "yellow",
        canvas_format: str = "vertical",
    ) -> bool:
        """
        Assemble final video: background template + voiceover + phone overlay.
        Supports vertical (1080x1920), square (1080x1080), widescreen (1920x1080).
        """
        # Resolve canvas dimensions
        if canvas_format == "vertical":
            scale_filter = "scale=1080:1920"
            canvas_dim = "1080x1920"
        elif canvas_format == "square":
            scale_filter = "scale=1080:1080"
            canvas_dim = "1080x1080"
        else:
            scale_filter = "scale=1920:1080"
            canvas_dim = "1920x1080"

        # Ensure template exists; generate a canvas if missing
        tp = Path(template_path)
        if not tp.exists():
            log.warning(f"[si.brain] template missing: {template_path} — generating {canvas_dim} canvas")
            subprocess.run(
                [
                    self.ffmpeg_bin, "-y", "-f", "lavfi",
                    "-i", f"color=c=black:s={canvas_dim}:d=8",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tp),
                ],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

        font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        if not os.path.exists(font_path):
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        if not os.path.exists(font_path):
            font_path = "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"

        cmd = [
            self.ffmpeg_bin, "-y",
            "-i", str(tp),
            "-i", str(audio_path),
            "-vf", (
                f"{scale_filter},drawtext=fontfile={font_path}:"
                f"text='{phone}':fontcolor={color}:fontsize=72:"
                f"box=1:boxcolor=black@0.7:x=(w-text_w)/2:y=h-350"
            ),
            "-c:v", "libx264", "-preset", "veryfast", "-shortest",
            str(output_path),
        ]

        log.info(f"[si.brain] rendering {canvas_format} video: {' '.join(cmd[:6])}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            log.error(f"[si.brain] FFmpeg error: {result.stderr[-300:]}")
            return False

        log.info(f"[si.brain] video rendered: {output_path} ({Path(output_path).stat().st_size} bytes)")
        return True

    # ── 5. SELF-CORRECTION: QUALITY CONTROL ──────────────────────────
    async def quality_check(self, script: str, output_path: str) -> Dict[str, Any]:
        """LLM-based quality control pass on the rendered output."""
        system = (
            "You are the Quality Control System for Empire AI. Review the compiled metrics "
            "and determine if the production generation passed successfully. "
            "Return JSON with: verified (true or false), diagnostic_log (brief statement)."
        )
        file_size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
        prompt = (
            f"Generated Script: {script} | "
            f"File Created: {Path(output_path).name} | "
            f"File Size: {file_size} bytes"
        )

        if self.router:
            result = await self.router.generate_json(
                prompt=prompt,
                task="si.quality",
                system=system,
                temperature=0.1,
                max_tokens=150,
            )
        else:
            # Fallback heuristic: file > 10KB = pass
            return {"verified": file_size > 10240, "diagnostic_log": f"Heuristic: {file_size} bytes output"}

        return result

    # ── MAIN PIPELINE (WITH SELF-CORRECTION LOOP) ───────────────────
    async def execute(self, objective: str, dream_wisdom: str = "") -> Dict[str, Any]:
        """
        Run the full autonomous media pipeline with self-correcting retries.
        If QC fails, feeds diagnostics back to the LLM and retries up to
        max_correction_loops times.
        """
        self.stats["runs"] += 1
        self.stats["last_run_ts"] = datetime.now(timezone.utc).isoformat()

        # Step 1: Audit system assets (once — doesn't change between attempts)
        available_templates = self.audit_assets()

        # Step 2: Formulate initial execution strategy via local LLM
        strategy = await self.formulate_strategy(objective, available_templates, dream_wisdom=dream_wisdom)
        if strategy.get("_error"):
            self.stats["failed"] += 1
            raise HTTPException(status_code=500, detail=strategy["_error"])

        # ── Self-correction retry loop ──────────────────────────────
        for attempt in range(1, self.max_correction_loops + 1):
            log.info(f"[si.brain] execution attempt {attempt}/{self.max_correction_loops}")

            script = strategy.get("script_copy", "Call us today for your properties needs.")
            template_filename = strategy.get("chosen_template")
            phone = strategy.get("target_phone", "Contact Us Now")
            voice = strategy.get("voice_profile", "am_michael")
            color = strategy.get("text_overlay_color", "yellow")
            canvas_fmt = strategy.get("canvas_format", "vertical")

            # Resolve template path
            template_path = (
                self.templates_dir / template_filename
                if template_filename
                else self.templates_dir / "roofing.mp4"
            )

            # Step 3: Synthesize voiceover via Kokoro TTS
            campaign_dir = self.output_dir / f"synthetic_{os.urandom(3).hex()}"
            campaign_dir.mkdir(parents=True, exist_ok=True)
            audio_path = campaign_dir / "voiceover.wav"

            try:
                self.synthesize_voiceover(script, str(audio_path), voice=voice)
            except Exception as e:
                self.stats["failed"] += 1
                if attempt < self.max_correction_loops:
                    log.warning(f"[si.brain] voice synthesis failed, retrying: {e}")
                    strategy = await self._correct_strategy(strategy, f"Voice synthesis failed: {e}", available_templates)
                    continue
                raise HTTPException(status_code=500, detail=f"Voice synthesis block failure: {str(e)}")

            # Step 4: Assemble video via FFmpeg
            output_video_path = campaign_dir / "rendered_output.mp4"
            success = await asyncio.to_thread(
                self.render_video,
                str(template_path), str(audio_path), str(output_video_path),
                phone=phone, color=color, canvas_format=canvas_fmt,
            )

            if not success:
                self.stats["failed"] += 1
                if attempt < self.max_correction_loops:
                    log.warning("[si.brain] FFmpeg render failed, retrying")
                    strategy = await self._correct_strategy(
                        strategy, "FFmpeg render returned non-zero exit code — check template and canvas format",
                        available_templates,
                    )
                    continue
                return {
                    "status": "FAILED",
                    "error": "FFmpeg render returned non-zero exit code",
                    "attempts": attempt,
                    "strategy": self._strategy_snapshot(strategy),
                    "meta": {
                        "script_executed": script,
                        "voice_profile": voice,
                        "canvas_format": canvas_fmt,
                        "system_template_used": str(template_path),
                    },
                }

            # Step 5: Self-correction quality control
            audit_result = await self.quality_check(script, str(output_video_path))
            passed = audit_result.get("verified", False)

            if passed:
                self.stats["completed"] += 1
                return {
                    "status": "COMPLETED",
                    "attempts": attempt,
                    "agent_diagnostics": audit_result.get("diagnostic_log", "No log provided"),
                    "strategy": self._strategy_snapshot(strategy),
                    "meta": {
                        "script_executed": script,
                        "voice_profile": voice,
                        "canvas_format": canvas_fmt,
                        "system_template_used": str(template_path),
                        "production_location": str(output_video_path),
                    },
                }

            # QC failed — self-correct and retry
            log.warning(
                f"[si.brain] QC failed (attempt {attempt}/{self.max_correction_loops}): "
                f"{audit_result.get('diagnostic_log', 'no diagnostics')}"
            )
            strategy = await self._correct_strategy(
                strategy,
                audit_result.get("diagnostic_log", "Quality check failed — adjust parameters"),
                available_templates,
            )

        # All attempts exhausted
        self.stats["failed"] += 1
        return {
            "status": "TERMINATED",
            "error": f"Max self-correction loops ({self.max_correction_loops}) exhausted without passing QC",
            "attempts": self.max_correction_loops,
            "strategy": self._strategy_snapshot(strategy),
            "meta": {
                "script_executed": script,
                "voice_profile": voice,
                "canvas_format": canvas_fmt,
                "system_template_used": str(template_path),
            },
        }

    # ── SELF-CORRECTION HELPER: RE-QUERY LLM WITH DIAGNOSTICS ────────
    async def _correct_strategy(
        self, previous_strategy: Dict[str, Any], failure_reason: str,
        available_templates: List[str] = None,
    ) -> Dict[str, Any]:
        """Feed failure diagnostics back to the LLM for a corrected strategy."""
        assets = available_templates or []
        system = (
            "You are the master self-correction layer for Empire AI's media pipeline. "
            "The previous strategy failed diagnostics. Analyze the failure reason, "
            "adjust the problematic keys, and output a corrected JSON configuration "
            "with the same keys: script_copy, chosen_template (pick ONLY from the available templates list), "
            "target_phone, voice_profile, text_overlay_color, canvas_format."
        )
        prompt = (
            f"Previous strategy: {json.dumps(previous_strategy)}\n"
            f"Failure reason: {failure_reason}\n"
            f"Available templates (choose from these): {json.dumps(assets)}"
        )

        if self.router:
            result = await self.router.generate_json(
                prompt=prompt,
                task="si.correct",
                system=system,
                temperature=0.3,
                max_tokens=300,
            )
        else:
            result = await self._ollama_chat_json(system, prompt)

        if result.get("_error"):
            log.warning(f"[si.brain] correction LLM call failed: {result.get('_error')}")
            return previous_strategy  # Keep the old strategy if correction fails
        return result

    # ── STRATEGY SNAPSHOT ───────────────────────────────────────────
    @staticmethod
    def _strategy_snapshot(strategy: Dict[str, Any]) -> Dict[str, Any]:
        """Return a clean subset of the strategy for the response payload."""
        return {
            "script_copy": strategy.get("script_copy"),
            "chosen_template": strategy.get("chosen_template"),
            "target_phone": strategy.get("target_phone"),
            "voice_profile": strategy.get("voice_profile"),
            "text_overlay_color": strategy.get("text_overlay_color"),
            "canvas_format": strategy.get("canvas_format", "vertical"),
        }


# ─────────────────────────────────────────────────────────────────────
# FASTAPI ROUTE REGISTRATION
# ─────────────────────────────────────────────────────────────────────
def register_synthetic_routes(
    app: FastAPI,
    *,
    brain: SyntheticBrain,
    require_auth: Callable,
    auth_engine=None,
):
    """Register /api/v1/synthetic/run on the FastAPI app."""

    @app.post("/api/v1/synthetic/run")
    async def synthetic_run(payload: AGICommand, auth: bool = Depends(require_auth)):
        """Execute the autonomous media pipeline from an operator command."""
        try:
            # Fetch latest dream wisdom for deeper context
            dream_wisdom = ""
            try:
                from empire_dream import get_latest_wisdom
                dream_wisdom = await get_latest_wisdom()
            except Exception:
                pass
            result = await brain.execute(payload.objective, dream_wisdom=dream_wisdom)

            # Audit trail: log the pipeline run outcome
            if auth_engine:
                _op_id = (auth.get("id") or "") if isinstance(auth, dict) else ""
                _op_name = (auth.get("name") or "operator") if isinstance(auth, dict) else "operator"
                _op_email = (auth.get("email") or "") if isinstance(auth, dict) else ""
                try:
                    await auth_engine.audit(
                        operator_id=_op_id,
                        operator_name=_op_name,
                        operator_email=_op_email,
                        action="synthetic_pipeline_run",
                        target_type="synthetic_brain",
                        target_id=result.get("meta", {}).get("production_location", ""),
                        details={
                            "status": result.get("status"),
                            "objective": payload.objective[:200],
                            "diagnostics": result.get("agent_diagnostics", "")[:200],
                            "script": result.get("meta", {}).get("script_executed", "")[:200],
                        },
                    )
                except Exception:
                    pass

            return result
        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[si.brain] pipeline error: {e}")
            return JSONResponse(
                {"status": "FAILED", "error": str(e)},
                status_code=500,
            )

    log.info("[si.brain] Route registered · POST /api/v1/synthetic/run")
