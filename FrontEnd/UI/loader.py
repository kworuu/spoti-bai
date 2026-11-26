"""Full-screen SpotiBai loading screen, shown while the app pulls data from Spotify.

Layout: equalizer + SPOTIBAI wordmark, one fun line that keeps rotating (so long waits like the
AI roast still feel alive), and a small pill with a tiny spinning record + the current step.

Usage (see wheel.py) — same API as before:
    loader = LoadingScreen(lang)
    loader.show(0)                    # step 0, 1, 2
    loader.show(1, covers=[url, ...]) # optional: use these covers (e.g. the user's own songs)
    loader.hide()                     # before showing the page or an error

Pure HTML/CSS (Streamlit strips <script> from st.markdown), so every animation is CSS-only.
"""
import random
from html import escape

import streamlit as st

TRACKS = {   # step names shown in the pill
    "en": ["Your top songs", "Your library", "The roast"],
    "ceb": ["Imong top songs", "Imong library", "Ang roast"],
}

QUIPS = {   # per step; 4 are picked and rotate while that step runs
    "en": [
        [
            "Sneaking into your Spotify…",
            "Counting replays of that one song…",
            "Ignoring your guilty pleasures (for now)…",
            "Finding the song you skip but never remove…",
            "Unzipping your top 10…",
        ],
        [
            "Measuring how basic your top artist is…",
            "Calculating main character energy…",
            "Found a playlist called 'sad hours'. Noted.",
            "Consulting 4,812 music snobs…",
            "Checking if you're still in your 2019 era…",
        ],
        [
            "Asked the AI to be nice. It said no.",
            "Sharpening the insults…",
            "Writing your verdict in all caps…",
            "Rating your aux cord privileges…",
            "Almost done. Brace yourself.",
        ],
    ],
    "ceb": [
        [
            "Gisilip imong Spotify…",
            "Giihap pila ka replay sa usa ka kanta…",
            "Gitago ang imong guilty pleasures…",
            "Gipangita ang kanta nga permi nimo gi-skip…",
        ],
        [
            "Gisukod kung unsa ka basic imong top artist…",
            "Naa kay playlist nga 'sad hours'. Na-note.",
            "Gisusi kung naa pa ka sa imong 2019 era…",
            "Gikalot imong tibuok library…",
        ],
        [
            "Gihangyo ang AI nga buotan. Nidumili siya.",
            "Gipahait ang mga insulto…",
            "Gi-rate imong aux cord privileges…",
            "Hapit na. Pangandam.",
        ],
    ],
}

