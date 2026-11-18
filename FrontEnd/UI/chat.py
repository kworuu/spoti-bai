"""Chat pieces shared by every conversational screen.

- ai_say()        AI message that is "typed" character by character (pure CSS, no server waiting)
- choice_buttons()  reply buttons that stay invisible + unclickable until typing finishes, then fade in
- ai_said() / chosen_pills()  how finished messages and past choices look in the history
Tune the speed with CHAR_SECONDS (lower = faster)."""
from html import escape
import streamlit as st

CHAR_SECONDS = 0.018   # typing speed: seconds per character
FADE_SECONDS = 0.7     # how long the reply buttons take to fade in (set in theme.py CSS too)


def _typed(text: str) -> tuple[str, float]:
    """Wrap each character in a span with its own start time. Returns (html, total seconds)."""
    spans, i = [], 0                       # i = position on the "typing clock" (in character units)
    lines = text.split("\n")
    for n, line in enumerate(lines):
        for k, ch in enumerate(line):
            nxt = i + 1 + (8 if ch in ".!?" else 3 if ch == "," else 0)   # human-ish pauses
            spans.append([f'<span class="sb-ch" aria-hidden="true" style="--i:{i};--g:{nxt - i}">{escape(ch)}</span>'])
            i = nxt
        if n < len(lines) - 1:
            spans.append(["<br>"])
            i += 6
    flat = [s[0] for s in spans]
    for j in range(len(flat) - 1, -1, -1):  # mark the last character (its caret blinks, then vanishes)
        if flat[j].startswith("<span"):
            flat[j] = flat[j].replace('class="sb-ch"', 'class="sb-ch sb-last"', 1)
            break
    return "".join(flat), i * CHAR_SECONDS


def ai_say(text: str, step: int) -> float:
    """Show `text` as a typed AI message. `step` must be unique per message. Returns typing seconds."""
    spans, secs = _typed(text)
    # the style tag sets how long this step's reply buttons stay hidden (same element = no extra gap)
    st.markdown(
        f'<style>.st-key-sb_choices_{step}{{--wait:{secs + 0.3:.2f}s}}</style>'
        f'<p class="sb-bot sb-typed" style="--cps:{CHAR_SECONDS}s" aria-label="{escape(" ".join(text.split()))}">{spans}</p>',
        unsafe_allow_html=True)
    return secs


def ai_said(text: str) -> None:
    """A finished AI message in the history (no typing animation)."""
    st.markdown(f'<p class="sb-bot">{escape(text).replace(chr(10), "<br>")}</p>', unsafe_allow_html=True)


def chosen_pills(labels: list[str], chosen: int) -> None:
    """Past reply options: the one the user picked is black, the rest stay slate."""
    pills = "".join(f'<span class="sb-pill{" chosen" if i == chosen else ""}">{escape(t)}</span>'
                    for i, t in enumerate(labels))
    st.markdown(f'<div class="sb-hist">{pills}</div>', unsafe_allow_html=True)


def choice_buttons(options: list[dict], step: int) -> int | None:
    """options: [{"label": str, "brand": "spotify"|"youtube" (optional)}]. Returns the clicked index.
    Hidden and unclickable until the typing is done (CSS timer), then fades in."""
    clicked = None
    with st.container(key=f"sb_choices_{step}"):
        for i, o in enumerate(options):
            brand = f"_brand-{o['brand']}" if o.get("brand") else ""
            if st.button(o["label"], key=f"c{step}_{i}{brand}", type="secondary"):
                clicked = i
    return clicked


def follow_scroll(seconds: float, step: int) -> None:
    """Keep the newest text in view while it types (long chats grow below the fold)."""
    js = ("<script>/*%d*/(function(){var end=Date.now()+%d;"
          "var m=document.querySelector('[data-testid=\"stMain\"]')||document.scrollingElement;"
          "var t=setInterval(function(){m.scrollTo({top:m.scrollHeight,behavior:'smooth'});"
          "if(Date.now()>end)clearInterval(t);},250);})();</script>") % (step, int(seconds * 1000))
    with st.container(key="sb_js"):
        try:
            st.html(js, unsafe_allow_javascript=True)
        except TypeError:  # older Streamlit without JS support: just no auto-scroll
            pass
