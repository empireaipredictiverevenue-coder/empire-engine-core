"""
EMPIRE V49 · YOUTUBE SHORTS AGENT
===================================
Autonomous faceless YouTube Shorts creation for Empire AI's niches.

Pipeline:
  1. RESEARCH — Pull trending topics from storm/contractor niches via existing AI
  2. SCRIPT    — Generate short-form script (15-60s) optimized for Shorts
  3. VISUALS   — Create visual brief + generate/select assets
  4. RENDER    — Compose via Media Lab / mesh_studio_render (FFmpeg 1080×1920)
  5. PUBLISH   — Upload to YouTube via Data API v3 (requires API key)
  6. ANALYZE   — Track views, retention, iterate

Integrates with:
  - empire_media_lab.py   — Video rendering + design generation
  - empire_ai_router.py    — LLM script generation
  - mesh_studio_render.py  — FFmpeg video rendering
  - Skills Framework       — youtube.shorts.* skill namespace

Run modes:
  python3 -m bots.youtube_shorts_agent              # Dry-run (render local, no upload)
  python3 -m bots.youtube_shorts_agent --publish    # Full pipeline with YouTube upload
  python3 -m bots.youtube_shorts_agent --topic "How hail damages roofs"  # Specific topic
"""

import os
import sys
import json
import asyncio
import logging
import argparse
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")
except ImportError:
    pass

log = logging.getLogger("empire.youtube_shorts")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [youtube-shorts] %(levelname)s %(message)s",
)

# ── Config ───────────────────────────────────────────────────────────────
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "")

OUTPUT_DIR = REPO / "youtube_shorts_output"
OUTPUT_DIR.mkdir(exist_ok=True)

DEFAULT_VOICE = os.environ.get("YT_VOICE", "am_michael")  # Kokoro TTS voice

# Empire Media Engine — HeyGen-like video generation pipeline
MEDIA_ENGINE_DIR = os.environ.get("MEDIA_ENGINE_DIR", "/root/empire_media_engine")
MEDIA_ENGINE_SCRIPT = "render_pro.py"
MEDIA_ENGINE_AVAILABLE = os.path.exists(MEDIA_ENGINE_DIR) and os.path.exists(os.path.join(MEDIA_ENGINE_DIR, MEDIA_ENGINE_SCRIPT))

# Empire AI's core niches — content pillars for the channel
CONTENT_PILLARS = [
    {
        "id": "storm_education",
        "label": "Storm Education",
        "hooks": [
            "How hail forms and why your roof is at risk",
            "The real cost of ignoring storm damage",
            "3 signs your roof has hidden hail damage",
            "Why insurance claims get denied (and how to fix it)",
            "How AI predicts where the next storm will hit",
        ],
        "angle": "Educational — explains storm science, damage, and insurance",
    },
    {
        "id": "contractor_tips",
        "label": "Contractor Tips",
        "hooks": [
            "3 things every roofer should know about insurance claims",
            "How to get more leads without cold calling",
            "The contractor's guide to storm season prep",
            "Why top contractors use AI for lead gen",
            "How much money restoration contractors really make",
        ],
        "angle": "Value-driven — practical tips for contractors in storm restoration",
    },
    {
        "id": "case_studies",
        "label": "Case Studies & Social Proof",
        "hooks": [
            "This contractor made $12K from 1 SMS reply",
            "How we found 500 qualified leads in one week",
            "Real numbers: storm restoration ROI breakdown",
            "Before and after: contractor who switched to AI",
            "The referral fee that paid for a new truck",
        ],
        "angle": "Social proof — real results, real numbers, real contractors",
    },
    {
        "id": "industry_insights",
        "label": "Industry Insights",
        "hooks": [
            "The real cost of hail damage in DFW this year",
            "Why storm restoration is a $12B industry",
            "Insurance claim trends every contractor must know",
            "The future of property restoration is AI-powered",
            "Which US cities get the most hail damage?",
        ],
        "angle": "Thought leadership — data-driven industry analysis",
    },
    {
        "id": "behind_scenes",
        "label": "Behind the Scenes",
        "hooks": [
            "How AI detects storms in real-time",
            "The tech stack behind a modern lead gen platform",
            "How our contractors get leads before competitors",
            "The automated pipeline: storm → lead → dispatch",
            "Meet the AI that runs our lead generation",
        ],
        "angle": "Product marketing — show the technology and process",
    },
]

