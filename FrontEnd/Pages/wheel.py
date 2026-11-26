"""
SPOTIBAI — Song Wheel + Chat (Streamlit + Spotify)

After login:
- the user's top 10 songs (the same list as the receipt) are loaded automatically and shuffled
- rounded rectangular cards on an arc shuffle upward by itself, then play each
    song for CLIP_SECONDS in wheel order (cards move up along the arc, the top
    card fades out and a new one fades in at the bottom); album covers fill
    the cards
- users can also drag up/down on the wheel to scrub through songs and play
    whichever song they land on
- an animated equalizer sits in the wheel's hole; an arrow points at the playing song
- the SPOTIBAI chat card sits on top of the wheel on the right

Backend hook (left open on purpose):
- get_opening_messages(songs)  → what SPOTIBAI says first (Python, below)
- getBotReply(text, history)   → SPOTIBAI's answer to the user (JavaScript, in the HTML)

Run:  streamlit run wheel.py
Open: http://127.0.0.1:8501   (use 127.0.0.1, not localhost — must match the redirect URI)
"""

import json
import random

import requests
import spotipy
import streamlit as st
import streamlit.components.v1 as components
from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth

from BackEnd.config import get_secret
from BackEnd.sources.spotify import SCOPE

# Must be the first Streamlit call.
st.set_page_config(page_title="SPOTIBAI", page_icon="🎡", layout="wide")

# ---- Secrets: st.secrets on Streamlit Cloud, .streamlit/secrets.toml locally ----
SPOTIFY_CLIENT_ID = get_secret("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = get_secret("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = get_secret("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8501/wheel")
if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    st.error("Spotify isn't set up: add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to the app's secrets.")
    st.stop()

# ---- Settings you can change ------------------------------------------------
TOP_N = 10                  # songs on the wheel
CLIP_SECONDS = 30           # how long each song plays (30 or 60)
# -----------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1. Auth — keep each user's token in THEIR session (not a shared .cache file)
# ---------------------------------------------------------------------------
class SessionCacheHandler(CacheHandler):
    """Stores the token dict in st.session_state so users don't share tokens
    and spotipy can refresh it automatically after it expires (1 hour)."""

    def get_cached_token(self):
        return st.session_state.get("token_info")

    def save_token_to_cache(self, token_info):
        st.session_state["token_info"] = token_info


auth = SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope=SCOPE,
    cache_handler=SessionCacheHandler(),
    open_browser=False,
    show_dialog=True,
)
# P7: which service this user logged in with ("youtube" is set by youtube_login.py)
SOURCE = st.session_state.get("source", "spotify")
if SOURCE == "youtube" and "profile" not in st.session_state:
    st.switch_page("FrontEnd/Pages/youtube_login.py")      # their YouTube session was lost: log in again

params = st.query_params

if "error" in params:  # user pressed "Cancel" on Spotify's login page
    st.session_state["login_failed"] = True
    st.session_state["login_message"] = f"Spotify login was cancelled ({params['error']})."
    st.query_params.clear()
    st.rerun()

if "code" in params:  # Spotify sent us back with a login code
    # Leaving for Spotify's login page started a NEW session, so the roast language comes back in `state`
    if params.get("state") in ("en", "ceb"):
        st.session_state["lang"] = params["state"]
    try:
        auth.get_access_token(params["code"], as_dict=False, check_cache=False)
        st.session_state["login_failed"] = False
    except Exception as e:
        st.session_state["login_failed"] = True
        st.session_state["login_message"] = f"Login failed: {e}"
    st.query_params.clear()
    st.rerun()

if SOURCE == "spotify" and not auth.validate_token(auth.cache_handler.get_cached_token()):
    spotify_login_url = auth.get_authorize_url(state=st.session_state.get("lang", "en"))

    # If the last try failed, stop and show why instead of jumping to Spotify again.
    if st.session_state.get("login_failed"):
        st.error(st.session_state.get("login_message", "Login failed."))
        st.link_button("Try Spotify login again", spotify_login_url, type="primary")
        st.stop()

    components.html(
        f"""
        <script>
          const redirectScript = window.parent.document.createElement("script");
          redirectScript.textContent = "window.top.location.href = " + JSON.stringify({json.dumps(spotify_login_url)}) + ";";
          window.parent.document.head.appendChild(redirectScript);
        </script>
        """,
        height=0,
    )
    st.stop()


