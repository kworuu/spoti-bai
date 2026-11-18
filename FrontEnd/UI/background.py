"""Floating album-cover background. CSS does all the motion; a tiny script only marks covers
as "ready" once their image has loaded, so nothing shows until it can fade in smoothly.

>>> Edit the SETTINGS below to change how busy the background is. <<<"""
import math
import random
import streamlit as st

# ------------------------------- SETTINGS -------------------------------
COVER_COUNT = 60       # total covers floating around. 30 = calm, 60 = busy, ~100 = max sensible
VISIBLE_PERCENT = 45   # % of covers visible at any moment (the rest are faded out and rotate in)
SIZE_SCALE = 5.5       # multiply all cover sizes (0.8 = smaller, 1.2 = bigger)
TIER_MIX = {"big": 0.15, "mid": 0.4, "small": 0.45}   # share of big / medium / small covers
# ------------------------------------------------------------------------

# tier: (min px, max px, blur px, opacity, drift seconds range)
TIERS = {
    "big":   (190, 270, 0.8, 0.85, (20, 30)),
    "mid":   (100, 150, 1.6, 0.70, (14, 22)),
    "small": (56, 90, 3.0, 0.50, (9, 16)),
}

# Marks each <img> with .ready when it has finished loading (CSS keeps it invisible until then).
READY_JS = """<script>
(function(){
  function mark(){
    var bg=document.querySelector('.sb-bg'); if(!bg) return false;
    bg.classList.add('sb-js');
    bg.querySelectorAll('img.sb-cover').forEach(function(im){
      if(im.complete && im.naturalWidth>0){ im.classList.add('ready'); }
      else{ im.addEventListener('load',function(){ im.classList.add('ready'); },{once:true}); }
    });
    return true;
  }
  if(!mark()){ var n=0,t=setInterval(function(){ if(mark()||++n>60) clearInterval(t); },50); }
})();
</script>"""


def fade_css() -> str:
    """Fade keyframes built from VISIBLE_PERCENT, plus how many covers phones keep."""
    v = max(5, min(95, VISIBLE_PERCENT))
    a, b = v * 0.35, v * 0.65
    keep = max(10, COVER_COUNT // 3)
    return (f"@keyframes sb-fade{{0%{{opacity:0}}{a:.1f}%{{opacity:1}}{b:.1f}%{{opacity:1}}"
            f"{v}%{{opacity:0}}100%{{opacity:0}}}}"
            f"@media (max-width:700px){{.sb-x:nth-child(n+{keep + 1}){{display:none}}}}")


def _tier_order(rnd: random.Random, n: int) -> list[str]:
    counts = {t: int(n * TIER_MIX[t]) for t in ("big", "mid")}
    counts["small"] = n - counts["big"] - counts["mid"]
    order = [t for t, c in counts.items() for _ in range(c)]
    rnd.shuffle(order)
    return order


def render_background(covers: list[dict], seed: int = 7) -> None:
    rnd = random.Random(seed)
    n = max(1, COVER_COUNT)
    pool = list(covers)
    rnd.shuffle(pool)
    # spread covers over a jittered grid sized to the window's shape, then pick n random cells
    cols = max(1, math.ceil(math.sqrt(n * 16 / 9)))
    rows = math.ceil(n / cols)
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    rnd.shuffle(cells)
    size_mult = SIZE_SCALE * min(1.0, (30 / n) ** 0.35)   # denser = slightly smaller, keeps big/small contrast
    tiles = []
    for i, tier in enumerate(_tier_order(rnd, n)):
        lo, hi, blur, opacity, (dmin, dmax) = TIERS[tier]
        row, col = cells[i]
        size = int(rnd.randint(lo, hi) * size_mult)
        x = (col + rnd.uniform(0, 0.8)) / cols * 100
        y = (row + rnd.uniform(0, 0.8)) / rows * 100
        xd, yd = rnd.uniform(dmin, dmax), rnd.uniform(dmin * 0.8, dmax * 0.8)
        fd = rnd.uniform(24, 34)
        phase = (i * 0.6180339887) % 1  # golden-ratio spacing: fade cycles are spread evenly
        outer = (f"--x:{x:.1f}vw;--y:{y:.1f}vh;--s:{size}px;"
                 f"--xd:{xd:.1f}s;--xdelay:-{rnd.uniform(0, xd):.1f}s;"
                 f"--fd:{fd:.1f}s;--fdelay:-{phase * fd:.1f}s;"
                 f"--dx:{rnd.choice((-1, 1)) * rnd.uniform(8, 22):.1f}vw")
        inner = (f"--b:{blur}px;--o:{opacity};"
                 f"--yd:{yd:.1f}s;--ydelay:-{rnd.uniform(0, yd):.1f}s;"
                 f"--dy:{rnd.choice((-1, 1)) * rnd.uniform(8, 22):.1f}vh;"
                 f"--r0:{rnd.uniform(-8, 8):.1f}deg;--r1:{rnd.uniform(-8, 8):.1f}deg")
        if pool:
            c = pool[i % len(pool)]
            src = c["s"] if tier == "small" else c["m"]  # small tiles load the 64px image
            img = (f'<img class="sb-cover" src="{src}" alt="" decoding="async" '
                   f'referrerpolicy="no-referrer" style="{inner}">')
        else:  # fallback: empty wireframe boxes
            img = f'<i class="sb-cover sb-empty" style="{inner}"></i>'
        tiles.append(f'<div class="sb-x" style="{outer}">{img}</div>')
    # one line, no blank lines: Streamlit's markdown parser breaks HTML otherwise
    html = ('<div class="sb-bg" aria-hidden="true">' + "".join(tiles) +
            '<span class="sb-credit">Album art from Spotify</span></div>')
    with st.container(key="sb_bg"):
        try:
            st.html(html + READY_JS, unsafe_allow_javascript=True)
        except TypeError:  # older Streamlit: no JS support, covers just fade in as they arrive
            st.markdown(html, unsafe_allow_html=True)