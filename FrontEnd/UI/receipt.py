"""SpotiBai playlist receipt: the user's top 10 songs as a tilted paper receipt (PNG, 1080x1350).

Follows the "Recibo" template: zigzag paper on a gradient that is GREEN for Spotify and RED for
YouTube. Each song is one line and its length is the "price". The total is always "Priceless".
Spotify doesn't give play counts, so the list is the top tracks of the last ~4 weeks, most played
first (topped up from the ~1 year list). wheel.py uses the SAME list, so wheel = receipt.
"""
import hashlib
import io
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parents[1] / "static" / "fonts"
MANILA = timezone(timedelta(hours=8))
TOP_N = 10

CANVAS = (1080, 1350)
TILT = 3.5                       # degrees, counter-clockwise like the template
S = 2                            # paper is drawn at 2x, then scaled down = smooth edges
PAPER_W, PAD = 640 * S, 66 * S   # paper width, text margin
TOOTH_W, TOOTH_H = 32 * S, 16 * S
PAPER = (253, 251, 247, 255)
INK = (26, 26, 26, 255)

# background gradients, left -> right (colours sampled from the template)
GRADIENTS = {
    "spotify": [(0.0, (252, 227, 138)), (0.5, (116, 166, 51)), (1.0, (95, 141, 34))],
    "youtube": [(0.0, (252, 227, 138)), (0.5, (214, 58, 44)), (1.0, (168, 28, 24))],
}


def _font(size: int, bold: bool = False):
    name = "CourierPrime-Bold.ttf" if bold else "CourierPrime-Regular.ttf"
    try:
        return ImageFont.truetype(str(FONTS / name), size * S)
    except OSError:
        try:
            return ImageFont.load_default(size=size * S)   # Pillow >= 10.1
        except TypeError:
            return ImageFont.load_default()


