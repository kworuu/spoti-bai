"""Editorial skin for onboarding screens (used by Pages/intro.py).

Makes /intro feel like a continuation of the landing page: white canvas, charcoal #1A1A1A ink,
Georgia headline with the yellow highlighter, sharp zero-radius corners, uppercase tracked buttons,
and sharp album covers floating at random across the whole background.

Nothing in theme.py / chat.py / home.py is edited. This module REUSES the theme's typing and fade-in
machinery (via THEME CSS) and overrides the look, so roastChat and every other page stay as they are.
Everything is scoped to the "ed_card" container or to classes starting with "ed-".

    setup_editorial_page("SpotiBai")
    with editorial_card():
        editorial_header("01")
        ...                      # ai_say / ai_said / chosen_pills from UI/chat.py still work
        picked = choice_buttons(options, step)
"""
from contextlib import contextmanager
from html import escape
import math
import random

import streamlit as st

from FrontEnd.Pages.spotify_covers import get_covers
from .theme import CSS as BASE_CSS   # typing animation, reply fade-in, hidden sidebar/chrome

# ------------------------------- SETTINGS (floating album covers) -------------------------------
FLOAT_COUNT = 36            # covers floating around the whole page (24 = calm, 36 = lively, 60 = busy)
FLOAT_VISIBLE_PERCENT = 50  # % of covers visible at any moment; the rest are faded out and rotate in
FLOAT_SIZE_SCALE = 1.0      # multiply every cover size (0.8 = smaller, 1.2 = bigger)
# tier: (min px, max px, share of covers, drift seconds range)  big = slower and "closer"
FLOAT_TIERS = {
    "big":   (170, 230, 0.15, (22, 34)),
    "mid":   (105, 150, 0.35, (16, 26)),
    "small": (62, 95, 0.50, (11, 19)),
}
# --------------------------------------------------------------------------------------------------

ED_IMPORT = "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');"

