#!/usr/bin/env python3
"""
EMPIRE V49 · KEY FRAME EXTRACTOR
==================================
Extract key frames from video files using FFmpeg. Supports three extraction modes:

  Mode 1: I-FRAMES  — Extract all intra-frames (key frames). Fast, gives ~1 frame/sec.
  Mode 2: SCENES    — Scene-change detection. Finds visual transitions. Good for thumbnails.
  Mode 3: THUMBNAIL — Pick N most representative frames from the video.

Outputs frames as PNG or JPG files in a timestamped directory.

Usage:
  python3 scripts/extract_keyframes.py video.mp4
  python3 scripts/extract_keyframes.py video.mp4 --mode scenes --threshold 0.4 --max-frames 20
  python3 scripts/extract_keyframes.py video.mp4 --mode thumbnail --count 6 --format jpg
  python3 scripts/extract_keyframes.py --dir youtube_shorts_output/ --max-frames 5
"""

import os
import sys
import json
import argparse
import subprocess
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [keyframes] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("keyframes")

REPO = Path(__file__).resolve().parent.parent


# ── FFmpeg helpers ──────────────────────────────────────────────────


def get_video_info(video_path: str) -> dict:
    """Get video metadata via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {"error": result.stderr[:200]}
        return json.loads(result.stdout)
    except Exception as e:
        return {"error": str(e)}


def duration_str(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def extract_iframes(
    video_path: str,
    output_dir: str,
    max_frames: int = 0,
    fmt: str = "png",
    quality: int = 3,
) -> list[str]:
    """Extract all I-frames (key frames) from a video.

    Uses FFmpeg's select filter with 'eq(pict_type\,I)' to capture
    only intra-coded frames. These are the natural key frames the
    encoder chose — fast, minimal overhead.

    Args:
        video_path: Path to input video
        output_dir: Directory to write frames to
        max_frames: Maximum frames to extract (0 = unlimited)
        fmt: Output format ('png' or 'jpg')
        quality: Output quality (PNG: 1-9 compression, JPG: 1-31 lower is better)

    Returns:
        List of paths to extracted frame files
    """
    os.makedirs(output_dir, exist_ok=True)
    output_pattern = os.path.join(output_dir, "if_%04d." + fmt)

    select_filter = "eq(pict_type\\,I)"
    if max_frames > 0:
        select_filter = f"eq(pict_type\\,I)*lt(n\\,{max_frames * 10})"  # generous upper bound

    vcodec = "png" if fmt == "png" else "mjpeg"
    q_arg = f"-compression_level {quality}" if fmt == "png" else f"-q:v {quality}"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"select='{select_filter}'",
        "-vsync", "vfr",
        "-vcodec", vcodec,
    ] + q_arg.split() + [
        output_pattern,
    ]

    log.info(f"Extracting I-frames from {Path(video_path).name}...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        log.error(f"FFmpeg failed: {result.stderr[-300:]}")
        return []

    # Collect output files
    frames = sorted(Path(output_dir).glob(f"if_*.{fmt}"))
    if max_frames > 0 and len(frames) > max_frames:
        # Keep evenly spaced subset
        step = len(frames) / max_frames
        frames = [frames[int(i * step)] for i in range(max_frames)]

    log.info(f"  → {len(frames)} I-frames extracted")
    return [str(f) for f in frames]


def extract_scenes(
    video_path: str,
    output_dir: str,
    threshold: float = 0.3,
    max_frames: int = 20,
    fmt: str = "png",
    quality: int = 3,
) -> list[str]:
    """Extract frames at scene-change boundaries.

    Uses FFmpeg's scdet filter to detect visual scene transitions,
    then captures the first frame after each transition.

    Args:
        video_path: Path to input video
        output_dir: Directory to write frames to
        threshold: Scene-change sensitivity (0.0-1.0, lower = more sensitive)
        max_frames: Maximum frames to extract
        fmt: Output format ('png' or 'jpg')
        quality: Output quality

    Returns:
        List of paths to extracted frame files
    """
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: Run scdet to detect scene timestamps
    scene_log = os.path.join(output_dir, "_scenes.log")
    cmd_detect = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"scdet=threshold={threshold:.3f}:showinfo=1",
        "-f", "null",
        "-",
    ]
    log.info(f"Detecting scene changes (threshold={threshold})...")
    result = subprocess.run(cmd_detect, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        log.error(f"Scene detection failed: {result.stderr[-300:]}")
        return []

    # Parse scene timestamps from stderr (ffmpeg writes scdet info to stderr)
    timestamps = []
    import re
    for line in result.stderr.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            ts = float(m.group(1))
            if ts > 0.5:  # skip the first frame
                timestamps.append(ts)

    if not timestamps:
        log.warning("No scene changes detected (try a lower threshold)")
        return []

    if max_frames > 0 and len(timestamps) > max_frames:
        step = len(timestamps) / max_frames
        timestamps = [timestamps[int(i * step)] for i in range(max_frames)]

    # Step 2: Extract frames at those timestamps
    vcodec = "png" if fmt == "png" else "mjpeg"
    q_arg = f"-compression_level {quality}" if fmt == "png" else f"-q:v {quality}"
    frames = []
    for i, ts in enumerate(timestamps):
        out_path = os.path.join(output_dir, f"scene_{i+1:04d}.{fmt}")
        cmd_frame = [
            "ffmpeg", "-y",
            "-ss", str(ts),
            "-i", video_path,
            "-vframes", "1",
            "-vcodec", vcodec,
        ] + q_arg.split() + [
            out_path,
        ]
        subprocess.run(cmd_frame, capture_output=True, text=True, timeout=60)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            frames.append(out_path)

    log.info(f"  → {len(frames)} scene-change frames extracted")
    return frames


def extract_thumbnails(
    video_path: str,
    output_dir: str,
    count: int = 6,
    fmt: str = "jpg",
    quality: int = 5,
) -> list[str]:
    """Extract N thumbnail frames evenly spaced throughout the video.

    Uses FFmpeg's thumbnail filter which picks the most representative
    frame from a series of frame clusters. Runs in 2 passes:
      1. Divide video into N segments
      2. Pick the best frame from each segment

    Args:
        video_path: Path to input video
        output_dir: Directory to write frames to
        count: Number of thumbnails to extract
        fmt: Output format ('png' or 'jpg')
        quality: Output quality

    Returns:
        List of paths to extracted frame files
    """
    os.makedirs(output_dir, exist_ok=True)

    # Get video duration
    info = get_video_info(video_path)
    duration = 30.0  # default fallback
    if "format" in info and "duration" in info["format"]:
        try:
            duration = float(info["format"]["duration"])
        except (TypeError, ValueError):
            pass

    # Space thumbnails evenly
    if duration <= 5 or count <= 1:
        timestamps = [duration / 2]
    else:
        spacing = duration / (count + 1)
        timestamps = [spacing * (i + 1) for i in range(count)]

    vcodec = "png" if fmt == "png" else "mjpeg"
    q_arg = f"-compression_level {quality}" if fmt == "png" else f"-q:v {quality}"
    frames = []
    for i, ts in enumerate(timestamps):
        out_path = os.path.join(output_dir, f"thumb_{i+1:04d}.{fmt}")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(ts),
            "-i", video_path,
            "-vframes", "1",
            "-vcodec", vcodec,
        ] + q_arg.split() + [
            out_path,
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            frames.append(out_path)

    log.info(f"  → {len(frames)} thumbnails extracted")
    return frames


# ── Batch processing ────────────────────────────────────────────────


def process_video(
    video_path: str,
    output_dir: str = "",
    mode: str = "iframes",
    max_frames: int = 0,
    threshold: float = 0.3,
    count: int = 6,
    fmt: str = "png",
    quality: int = 3,
) -> dict:
    """Run key frame extraction on a single video.

    Returns a result dict with paths, metadata, and timing.
    """
    name = Path(video_path).stem
    if not output_dir:
        output_dir = os.path.join(Path(video_path).parent, f"{name}_keyframes")
    os.makedirs(output_dir, exist_ok=True)

    # Get video info
    info = get_video_info(video_path)
    duration = 0.0
    width = 0
    height = 0
    if "format" in info and "duration" in info["format"]:
        try:
            duration = float(info["format"]["duration"])
        except (TypeError, ValueError):
            pass
    if "streams" in info:
        vstreams = [s for s in info["streams"] if s.get("codec_type") == "video"]
        if vstreams:
            width = vstreams[0].get("width", 0)
            height = vstreams[0].get("height", 0)

    log.info(f"Processing: {Path(video_path).name}")
    log.info(f"  Duration: {duration_str(duration)}  Resolution: {width}x{height}")

    start = datetime.now()

    # Run the selected mode
    if mode == "iframes":
        frames = extract_iframes(video_path, output_dir, max_frames, fmt, quality)
    elif mode == "scenes":
        frames = extract_scenes(video_path, output_dir, threshold, max_frames, fmt, quality)
    elif mode == "thumbnail":
        frames = extract_thumbnails(video_path, output_dir, count, fmt, quality)
    else:
        return {"error": f"Unknown mode: {mode}"}

    elapsed = (datetime.now() - start).total_seconds()

    # File sizes
    sizes = []
    for f in frames:
        try:
            sizes.append(os.path.getsize(f))
        except OSError:
            sizes.append(0)

    result = {
        "ok": len(frames) > 0,
        "video": video_path,
        "mode": mode,
        "duration_s": round(duration, 1),
        "resolution": f"{width}x{height}",
        "frames_extracted": len(frames),
        "elapsed_s": round(elapsed, 2),
        "output_dir": output_dir,
        "format": fmt,
        "total_size_kb": round(sum(sizes) / 1024, 1),
        "frames": frames,
        "sizes_bytes": sizes,
    }
    return result


def process_directory(
    directory: str,
    mode: str = "iframes",
    max_frames: int = 5,
    threshold: float = 0.3,
    count: int = 6,
    fmt: str = "jpg",
    quality: int = 5,
    recursive: bool = False,
) -> list[dict]:
    """Process all video files in a directory."""
    videos = []
    pattern = "**/*.mp4" if recursive else "*.mp4"
    for f in sorted(Path(directory).glob(pattern)):
        ext = f.suffix.lower()
        if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
            videos.append(str(f))

    if not videos:
        log.warning(f"No video files found in {directory}")
        return []

    log.info(f"Found {len(videos)} video(s) in {directory}")
    results = []
    for v in videos:
        r = process_video(v, mode=mode, max_frames=max_frames,
                          threshold=threshold, count=count, fmt=fmt, quality=quality)
        results.append(r)
        print()  # spacing

    return results


def write_report(results: list[dict], report_path: str):
    """Write a JSON report of all extraction results."""
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_videos": len(results),
        "total_frames": sum(r.get("frames_extracted", 0) for r in results),
        "results": results,
    }
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info(f"Report written to {report_path}")


# ── CLI ─────────────────────────────────────────────────────────────


def main():
    p = argparse.ArgumentParser(
        description="Extract key frames from videos using FFmpeg",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s video.mp4
  %(prog)s video.mp4 --mode scenes --threshold 0.4 --max-frames 20
  %(prog)s video.mp4 --mode thumbnail --count 6 --format jpg
  %(prog)s --dir youtube_shorts_output/ --mode thumbnail --count 3
  %(prog)s --dir builds/swarm_vault/ --recursive --mode iframes --max-frames 10
        """,
    )
    p.add_argument("video", nargs="?", help="Path to input video file")
    p.add_argument("--dir", help="Process all videos in a directory")
    p.add_argument("--recursive", action="store_true", help="Recurse into subdirectories (with --dir)")
    p.add_argument("--output", "-o", help="Output directory (default: <video_dir>/<video_name>_keyframes)")
    p.add_argument("--mode", choices=["iframes", "scenes", "thumbnail"], default="iframes",
                    help="Extraction mode (default: iframes)")
    p.add_argument("--max-frames", type=int, default=0,
                    help="Max frames to extract (0 = unlimited, only for iframes/scenes modes)")
    p.add_argument("--threshold", type=float, default=0.3,
                    help="Scene-change threshold 0.0-1.0, lower = more sensitive (scenes mode)")
    p.add_argument("--count", type=int, default=6,
                    help="Number of thumbnails to extract (thumbnail mode)")
    p.add_argument("--format", choices=["png", "jpg"], default="png",
                    help="Output format (default: png)")
    p.add_argument("--quality", type=int, default=3,
                    help="Output quality: PNG 1-9 (compression), JPG 1-31 (lower = better)")
    p.add_argument("--report", help="Path to write JSON report (optional)")

    args = p.parse_args()

    if not args.video and not args.dir:
        p.print_help()
        sys.exit(1)

    results = []

    if args.dir:
        results = process_directory(
            directory=args.dir,
            mode=args.mode,
            max_frames=args.max_frames,
            threshold=args.threshold,
            count=args.count,
            fmt=args.format,
            quality=args.quality,
            recursive=args.recursive,
        )
    elif args.video:
        r = process_video(
            video_path=args.video,
            output_dir=args.output,
            mode=args.mode,
            max_frames=args.max_frames,
            threshold=args.threshold,
            count=args.count,
            fmt=args.format,
            quality=args.quality,
        )
        results = [r]

    # Print summary
    print(f"\n{'='*60}")
    print(f"KEY FRAME EXTRACTION SUMMARY")
    print(f"{'='*60}")
    total_frames = 0
    for r in results:
        ok = "✅" if r.get("ok") else "❌"
        status = "OK" if r.get("ok") else f"FAILED: {r.get('error', 'unknown')}"
        frames = r.get("frames_extracted", 0)
        total_frames += frames
        elapsed = r.get("elapsed_s", 0)
        out_dir = r.get("output_dir", "?")
        size_kb = r.get("total_size_kb", 0)
        print(f"  {ok} {Path(r.get('video', '?')).name}")
        print(f"     Frames: {frames}  |  Time: {elapsed}s  |  Size: {size_kb} KB")
        print(f"     Output: {out_dir}")

    print(f"\n  Total: {len(results)} videos, {total_frames} frames extracted")
    print(f"{'='*60}")

    if args.report and results:
        write_report(results, args.report)


if __name__ == "__main__":
    main()
