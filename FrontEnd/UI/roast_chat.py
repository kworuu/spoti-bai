"""The SPOTIBAI chat card on the wheel page.

The card is drawn by Streamlit and floats over the wheel. It runs inside @st.fragment, so clicking a
reply only reruns this card: the wheel iframe never reloads and the music keeps playing.

Flow:
    roast beats, one at a time, each with reply buttons (buttons only move the story forward)
    -> verdict message (Aux Cord Rating + persona)
    -> free chat with st.chat_input

Session keys used: roast (dict from BackEnd.roast.make_roast), beat (int), chat (list of messages).
"""
import re
from html import escape

import streamlit as st

CHAR_SECONDS = 0.016  # typing speed (seconds per character)

# Card position/size keeps the wheel-page layout (1 unit = 100vh / 800; left 600, right 100, top/bottom 70).
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

.stApp .st-key-rc_panel {
  --u: calc(100vh / 800);
  --ink: #1A1A1A;
  --hl: #FCE38A;
  --mute: #6B6B6B;
  --line: #E5E5E5;
  position: fixed !important;
  z-index: 20;
  width: auto !important;
  max-width: none !important;
  height: auto !important;
  left: calc(600 * var(--u));
  right: calc(100 * var(--u));
  top: calc(70 * var(--u));
  bottom: calc(70 * var(--u));
  box-sizing: border-box;
  background: #FFFFFF;
  border: max(1.5px, calc(2 * var(--u))) solid var(--ink);
  border-radius: calc(16 * var(--u)) !important;
  box-shadow: calc(8 * var(--u)) calc(8 * var(--u)) 0 var(--ink);
  padding: calc(34 * var(--u)) calc(44 * var(--u)) calc(30 * var(--u)) !important;
  display: flex !important;
  flex-direction: column !important;
  gap: calc(16 * var(--u)) !important;
  overflow: hidden !important;
  color: var(--ink);
  animation: rc-card .65s cubic-bezier(.22, 1, .36, 1) both;
}
.st-key-rc_panel,
.st-key-rc_panel * {
  font-family: 'Inter', system-ui, sans-serif;
  box-sizing: border-box;
}
@keyframes rc-card {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: none; }
}

/* ---- header ---- */
.rc-head,
.rc-head * {
  text-align: center;
  border: none !important;
  box-shadow: none !important;
  margin-bottom: calc(18 * var(--u)) !important;
}
.rc-title {
  margin: 0;
  font-family: Georgia, 'Times New Roman', serif !important;
  font-weight: 400;
  font-size: max(24px, calc(38 * var(--u)));
  letter-spacing: .06em;
  line-height: 1.12;
  text-transform: uppercase;
}
.rc-hl {
  background: linear-gradient(180deg, transparent 62%, var(--hl) 62%);
  padding: 0 4px;
}

/* ---- scrollable message log ---- */
.st-key-rc_panel > [data-testid="stLayoutWrapper"]:has(> .st-key-rc_log) {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.st-key-rc_log {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto !important;
  display: block !important;
  scrollbar-width: thin;
  scrollbar-color: #C8C8C8 transparent;
  padding-right: 4px;
}
.st-key-rc_inner {
  gap: calc(35 * var(--u)) !important;
  padding-right: 6px;
  padding-bottom: calc(8 * var(--u));
  overflow: visible !important;
  flex-shrink: 0 !important;
  height: auto !important;
}

/* ---- bot and user messages ---- */
.rc-bot {
  margin: 0;
  max-width: 92%;
  font-size: max(16px, calc(22 * var(--u)));
  line-height: 1.6;
  color: #222222;
  white-space: pre-line;
}
.rc-bot b {
  color: var(--ink);
  font-weight: 600;
}
.rc-me {
  display: flex;
  justify-content: flex-end;
  margin: 0;
}
.rc-me span {
  max-width: 82%;
  padding: calc(9 * var(--u)) calc(16 * var(--u));
  background: var(--ink);
  color: #FFFFFF;
  font-size: max(13px, calc(16 * var(--u)));
  line-height: 1.4;
}

/* ---- verdict box ---- */
.rc-verdict {
  margin: 0;
  padding: calc(14 * var(--u)) calc(18 * var(--u));
  border: 1.5px solid var(--ink);
  background: #FFFFFF;
  box-shadow: calc(4 * var(--u)) calc(4 * var(--u)) 0 var(--hl);
  font-size: max(13px, calc(17 * var(--u)));
  line-height: 1.5;
  animation: rc-fade-up .45s ease both;
}
@keyframes rc-fade-up {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: none; }
}
.rc-verdict b.big {
  font-family: Georgia, 'Times New Roman', serif !important;
  font-size: max(20px, calc(30 * var(--u)));
  font-weight: 400;
  background: linear-gradient(180deg, transparent 58%, var(--hl) 58%);
  padding: 0 4px;
}