ED_CSS = """
:root{--ink:#1A1A1A;--hl:#FCE38A;--mute:#9E9E9E}

/* ---- canvas: pure white, like the landing page ---- */
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:#FFFFFF!important}
header[data-testid="stHeader"]{background:transparent!important}
.stApp,.stApp p,.stApp button,.stApp input{font-family:'Inter',system-ui,sans-serif}
.stMain .block-container{max-width:680px;padding:9vh 1.25rem 6rem}

/* ---- editorial card: sharp corners, crisp border, hard offset shadow ---- */
.st-key-ed_card{background:#fff;border:1.5px solid var(--ink);border-radius:0;padding:48px;position:relative;z-index:2;
  box-shadow:8px 8px 0 var(--ink);animation:ed-card .8s cubic-bezier(.22,1,.36,1) both}
@keyframes ed-card{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}

/* ---- header: eyebrow + serif title with the yellow highlighter ---- */
.ed-head{margin:0 0 1.1rem}
.ed-head .ed-eyebrow{font-size:.6875rem;letter-spacing:.15em;text-transform:uppercase;color:var(--mute);margin:0 0 .6rem}
.ed-head .ed-title{font-family:Georgia,'Times New Roman',serif;font-weight:400;font-size:clamp(2rem,6vw,2.75rem);
  letter-spacing:.06em;line-height:1.15;text-transform:uppercase;color:var(--ink);margin:0;padding:0}
.ed-head .ed-hl{background:linear-gradient(180deg,transparent 62%,var(--hl) 62%);padding:0 4px}

/* ---- chat text ---- */
.st-key-ed_card .sb-bot{color:#222;line-height:1.6;font-size:1rem;margin:.3rem 0}
.ed-label{display:block;font-size:.6875rem;letter-spacing:.15em;text-transform:uppercase;color:#6B6B6B;text-align:right;line-height:1.4;margin:.4rem 0 0;padding-bottom:1.15rem}   /* 1rem of it cancels Streamlit's -1rem markdown margin */
.st-key-ed_card [class*="st-key-sb_choices"]{gap:.6rem}

/* ---- reply buttons: ONE rule set drives every state through variables (beats the theme's rounded pills) ---- */
.stApp .st-key-ed_card [data-testid^="stBase"]{
  --ed-bg:#fff;--ed-fg:#1A1A1A;--ed-bd:#1A1A1A;
  background:var(--ed-bg)!important;color:var(--ed-fg)!important;border:1px solid var(--ed-bd)!important;
  border-radius:0!important;padding:.65rem 1.6rem;min-height:40px;box-shadow:none;
  transition:background-color .25s ease,color .25s ease,border-color .25s ease,transform .2s ease}
.stApp .st-key-ed_card [data-testid^="stBase"] p{color:var(--ed-fg)!important;margin:0;font-size:.75rem;font-weight:500;
  letter-spacing:.14em;text-transform:uppercase;line-height:1.4;transition:color .25s ease}
/* primary: solid ink, turns yellow on hover */
.stApp .st-key-ed_card [data-testid="stBaseButton-primary"]{--ed-bg:#1A1A1A;--ed-fg:#fff}
.stApp .st-key-ed_card [data-testid="stBaseButton-primary"]:hover{--ed-bg:#FCE38A;--ed-fg:#1A1A1A}
/* secondary: outlined, fills light grey on hover */
.stApp .st-key-ed_card [data-testid="stBaseButton-secondary"]:hover{--ed-bg:#F5F5F5}
.stApp .st-key-ed_card [data-testid^="stBase"]:hover{transform:translateY(-2px)}
.stApp .st-key-ed_card [data-testid^="stBase"]:active{transform:translateY(0)}
/* login step keeps the brand hover colors */
.stApp .st-key-ed_card [class*="_brand-spotify"] [data-testid^="stBase"]:hover{--ed-bg:#1ED760;--ed-fg:#1A1A1A}
.stApp .st-key-ed_card [class*="_brand-youtube"] [data-testid^="stBase"]:hover{--ed-bg:#FF0000;--ed-fg:#fff;--ed-bd:#FF0000}

/* ---- past replies: SAME size as the live buttons (so nothing jumps when you click); picked = solid ink ---- */
.st-key-ed_card .sb-hist{gap:.6rem;margin:.35rem 0 .9rem}
.st-key-ed_card .sb-pill{box-sizing:border-box;min-height:40px;padding:.65rem 1.6rem;border:1px solid var(--ink);border-radius:0;
  background:#fff;color:var(--ink);font-size:.75rem;font-weight:500;letter-spacing:.14em;text-transform:uppercase;line-height:1.4}
.st-key-ed_card .sb-pill.chosen{background:var(--ink);color:#fff}

/* ---- sharp album covers drifting at random behind everything (no tilt, no blur) ---- */
.st-key-ed_art{position:absolute;height:0;margin:0;padding:0}
.ed-art{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
.ed-f{position:absolute;left:var(--x);top:var(--y);width:calc(var(--s)*var(--k,1));aspect-ratio:1;will-change:transform,opacity;
  animation:ed-fx var(--xd) ease-in-out var(--xdelay) infinite alternate,ed-fade var(--fd) ease-in-out var(--fdelay) infinite}
.ed-f img{display:block;width:100%;height:100%;object-fit:cover;border-radius:0;opacity:0;will-change:transform;
  filter:drop-shadow(0 10px 18px rgba(0,0,0,.12));   /* drop-shadow only exists once the picture has loaded */
  animation:ed-fy var(--yd) ease-in-out var(--ydelay) infinite alternate}
.ed-js img{transition:opacity 1.2s ease var(--d)}
.ed-js img.ready,.ed-static img{opacity:1}
@keyframes ed-fx{from{transform:translateX(0)}to{transform:translateX(var(--dx))}}
@keyframes ed-fy{from{transform:translateY(0)}to{transform:translateY(var(--dy))}}

/* ---- phones ---- */
@media (max-width:640px){
  .stMain .block-container{padding:4vh .9rem 4rem}
  .st-key-ed_card{padding:28px 22px;box-shadow:5px 5px 0 var(--ink)}
  .ed-head .ed-title{letter-spacing:.04em}
  .ed-f{--k:.62}
  .ed-f:nth-child(n+17){display:none}
  .stApp .st-key-ed_card [data-testid^="stBase"]{padding:.65rem 1.1rem}
  .stApp .st-key-ed_card [data-testid^="stBase"] p{white-space:normal;text-align:right}
}
"""

# marks each cover .ready once its image has loaded, so it only fades in when it can actually be seen
_ART_JS = """<script>
(function(){
  function mark(){
    var a=document.querySelector('.ed-art'); if(!a) return false;
    a.classList.add('ed-js');
    a.querySelectorAll('img').forEach(function(im){
      if(im.complete && im.naturalWidth>0){ im.classList.add('ready'); }
      else{ im.addEventListener('load',function(){ im.classList.add('ready'); },{once:true}); }
    });
    return true;
  }
  if(!mark()){ var n=0,t=setInterval(function(){ if(mark()||++n>60) clearInterval(t); },50); }
})();
</script>"""


def _float_css() -> str:
    """Fade keyframes built from FLOAT_VISIBLE_PERCENT (fade in, hold, fade out, rest)."""
    v = max(5, min(95, FLOAT_VISIBLE_PERCENT))
    return (f"@keyframes ed-fade{{0%{{opacity:0}}{v * .35:.1f}%{{opacity:1}}{v * .65:.1f}%{{opacity:1}}"
            f"{v}%{{opacity:0}}100%{{opacity:0}}}}")


