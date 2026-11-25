"""The SPOTIBAI chat card on the wheel page (P4).

Why this exists: the chat used to live inside the wheel's HTML iframe, where nothing the user did
could reach Python. Now the card is drawn by Streamlit, floating over the wheel in the same spot and
style, and runs inside @st.fragment: clicking a reply only reruns THIS card, so the wheel iframe is
never reloaded and the music keeps playing.

Flow (option "a", agreed Nov 25):
    6 roast beats, one at a time, each with 2 reply buttons (buttons only move the story forward)
    → verdict message (Aux Cord Rating + persona; the real card is P5)
    → free chat with st.chat_input (real replies are P6; placeholder for now)

Session keys used: roast (dict from BackEnd.roast.make_roast), beat (int), chat (list of messages).
"""
import re
from html import escape

import streamlit as st

CHAR_SECONDS = 0.016        # typing speed (seconds per character)

# Card position/size copy Eros's design: the wheel page is 800 "units" tall and scaled to the
# window height, so 1 unit = 100vh / 800. Chat card: left 600, right 100, top/bottom 32 units.
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap');
.st-key-rc_panel{--u:calc(100vh / 800);position:fixed!important;z-index:20;width:auto!important;max-width:none!important;height:auto!important;
  left:calc(600 * var(--u));right:calc(100 * var(--u));top:calc(32 * var(--u));bottom:calc(32 * var(--u));
  box-sizing:border-box;background:#fff;border:max(2px, calc(3 * var(--u))) solid #000;
  border-radius:calc(22 * var(--u));padding:calc(40 * var(--u)) calc(56 * var(--u)) calc(36 * var(--u)) !important;
  display:flex!important;flex-direction:column!important;gap:calc(18 * var(--u))!important;overflow:hidden!important;
  font-family:Inter,system-ui,sans-serif;color:#000}
.st-key-rc_panel *{font-family:Inter,system-ui,sans-serif}
.rc-title{margin:0;text-align:center;font-size:calc(46 * var(--u));font-weight:800;letter-spacing:.01em;line-height:1.1}
/* message log: scrolls inside the card; _scroll_to_bottom() keeps the newest message in view */
.st-key-rc_panel > [data-testid="stLayoutWrapper"]:has(> .st-key-rc_log){flex:1 1 auto;min-height:0;display:flex;flex-direction:column}
.st-key-rc_log{flex:1 1 auto;min-height:0;overflow-y:auto!important;display:block!important;scrollbar-width:thin;scrollbar-color:#bbb transparent}
.st-key-rc_inner{gap:calc(24 * var(--u))!important;padding-right:6px;overflow:visible!important;flex-shrink:0!important;height:auto!important}
.rc-bot{margin:0;font-size:max(15px, calc(19 * var(--u)));line-height:1.55;white-space:pre-line;max-width:92%}
.rc-me{display:flex;justify-content:flex-end;margin:0}
.rc-me span{max-width:80%;padding:calc(10 * var(--u)) calc(18 * var(--u));border-radius:16px 16px 4px 16px;background:#000;color:#fff;
  font-size:max(14px, calc(18 * var(--u)));line-height:1.35}
.rc-verdict{margin:0;padding:calc(14 * var(--u)) calc(18 * var(--u));border:2px solid #000;border-radius:14px;
  font-size:max(14px, calc(18 * var(--u)));line-height:1.45}
.rc-verdict b.big{font-size:max(22px, calc(34 * var(--u)));font-weight:800}
/* typed text: each character appears at its own time (--i) */
.rc-ch{opacity:0;animation:rc-pop 1ms linear calc(var(--i) * var(--cps)) both}
@keyframes rc-pop{to{opacity:1}}
/* reply buttons: hidden until typing ends (--wait), then fade in */
[class*="st-key-rc_choices"]{flex-direction:row!important;flex-wrap:wrap;justify-content:flex-end;gap:10px!important;
  animation:rc-reveal .5s ease var(--wait, 0s) both}
@keyframes rc-reveal{from{opacity:0;visibility:hidden;pointer-events:none}to{opacity:1;visibility:visible;pointer-events:auto}}
[class*="st-key-rc_choices"] [data-testid="stElementContainer"]{width:auto!important}
[class*="st-key-rc_choices"] button{border-radius:999px!important;border:2px solid #000!important;background:#fff!important;
  color:#000!important;padding:6px 18px!important;min-height:44px}
[class*="st-key-rc_choices"] button p{color:inherit!important;font-weight:500}
[class*="st-key-rc_choices"] button:hover{background:#000!important;color:#fff!important}
[class*="st-key-rc_choices"] [class*="st-key-rc_c"]:first-child button{background:#000!important;color:#fff!important}
/* chat input in the card */
.st-key-rc_panel [data-testid="stChatInput"]{border-radius:12px;background:#5F5B5B}
.st-key-rc_panel [data-testid="stChatInput"] textarea{color:#fff;font-size:16px}
.st-key-rc_panel [data-testid="stChatInput"] textarea::placeholder{color:#E6E6E6}
.st-key-rc_js{position:absolute;height:0;overflow:hidden}
</style>
"""

_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _segments(text: str):
    """Split '**Artist** is fine' into [(True,'Artist'), (False,' is fine')]."""
    out, last = [], 0
    for m in _BOLD.finditer(text):
        if m.start() > last:
            out.append((False, text[last:m.start()]))
        out.append((True, m.group(1)))
        last = m.end()
    if last < len(text):
        out.append((False, text[last:]))
    return out


def _static_html(text: str) -> str:
    return "".join(f"<b>{escape(s)}</b>" if bold else escape(s) for bold, s in _segments(text))


def _typed_html(text: str) -> tuple[str, float]:
    """Each character gets its own start time; **bold** stays bold. Returns (html, seconds)."""
    parts, i = [], 0
    for bold, seg in _segments(text):
        chars = []
        for ch in seg:
            chars.append(f'<span class="rc-ch" style="--i:{i}">{escape(ch)}</span>')
            i += 1 + (8 if ch in ".!?" else 3 if ch == "," else 0)
        parts.append(f"<b>{''.join(chars)}</b>" if bold else "".join(chars))
    return "".join(parts), i * CHAR_SECONDS


def _bot(text: str, typed_step: int | None = None) -> float:
    """Show a bot message; if typed_step is given it types out. Returns typing seconds."""
    if typed_step is None:
        st.markdown(f'<p class="rc-bot">{_static_html(text)}</p>', unsafe_allow_html=True)
        return 0.0
    html, secs = _typed_html(text)
    st.markdown(f'<style>.st-key-rc_choices_{typed_step}{{--wait:{secs + 0.2:.2f}s}}</style>'
                f'<p class="rc-bot" style="--cps:{CHAR_SECONDS}s" aria-label="{escape(text)}">{html}</p>',
                unsafe_allow_html=True)
    return secs


def _render(m: dict) -> None:
    if m["role"] == "bot":
        _bot(m["text"])
    elif m["role"] == "choice":          # only the reply they picked stays, as their own bubble
        st.markdown(f'<div class="rc-me"><span>{escape(m["labels"][m["picked"]])}</span></div>',
                    unsafe_allow_html=True)
    elif m["role"] == "verdict":
        st.markdown(f'<div class="rc-verdict">{m["html"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="rc-me"><span>{escape(m["text"])}</span></div>', unsafe_allow_html=True)


def _verdict_html(roast: dict, lang: str) -> str:
    aux, persona = roast["aux_cord"], roast["persona"]
    label = "Aux Cord Rating" if lang == "en" else "Aux Cord Rating mo"
    lines = [f'{label}: <b class="big">{aux["score"]}/10</b>']
    if aux.get("reason"):
        lines.append(escape(aux["reason"]))
    if persona.get("aesthetic"):
        lines.append(f"<b>Aesthetic:</b> {escape(persona['aesthetic'])}")
    if persona.get("vibe"):
        lines.append(f"<b>Vibe:</b> {escape(persona['vibe'])}")
    return "<br>".join(lines)


def _scroll_to_bottom(step: int) -> None:
    """Scroll the log to the newest message (a few times, while Streamlit finishes drawing)."""
    js = ("<script>/*%d*/(function(){var n=0,t=setInterval(function(){"
          "var l=document.querySelector('.st-key-rc_log');if(l)l.scrollTop=l.scrollHeight;"
          "if(++n>8)clearInterval(t);},150);})();</script>") % step
    with st.container(key="rc_js"):
        try:
            st.html(js, unsafe_allow_javascript=True)
        except TypeError:          # older Streamlit without JS in st.html: no auto-scroll
            pass


def placeholder_reply(text: str, lang: str) -> str:
    """TODO (P6): replace with BackEnd.chat.reply(profile, stats, history, lang)."""
    return ("Talk-back chat is coming soon. For now, I've said what I had to say."
            if lang == "en" else "Moabot ra ang talk-back chat. Sa karon, nasulti na nako tanan.")


def init_chat_state(roast: dict) -> None:
    """Call whenever a NEW roast is generated (new login or language change)."""
    st.session_state.roast = roast
    st.session_state.beat = 0
    st.session_state.chat = []


@st.fragment
def chat_panel() -> None:
    ss = st.session_state
    roast, lang = ss.roast, ss.roast.get("lang", "en")
    beats = roast["beats"]

    st.markdown(CSS, unsafe_allow_html=True)
    with st.container(key="rc_panel"):
        st.markdown('<h1 class="rc-title">SPOTIBAI</h1>', unsafe_allow_html=True)
        with st.container(key="rc_log"):
            with st.container(key="rc_inner"):
                for m in ss.chat:
                    _render(m)

                # 1) scripted roast: current beat types out, then its 2 buttons fade in
                if ss.beat < len(beats):
                    b = beats[ss.beat]
                    _bot(b["text"], typed_step=ss.beat)
                    picked = None
                    with st.container(key=f"rc_choices_{ss.beat}"):
                        for i, label in enumerate(b["replies"]):
                            if st.button(label, key=f"rc_c{ss.beat}_{i}"):
                                picked = i
                    if picked is not None:
                        ss.chat += [{"role": "bot", "text": b["text"]},
                                    {"role": "choice", "labels": b["replies"], "picked": picked}]
                        ss.beat += 1
                        if ss.beat == len(beats):           # roast done → verdict
                            ss.chat.append({"role": "verdict", "html": _verdict_html(roast, lang)})
                        st.rerun(scope="fragment")

        _scroll_to_bottom(len(ss.chat) * 10 + ss.beat)

        # 2) free chat, only after the roast
        if ss.beat >= len(beats):
            text = st.chat_input("Talk back to SpotiBai…" if lang == "en" else "Tubag sa SpotiBai…",
                                 max_chars=500, key="rc_input")
            if text:
                ss.chat.append({"role": "user", "text": text})
                ss.chat.append({"role": "bot", "text": placeholder_reply(text, lang)})
                st.rerun(scope="fragment")