/* ---- typing animation (one span per character) ---- */
.rc-ch {
  opacity: 0;
  display: inline;
  animation: rc-pop .08s ease-out calc(var(--i) * var(--cps)) forwards;
}
@keyframes rc-pop {
  from { opacity: 0; transform: translateY(2px); }
  to { opacity: 1; transform: none; }
}

/* ---- reply buttons: appear after typing finishes ---- */
[class*="st-key-rc_choices"] {
  flex-direction: row !important;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: calc(8 * var(--u)) !important;
  animation: rc-reveal .4s ease var(--wait, 0s) both;
}
@keyframes rc-reveal {
  0% { opacity: 0; visibility: hidden; pointer-events: none; transform: translateY(4px); }
  1% { visibility: visible; pointer-events: none; }
  100% { opacity: 1; visibility: visible; pointer-events: auto; transform: none; }
}
[class*="st-key-rc_choices"] [data-testid="stElementContainer"] {
  width: auto !important;
}
[class*="st-key-rc_choices"] button {
  border-radius: 0 !important;
  border: 1px solid var(--ink) !important;
  background: #FFFFFF !important;
  color: var(--ink) !important;
  padding: calc(7 * var(--u)) calc(16 * var(--u)) !important;
  min-height: 38px;
  box-shadow: none !important;
  transition: background-color .2s ease, color .2s ease, transform .18s ease !important;
}
[class*="st-key-rc_choices"] button p {
  color: inherit !important;
  font-size: max(11px, calc(12 * var(--u))) !important;
  font-weight: 500 !important;
  letter-spacing: .12em !important;
  text-transform: uppercase !important;
  line-height: 1.35 !important;
  margin: 0 !important;
}
[class*="st-key-rc_choices"] button:hover {
  background: #F5F5F5 !important;
  transform: translateY(-1px);
}
[class*="st-key-rc_choices"] [class*="st-key-rc_c"]:first-child button {
  background: var(--ink) !important;
  color: #FFFFFF !important;
}
[class*="st-key-rc_choices"] [class*="st-key-rc_c"]:first-child button:hover {
  background: var(--hl) !important;
  color: var(--ink) !important;
}

/* ---- chat input ---- */
.stApp .st-key-rc_panel [data-testid="stChatInput"],
.stApp .st-key-rc_panel [data-testid="stChatInput"] > div,
.stApp .st-key-rc_panel [data-testid="stChatInput"] [data-baseweb="textarea"],
.stApp .st-key-rc_panel [data-testid="stChatInput"] textarea {
  border-radius: calc(16 * var(--u)) !important;
}
.stApp .st-key-rc_panel [data-testid="stChatInput"] > div {
  border: 1px solid var(--ink) !important;
  background: #FFFFFF !important;
}
.stApp .st-key-rc_panel [data-testid="stChatInput"] textarea {
  border: none !important;
  color: var(--ink) !important;
  -webkit-text-fill-color: var(--ink);
  caret-color: var(--ink);
  font-size: max(13px, calc(15 * var(--u)));
}
.stApp .st-key-rc_panel [data-testid="stChatInput"] textarea::placeholder {
  color: #8A8A8A;
  -webkit-text-fill-color: #8A8A8A;
}

/* hidden holder for the auto-scroll script */
.st-key-rc_js {
  position: absolute;
  height: 0;
  overflow: hidden;
}

