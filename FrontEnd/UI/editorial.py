"""Editorial skin for onboarding screens (used by Pages/intro.py).

Makes /intro look like the SPOTIBAI chat card on the wheel page (UI/roast_chat.py): white card with
rounded corners, charcoal #1A1A1A ink border and hard offset shadow, centered Georgia headline with
the yellow highlighter, large bot text, square uppercase reply buttons in a right-aligned row, and the
picked reply kept as a solid-ink bubble. Sharp album covers still float across the whole background.
Sizes use the same unit as roast_chat (1u = 100vh / 800) so both screens scale the same way.

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
from pathlib import Path
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
# ------------------------------------ SETTINGS (card extras) --------------------------------------
SHOW_STEP_EYEBROW = False   # "Initializing judgment // Step 01" above the title (roast_chat has none)
SHOW_CHOICE_LABEL = False   # "Choose a response:" above the buttons (roast_chat has none)
# --------------------------------------------------------------------------------------------------

ED_IMPORT = "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');"

ED_CSS = """
:root{--ink:#1A1A1A;--hl:#FCE38A;--mute:#9E9E9E}

/* ---- canvas: pure white, like the landing page ---- */
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:#FFFFFF!important}
header[data-testid="stHeader"]{background:transparent!important}
.stApp,.stApp p,.stApp button,.stApp input{font-family:'Inter',system-ui,sans-serif}
.stMain .block-container{max-width:none;padding:0}

/* ---- card: EXACT roast_chat rc_panel numbers (1u = 100vh / 800) ----
   roast_chat sits right of the wheel (left 600u, right 100u). Here there is no wheel, so the same
   700u of side space is split evenly: same width, same height, just centered. */
.stApp .st-key-ed_card{--u:calc(100vh / 800);
  position:fixed!important;z-index:20;
  /* width = roast_chat's (100vw - 700u), but never narrower than 560px on squarish windows */
  width:max(min(560px,calc(100vw - 32px)),calc(100vw - 700 * var(--u)))!important;max-width:none!important;height:auto!important;
  left:0;right:0;margin:0 auto!important;top:calc(70 * var(--u));bottom:calc(70 * var(--u));
  box-sizing:border-box;background:#FFFFFF;
  border:max(1.5px,calc(2 * var(--u))) solid var(--ink);border-radius:calc(16 * var(--u))!important;
  box-shadow:calc(8 * var(--u)) calc(8 * var(--u)) 0 var(--ink);
  padding:calc(34 * var(--u)) calc(44 * var(--u)) calc(30 * var(--u))!important;
  display:flex!important;flex-direction:column!important;gap:calc(16 * var(--u))!important;
  overflow-x:hidden!important;overflow-y:auto!important;scrollbar-width:thin;scrollbar-color:#C8C8C8 transparent;
  color:var(--ink);animation:ed-card .65s cubic-bezier(.22,1,.36,1) both}
.st-key-ed_card,.st-key-ed_card *{font-family:'Inter',system-ui,sans-serif;box-sizing:border-box}
@keyframes ed-card{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}

/* ---- header: same rules as roast_chat's .rc-head / .rc-title / .rc-hl ---- */
.ed-head,.ed-head *{text-align:center;border:none!important;box-shadow:none!important;
  margin-bottom:calc(18 * var(--u))!important}
.ed-head .ed-eyebrow{font-size:.6875rem;letter-spacing:.15em;text-transform:uppercase;color:var(--mute)}
.ed-title{margin:0;font-family:Georgia,'Times New Roman',serif!important;font-weight:400;
  font-size:max(24px,calc(38 * var(--u)));letter-spacing:.06em;line-height:1.12;text-transform:uppercase}
.ed-hl{background:linear-gradient(180deg,transparent 62%,var(--hl) 62%);padding:0 4px}

/* ---- bot text: same as .rc-bot (bottom margin makes text -> buttons = roast's 35u message gap) ---- */
.st-key-ed_card .sb-bot{margin:0 0 calc(19 * var(--u));max-width:92%;font-size:max(16px,calc(22 * var(--u)));
  line-height:1.6;color:#222222;white-space:pre-line}
.st-key-ed_card .sb-bot b{color:var(--ink);font-weight:600}
.ed-label{display:block;width:100%;font-size:.6875rem;letter-spacing:.15em;text-transform:uppercase;color:#6B6B6B;
  text-align:right;line-height:1.4;margin:0}

/* ---- reply buttons: same as rc_choices ---- */
.st-key-ed_card [class*="st-key-sb_choices"]{flex-direction:column!important;flex-wrap:nowrap;justify-content:flex-start;align-items:flex-end;
  gap:calc(8 * var(--u))!important}
.st-key-ed_card [class*="st-key-sb_choices"] [data-testid="stElementContainer"]{width:auto!important}
.st-key-ed_card [class*="st-key-sb_choices"] [data-testid="stElementContainer"]:has(.ed-label){width:100%!important}
/* ONE rule set drives every state through variables (beats the theme's rounded pills) */
.stApp .st-key-ed_card [data-testid^="stBase"]{
  --ed-bg:#fff;--ed-fg:#1A1A1A;--ed-bd:#1A1A1A;
  background:var(--ed-bg)!important;color:var(--ed-fg)!important;border:1px solid var(--ed-bd)!important;
  border-radius:0!important;padding:calc(7 * var(--u)) calc(16 * var(--u))!important;min-height:38px;box-shadow:none!important;
  transition:background-color .2s ease,color .2s ease,border-color .2s ease,transform .18s ease!important}
.stApp .st-key-ed_card [data-testid^="stBase"] p{color:var(--ed-fg)!important;margin:0!important;
  font-size:max(11px,calc(12 * var(--u)))!important;font-weight:500!important;letter-spacing:.12em!important;
  text-transform:uppercase!important;line-height:1.35!important}
/* primary: solid ink, turns yellow on hover (roast_chat's first button) */
.stApp .st-key-ed_card [data-testid="stBaseButton-primary"]{--ed-bg:#1A1A1A;--ed-fg:#fff}
.stApp .st-key-ed_card [data-testid="stBaseButton-primary"]:hover{--ed-bg:#FCE38A;--ed-fg:#1A1A1A}
/* secondary: outlined, fills light grey on hover */
.stApp .st-key-ed_card [data-testid="stBaseButton-secondary"]:hover{--ed-bg:#F5F5F5}
.stApp .st-key-ed_card [data-testid^="stBase"]:hover{transform:translateY(-1px)}
.stApp .st-key-ed_card [data-testid^="stBase"]:active{transform:translateY(0)}
/* login step keeps the brand hover colors */
.stApp .st-key-ed_card [class*="_brand-spotify"] [data-testid^="stBase"]:hover{--ed-bg:#1ED760;--ed-fg:#1A1A1A}
.stApp .st-key-ed_card [class*="_brand-youtube"] [data-testid^="stBase"]:hover{--ed-bg:#FF0000;--ed-fg:#fff;--ed-bd:#FF0000}

/* ---- past replies: only the picked one stays, as a right-aligned solid-ink bubble (like rc-me) ---- */
.st-key-ed_card .sb-hist{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:0;margin:0 0 calc(19 * var(--u))}
.st-key-ed_card .sb-pill{display:none}
.st-key-ed_card .sb-pill.chosen{display:inline-block;max-width:82%;padding:calc(9 * var(--u)) calc(16 * var(--u));
  border:0;border-radius:0;background:var(--ink);color:#fff;font-size:max(13px,calc(16 * var(--u)));font-weight:400;
  letter-spacing:normal;text-transform:none;line-height:1.4}

/* ---- chat input (if one is placed inside the card): rounded, ink outline ---- */
.stApp .st-key-ed_card [data-testid="stChatInput"],
.stApp .st-key-ed_card [data-testid="stChatInput"] > div,
.stApp .st-key-ed_card [data-testid="stChatInput"] [data-baseweb="textarea"],
.stApp .st-key-ed_card [data-testid="stChatInput"] textarea{border-radius:calc(16 * var(--u))!important}
.stApp .st-key-ed_card [data-testid="stChatInput"] > div{border:1px solid var(--ink)!important;background:#fff!important}
.stApp .st-key-ed_card [data-testid="stChatInput"] textarea{border:none!important;color:var(--ink)!important;
  -webkit-text-fill-color:var(--ink);caret-color:var(--ink);font-size:max(13px,calc(15 * var(--u)))}
.stApp .st-key-ed_card [data-testid="stChatInput"] textarea::placeholder{color:#8A8A8A;-webkit-text-fill-color:#8A8A8A}

/* ---- sharp album covers drifting at random behind everything (no tilt, no blur) ---- */
.st-key-ed_art,.st-key-ed_audio{position:absolute;height:0;margin:0;padding:0;overflow:hidden}
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
  .stApp .st-key-ed_card{width:auto!important;left:12px;right:12px;top:3vh;bottom:3vh;padding:26px 20px 22px!important;
    border-radius:12px!important;box-shadow:5px 5px 0 var(--ink)}
  .ed-title{letter-spacing:.04em}
  .ed-f{--k:.62}
  .ed-f:nth-child(n+17){display:none}
  .stApp .st-key-ed_card [data-testid^="stBase"]{padding:.55rem 1rem!important}
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


def setup_editorial_page(title: str = "SpotiBai", extra_css: str = "") -> None:
    """Must be the first Streamlit call on the page (replaces setup_page for editorial screens).
    extra_css goes into the SAME first style tag, so it is already active while the page redraws
    (no flash of album covers / normal-size buttons after a click)."""
    st.set_page_config(page_title=title, page_icon="🎧", layout="centered", initial_sidebar_state="collapsed")
    st.markdown(f"<style>{ED_IMPORT}{BASE_CSS}{ED_CSS}{_float_css()}{extra_css}</style>", unsafe_allow_html=True)
    _floating_art(get_covers(max(30, FLOAT_COUNT)))


@contextmanager
def editorial_card(key: str = "card"):
    """The sharp, bordered card with a hard offset shadow. Use a different key per card on one page."""
    with st.container(key=f"ed_{key}"):
        yield


def editorial_header(step: str = "01") -> None:
    """Centered serif SPOTIBAI title with the yellow highlighter on 'BAI' (eyebrow only if SHOW_STEP_EYEBROW)."""
    eyebrow = (f'<div class="ed-eyebrow">Initializing judgment // Step {escape(step)}</div>'
               if SHOW_STEP_EYEBROW else "")
    st.markdown(
        f'<div class="ed-head">{eyebrow}'
        '<h1 class="ed-title">SPOTI<span class="ed-hl">BAI</span></h1></div>',
        unsafe_allow_html=True)


def choice_buttons(options: list[dict], step: int) -> int | None:
    """Right-aligned row of reply buttons. options: [{"label", "primary"?, "brand"?}].
    Hidden + unclickable until the AI finishes typing, then fade in (same timer as chat.choice_buttons)."""
    clicked = None
    with st.container(key=f"sb_choices_{step}"):   # this key name is what the typing timer + fade-in CSS target
        if SHOW_CHOICE_LABEL:
            st.markdown('<div class="ed-label">Choose a response:</div>', unsafe_allow_html=True)
        for i, o in enumerate(options):
            brand = f"_brand-{o['brand']}" if o.get("brand") else ""
            if st.button(o["label"], key=f"c{step}_{i}{brand}", type="primary" if o.get("primary") else "secondary"):
                clicked = i
    return clicked

# ----------------------------- the "click no, yes gets bigger" meme -----------------------------
PUSHY_GROW = 1.20     # how much bigger the yes button gets per "no" (0.45 = +45% each time)
PUSHY_SHRINK = 0.15   # how much smaller the no button gets per "no" (0.25 = gone after 4)

SHAKE_AMP = 1.6               # px of sideways shake added per "no"
SHAKE_ROT = 0.7               # degrees of wobble added per "no"
SHAKE_SECONDS = 0.6           # shake speed at the 1st "no"; gets faster each time...
SHAKE_MIN_SECONDS = 0.18      # ...down to this
SHAKE_CONTINUOUS_AFTER = 3    # before this many "no"s it shakes in bursts, from here on it never stops

# burst = shake for the first half, then hold still; nonstop = shake the whole cycle
SHAKE_KEYFRAMES = """
@keyframes ed-shake-burst{
  0%,50%,100%{transform:translate(0,0) rotate(0)}
  8%{transform:translate(calc(var(--amp) * -1),calc(var(--amp) * .3)) rotate(calc(var(--rot) * -1))}
  16%{transform:translate(var(--amp),calc(var(--amp) * -.3)) rotate(var(--rot))}
  24%{transform:translate(calc(var(--amp) * -.8),0) rotate(calc(var(--rot) * -.6))}
  32%{transform:translate(calc(var(--amp) * .8),calc(var(--amp) * .2)) rotate(calc(var(--rot) * .6))}
  40%{transform:translate(calc(var(--amp) * -.4),0) rotate(0)}}
@keyframes ed-shake{
  0%,100%{transform:translate(0,0) rotate(0)}
  15%{transform:translate(calc(var(--amp) * -1),calc(var(--amp) * .4)) rotate(calc(var(--rot) * -1))}
  30%{transform:translate(var(--amp),calc(var(--amp) * -.4)) rotate(var(--rot))}
  45%{transform:translate(calc(var(--amp) * -.9),calc(var(--amp) * -.2)) rotate(calc(var(--rot) * -.7))}
  60%{transform:translate(calc(var(--amp) * .9),calc(var(--amp) * .3)) rotate(calc(var(--rot) * .8))}
  75%{transform:translate(calc(var(--amp) * -.5),calc(var(--amp) * .2)) rotate(calc(var(--rot) * -.4))}
  90%{transform:translate(calc(var(--amp) * .4),0) rotate(calc(var(--rot) * .3))}}
@media (prefers-reduced-motion:reduce){[class*="st-key-c"]{animation:none!important}}
"""

def pushy_css(step: int, yes_index: int, no_index: int, no_clicks: int) -> str:
    """CSS for the meme: every 'no' grows the yes button, shrinks the no button until only yes is left,
    and shakes the yes button harder and faster each time.
    Pass the result to setup_editorial_page(extra_css=...)."""
    if no_clicks <= 0:
        return ""
    grow = 1 + PUSHY_GROW * no_clicks
    shrink = max(0.0, 1 - PUSHY_SHRINK * no_clicks)
    yes = f'.stApp .st-key-ed_card [class*="st-key-c{step}_{yes_index}"] [data-testid^="stBase"]'
    no = f'.stApp .st-key-ed_card [class*="st-key-c{step}_{no_index}"]'
    # padding/font grow (not transform) so the big button pushes the others away instead of overlapping them
    css = (f"{yes}{{padding:calc(7px * {grow:.2f}) calc(16px * {grow:.2f})!important;"
           f"min-height:calc(38px * {grow:.2f})!important}}"
           f"{yes} p{{font-size:calc(12px * {grow:.2f})!important}}"
           f"{no}{{opacity:{shrink:.2f};transform:scale({shrink:.2f});transform-origin:right center}}")
    if shrink <= 0:
        css += f"{no}{{display:none!important}}"
    # shake the yes button's wrapper (not the button itself, whose transform is used by the hover lift)
    amp, rot = SHAKE_AMP * no_clicks, SHAKE_ROT * no_clicks
    dur = max(SHAKE_MIN_SECONDS, SHAKE_SECONDS - 0.1 * (no_clicks - 1))
    anim = "ed-shake" if no_clicks >= SHAKE_CONTINUOUS_AFTER else "ed-shake-burst"
    yes_box = f'.stApp .st-key-ed_card [class*="st-key-c{step}_{yes_index}"]'
    css += (SHAKE_KEYFRAMES +
            f"{yes_box}{{--amp:{amp:.1f}px;--rot:{rot:.1f}deg;transform-origin:center;"
            f"animation:{anim} {dur:.2f}s ease-in-out infinite}}")
    return css


# ----------------------------- dark mood (the bot is losing patience) -----------------------------
DARK_RED = "#B3261E"
DARK_CSS = f"""
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],header[data-testid="stHeader"]{{background:#000000!important;transition:background-color 1.2s ease}}
.ed-art{{opacity:0;visibility:hidden;transition:opacity 1.2s ease,visibility 0s linear 1.2s}}
html .stApp .st-key-ed_card{{--ink:#EDEDED;--hl:{DARK_RED};background:#161616;color:#EDEDED;
  box-shadow:calc(8 * var(--u)) calc(8 * var(--u)) 0 {DARK_RED};
  transition:background-color 1.2s ease,box-shadow 1.2s ease,border-color 1.2s ease}}
html .stApp .st-key-ed_card .ed-title{{color:#EDEDED}}
html .stApp .st-key-ed_card .sb-bot{{color:#D6D6D6}}
html .stApp .st-key-ed_card .sb-bot b{{color:#FFFFFF}}
html .stApp .st-key-ed_card .sb-pill.chosen{{background:#EDEDED;color:#161616}}
html .stApp .st-key-ed_card [data-testid^="stBase"]{{--ed-bg:transparent;--ed-fg:#EDEDED;--ed-bd:#EDEDED}}
html .stApp .st-key-ed_card [data-testid="stBaseButton-secondary"]:hover{{--ed-bg:#2A2A2A}}
html .stApp .st-key-ed_card [data-testid="stBaseButton-primary"]{{--ed-bg:{DARK_RED};--ed-fg:#FFFFFF;--ed-bd:{DARK_RED}}}
html .stApp .st-key-ed_card [data-testid="stBaseButton-primary"]:hover{{--ed-bg:#7F1D1D;--ed-fg:#FFFFFF;--ed-bd:#7F1D1D}}
"""


def dark_css(on: bool) -> str:
    """Pure black page, no album covers, dark card with red shadow + highlighter.
    Pass the result to setup_editorial_page(extra_css=...)."""
    return DARK_CSS if on else ""


# ----------------------------- horror music (plays while the page is dark) -----------------------------
# FrontEnd/static/horror.mp3  (editorial.py is FrontEnd/UI/editorial.py, so parents[1] = FrontEnd)
HORROR_FILE = Path(__file__).resolve().parents[1] / "static" / "horror.mp3"


def horror_music(on: bool, tag=None) -> None:
    """Loops the horror track while on=True; stops the moment on=False (the player is removed).
    Call on EVERY run, at the same spot, so the player stays put (and keeps playing) between 'no' clicks."""
    with st.container(key="ed_audio"):   # hidden by CSS (.st-key-ed_audio)
        if not on:
            return
        if not HORROR_FILE.exists():
            print(f"[SpotiBai horror] missing file: {HORROR_FILE}")
            return
        try:
            st.audio(str(HORROR_FILE), format="audio/mpeg", autoplay=True, loop=True)
        except TypeError:   # older Streamlit without loop=
            st.audio(str(HORROR_FILE), format="audio/mpeg", autoplay=True)