def _fit(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    """Cut text with '…' so it fits inside width pixels."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _price(ms: int | None) -> str:
    """Song length shown like a price: 4:01 -> '4.01' (template style). Unknown length -> '0.00'."""
    if not ms:
        return "0.00"
    seconds = round(ms / 1000)
    return f"{seconds // 60}.{seconds % 60:02d}"


def _ms(track) -> int | None:
    """Song length in ms, or None if this profile's Track model has no length (e.g. YouTube, older models)."""
    return getattr(track, "duration_ms", None)


def top_songs(profile) -> list:
    """The 10 songs that best show their taste: the same CORE / PHASE / PAST layers the roast uses
    (BackEnd/insights.taste_tracks), so the wheel, the receipt and the roast all agree."""
    from BackEnd.insights import taste_tracks
    return taste_tracks(profile, TOP_N)


def wheel_songs(profile) -> list[dict]:
    """The receipt's top 10 as the wheel's song dicts, so the wheel and the receipt always match."""
    songs = []
    for track in top_songs(profile):
        uri = getattr(track, "uri", "") or ""
        if not uri:                       # the wheel can't play a song without a uri
            continue
        artists = getattr(track, "artists", None) or []
        songs.append({
            "name": track.name,
            "artist": ", ".join(artists) or "Unknown",
            "uri": uri,
            "image": getattr(track, "image", "") or "",
            "album": getattr(track, "album", "") or "",
            "release_date": str(getattr(track, "year", "") or ""),
        })
    return songs


def _gradient(source: str) -> Image.Image:
    stops = GRADIENTS.get(source, GRADIENTS["spotify"])
    w, h = CANVAS
    row = Image.new("RGB", (w, 1))
    for x in range(w):
        t = x / (w - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                row.putpixel((x, 0), tuple(round(a + (b - a) * k) for a, b in zip(c0, c1)))
                break
    return row.resize((w, h)).convert("RGBA")


def _zigzag_paper(height: int) -> tuple[Image.Image, Image.Image]:
    """White paper with torn (zigzag) top and bottom edges. Returns (paper, mask)."""
    teeth = PAPER_W // TOOTH_W
    tooth = PAPER_W / teeth
    top = [(i * tooth / 2, 0 if i % 2 else TOOTH_H) for i in range(teeth * 2 + 1)]
    bottom = [(PAPER_W - i * tooth / 2, height - (0 if i % 2 else TOOTH_H)) for i in range(teeth * 2 + 1)]
    mask = Image.new("L", (PAPER_W, height), 0)
    ImageDraw.Draw(mask).polygon(top + bottom, fill=255)
    paper = Image.new("RGBA", (PAPER_W, height), (0, 0, 0, 0))
    paper.paste(Image.new("RGBA", (PAPER_W, height), PAPER), (0, 0), mask)
    return paper, mask


def make_receipt_png(profile, now: datetime | None = None) -> bytes:
    songs = top_songs(profile)
    source = getattr(profile, "source", "spotify") or "spotify"
    now = (now or datetime.now(MANILA)).astimezone(MANILA)
    seed = int(hashlib.sha1(f"{getattr(profile, 'display_name', '')}|{now:%Y%m%d}".encode()).hexdigest(), 16)
    rng = random.Random(seed)

    title, body, bold = _font(36, bold=True), _font(20), _font(21, bold=True)
    rows = max(len(songs), 1)
    ink = Image.new("RGBA", (PAPER_W, (150 + 45 * rows + 400) * S), (0, 0, 0, 0))   # text goes here first
    d = ImageDraw.Draw(ink)
    left, right = PAD, PAPER_W - PAD

    def dashed(y: int) -> None:
        dash, gap = 12 * S, 9 * S
        for x in range(left, right, dash + gap):
            d.line((x, y, min(x + dash, right), y), fill=INK, width=2 * S)

    y = 70 * S
    d.text((PAPER_W // 2, y), "RECEIPTNIBAI", font=title, fill=INK, anchor="ma")
    y += 58 * S
    d.text((PAPER_W // 2, y), f"playlist receipt · {now:%m.%d.%y}", font=body, fill=INK, anchor="ma")
    y += 50 * S
    dashed(y)
    y += 26 * S

    price_w = d.textlength("00.00", font=body) + 16 * S
    if songs:
        for track in songs:
            artists = getattr(track, "artists", None) or []
            line = f"{track.name} - {artists[0]}" if artists else str(track.name)
            d.text((left, y), _fit(d, line.lower(), body, int(right - left - price_w)), font=body, fill=INK)
            d.text((right, y), _price(_ms(track)), font=body, fill=INK, anchor="ra")
            y += 45 * S
    else:
        d.text((left, y), "no songs yet. play something!", font=body, fill=INK)
        y += 45 * S

    y += 6 * S
    dashed(y)
    y += 30 * S
    d.text((left, y), "TOTAL", font=bold, fill=INK)
    d.text((right, y), "Priceless", font=bold, fill=INK, anchor="ra")
    y += 52 * S
    dashed(y)
    y += 50 * S

    # barcode: random-looking, but the same for the same user on the same day
    bar_w, bar_h = 250 * S, 118 * S
    x, end = PAPER_W // 2 - bar_w // 2, PAPER_W // 2 + bar_w // 2
    while x < end:
        thick = rng.choice((1, 2, 2, 3, 5)) * S
        d.rectangle((x, y, min(x + thick, end) - 1, y + bar_h), fill=INK)
        x += thick + rng.choice((2, 3, 4)) * S
    y += bar_h + 30 * S
    d.text((PAPER_W // 2, y), "SPOTIBAI.COM", font=body, fill=INK, anchor="ma")
    y += 70 * S

    # cut the paper to its real length, then tilt it onto the gradient
    paper, _ = _zigzag_paper(y)
    paper.alpha_composite(ink.crop((0, 0, PAPER_W, y)))
    small = paper.resize((PAPER_W // S, y // S), Image.LANCZOS)
    tilted = small.rotate(TILT, resample=Image.BICUBIC, expand=True)

    canvas = _gradient(source)
    cx, cy = CANVAS[0] // 2, CANVAS[1] // 2
    canvas.alpha_composite(tilted, (cx - tilted.width // 2, cy - tilted.height // 2))

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()