/* ---- song picks ---- */
.rc-picks {
  margin: 0;
  border: 1.5px solid var(--ink);
  background: #FFFFFF;
  padding: calc(6 * var(--u)) calc(14 * var(--u));
}
.rc-pick {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 7px 0;
  border-bottom: 1px solid var(--line);
  font-size: max(13px, calc(15 * var(--u)));
  color: var(--ink);
  text-decoration: none;
}
.rc-pick:last-child {
  border-bottom: 0;
}
.rc-pick img,
.rc-pick .rc-noimg {
  width: 40px;
  height: 40px;
  border: 1px solid var(--ink);
  object-fit: cover;
  flex: none;
  background: #F2F2F2;
}
.rc-pick span {
  flex: 1;
  min-width: 0;
}
.rc-pick small {
  color: var(--mute);
}
a.rc-pick:hover {
  background: #FFFDF5;
}
a.rc-pick:hover b {
  background: linear-gradient(180deg, transparent 55%, var(--hl) 55%);
}
</style>
"""

BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


def _split_bold(text: str) -> list[tuple[bool, str]]:
    """Split '**Artist** is fine' into [(True, 'Artist'), (False, ' is fine')]."""
    pieces, last_end = [], 0
    for match in BOLD_PATTERN.finditer(text):
        if match.start() > last_end:
            pieces.append((False, text[last_end:match.start()]))
        pieces.append((True, match.group(1)))
        last_end = match.end()
    if last_end < len(text):
        pieces.append((False, text[last_end:]))
    return pieces


def _plain_html(text: str) -> str:
    return "".join(
        f"<b>{escape(piece)}</b>" if is_bold else escape(piece)
        for is_bold, piece in _split_bold(text)
    )


def _typed_html(text: str) -> tuple[str, float]:
    """Give each character its own start time (pausing on punctuation). Returns (html, seconds)."""
    parts, position = [], 0
    for is_bold, piece in _split_bold(text):
        letters = []
        for char in piece:
            if char == "\n":
                letters.append("<br>")
                position += 4
            else:
                letters.append(f'<span class="rc-ch" style="--i:{position}">{escape(char)}</span>')
                position += 1 + (8 if char in ".!?" else 4 if char in ",;:" else 0)
        joined = "".join(letters)
        parts.append(f"<b>{joined}</b>" if is_bold else joined)
    total_seconds = max(0.0, (position - 1) * CHAR_SECONDS + 0.08)
    return "".join(parts), total_seconds


def _show_bot_message(text: str, typing_step: int | None = None) -> None:
    """Show a bot message. Pass typing_step to type it out and delay that step's reply buttons."""
    if typing_step is None:
        st.markdown(f'<p class="rc-bot">{_plain_html(text)}</p>', unsafe_allow_html=True)
        return
    html, seconds = _typed_html(text)
    st.markdown(
        f"<style>.st-key-rc_choices_{typing_step}{{--wait:{seconds + 0.25:.2f}s}}</style>"
        f'<p class="rc-bot" style="--cps:{CHAR_SECONDS}s" aria-label="{escape(text)}">{html}</p>',
        unsafe_allow_html=True,
    )


def _show_picks(picks: list[dict]) -> None:
    rows = []
    for pick in picks:
        image = (
            f'<img src="{escape(pick["image"])}" alt="">'
            if pick.get("image")
            else '<div class="rc-noimg"></div>'
        )
        body = f'{image}<span><b>{escape(pick["name"])}</b><br><small>{escape(pick["artist"])}</small></span>'
        if pick.get("url"):
            rows.append(f'<a class="rc-pick" href="{escape(pick["url"])}" target="_blank" rel="noopener">{body}</a>')
        else:
            rows.append(f'<div class="rc-pick">{body}</div>')
    st.markdown(f'<div class="rc-picks">{"".join(rows)}</div>', unsafe_allow_html=True)


def _show_message(message: dict) -> None:
    role = message["role"]
    if role == "bot":
        _show_bot_message(message["text"])
    elif role == "picks":
        _show_picks(message["picks"])
    elif role == "verdict":
        st.markdown(f'<div class="rc-verdict">{message["html"]}</div>', unsafe_allow_html=True)
    else:  # "choice" (a clicked reply button) or "user" (typed text)
        text = message["labels"][message["picked"]] if role == "choice" else message["text"]
        st.markdown(f'<div class="rc-me"><span>{escape(text)}</span></div>', unsafe_allow_html=True)


