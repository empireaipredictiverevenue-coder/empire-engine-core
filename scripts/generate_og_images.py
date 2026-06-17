"""v3: write OG images as static files at startup. The /static mount
serves them. No conflict with FastAPI routing because we don't
register a route at all — the files just exist.

Render on demand via /api/v1/og/{slug}/refresh endpoint (operator
action), or via the storm_url_refresh cron (every 6h).
"""
import os
from pathlib import Path
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


STORM_METROS = [
    ("san-antonio-tx", "San Antonio", "TX"),
    ("atlanta-ga", "Atlanta", "GA"),
    ("denver-co", "Denver", "CO"),
    ("chicago-il", "Chicago", "IL"),
    ("kansas-city-mo", "Kansas City", "MO"),
    ("tulsa-ok", "Tulsa", "OK"),
    ("houston-tx", "Houston", "TX"),
    ("dallas-tx", "Dallas", "TX"),
    ("st-louis-mo", "St. Louis", "MO"),
    ("oklahoma-city-ok", "Oklahoma City", "OK"),
]


def _font(size):
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render(city, state, n_active, n_all):
    W, H = 1200, 630
    BG = (10, 26, 47)
    FG = (232, 238, 246)
    TEAL = (111, 207, 192)
    MIST = (143, 160, 181)
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(BG[0] + (5 - BG[0]) * t)
        g = int(BG[1] + (11 - BG[1]) * t)
        b = int(BG[2] + (20 - BG[2]) * t)
        d.line([(0, y), (W, y)], fill=(r, g, b))
    d.rectangle([(0, 0), (W, 6)], fill=TEAL)
    d.text((60, 60), "EMPIRE AI", fill=TEAL, font=_font(28))
    d.text((60, 100), "Pre-screened storm leads for vetted contractors",
           fill=MIST, font=_font(18))
    city_font = _font(110)
    city_text = city.upper()
    bbox = d.textbbox((0, 0), city_text, font=city_font)
    tw = bbox[2] - bbox[0]
    if tw > W - 120:
        city_font = _font(84)
        bbox = d.textbbox((0, 0), city_text, font=city_font)
        tw = bbox[2] - bbox[0]
    d.text(((W - tw) / 2, 180), city_text, fill=FG, font=city_font)
    state_font = _font(48)
    bbox = d.textbbox((0, 0), state, font=state_font)
    sw = bbox[2] - bbox[0]
    d.text(((W - sw) / 2, 320), state, fill=TEAL, font=state_font)
    stat_font = _font(64)
    label_font = _font(16)
    def stat(x_center, value, label):
        s = str(value)
        bbox = d.textbbox((0, 0), s, font=stat_font)
        sw_ = bbox[2] - bbox[0]
        d.text((x_center - sw_ / 2, 430), s, fill=FG, font=stat_font)
        bbox = d.textbbox((0, 0), label, font=label_font)
        lw = bbox[2] - bbox[0]
        d.text((x_center - lw / 2, 510), label, fill=MIST, font=label_font)
    stat(W * 0.30, n_active, "ACTIVE TARGETS RIGHT NOW")
    stat(W * 0.70, n_all, "ALL-TIME LEADS DELIVERED")
    d.text((60, 580), "3% on settled claims. No per-lead fees. empire-ai.co.uk",
           fill=MIST, font=_font(20))
    d.rectangle([(0, H - 6), (W, H)], fill=TEAL)
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_all(static_dir: str = "/root/empire-v49/static") -> dict:
    """Render OG images for all metros + a default. Returns a dict of
    slug -> filename written. Idempotent (overwrites)."""
    os.makedirs(static_dir, exist_ok=True)
    # Pull live counts from supabase if env vars present
    counts = {}
    try:
        from supabase import create_client
        sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
        for slug, city, state in STORM_METROS:
            rt = sb.table("radar_targets").select("id", count="exact").eq("city", city).eq("state", state).eq("status", "active").limit(1).execute()
            el = sb.table("enriched_leads").select("id", count="exact").eq("city", city).eq("state", state).limit(1).execute()
            counts[slug] = {"city": city, "state": state, "active": rt.count or 0, "all": el.count or 0}
    except Exception as e:
        # No supabase; render with placeholder zeros
        for slug, city, state in STORM_METROS:
            counts[slug] = {"city": city, "state": state, "active": 0, "all": 0}
        counts["__error"] = str(e)

    written = {}
    for slug, info in counts.items():
        if slug == "__error":
            continue
        city = info["city"]
        state = info["state"]
        png = render(city, state, info["active"], info["all"])
        fn = "og-" + slug + ".png"
        path = os.path.join(static_dir, fn)
        with open(path, "wb") as f:
            f.write(png)
        written[slug] = fn
    # Default (for the index page)
    png = render("Empire AI", "Storm Leads", 0, 0)
    with open(os.path.join(static_dir, "og-default.png"), "wb") as f:
        f.write(png)
    written["default"] = "og-default.png"
    return written


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "/root/empire-v49")
    try:
        from dotenv import load_dotenv
        load_dotenv("/root/.env")
    except Exception:
        pass
    written = render_all()
    print("wrote " + str(len(written)) + " OG images:")
    for k, v in written.items():
        print("  " + v)
