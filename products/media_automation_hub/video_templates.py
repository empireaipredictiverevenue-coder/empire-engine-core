"""
EMPIRE V49 · VIDEO SIZE TEMPLATES — All Social Media Platforms
==============================================================
Reference for every video size/format across platforms.
Used by the media automation hub's FFmpegComposer and render pipelines.

Format: {platform}_{variant} = {width, height, aspect_ratio, fps, bitrate_kbps}
"""

# ═══════════════════════════════════════════════════════════════════════
# SHORT-FORM VERTICAL (9:16)
# ═══════════════════════════════════════════════════════════════════════

SHORTS_VERTICAL = {
    ##### = format = width = height = resolution = fps = bitrate_kbps = max_duration_sec = notes
    "youtube_shorts":   {"width": 1080, "height": 1920, "label": "1080x1920", "fps": 30, "bitrate_kbps": 6000, "max_duration_sec": 60, "aspect": "9:16"},
    "tiktok":           {"width": 1080, "height": 1920, "label": "1080x1920", "fps": 30, "bitrate_kbps": 5000, "max_duration_sec": 180, "aspect": "9:16"},
    "instagram_reels":  {"width": 1080, "height": 1920, "label": "1080x1920", "fps": 30, "bitrate_kbps": 5500, "max_duration_sec": 90, "aspect": "9:16"},
    "instagram_stories": {"width": 1080, "height": 1920, "label": "1080x1920", "fps": 30, "bitrate_kbps": 4500, "max_duration_sec": 60, "aspect": "9:16"},
    "facebook_reels":   {"width": 1080, "height": 1920, "label": "1080x1920", "fps": 30, "bitrate_kbps": 5000, "max_duration_sec": 90, "aspect": "9:16"},
    "facebook_stories": {"width": 1080, "height": 1920, "label": "1080x1920", "fps": 30, "bitrate_kbps": 4500, "max_duration_sec": 60, "aspect": "9:16"},
    "snapchat":         {"width": 1080, "height": 1920, "label": "1080x1920", "fps": 30, "bitrate_kbps": 4000, "max_duration_sec": 60, "aspect": "9:16"},
}

# ═══════════════════════════════════════════════════════════════════════
# LONG-FORM HORIZONTAL (16:9)
# ═══════════════════════════════════════════════════════════════════════

LONGFORM_HORIZONTAL = {
    "youtube_1080p":    {"width": 1920, "height": 1080, "label": "1920x1080", "fps": 30, "bitrate_kbps": 12000, "max_duration_sec": None, "aspect": "16:9"},
    "youtube_4k":       {"width": 3840, "height": 2160, "label": "3840x2160", "fps": 30, "bitrate_kbps": 45000, "max_duration_sec": None, "aspect": "16:9"},
    "youtube_720p":     {"width": 1280, "height": 720,  "label": "1280x720",  "fps": 30, "bitrate_kbps": 5000,  "max_duration_sec": None, "aspect": "16:9"},
    "facebook_feed":    {"width": 1280, "height": 720,  "label": "1280x720",  "fps": 30, "bitrate_kbps": 4000,  "max_duration_sec": 240, "aspect": "16:9"},
    "linkedin_feed":    {"width": 1920, "height": 1080, "label": "1920x1080", "fps": 30, "bitrate_kbps": 5000,  "max_duration_sec": 600, "aspect": "16:9"},
    "twitter_feed":     {"width": 1280, "height": 720,  "label": "1280x720",  "fps": 30, "bitrate_kbps": 4000,  "max_duration_sec": 140, "aspect": "16:9"},
}

# ═══════════════════════════════════════════════════════════════════════
# SQUARE & PORTRAIT (1:1, 4:5)
# ═══════════════════════════════════════════════════════════════════════