sp = spotipy.Spotify(
    # YouTube users have no Spotify login: an app-only client is enough to check song picks (P7)
    auth_manager=auth if SOURCE == "spotify" else SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET),
    requests_timeout=20,   # wait up to 20 s instead of 5
    retries=3,             # try again automatically
    status_retries=0,
)

if "me" not in st.session_state:
    try:
        st.session_state.me = sp.current_user()
    except spotipy.SpotifyException as e:
        if e.http_status == 403:
            st.error("This Spotify account isn't allowed to use the app yet. "
                     "Ask the app owner to add your Spotify email under "
                     "Dashboard → Settings → User Management, then log in again.")
        else:
            st.error(f"Spotify error ({e.http_status}): {e.msg}")
        if st.button("Log out and try another account"):
            st.session_state.clear()
            st.rerun()
        st.stop()
    except requests.exceptions.RequestException:
        st.error("Couldn't reach Spotify — check your connection and press Retry.")
        st.button("Retry")
        st.stop()
me = st.session_state.me


# ---------------------------------------------------------------------------
# 2. Profile (once per login) — the wheel AND the receipt both come from it
# ---------------------------------------------------------------------------
from FrontEnd.UI.loader import LoadingScreen          # noqa: E402
from BackEnd.roast import make_roast                      # noqa: E402
from BackEnd.sources.spotify import fetch_profile         # noqa: E402
from BackEnd.stats import compute_all                     # noqa: E402
from FrontEnd.UI.receipt import wheel_songs               # noqa: E402
from FrontEnd.UI.roast_chat import chat_panel, init_chat_state  # noqa: E402

lang = st.session_state.get("lang", "en")              # set by the intro's language step
loader = LoadingScreen(lang)                           # full-screen loader for the fetches below

@st.cache_data(ttl=3600, show_spinner=False)
def cached_profile(user_id: str, _sp):          # "_sp" = not part of the cache key
    return fetch_profile(_sp)

if "profile" not in st.session_state:
    try:
        loader.show(0)
        st.session_state.profile = cached_profile(me["id"], sp)
        loader.show(1)
        st.session_state.stats = compute_all(st.session_state.profile)
    except spotipy.SpotifyException as e:
        loader.hide()
        if e.http_status == 429:
            st.error("Spotify says we've made too many requests. Wait a while, then press Retry.")
        else:
            st.error(f"Spotify error ({e.http_status}): {e.msg}")
        st.button("Retry")
        st.stop()
    except (spotipy.SpotifyException, requests.exceptions.RequestException) as e:
        loader.hide()
        st.error(f"Couldn't read your listening history from Spotify: {e}")
        st.button("Retry")
        st.stop()

# The wheel = the same top 10 songs as the receipt (FrontEnd/UI/receipt.py), shuffled.
# Built ONCE per login: a new order on every rerun would reload the wheel and restart the music.
if not st.session_state.get("wheel_from_receipt") or "wheel" not in st.session_state:
    songs = wheel_songs(st.session_state.profile)[:TOP_N]
    random.shuffle(songs)
    st.session_state.wheel = songs
    st.session_state.wheel_from_receipt = True

wheel = st.session_state.wheel
if not wheel:
    loader.hide()
    st.warning("Your account doesn't have listening history yet. "
               "Play a few songs, then refresh this page.")
    st.stop()


# ---------------------------------------------------------------------------
# 3. Roast (P4) — AI roast, once per login and language
# ---------------------------------------------------------------------------
st.session_state.sp = sp    # the chat uses it to check song picks exist on Spotify
if st.session_state.get("roast", {}).get("lang") != lang:
    loader.show(2)
    # 1 AI call (1 AK). Never raises: falls back to template lines if the AI fails.
    init_chat_state(make_roast(st.session_state.profile, st.session_state.stats, lang))
loader.hide()                                          # data is ready: reveal the wheel