QUIP_SECS = 2.8          # how long each fun line stays up
COVER_SECS = 1.6         # how long each cover stays on the vinyl label

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,800&family=Instrument+Sans:wght@400;500;600&display=swap');
.sb-load{position:fixed;inset:0;z-index:999999;display:flex;flex-direction:column;align-items:center;
  justify-content:center;gap:1.1rem;padding:1rem;box-sizing:border-box;background:#E8E8EA;
  font-family:'Instrument Sans',system-ui,sans-serif;color:#0E0E10}
.sb-load *{box-sizing:border-box}
.sb-load-head{display:flex;flex-direction:column;align-items:center;gap:.55rem}
.sb-eq{display:flex;align-items:flex-end;gap:5px;height:28px}
.sb-eq i{width:4px;height:100%;background:#0E0E10;border-radius:2px;transform-origin:bottom;
  animation:sb-eq 1s ease-in-out infinite}
.sb-eq i:nth-child(1){animation-delay:-.9s}.sb-eq i:nth-child(2){animation-delay:-.6s}
.sb-eq i:nth-child(3){animation-delay:-.3s}.sb-eq i:nth-child(4){animation-delay:-.75s}
.sb-eq i:nth-child(5){animation-delay:-.45s}
@keyframes sb-eq{0%,100%{transform:scaleY(.2)}50%{transform:scaleY(1)}}
.sb-load-mark{font:800 2rem 'Bricolage Grotesque',sans-serif;letter-spacing:-.02em;margin:0;padding:0}

/* rotating fun line */
.sb-quips{position:relative;height:1.5em;width:min(460px,100%);text-align:center;font-size:.95rem;color:#5B5757}
.sb-quips span{position:absolute;inset:0;opacity:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  animation:sb-quip var(--cycle) ease var(--d) infinite}
@keyframes sb-quip{0%{opacity:0;transform:translateY(6px)}4%,21%{opacity:1;transform:none}25%,100%{opacity:0;transform:translateY(-6px)}}

/* small step pill: tiny spinning record + step */
.sb-pill{display:inline-flex;align-items:center;gap:.6rem;margin-top:.4rem;padding:.35rem .9rem .35rem .4rem;
  background:#fff;border:1.5px solid #0E0E10;border-radius:999px;font-size:.8rem;white-space:nowrap}
.sb-vinyl{position:relative;flex:none;width:24px;height:24px;border-radius:50%;
  background:repeating-radial-gradient(circle,#2a2a2e 0 1px,#0E0E10 1px 2px);animation:sb-spin 1.8s linear infinite}
.sb-label{position:absolute;inset:28%;border-radius:50%;overflow:hidden;background:#1ED760}
.sb-label img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;
  animation:sb-cover var(--cycle) linear var(--d) infinite}
@keyframes sb-spin{to{transform:rotate(360deg)}}
.sb-pill .n{font-variant-numeric:tabular-nums;color:#5B5757}
.sb-pill .t{font-weight:600}
.sb-dots{display:flex;gap:4px;margin-left:.15rem}
.sb-dots i{width:5px;height:5px;border-radius:50%;background:#0E0E10;opacity:.18}
.sb-dots i.on{opacity:1}

@media (max-width:520px){.sb-quips{height:3em}.sb-quips span{white-space:normal}}
"""


def _default_covers(limit: int = 6) -> list[str]:
    """Same cached covers the home-page background uses (instant, no extra Spotify call)."""
    try:
        from FrontEnd.Pages.spotify_covers import get_covers
        return [c["m"] for c in get_covers(limit) if c.get("m")]
    except Exception:  # noqa: BLE001 — covers are decoration; never break loading over them
        return []


def _cover_css(n: int) -> str:
    """Keyframes for n covers taking turns on the label (each visible 1/n of the cycle)."""
    share = 100 / n
    fade = min(6.0, share / 3)
    return (f"@keyframes sb-cover{{0%{{opacity:0}}{fade:.2f}%,{share:.2f}%{{opacity:1}}"
            f"{share + fade:.2f}%,100%{{opacity:0}}}}")


class LoadingScreen:
    """One placeholder that is redrawn per step, so the screen never flickers away between steps."""

    def __init__(self, lang: str = "en"):
        self.lang = lang if lang in TRACKS else "en"
        self.quips = [random.sample(pool, 4) for pool in QUIPS[self.lang]]   # 4 per step (CSS assumes 4)
        self.covers: list[str] | None = None
        self._slot = st.empty()

    def show(self, step: int, covers: list[str] | None = None) -> None:
        tracks = TRACKS[self.lang]
        step = max(0, min(step, len(tracks) - 1))
        if covers:
            self.covers = [c for c in covers if c][:8]
        if self.covers is None:
            self.covers = _default_covers()

        # vinyl label: covers take turns (falls back to a plain green label)
        n = len(self.covers)
        imgs = "".join(f'<img src="{escape(u)}" alt="" decoding="async" style="--d:{i * COVER_SECS}s">'
                       for i, u in enumerate(self.covers))
        label = f'<div class="sb-label" style="--cycle:{max(n, 1) * COVER_SECS}s">{imgs}</div>'

        title = tracks[step]
        dots = "".join(f'<i class="{"on" if i <= step else ""}"></i>' for i in range(len(tracks)))
        quips = "".join(f'<span style="--d:{i * QUIP_SECS}s">{escape(q)}</span>'
                        for i, q in enumerate(self.quips[step]))

        self._slot.markdown(
            f"<style>{CSS}{_cover_css(max(n, 1))}</style>"
            '<div class="sb-load" role="status" aria-live="polite">'
            '<div class="sb-load-head"><div class="sb-eq" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div>'
            '<p class="sb-load-mark">SPOTIBAI</p></div>'
            f'<div class="sb-quips" style="--cycle:{4 * QUIP_SECS}s">{quips}</div>'
            f'<div class="sb-pill"><div class="sb-vinyl" aria-hidden="true">{label}</div>'
            f'<span class="n">{step + 1:02d}/{len(tracks):02d}</span><span class="t">{escape(title)}</span>'
            f'<span class="sb-dots" aria-hidden="true">{dots}</span></div>'
            "</div>",
            unsafe_allow_html=True,
        )

    def hide(self) -> None:
        self._slot.empty()