SQUARE_PORTRAIT = {
    "instagram_feed_square":  {"width": 1080, "height": 1080, "label": "1080x1080", "fps": 30, "bitrate_kbps": 5500, "max_duration_sec": 60, "aspect": "1:1"},
    "instagram_feed_portrait": {"width": 1080, "height": 1350, "label": "1080x1350", "fps": 30, "bitrate_kbps": 5500, "max_duration_sec": 60, "aspect": "4:5"},
    "facebook_feed_square":   {"width": 1080, "height": 1080, "label": "1080x1080", "fps": 30, "bitrate_kbps": 4000, "max_duration_sec": 240, "aspect": "1:1"},
    "linkedin_feed_square":   {"width": 1080, "height": 1080, "label": "1080x1080", "fps": 30, "bitrate_kbps": 4000, "max_duration_sec": 600, "aspect": "1:1"},
    "pinterest":              {"width": 1000, "height": 1500, "label": "1000x1500", "fps": 25, "bitrate_kbps": 3000, "max_duration_sec": 240, "aspect": "2:3"},
}

# ═══════════════════════════════════════════════════════════════════════
# UNION — all templates in one dict
# ═══════════════════════════════════════════════════════════════════════

ALL_TEMPLATES = {
    **SHORTS_VERTICAL,
    **LONGFORM_HORIZONTAL,
    **SQUARE_PORTRAIT,
}

# ═══════════════════════════════════════════════════════════════════════
# HELPER: FFmpeg CLI builder
# ═══════════════════════════════════════════════════════════════════════

def ffmpeg_scale_filter(template_key: str) -> str:
    """Return an ffmpeg scale filter string for the given template key."""
    t = ALL_TEMPLATES.get(template_key)
    if not t:
        raise KeyError(f"Unknown template: {template_key}. Available: {list(ALL_TEMPLATES.keys())}")
    return f"scale={t['width']}:{t['height']}:force_original_aspect_ratio=decrease,pad={t['width']}:{t['height']}:(ow-iw)/2:(oh-ih)/2"


def ffmpeg_encode_args(template_key: str) -> list:
    """Return ffmpeg output args (codec, bitrate, fps) for the given template."""
    t = ALL_TEMPLATES.get(template_key)
    if not t:
        raise KeyError(f"Unknown template: {template_key}")
    return [
        "-c:v", "libx264",
        "-preset", "medium",
        "-b:v", f"{t['bitrate_kbps']}k",
        "-maxrate", f"{int(t['bitrate_kbps'] * 1.5)}k",
        "-bufsize", f"{int(t['bitrate_kbps'] * 2)}k",
        "-r", str(t["fps"]),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
    ]


def get_template(platform: str, variant: str = "feed") -> dict:
    """Resolve a human-readable platform + variant to a template dict.

    Examples:
        get_template("youtube", "shorts") → 1080x1920
        get_template("youtube", "1080p")  → 1920x1080
        get_template("tiktok")            → 1080x1920
        get_template("instagram", "reels") → 1080x1920
        get_template("instagram", "feed")  → 1080x1080
    """
    key_map = {
        ("youtube", "shorts"): "youtube_shorts",
        ("youtube", "1080p"): "youtube_1080p",
        ("youtube", "4k"): "youtube_4k",
        ("youtube", "720p"): "youtube_720p",
        ("tiktok", "feed"): "tiktok",
        ("tiktok",): "tiktok",
        ("instagram", "reels"): "instagram_reels",
        ("instagram", "stories"): "instagram_stories",
        ("instagram", "feed"): "instagram_feed_square",
        ("instagram", "portrait"): "instagram_feed_portrait",
        ("facebook", "reels"): "facebook_reels",
        ("facebook", "stories"): "facebook_stories",
        ("facebook", "feed"): "facebook_feed",
        ("linkedin", "feed"): "linkedin_feed",
        ("twitter", "feed"): "twitter_feed",
        ("snapchat",): "snapchat",
        ("pinterest",): "pinterest",
    }
    lookup = (platform.lower(), variant.lower()) if variant else (platform.lower(),)
    template_key = key_map.get(lookup)
    if not template_key:
        raise KeyError(f"No template for platform={platform} variant={variant}. Available keys: {sorted(ALL_TEMPLATES.keys())}")
    return ALL_TEMPLATES[template_key]