# ---------------------------------------------------------------------------
# 4. Page — wheel + music card + chat, all in one HTML block so they can overlap
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
      [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], footer { display: none !important; }
      .block-container, [data-testid="stMainBlockContainer"] { padding: 0 !important; max-width: 100% !important; }
      [data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stVerticalBlock"] {
        overflow: hidden !important;
        gap: 0 !important;
        padding-top: 0 !important;
      }
      [data-testid="stElementContainer"]:has(iframe) {
        height: 100vh !important;
      }
      iframe[title="st.iframe"], iframe[data-testid="stIFrame"] {
        display: block;
        width: 100% !important;
        height: 100vh !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

PAGE_HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
  html, body { margin: 0; height: 100%; overflow: hidden; background: #FFFFFF;
               font-family: Inter, system-ui, sans-serif; color: #000000; }

  /* Design units: the page is always 800 units tall and scaled to the window's height,
     so the wheel fills the screen on any laptop or monitor. Its width follows the window. */
  #stage { position: absolute; left: 0; top: 0; height: 800px; transform-origin: 0 0;
           cursor: grab; touch-action: none; user-select: none; }
  #stage.dragging { cursor: grabbing; }
  #wheel { position: absolute; left: 0; top: 0; overflow: visible; }

  /* Equalizer inside the vinyl center label (hole radius 185, centre at x 0, y 400) */
  #viz  { position: absolute; left: 0; top: 215px; width: 125px; height: 370px; pointer-events: none; }
  #hint { position: absolute; left: 12px; top: 520px; width: 150px; font-size: 12px; font-weight: 700;
          line-height: 1.3; color: #000; display: none; pointer-events: none; }

  /* The Spotify player itself does the playing; it is kept out of sight. */
  #embed-box { position: fixed; right: 0; bottom: 0; width: 300px; height: 80px;
               opacity: 0; pointer-events: none; }
  /* P7: YouTube's rules require a VISIBLE player of at least 200x200, so it sits bottom-left */
  body.yt #embed-box { opacity: 0; pointer-events: none; left: 0; right: auto; bottom: 0;
               width: 356px; height: 200px; }
  body.yt #embed-box iframe { width: 100%; height: 100%; display: block; border: 0; }

  /* The chat card is no longer here: it's drawn by Streamlit (FrontEnd/UI/roast_chat.py). */
</style>
</head>
<body>
<div id="stage">
  <svg id="wheel" width="800" height="800" viewBox="0 -400 800 800" aria-hidden="true">
    <defs>
      <filter id="cardShadow" x="-25%" y="-25%" width="150%" height="150%">
        <feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#000000" flood-opacity="0.68" />
      </filter>
      <filter id="activeShadow" x="-30%" y="-30%" width="160%" height="160%">
        <feDropShadow dx="0" dy="14" stdDeviation="18" flood-color="#000000" flood-opacity="0.78" />
      </filter>
      <radialGradient id="vinylGlossRadial" cx="28%" cy="22%" r="72%">
        <stop offset="0%" stop-color="#FFFFFF" stop-opacity="0.24" />
        <stop offset="22%" stop-color="#8E929B" stop-opacity="0.09" />
        <stop offset="55%" stop-color="#050507" stop-opacity="0.35" />
        <stop offset="100%" stop-color="#020203" stop-opacity="0.85" />
      </radialGradient>
      <linearGradient id="vinylGlossBand" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#000000" stop-opacity="0.45" />
        <stop offset="28%" stop-color="#FFFFFF" stop-opacity="0.02" />
        <stop offset="44%" stop-color="#FFFFFF" stop-opacity="0.22" />
        <stop offset="52%" stop-color="#FFFFFF" stop-opacity="0.03" />
        <stop offset="76%" stop-color="#000000" stop-opacity="0.2" />
        <stop offset="100%" stop-color="#000000" stop-opacity="0.75" />
      </linearGradient>
    </defs>

    <!-- Deep glossy vinyl record backdrop + light center label -->
    <g id="vinyl">
      <circle cx="0" cy="0" r="560" fill="#070709" stroke="#020203" stroke-width="3"></circle>

      <g fill="none" stroke="#FFFFFF" stroke-opacity="0.08" stroke-width="1.4">
        <circle cx="0" cy="0" r="448"></circle>
        <circle cx="0" cy="0" r="420"></circle>
        <circle cx="0" cy="0" r="392"></circle>
        <circle cx="0" cy="0" r="364"></circle>
        <circle cx="0" cy="0" r="336"></circle>
        <circle cx="0" cy="0" r="308"></circle>
        <circle cx="0" cy="0" r="280"></circle>
        <circle cx="0" cy="0" r="252"></circle>
        <circle cx="0" cy="0" r="224"></circle>
        <circle cx="0" cy="0" r="198"></circle>
      </g>

      <!-- Glossy reflections over deep black vinyl -->
      <circle cx="0" cy="0" r="560" fill="url(#vinylGlossRadial)"></circle>
      <circle cx="0" cy="0" r="560" fill="url(#vinylGlossBand)"></circle>

      <!-- Center label for the sound wavelength / equalizer -->
      <circle cx="0" cy="0" r="185" fill="#EFECE6" stroke="#111111" stroke-width="2"></circle>
      
    </g>

    <!-- Tilted rectangular album cards along the arc -->
    <g id="cards"></g>

    <!-- Arrow pointing at the active card on the arc -->
    <g id="arrow" transform="translate(362, 0)">
    </g>
  </svg>

  <canvas id="viz" aria-hidden="true"></canvas>
  