SHORTS_SCRIPT_TEMPLATE = """[HOOK - first 3 seconds, grab attention]
{hook}

[PROBLEM - 5-10 seconds]
{problem}

[SOLUTION - 10-20 seconds]
{solution}

[VISUAL CUE - key visual moment]
{visual_cue}

[CTA - last 3-5 seconds]
{cta}

---
Duration: ~{duration_seconds}s
Tone: {tone}
Tags: {tags}
"""


class YouTubeShortsAgent:
    """Autonomous YouTube Shorts creation agent.

    Args:
        get_db: Optional callable that returns a Supabase client.
               Used to access MediaLabAgent for rendering. If None,
               creates a standalone client when needed.
    """

    def __init__(self, get_db=None):
        self._get_db = get_db
        self._video_counter = 0
        self._generated_scripts: list[dict] = []
        self._rendered_videos: list[dict] = []

    # ── 1. RESEARCH ───────────────────────────────────────────────────

    async def research_topic(self, niche: str = "") -> dict:
        """Research a topic for a Shorts video based on Empire AI's content pillars.

        Returns a topic brief with hook, angle, and content pillar.
        """
        # Pick a random pillar, or filter by niche if specified
        pillars = CONTENT_PILLARS
        if niche:
            niche_lower = niche.lower()
            pillars = [p for p in pillars if
                       any(kw in niche_lower for kw in p["id"].split("_")) or
                       any(kw in niche_lower for kw in ["storm", "contractor", "roof", "restore", "insurance", "claim"])]
        if not pillars:
            pillars = CONTENT_PILLARS

        pillar = random.choice(pillars)
        hook = random.choice(pillar["hooks"])

        return {
            "pillar_id": pillar["id"],
            "label": pillar["label"],
            "hook": hook,
            "angle": pillar["angle"],
            "duration_seconds": random.choice([30, 45, 60]),
            "tone": random.choice(["educational", "urgent", "inspiring", "direct"]),
        }

    # ── 2. SCRIPT GENERATION ─────────────────────────────────────────

    async def generate_script(self, topic_brief: dict) -> dict:
        """Generate a complete Shorts script from a topic brief.

        Uses the AI Router when available, falls back to template-based generation.
        """
        hook = topic_brief["hook"]
        tone = topic_brief["tone"]
        duration = topic_brief["duration_seconds"]

        # Try AI Router for richer scripts (with timeout fallback)
        script = None
        try:
            from empire_ai_router import AIRouter
            router = AIRouter()
            system = (
                "You write YouTube Shorts scripts for Empire AI — a company that uses AI to "
                "detect storms and generate qualified leads for restoration contractors. "
                "Each script must be:\n"
                "- Under 60 seconds spoken (roughly 150 words for 60s)\n"
                "- Attention-grabbing first 3 seconds (the hook)\n"
                "- Clear problem → solution structure\n"
                "- Natural, conversational tone (not salesy)\n"
                "- End with a clear CTA: 'Visit empire-ai.co.uk to learn more'\n"
                f"Tone: {tone}\n"
                "Return as JSON with keys: hook, problem, solution, visual_cue, cta, tags (comma-separated)"
            )
            result = await asyncio.wait_for(
                router.generate_json(
                    prompt=f"Write a YouTube Shorts script about: {hook}. Duration: {duration}s.",
                    system=system,
                    task="youtube.shorts.script",
                    temperature=0.7,
                    max_tokens=600,
                ),
                timeout=8.0,  # Quick fallback if AI Router is slow/hung
            )
            if result and isinstance(result, dict) and result.get("hook"):
                script = result
        except Exception as e:  # includes asyncio.TimeoutError (subclass of Exception)
            log.warning(f"[youtube_shorts] AI Router unavailable for script: {e}")

        if not script:
            # Fallback template-based script
            script = self._template_script(topic_brief)

        script["hook"] = script.get("hook", hook)
        script["duration_seconds"] = duration
        script["tone"] = tone
        script["pillar_id"] = topic_brief["pillar_id"]
        script["generated_at"] = datetime.now(timezone.utc).isoformat()

        # Build full script text
        tags = script.get("tags", "storm damage, roof repair, insurance claim, contractor, AI lead gen")
        visual_cue = script.get("visual_cue", "Storm clouds rolling in over a neighborhood")
        script["full_text"] = SHORTS_SCRIPT_TEMPLATE.format(
            hook=script["hook"],
            problem=script.get("problem", "Most contractors miss storm damage opportunities because they don't find leads fast enough."),
            solution=script.get("solution", "Empire AI uses real-time weather data and AI to find qualified leads before your competitors. Contractors get SMS alerts the moment a storm hits their service area."),
            visual_cue=visual_cue,
            cta=script.get("cta", "Visit empire-ai.co.uk to start getting AI-qualified leads today."),
            duration_seconds=duration,
            tone=tone,
            tags=tags,
        )

        script["tags"] = tags
        self._generated_scripts.append(script)
        return script

    def _template_script(self, brief: dict) -> dict:
        """Generate a template-based script when AI is unavailable."""
        hook = brief["hook"]
        return {
            "hook": hook,
            "problem": "Most contractors miss out on storm damage leads because they can't detect opportunities fast enough. By the time they find out, competitors have already closed the deal.",
            "solution": "Empire AI's predictive technology scans weather data in real-time. When a storm hits your area, you get an SMS with a qualified lead within minutes. No cold calling. No guessing.",
            "visual_cue": "Animation of storm radar map with pins dropping on affected properties, then SMS notification appearing on a phone screen",
            "cta": "Visit empire-ai.co.uk and get your first 2 deals free. No contract. No risk.",
            "tags": "storm damage, roof repair, lead generation, contractor marketing, AI technology",
        }

    # ── 3. VISUAL BRIEF ──────────────────────────────────────────────

    async def create_visual_brief(self, script: dict) -> dict:
        """Create a visual production brief from a script."""
        hook = script.get("hook", "")
        visual_cue = script.get("visual_cue", "")

        # Generate background/visual style based on content pillar
        pillar = script.get("pillar_id", "storm_education")
        style_map = {
            "storm_education": {
                "bg_style": "Dark storm cloud time-lapse with lightning flashes",
                "text_color": "#FFFFFF",
                "accent_color": "#44E5B8",
                "footage_type": "storm clouds, lightning, rain on roof, damage inspection",
            },
            "contractor_tips": {
                "bg_style": "Contractor workspace with blueprints and tablet",
                "text_color": "#FFFFFF",
                "accent_color": "#5AC8FA",
                "footage_type": "contractors working, roof inspection, digital tablet, phone notifications",
            },
            "case_studies": {
                "bg_style": "Data dashboard with growth charts and numbers",
                "text_color": "#44E5B8",
                "accent_color": "#FFB800",
                "footage_type": "data visualization, charts, dollar signs, checkmarks",
            },
            "industry_insights": {
                "bg_style": "USA map with storm heat zones and statistics overlay",
                "text_color": "#FFFFFF",
                "accent_color": "#FF6B6B",
                "footage_type": "US map, weather radar, statistics, insurance documents",
            },
            "behind_scenes": {
                "bg_style": "Server room / AI visualization with neural network overlay",
                "text_color": "#5AC8FA",
                "accent_color": "#9945FF",
                "footage_type": "servers, code on screens, AI visualization, network diagrams",
            },
        }

        style = style_map.get(pillar, style_map["storm_education"])

        visual_brief = {
            "hook": hook,
            "visual_cue": visual_cue,
            "style": style,
            "resolution": "1080x1920",
            "format": "vertical_short",
            "duration_seconds": script.get("duration_seconds", 30),
            "text_overlays": [
                {"text": hook, "position": "center", "duration_seconds": 3, "font_size": 48, "animation": "fade_in"},
                {"text": "Empire AI", "position": "bottom", "duration_seconds": 5, "font_size": 32, "animation": "slide_up"},
            ],
            "use_stock_footage": True,
            "use_ai_overlay": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        return visual_brief

    # ── 4. RENDER ────────────────────────────────────────────────────

    async def _render_with_engine(self, script: dict, video_id: str,
                                    bg_video: str = "") -> Optional[str]:
        """Render a Shorts video using the Empire Media Engine (HeyGen-like).

        Calls render_pro.py via subprocess — same pattern as mesh_studio_render.py.
        Returns the output video path on success, None on failure.
        """
        if not MEDIA_ENGINE_AVAILABLE:
            log.warning("[youtube_shorts] Media Engine not available at %s", MEDIA_ENGINE_DIR)
            return None

        # Prepare script text for render_pro.py
        full_text = script.get("full_text", script.get("hook", ""))

        # Use provided bg video or default fallback from media engine templates
        bg_path = bg_video if bg_video else ""
        if not bg_path:
            # Let render_pro.py use its own fallback
            bg_arg = ""
        else:
            # Make path relative to media engine dir if it's inside it
            norm_bg = bg_path.rstrip("/")
            norm_dir = MEDIA_ENGINE_DIR.rstrip("/")
            if norm_bg.startswith(norm_dir + "/"):
                bg_arg = norm_bg[len(norm_dir) + 1:]
            elif norm_bg == norm_dir:
                bg_arg = ""
            else:
                bg_arg = bg_path

        cmd = ["python3", MEDIA_ENGINE_SCRIPT, bg_arg, full_text]
        output_path = str(OUTPUT_DIR / f"{video_id}.mp4")

        log.info(f"[youtube_shorts] Engine render: {video_id} via {' '.join(cmd)}")

        try:
            import subprocess
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                cwd=MEDIA_ENGINE_DIR,
                timeout=180,  # 3 min for TTS + WhisperX + FFmpeg
            )

            if proc.returncode == 0:
                # Copy the rendered video from media engine's builds dir to our output
                # Note: render_pro.py always writes to builds/reel_test.mp4.
                # Concurrent renders may conflict if two requests hit simultaneously
                # (sequential processing per call prevents race within a single run).
                engine_output = os.path.join(MEDIA_ENGINE_DIR, "builds", "reel_test.mp4")
                if os.path.exists(engine_output):
                    import shutil
                    shutil.copy2(engine_output, output_path)
                    log.info(f"[youtube_shorts] Engine render success: {output_path}")
                    return output_path
                else:
                    log.warning(f"[youtube_shorts] Engine rendered but output not found at {engine_output}")
                    return None
            else:
                stderr = (proc.stderr or "")[-500:]
                log.warning(f"[youtube_shorts] Engine render failed (code {proc.returncode}): {stderr}")
                return None

        except subprocess.TimeoutExpired:
            log.error(f"[youtube_shorts] Engine render timeout for {video_id}")
            return None
        except Exception as e:
            log.warning(f"[youtube_shorts] Engine render exception: {e}")
            return None

    async def render_short(self, script: dict, visual_brief: dict) -> dict:
        """Render a Shorts video using the best available renderer.

        Priority:
          1. Empire Media Engine (render_pro.py — HeyGen-like, Kokoro TTS + WhisperX + FFmpeg)
          2. Direct render_short.py (standalone TTS→WhisperX→FFmpeg pipeline)
          3. Media Lab Agent (empire_media_lab.py)
          4. Local spec file fallback (.md)
        """
        self._video_counter += 1
        video_id = f"YT-{self._video_counter:04d}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"

        output_path = None
        rendered_by = "none"
        full_text = script.get("full_text", script.get("hook", ""))

        def _file_exists(p: str) -> bool:
            return bool(p) and os.path.exists(p) and os.path.getsize(p) > 0

        # Priority 1: Empire Media Engine (HeyGen-like, Kokoro TTS + WhisperX captions)
        engine_path = await self._render_with_engine(script, video_id)
        if _file_exists(engine_path or ""):
            output_path = engine_path
            rendered_by = "engine"
            log.info(f"[youtube_shorts] Rendered via Empire Media Engine: {video_id}")

        # Priority 2: Direct render_short.py (proven, reliable standalone pipeline)
        if not _file_exists(output_path or ""):
            try:
                import subprocess as _sp
                render_short_py = str(REPO / "bots" / "render_short.py")
                if os.path.exists(render_short_py):
                    candidate_path = str(OUTPUT_DIR / f"{video_id}.mp4")
                    proc = await asyncio.to_thread(
                        _sp.run,
                        [
                            sys.executable, render_short_py,
                            full_text,
                            "--voice-provider", "kokoro",
                            "--output", candidate_path,
                        ],
                        capture_output=True,
                        text=True,
                        cwd=str(REPO),
                        timeout=180,
                    )
                    if proc.returncode == 0 and _file_exists(candidate_path):
                        output_path = candidate_path
                        rendered_by = "render_short.py"
                        log.info(f"[youtube_shorts] Rendered via render_short.py: {video_id}")
                    else:
                        log.warning(f"[youtube_shorts] render_short.py failed (code {proc.returncode})")
            except Exception as e:
                log.warning(f"[youtube_shorts] render_short.py unavailable: {e}")

        # Priority 3: Media Lab Agent fallback
        if not _file_exists(output_path or ""):
            try:
                from empire_media_lab import MediaLabAgent

                sb = None
                if self._get_db:
                    try:
                        sb = self._get_db()
                    except Exception:
                        pass
                if sb is None:
                    from supabase import create_client
                    sb_url = os.environ.get("SUPABASE_URL", "")
                    sb_key = os.getenv("SUPABASE_SERVICE_KEY", "")
                    sb = create_client(sb_url, sb_key) if sb_url and sb_key else None

                if sb:
                    ml = MediaLabAgent(get_db=lambda: sb)
                    result = await ml.render_video(
                        script=full_text,
                        niche=script.get("pillar_id", "storm_education"),
                        format_type="1080x1920",
                        voice=DEFAULT_VOICE,
                    )
                    if result.get("ok"):
                        job = result.get("job", {})
                        ml_path = job.get("output_url")
                        if ml_path and _file_exists(ml_path):
                            output_path = ml_path
                            rendered_by = "media_lab"
                            log.info(f"[youtube_shorts] Render delegated to Media Lab: {video_id}")
                        else:
                            log.warning(f"[youtube_shorts] Media Lab returned ok but file missing: {ml_path}")
            except Exception as e:
                log.warning(f"[youtube_shorts] Media Lab render unavailable: {e}")

        # Priority 4: Local spec file fallback
        if not _file_exists(output_path or ""):
            output_path = str(OUTPUT_DIR / f"{video_id}.md")
            with open(output_path, "w") as f:
                f.write(f"# YouTube Short: {video_id}\n\n")
                f.write(f"## Script\n\n{full_text}\n\n")
                f.write(f"## Visual Brief\n\n{json.dumps(visual_brief, indent=2)}\n\n")
                f.write(f"## Production Notes\n\n")
                f.write(f"- Voice: {DEFAULT_VOICE}\n")
                f.write(f"- Resolution: 1080x1920\n")
                f.write(f"- Duration: {script.get('duration_seconds', 30)}s\n")
                f.write(f"- Tags: {script.get('tags', '')}\n")
            rendered_by = "spec"
            log.info(f"[youtube_shorts] Render spec written to {output_path}")

        video_record = {
            "video_id": video_id,
            "script": script,
            "visual_brief": visual_brief,
            "output_path": output_path,
            "rendered": output_path and output_path.endswith(".mp4") and _file_exists(output_path),
            "rendered_by": rendered_by,
            "published": False,
            "publish_url": None,
            "rendered_at": datetime.now(timezone.utc).isoformat(),
        }
        self._rendered_videos.append(video_record)
        return video_record

    # ── 5. PUBLISH ───────────────────────────────────────────────────

    async def publish_short(self, video_record: dict) -> dict:
        """Publish a rendered Short to YouTube via Data API v3.

        Requires YOUTUBE_API_KEY, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET env vars.
        Currently a dry-run stub until API credentials are configured.
        """
        if not YOUTUBE_API_KEY:
            log.info("[youtube_shorts] No YOUTUBE_API_KEY — dry-run mode. Would publish:")
            log.info(f"  Title: {video_record['script']['hook']}")
            log.info(f"  Tags: {video_record['script']['tags']}")
            log.info(f"  File: {video_record['output_path']}")
            video_record["published"] = False
            video_record["publish_url"] = None
            return {
                "ok": False,
                "published": False,
                "reason": "YOUTUBE_API_KEY not configured. Set env vars and re-run with --publish",
                "dry_run_payload": {
                    "title": video_record["script"]["hook"],
                    "description": self._build_description(video_record["script"]),
                    "tags": video_record["script"].get("tags", "").split(", "),
                    "category": "22",  # People & Blogs
                    "privacy_status": "public" if os.environ.get("YT_PUBLIC") else "unlisted",
                },
            }

        # ── Full publish pipeline (requires YouTube Data API v3) ──
        # This would use google-auth + google-api-python-client
        # youtube = build('youtube', 'v3', credentials=creds)
        # body = { 'snippet': { ... }, 'status': { ... } }
        # media = MediaFileUpload(video_record['output_path'], chunksize=-1, resumable=True)
        # request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
        # response = request.execute()

        video_record["published"] = False
        video_record["publish_url"] = None

        return {
            "ok": False,
            "published": False,
            "reason": "YouTube API publish not yet wired. Install google-api-python-client and set up OAuth credentials.",
            "note": "See https://developers.google.com/youtube/v3/guides/uploading_a_video",
        }

    def _build_description(self, script: dict) -> str:
        """Build YouTube video description from script."""
        hook = script.get("hook", "")
        cta = script.get("cta", "")
        tags = script.get("tags", "")

        return (
            f"{hook}\\n\\n"
            f"{cta}\\n\\n"
            f"---\\n"
            f"Empire AI uses artificial intelligence to detect storms and deliver "
            f"qualified leads to restoration contractors. "
            f"Get started free at https://empire-ai.co.uk\\n\\n"
            f"#stormdamage #roofrepair #leadgeneration #contractor #airestoration\\n\\n"
            f"Tags: {tags}"
        )

    # ── FULL PIPELINE ────────────────────────────────────────────────

    async def run_pipeline(self, topic: str = "", niche: str = "",
                           publish: bool = False, count: int = 1) -> list[dict]:
        """Run the full Shorts creation pipeline 1 or more times.

        Args:
            topic: Specific topic/hook to use (optional)
            niche: Niche filter for content pillars (optional)
            publish: If True, attempt YouTube upload (requires API key)
            count: Number of Shorts to generate

        Returns:
            List of video records
        """
        results = []

        for i in range(count):
            log.info(f"=== Short {i+1}/{count} ===")

            # 1. Research
            if topic:
                topic_brief = {
                    "pillar_id": "custom",
                    "label": "Custom Topic",
                    "hook": topic,
                    "angle": "Custom",
                    "duration_seconds": 45,
                    "tone": "educational",
                }
            else:
                topic_brief = await self.research_topic(niche)
            log.info(f"Topic: {topic_brief['hook']} ({topic_brief['pillar_id']})")

            # 2. Script
            script = await self.generate_script(topic_brief)
            log.info(f"Script generated: {len(script.get('full_text', ''))} chars")

            # 3. Visual brief
            visual_brief = await self.create_visual_brief(script)
            log.info(f"Visual brief created: {visual_brief['style']['bg_style'][:60]}...")

            # 4. Render
            video = await self.render_short(script, visual_brief)
            log.info(f"Video rendered: {video['video_id']} → {video['output_path']}")

            # 5. Publish (only if --publish flag)
            if publish:
                pub_result = await self.publish_short(video)
                log.info(f"Publish: {'✓' if pub_result.get('published') else '✗'} {pub_result.get('reason', '')}")

            results.append(video)

        summary = {
            "generated": len(results),
            "rendered": sum(1 for v in results if v.get("rendered")),
            "published": sum(1 for v in results if v.get("published")),
            "output_dir": str(OUTPUT_DIR),
            "publish_mode": publish,
        }
        log.info(f"=== PIPELINE COMPLETE ===")
        log.info(f"Generated: {summary['generated']} | Rendered: {summary['rendered']} | Published: {summary['published']}")

        return results

    def snapshot(self) -> dict:
        """Return agent state snapshot."""
        return {
            "agent": "youtube_shorts_agent",
            "videos_generated": len(self._generated_scripts),
            "videos_rendered": len(self._rendered_videos),
            "videos_published": sum(1 for v in self._rendered_videos if v.get("published")),
            "output_dir": str(OUTPUT_DIR),
            "youtube_api_configured": bool(YOUTUBE_API_KEY),
            "content_pillars": [p["id"] for p in CONTENT_PILLARS],
            "last_run": datetime.now(timezone.utc).isoformat(),
        }


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="YouTube Shorts Agent — faceless short-form video creation")
    p.add_argument("--topic", type=str, default="", help="Specific topic/hook for the Short")
    p.add_argument("--niche", type=str, default="", help="Filter content pillars by niche keyword")
    p.add_argument("--publish", action="store_true", help="Attempt YouTube upload (requires API key)")
    p.add_argument("--count", type=int, default=1, help="Number of Shorts to generate")
    p.add_argument("--snapshot", action="store_true", help="Print agent state snapshot")
    args = p.parse_args()

    agent = YouTubeShortsAgent()

    if args.snapshot:
        print(json.dumps(agent.snapshot(), indent=2))
        return

    results = asyncio.run(agent.run_pipeline(
        topic=args.topic,
        niche=args.niche,
        publish=args.publish,
        count=args.count,
    ))

    print(f"\\n=== Results ===")
    print(f"Generated: {len(results)}")
    for v in results:
        print(f"  {v['video_id']}: {v['script']['hook'][:60]}...")
        print(f"    → {v['output_path']}")
    print()


if __name__ == "__main__":
    main()
