"""Shared SpotiBai look. Call setup_page() first on every screen, then build inside card()."""
from contextlib import contextmanager
from html import escape
import streamlit as st
from spotify_covers import get_covers
from .background import COVER_COUNT, fade_css, render_background

# The floating background IS the design, so by default it keeps moving even when the OS asks for
# reduced motion (Windows: Settings > Accessibility > Visual effects > Animation effects off,
# or Battery saver, both turn this on). Set True to freeze the covers for those users instead.
RESPECT_REDUCED_MOTION = False
FREEZE_CSS = "@media (prefers-reduced-motion:reduce){.sb-x,.sb-cover{animation:none}}"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,800&family=Instrument+Sans:wght@400;500;600&display=swap');
:root{--ink:#0E0E10;--paper:#fff;--fog:#E8E8EA;--slate:#5B5757}

/* hide multipage sidebar + chrome; screens navigate themselves */
[data-testid="stSidebar"],[data-testid="stSidebarNav"],[data-testid="stSidebarCollapsedControl"],[data-testid="stExpandSidebarButton"],
[data-testid="collapsedControl"],footer,#MainMenu,.stAppDeployButton{display:none!important}
header[data-testid="stHeader"]{background:transparent}
.stApp,.stApp p,.stApp button,.stApp input{font-family:'Instrument Sans',system-ui,sans-serif}
.stMain .block-container{position:relative;z-index:1;max-width:560px;padding-top:12vh}

/* background layer: .sb-bg is fixed to the browser window, independent of Streamlit wrappers */
.st-key-sb_bg{position:absolute;height:0;margin:0;padding:0}
.sb-bg{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden;animation:sb-in 1.2s ease both}
.sb-x{position:absolute;left:var(--x);top:var(--y);width:var(--s);height:var(--s);
  will-change:transform,opacity;
  animation:sb-x var(--xd) ease-in-out var(--xdelay) infinite alternate,
    sb-fade var(--fd) ease-in-out var(--fdelay) infinite}
.sb-cover{display:block;width:100%;height:100%;object-fit:cover;border:0;border-radius:2px;
  filter:drop-shadow(0 0 .5px #0E0E10) drop-shadow(0 0 .5px #0E0E10) blur(var(--b));opacity:var(--o);
  will-change:transform;
  animation:sb-y var(--yd) ease-in-out var(--ydelay) infinite alternate}
.sb-cover.sb-empty{background:#d4d4d8;border:1px solid var(--ink);filter:blur(var(--b))}
.sb-js img.sb-cover:not(.ready){opacity:0}
.sb-js img.sb-cover.ready{transition:opacity 1.4s ease}
.sb-bg::after{content:"";position:absolute;inset:0;background:radial-gradient(ellipse 42% 46% at 50% 46%,rgba(232,232,234,.8) 0%,rgba(232,232,234,.5) 60%,rgba(232,232,234,0) 100%);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);-webkit-mask-image:radial-gradient(ellipse 50% 54% at 50% 46%,#000 35%,transparent 100%);mask-image:radial-gradient(ellipse 50% 54% at 50% 46%,#000 35%,transparent 100%)}
.sb-credit{position:absolute;right:12px;bottom:8px;font:500 11px 'Instrument Sans',sans-serif;color:var(--slate)}
@keyframes sb-x{from{transform:translateX(0)}to{transform:translateX(var(--dx))}}
@keyframes sb-y{from{transform:translateY(0) rotate(var(--r0))}to{transform:translateY(var(--dy)) rotate(var(--r1))}}
@keyframes sb-in{from{opacity:0}to{opacity:1}}

/* card */
[class*="st-key-sb_card"]{background:var(--paper);border:2px solid var(--ink);border-radius:14px;
  padding:2rem 2rem 1.75rem;position:relative;z-index:2;box-shadow:0 24px 60px rgba(14,14,16,.18)}
.sb-wordmark{font-family:'Bricolage Grotesque',sans-serif;font-weight:800;font-size:2.1rem;
  letter-spacing:-.02em;text-align:center;margin:0 0 .25rem;padding:0;color:var(--ink)}
.sb-lede{text-align:center;color:var(--slate);margin:0 0 1.25rem}
.sb-bot{margin:.5rem 0;line-height:1.5}

/* buttons: black = primary reply, slate = alternate reply */
[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-secondary"]{
  border:0;border-radius:999px;padding:.5rem 1.3rem;color:#fff;font-weight:500}
[data-testid="stBaseButton-primary"]{background:var(--ink)}
[data-testid="stBaseButton-secondary"]{background:var(--slate)}
[data-testid^="stBase"] p{color:#fff;transition:color .35s ease}
.stApp [data-testid^="stBase"]{transition:background-color .35s ease,color .35s ease,transform .2s ease,opacity .35s ease,box-shadow .35s ease}
.stApp [data-testid="stBaseButton-primary"]:hover:not(:disabled){background:#2B2B30;color:#fff}
.stApp [data-testid="stBaseButton-secondary"]:hover:not(:disabled){background:#756F6F;color:#fff}
.stApp [data-testid^="stBase"]:hover:not(:disabled) p{color:#fff}
.stApp [data-testid^="stBase"]:active:not(:disabled){transform:scale(.985)}
.stApp [data-testid^="stBase"]:disabled,.stApp [data-testid^="stBase"]:disabled:hover{
  background:var(--slate);color:#fff;opacity:.5;cursor:not-allowed;border:0}
.stApp [data-testid^="stBase"]:disabled p{color:#fff}
/* brand hover colors: Spotify green (dark text for contrast), YouTube red */
.stApp .st-key-btn_spotify [data-testid="stBaseButton-primary"]:hover:not(:disabled){background:#1ED760;color:#0E0E10}
.stApp .st-key-btn_spotify [data-testid="stBaseButton-primary"]:hover:not(:disabled) p{color:#0E0E10}
.stApp .st-key-btn_youtube [data-testid^="stBase"]:disabled:hover{background:#FF0000;color:#fff;opacity:1}
[data-testid^="stBase"]:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
.st-key-sb_stack [data-testid="stElementContainer"]{width:100%!important}
.st-key-sb_stack button{width:100%}
.st-key-sb_replies{align-items:flex-end}
"""


def setup_page(title: str = "SpotiBai") -> None:
    """Must be the first Streamlit call on every screen."""
    st.set_page_config(page_title=title, page_icon="🎧", layout="centered",
                       initial_sidebar_state="collapsed")
    st.markdown(f"<style>{CSS}{fade_css()}{FREEZE_CSS if RESPECT_REDUCED_MOTION else ''}</style>", unsafe_allow_html=True)
    render_background(get_covers(COVER_COUNT))


@contextmanager
def card(key: str = "card"):
    """White bordered panel from the wireframes. Use a different key per card on one page."""
    with st.container(key=f"sb_{key}"):
        yield


def wordmark() -> None:
    st.markdown('<h1 class="sb-wordmark">SPOTIBAI</h1>', unsafe_allow_html=True)


def lede(text: str) -> None:
    st.markdown(f'<p class="sb-lede">{escape(text)}</p>', unsafe_allow_html=True)


def bot_say(text: str) -> None:
    st.markdown(f'<p class="sb-bot">{escape(text)}</p>', unsafe_allow_html=True)