</div>
<div id="embed-box"><div id="embed"></div></div>

<script>
/* ===================== data from Python ===================== */
const TRACKS   = __TRACKS__;      // shuffled top songs
const CLIP_MS  = __CLIP_MS__;     // how long each song plays
const PROVIDER = __PROVIDER__;    // "spotify" or "youtube" (P7)

/* ===================== size everything to the window ===================== */
const stage = document.getElementById("stage");
function fit() {
  const s = window.innerHeight / 800;                  // wheel always fills the window's height
  const stageW = window.innerWidth / s;                // window width in design units
  stage.style.transform = `scale(${s})`;
  stage.style.width = Math.max(stageW, 800) + "px";   // the chat stretches with this width
}
window.addEventListener("resize", fit);
fit();

/* ===================== tilted rectangular cards along an arc ===================== */
const N = TRACKS.length;
const STEP = 28;                  // angular spacing (degrees) between cards along the arc
const ARC_R = 475;                // radius from (0, 0) where card centers sit
const CARD_W = 330;               // rectangular card width
const CARD_H = 268;               // rectangular card height (overlaps nicely with STEP = 28)
const CARD_R = 28;                // corner radius
const TILT_OFFSET = -14;          // extra editorial pitch-deck tilt (degrees)
const NS = "http://www.w3.org/2000/svg";

const mod = (a, m) => ((a % m) + m) % m;

function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

const cardsLayer = document.getElementById("cards");
const cards = TRACKS.map((t, idx) => {
  const g = el("g", { filter: "url(#cardShadow)" }, cardsLayer);
  g.style.transformOrigin = "0px 0px";
  g.style.transformBox = "view-box";

  const clipId = `rectClip_${idx}`;
  const clip = el("clipPath", { id: clipId }, g);
  el("rect", {
    x: -CARD_W / 2,
    y: -CARD_H / 2,
    width: CARD_W,
    height: CARD_H,
    rx: CARD_R,
    ry: CARD_R,
  }, clip);

  // Base surface (shown if a track has no cover art)
  el("rect", {
    x: -CARD_W / 2,
    y: -CARD_H / 2,
    width: CARD_W,
    height: CARD_H,
    rx: CARD_R,
    ry: CARD_R,
    fill: "#EAEAEA",
  }, g);

  if (t.image) {
    const img = el("image", {
      x: -CARD_W / 2,
      y: -CARD_H / 2,
      width: CARD_W,
      height: CARD_H,
      preserveAspectRatio: "xMidYMid slice",
      "clip-path": `url(#${clipId})`,
    }, g);
    img.setAttribute("href", t.image);
  }

  return { g };
});

let pos = 0;              // how far the wheel has turned (in cards)
let playing = false;
let spinning = false;
let dragging = false;
let animId = null;

/* ===================== vinyl turning ===================== */
const vinylEl = document.getElementById("vinyl");
vinylEl.style.transformOrigin = "0px 0px";
vinylEl.style.transformBox = "view-box";

let vinylAngle = 0;
let lastVizTime = 0;

function setVinylAngle(deg) {
  vinylAngle = ((deg % 360) + 360) % 360;
  vinylEl.style.transform = `rotate(${vinylAngle.toFixed(2)}deg)`;
}