def _floating_art(covers: list[dict]) -> None:
    """Covers spread over the whole window; every cover has its own start point, drift distance and
    speed (sideways and up/down run on separate timers) and its own fade cycle. Seeded = stable layout."""
    if not covers:   # no covers available: stay clean white
        return
    rnd = random.Random(11)
    n = max(1, FLOAT_COUNT)
    pool = list(covers)
    rnd.shuffle(pool)
    counts = {t: int(n * FLOAT_TIERS[t][2]) for t in ("big", "mid")}
    counts["small"] = n - counts["big"] - counts["mid"]
    order = [t for t, c in counts.items() for _ in range(c)]
    rnd.shuffle(order)
    cols = max(1, math.ceil(math.sqrt(n * 16 / 9)))
    rows = math.ceil(n / cols)
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    rnd.shuffle(cells)
    tiles = []
    for i, tier in enumerate(order):
        lo, hi, _, (dmin, dmax) = FLOAT_TIERS[tier]
        row, col = cells[i]
        size = int(rnd.randint(lo, hi) * FLOAT_SIZE_SCALE)
        xd, yd, fd = rnd.uniform(dmin, dmax), rnd.uniform(dmin * .8, dmax * .8), rnd.uniform(26, 38)
        phase = (i * 0.6180339887) % 1   # golden-ratio spacing: fade cycles are spread evenly
        outer = (f"--x:{(col + rnd.uniform(0, .8)) / cols * 100:.1f}vw;--y:{(row + rnd.uniform(0, .8)) / rows * 100:.1f}vh;"
                 f"--s:{size}px;--xd:{xd:.1f}s;--xdelay:-{rnd.uniform(0, xd):.1f}s;"
                 f"--fd:{fd:.1f}s;--fdelay:-{phase * fd:.1f}s;--dx:{rnd.choice((-1, 1)) * rnd.uniform(6, 16):.1f}vw")
        inner = (f"--yd:{yd:.1f}s;--ydelay:-{rnd.uniform(0, yd):.1f}s;--dy:{rnd.choice((-1, 1)) * rnd.uniform(6, 14):.1f}vh;"
                 f"--d:{rnd.uniform(0, 2.5):.2f}s")
        tiles.append(f'<div class="ed-f" style="{outer}"><img src="{pool[i % len(pool)]["m"]}" alt="" '
                     f'decoding="async" referrerpolicy="no-referrer" style="{inner}"></div>')
    body = "".join(tiles)
    with st.container(key="ed_art"):
        try:
            st.html(f'<div class="ed-art" aria-hidden="true">{body}</div>' + _ART_JS, unsafe_allow_javascript=True)
        except TypeError:   # older Streamlit without JS support: covers just show (fade cycle still runs)
            st.markdown(f'<div class="ed-art ed-static" aria-hidden="true">{body}</div>', unsafe_allow_html=True)


def setup_editorial_page(title: str = "SpotiBai") -> None:
    """Must be the first Streamlit call on the page (replaces setup_page for editorial screens)."""
    st.set_page_config(page_title=title, page_icon="🎧", layout="centered", initial_sidebar_state="collapsed")
    st.markdown(f"<style>{ED_IMPORT}{BASE_CSS}{ED_CSS}{_float_css()}</style>", unsafe_allow_html=True)
    _floating_art(get_covers(max(30, FLOAT_COUNT)))


@contextmanager
def editorial_card(key: str = "card"):
    """The sharp, bordered card with a hard offset shadow. Use a different key per card on one page."""
    with st.container(key=f"ed_{key}"):
        yield


def editorial_header(step: str = "01") -> None:
    """Eyebrow label + serif SPOTIBAI title with the yellow highlighter on 'BAI'."""
    st.markdown(
        '<div class="ed-head">'
        f'<div class="ed-eyebrow">Initializing judgment // Step {escape(step)}</div>'
        '<h1 class="ed-title">SPOTI<span class="ed-hl">BAI</span></h1></div>',
        unsafe_allow_html=True)


def choice_buttons(options: list[dict], step: int) -> int | None:
    """Reply buttons under a "CHOOSE A RESPONSE:" label. options: [{"label", "primary"?, "brand"?}].
    Hidden + unclickable until the AI finishes typing, then fade in (same timer as chat.choice_buttons)."""
    clicked = None
    with st.container(key=f"sb_choices_{step}"):   # this key name is what the typing timer + fade-in CSS target
        st.markdown('<div class="ed-label">Choose a response:</div>', unsafe_allow_html=True)
        for i, o in enumerate(options):
            brand = f"_brand-{o['brand']}" if o.get("brand") else ""
            if st.button(o["label"], key=f"c{step}_{i}{brand}", type="primary" if o.get("primary") else "secondary"):
                clicked = i
    return clicked