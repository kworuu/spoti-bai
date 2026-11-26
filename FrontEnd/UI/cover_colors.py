"""Muted background colors from album covers (for the wheel page).

For each song we find the cover's dominant color, then turn it into:
  bg     - a very light, low-saturation tint for the page background
  accent - a darker muted shade for small details (the now-playing progress line)

Done in Python (not in the browser) because the covers come from Spotify/YouTube image servers,
and the browser may refuse to let page code read pixels from another site's images.
"""
import colorsys
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import requests
from PIL import Image

DEFAULT = {"bg": "#FFFFFF", "accent": "#1A1A1A"}

BG_LIGHTNESS = 0.87      # how light the page tint is (1.0 = white)
BG_MIN_SAT = 0.20        # colorful covers always get a tint you can actually see...
BG_MAX_SAT = 0.40        # ...but never a loud one
ACCENT_LIGHTNESS = 0.34
ACCENT_MAX_SAT = 0.38


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(c * 255))) for c in rgb)


@lru_cache(maxsize=500)   # plain cache: st.cache_data warns when called from worker threads
def cover_colors(url: str) -> dict:
    if not url:
        return DEFAULT
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        im = Image.open(BytesIO(r.content)).convert("RGB")
    except Exception:  # noqa: BLE001 — a missing color just means a white background
        return DEFAULT

    # centre crop: drops YouTube thumbnail letterbox bars and busy borders
    w, h = im.size
    im = im.crop((int(w * .15), int(h * .15), int(w * .85), int(h * .85)))
    im.thumbnail((64, 64))
    q = im.quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    total = im.size[0] * im.size[1]

    best, best_score, fallback = None, -1.0, None
    for count, idx in sorted(q.getcolors(), reverse=True):
        rgb = [c / 255 for c in pal[idx * 3: idx * 3 + 3]]
        hh, ll, ss = colorsys.rgb_to_hls(*rgb)
        if fallback is None:
            fallback = (hh, ll, ss)
        if ll < 0.10 or ll > 0.93:          # near black / near white say little about the cover
            continue
        # colorful beats merely common; dark shadow tones count less (they turn into grey-beige)
        score = (count / total) * (0.15 + 2 * ss) * (0.4 if ll < 0.22 else 1.0)
        if score > best_score:
            best, best_score = (hh, ll, ss), score
    hh, ll, ss = best or fallback

    if ss < 0.08:                            # greyscale cover: neutral grey tint
        return {"bg": _hex(colorsys.hls_to_rgb(0, 0.93, 0)), "accent": "#3A3A3A"}
    return {
        "bg": _hex(colorsys.hls_to_rgb(hh, BG_LIGHTNESS, min(max(ss, BG_MIN_SAT), BG_MAX_SAT))),
        "accent": _hex(colorsys.hls_to_rgb(hh, ACCENT_LIGHTNESS, min(ss, ACCENT_MAX_SAT))),
    }


def add_colors(songs: list[dict]) -> None:
    """Adds "bg" and "accent" to each song dict (in place). Covers are fetched in parallel."""
    todo = [s for s in songs if "bg" not in s]
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        for song, colors in zip(todo, pool.map(lambda s: cover_colors(s.get("image", "")), todo)):
            song.update(colors)