/* Smooth float animation helper used by spin(), nextSong(), and drag snap */
function animateToPos(targetPos, duration, onComplete) {
  if (animId) cancelAnimationFrame(animId);
  const startPos = pos;
  const startVinyl = vinylAngle;
  const deltaPos = targetPos - startPos;
  const deltaVinyl = deltaPos * 24;
  const t0 = performance.now();

  function step(now) {
    const p = Math.min(1, (now - t0) / duration);
    const eased = duration >= 2000
      ? 1 - Math.pow(1 - p, 4)
      : 1 - Math.pow(1 - p, 3);
    pos = startPos + deltaPos * eased;
    setVinylAngle(startVinyl + deltaVinyl * eased);
    layout(0);

    if (p < 1) {
      animId = requestAnimationFrame(step);
    } else {
      animId = null;
      pos = targetPos;
      layout(0);
      if (onComplete) onComplete();
    }
  }

  animId = requestAnimationFrame(step);
}

/* Place every card along the arc for current `pos` (can be fractional during spin/drag). */
function layout(ms) {
  const order = cards
    .map((_, i) => {
      const diff = i - pos;
      const off = ((diff % N) + N + N / 2) % N - N / 2;
      return { i, off, depth: Math.abs(off) };
    })
    .sort((a, b) => b.depth - a.depth);

  order.forEach(({ i, off }) => {
    const c = cards[i];
    if (cardsLayer.lastElementChild !== c.g) {
      cardsLayer.appendChild(c.g);
    }

    const ang = off * STEP;
    const rad = ang * Math.PI / 180;
    const x = ARC_R * Math.cos(rad);
    const y = ARC_R * Math.sin(rad);

    const abs = Math.abs(ang);
    const op = abs <= 65 ? 1 : abs >= 105 ? 0 : (105 - abs) / 40;

    const closeness = Math.max(0, 1 - Math.abs(off));
    const smoothActive = closeness * closeness * (3 - 2 * closeness);
    const sc = (0.94 + smoothActive * 0.2) * Math.max(0.9, 1 - Math.min(Math.abs(off), 4) * 0.02);
    const pushX = smoothActive * 18;
    const tilt = ang + TILT_OFFSET;

    const isSnappedActive = !spinning && !dragging && Math.round(pos) === i;
    c.g.setAttribute("filter", isSnappedActive && playing ? "url(#activeShadow)" : "url(#cardShadow)");
    c.g.style.transition = "none";
    c.g.style.transform = `translate(${(x + pushX).toFixed(1)}px, ${y.toFixed(1)}px) rotate(${tilt.toFixed(1)}deg) scale(${sc.toFixed(3)})`;
    c.g.style.opacity = op.toFixed(3);
  });
}
layout(0);

/* ===================== arrow ===================== */
const arrow = document.getElementById("arrow");
function nudgeArrow() {
  arrow.animate(
    [
      { transform: "translate(362px, 0px)" },
      { transform: "translate(372px, 0px)" },
      { transform: "translate(362px, 0px)" },
    ],
    { duration: 450, easing: "ease-out" }
  );
}

/* ===================== equalizer in the hole ===================== */
const viz = document.getElementById("viz");
const vctx = viz.getContext("2d");
const BARS = 21;
const BAR_W = 4.5, BAR_GAP = 3;
const BAR_MAX = 210;
let audioOn = false;
let songSeed = 1;
let vizGain = 1;
let vizTargetGain = 1;
const heights = new Array(BARS).fill(4);

function sizeViz() {
  const s = window.innerHeight / 800;
  const r = (window.devicePixelRatio || 1) * s;
  viz.width = 185 * r;
  viz.height = 370 * r;
  vctx.setTransform(r, 0, 0, r, 0, 0);
}
window.addEventListener("resize", sizeViz);
sizeViz();

function seedFrom(uri) {
  let h = 7;
  for (const ch of uri) h = (h * 31 + ch.charCodeAt(0)) % 9973;
  return h;
}