def _verdict_html(roast: dict, lang: str) -> str:
    aux, persona = roast["aux_cord"], roast["persona"]
    label = "Aux Cord Rating" if lang == "en" else "Aux Cord Rating mo"
    lines = [f'{label}: <b class="big">{escape(str(aux["score"]))}/10</b>']
    if aux.get("reason"):
        lines.append(escape(aux["reason"]))
    if persona.get("aesthetic"):
        lines.append(f"<b>Aesthetic:</b> {escape(persona['aesthetic'])}")
    if persona.get("vibe"):
        lines.append(f"<b>Vibe:</b> {escape(persona['vibe'])}")
    return "<br>".join(lines)


def _scroll_to_bottom(step: int) -> None:
    """Keep the log scrolled to the newest message while Streamlit finishes layout/animation.

    The changing number in the script comment makes Streamlit re-run it on every new message.
    """
    script = (
        "<script>/*%d*/(function(){var tries=0,timer=setInterval(function(){"
        "var log=document.querySelector('.st-key-rc_log');if(log)log.scrollTop=log.scrollHeight;"
        "if(++tries>10)clearInterval(timer);},150);})();</script>"
    ) % step
    with st.container(key="rc_js"):
        try:
            st.html(script, unsafe_allow_javascript=True)
        except TypeError:  # older Streamlit without unsafe_allow_javascript
            pass


def real_reply(text: str, lang: str) -> tuple[str, list[dict]]:
    """AI reply plus song picks checked against Spotify. Returns (reply_text, picks)."""
    from BackEnd.chat import reply
    from BackEnd.picks import resolve_picks

    state = st.session_state
    result = reply(state.profile, state.stats, state.roast, state.chat, text, lang)
    picks = resolve_picks(state.sp, result["picks"]) if result["picks"] and state.get("sp") else []
    return result["reply"], picks


def init_chat_state(roast: dict) -> None:
    """Call whenever a NEW roast is generated (new login or language change)."""
    st.session_state.roast = roast
    st.session_state.beat = 0
    st.session_state.chat = []


@st.fragment
def chat_panel() -> None:
    state = st.session_state
    roast = state.roast
    lang = roast.get("lang", "en")
    beats = roast["beats"]

    st.markdown(CSS, unsafe_allow_html=True)
    with st.container(key="rc_panel"):
        st.markdown(
            '<div class="rc-head"><h1 class="rc-title">SPOTI<span class="rc-hl">BAI</span></h1></div>',
            unsafe_allow_html=True,
        )

        with st.container(key="rc_log"):
            with st.container(key="rc_inner"):
                for message in state.chat:
                    _show_message(message)

                # Scripted roast: the current beat types out, then its reply buttons fade in.
                if state.beat < len(beats):
                    beat = beats[state.beat]
                    _show_bot_message(beat["text"], typing_step=state.beat)
                    picked = None
                    with st.container(key=f"rc_choices_{state.beat}"):
                        for index, label in enumerate(beat["replies"]):
                            if st.button(label, key=f"rc_c{state.beat}_{index}"):
                                picked = index
                    if picked is not None:
                        state.chat += [
                            {"role": "bot", "text": beat["text"]},
                            {"role": "choice", "labels": beat["replies"], "picked": picked},
                        ]
                        state.beat += 1
                        if state.beat == len(beats):
                            state.chat.append({"role": "verdict", "html": _verdict_html(roast, lang)})
                        st.rerun(scope="fragment")

        _scroll_to_bottom(len(state.chat) * 10 + state.beat)

        # Free chat opens only after the roast is finished.
        if state.beat >= len(beats):
            text = st.chat_input(
                "Talk back to SpotiBai…" if lang == "en" else "Tubag sa SpotiBai…",
                max_chars=500,
                key="rc_input",
            )
            if text:
                reply_function = state.get("reply_fn") or real_reply
                with st.spinner("SpotiBai is typing…" if lang == "en" else "Nag-type si SpotiBai…"):
                    answer, picks = reply_function(text, lang)
                if answer:
                    state.chat.append({"role": "user", "text": text})
                    state.chat.append({"role": "bot", "text": answer})
                    if picks:
                        state.chat.append({"role": "picks", "picks": picks})
                st.rerun(scope="fragment")