function drawViz(t) {
  const dt = lastVizTime ? Math.min(0.05, (t - lastVizTime) / 1000) : 0;
  lastVizTime = t;
  if (!spinning && !dragging && audioOn) {
    setVinylAngle(vinylAngle + dt * 28 * vizGain);
  }

  vizGain += (vizTargetGain - vizGain) * Math.min(1, dt * 6);

  vctx.clearRect(0, 0, 185, 370);
  const sec = t / 1000;
  const beat = 0.75 + 0.25 * Math.pow(Math.abs(Math.sin(sec * Math.PI * 2)), 6);
  for (let i = 0; i < BARS; i++) {
    const x = 6 + i * (BAR_W + BAR_GAP);
    const room = 2 * Math.sqrt(Math.max(0, 185 * 185 - (x + BAR_W) * (x + BAR_W))) - 60;
    const maxH = Math.max(6, Math.min(BAR_MAX, room));
    let target = 4;
    if (audioOn) {
      const a = Math.abs(Math.sin(sec * (2.1 + (songSeed % 7) * 0.31) + i * (0.55 + (songSeed % 5) * 0.07)));
      const b = Math.abs(Math.sin(sec * (3.7 + (songSeed % 3) * 0.4) - i * 0.9));
      target = maxH * (0.18 + 0.82 * a * b) * beat * vizGain;
    } else if (spinning || dragging) {
      target = maxH * 0.12 * (1 + Math.sin(sec * 8 - i * 0.6));
    }
    heights[i] += (target - heights[i]) * 0.25;
    const h = Math.max(4, heights[i]);
    vctx.fillStyle = "#000";
    vctx.beginPath();
    vctx.roundRect(x, 185 - h / 2, BAR_W, h, BAR_W / 2);
    vctx.fill();
  }
  requestAnimationFrame(drawViz);
}
requestAnimationFrame(drawViz);

/* ===================== Spotify playback with smooth fade-out / fade-in ===================== */
const hintEl = document.getElementById("hint");
let ctrl = null, current = -1, switchedAt = 0, started = false, switchTimer = null;
let advancing = false;

function playAt(i, { immediate = false } = {}) {
  if (switchTimer) {
    clearTimeout(switchTimer);
    switchTimer = null;
  }

  // Mark transition immediately so stale playback_update events don't re-trigger nextSong()
  switchedAt = performance.now();

  const applyTrack = () => {
    current = i;
    playing = true;
    advancing = false;
    songSeed = seedFrom(TRACKS[i].uri);
    nudgeArrow();
    switchedAt = performance.now();
    vizTargetGain = 1;
    if (!ctrl) return;
    ctrl.loadUri(TRACKS[i].uri);
    setTimeout(() => {
      if (!ctrl) return;
      ctrl.play();
      setTimeout(() => { if (!started) hintEl.style.display = "block"; }, 2500);
    }, 250);
  };

  if (immediate || current < 0) {
    vizGain = 0.25;
    applyTrack();
    return;
  }

  // Fade out current track/visualizer first, then switch and fade back in
  vizTargetGain = 0;
  if (ctrl) {
    try { ctrl.pause(); } catch (_) {}
  }
  switchTimer = setTimeout(applyTrack, 350);
}

function nextSong() {
  if (advancing || spinning || dragging) return;
  advancing = true;
  switchedAt = performance.now();

  const target = Math.round(pos) + 1;
  animateToPos(target, 850, () => {
    playAt(mod(target, N));
  });
}

/* ===================== drag up/down on the wheel ===================== */
const chatEl = document.getElementById("chat");
let dragStartY = 0;
let dragStartPos = 0;

stage.addEventListener("pointerdown", (e) => {
  if (e.button !== 0 && e.pointerType === "mouse") return;
  if (chatEl && chatEl.contains(e.target)) return;

  if (animId) { cancelAnimationFrame(animId); animId = null; }
  if (ctrl && !started && current >= 0) { switchedAt = performance.now(); ctrl.play(); }

  dragging = true;
  spinning = false;
  stage.classList.add("dragging");
  dragStartY = e.clientY;
  dragStartPos = pos;
  stage.setPointerCapture(e.pointerId);
});

stage.addEventListener("pointermove", (e) => {
  if (!dragging) return;
  const scale = window.innerHeight / 800 || 1;
  const dyDesign = (e.clientY - dragStartY) / scale;

  // Dragging UP (negative dy) moves cards UP (positive pos)
  const nextPos = dragStartPos - dyDesign / 95;
  const delta = nextPos - pos;
  pos = nextPos;
  setVinylAngle(vinylAngle + delta * 24);
  layout(0);
});

function finishDrag(e) {
  if (!dragging) return;
  dragging = false;
  stage.classList.remove("dragging");
  if (stage.hasPointerCapture(e.pointerId)) {
    stage.releasePointerCapture(e.pointerId);
  }

  const snapped = Math.round(pos);
  const songIdx = mod(snapped, N);
  animateToPos(snapped, 280, () => {
    if (songIdx !== current || !playing) {
      playAt(songIdx);
    }
  });
}

stage.addEventListener("pointerup", finishDrag);
stage.addEventListener("pointercancel", finishDrag);

function onUpdate(e) {
  const d = e.data;
  if (!d) return;
  audioOn = !d.isPaused;
  if (!d.isPaused && !started) { started = true; hintEl.style.display = "none"; }
  if (current < 0 || dragging || spinning || advancing) return;
  if (d.playingURI && d.playingURI !== TRACKS[current].uri) return;
  if (performance.now() - switchedAt < 2000) return;

  const end = (d.duration && d.duration > 1000)
    ? Math.min(CLIP_MS, d.duration - 300)
    : CLIP_MS;

  if (!d.isPaused && typeof d.position === "number" && d.position >= end) {
    nextSong();
  }
}

/* ===================== intro: smooth continuous glide, coast, and land ===================== */
let spun = false;
function spin() {
  if (spun || dragging) return;
  spun = true;
  spinning = true;

  const extraSteps = 14 + Math.floor(Math.random() * N);
  const targetPos = Math.round(pos + extraSteps);

  animateToPos(targetPos, 3200, () => {
    spinning = false;
    playAt(mod(targetPos, N), { immediate: true });
  });
}

function loadScript(src) {
  const s = document.createElement("script");
  s.src = src; s.async = true;
  document.body.appendChild(s);
}

if (PROVIDER === "youtube") {
  /* P7: a small adapter that makes the YouTube player look like Spotify's controller
     (loadUri / play / pause + playback_update events), so the wheel code above is unchanged. */
  document.body.classList.add("yt");
  window.onYouTubeIframeAPIReady = () => {
    let loaded = TRACKS[0].uri;
    let ytErrors = 0;    // songs in a row that refused to play
    const player = new YT.Player("embed", {
      width: 356, height: 200, videoId: TRACKS[0].uri.slice(3),      // uri = "yt:<videoId>"
      playerVars: {
        playsinline: 1, rel: 0,
        // We run inside Streamlit's iframe, so tell YouTube which site the player is on
        origin: window.parent.location.origin,
        widget_referrer: window.parent.location.href,
      },
      events: {
        onReady: () => {
          ctrl = {
            loadUri(uri) { loaded = uri; player.cueVideoById(uri.slice(3)); },
            play() { player.playVideo(); },
            pause() { player.pauseVideo(); },
          };
          setInterval(() => {
            if (player.getPlayerState() === YT.PlayerState.PLAYING) ytErrors = 0;
            onUpdate({ data: {
              isPaused: player.getPlayerState() !== YT.PlayerState.PLAYING,
              position: (player.getCurrentTime() || 0) * 1000,
              duration: (player.getDuration() || 0) * 1000,
              playingURI: loaded,
            } });
          }, 500);
          setTimeout(spin, 600);
        },
        // Some music videos don't allow embedding (errors 101/150): skip to the next song
        onError: (e) => {
          console.warn("YouTube player error", e.data, "on", loaded);   // 101/150 = embedding blocked, 153 = site not identified
          ytErrors += 1;
          if (ytErrors >= TRACKS.length) {           // every song refused: stop skipping
            hintEl.textContent = "None of these songs can play outside YouTube.";
            hintEl.style.display = "block";
            return;
          }
          if (!spinning && !dragging) setTimeout(nextSong, 400);
        },
      },
    });
  };
  loadScript("https://www.youtube.com/iframe_api");
} else {
  window.onSpotifyIframeApiReady = (IFrameAPI) => {
    IFrameAPI.createController(
      document.getElementById("embed"),
      { uri: TRACKS[0].uri, width: 300, height: 80 },
      (c) => {
        ctrl = c;
        c.addListener("playback_update", onUpdate);
        setTimeout(spin, 600);
      }
    );
  };
  loadScript("https://open.spotify.com/embed/iframe-api/v1");
}
setTimeout(spin, 6000);
</script>
</body>
</html>
"""


def to_js(value):
    """JSON that is safe to place inside a <script> tag."""
    return json.dumps(value).replace("</", "<\\/")


# The wheel HTML depends ONLY on the songs, so it is identical on every rerun and the
# iframe (and the music) is never reloaded. Don't put anything that changes in here.
html = (PAGE_HTML
        .replace("__TRACKS__", to_js(wheel))
        .replace("__CLIP_MS__", str(CLIP_SECONDS * 1000))
        .replace("__PROVIDER__", json.dumps(SOURCE)))
components.html(html, height=800)

chat_panel()