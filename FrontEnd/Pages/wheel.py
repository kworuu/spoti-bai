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

SCOPE = ("user-top-read user-read-recently-played user-library-read "
         "playlist-read-private playlist-read-collaborative "
         "streaming user-read-email user-read-private")   # last 3: Web Playback SDK (volume + fades)

# ---- Settings you can change ------------------------------------------------
TOP_N = 10                  # songs on the wheel
CLIP_SECONDS = 30           # how long each song plays (30 or 60)
USE_WEB_PLAYBACK = False     # Premium Spotify users play through the Web Playback SDK (volume + fades).
                            # False = everyone uses the old embed player (the safe fallback).
TIME_RANGE = "medium_term"  # "short_term" = last 4 weeks, "medium_term" = ~6 months, "long_term" = all time
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
    st.link_button("Log in with Spotify", spotify_login_url, type="primary")
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

# Web Playback SDK (needs Spotify Premium). We can't check Premium up front: since Feb 2026 Spotify
# no longer sends the "product" field to Development Mode apps. So every Spotify user TRIES the SDK;
# a free account gets an "account_error" from Spotify and the page falls back to the embed player.
# The token is captured ONCE per login so the wheel HTML (and the music) never reloads on reruns.
# Access tokens last 1 hour; after that the page says to refresh.
SDK_TOKEN = ""
if SOURCE == "spotify" and USE_WEB_PLAYBACK:
    if "sdk_token" not in st.session_state:
        st.session_state.sdk_token = (auth.get_cached_token() or {}).get("access_token", "")
    SDK_TOKEN = st.session_state.sdk_token


# ---------------------------------------------------------------------------
# 2. Profile (once per login) — the wheel AND the receipt both come from it
# ---------------------------------------------------------------------------
def to_song(track):
    """Spotify track object -> the small dict the wheel needs (or None)."""
    if not track or track.get("is_local"):
        return None
    uri = track.get("uri") or ""
    if not uri.startswith("spotify:track:"):
        return None  # skip podcast episodes / local files
    artists = ", ".join(a["name"] for a in track.get("artists", [])) or "Unknown"
    album = track.get("album") or {}
    images = album.get("images") or []
    image = min(images, key=lambda im: abs((im.get("width") or 300) - 300))["url"] if images else ""
    return {
        "name": track["name"],
        "artist": artists,
        "uri": uri,
        "image": image,
        "album": album.get("name", ""),
        "release_date": album.get("release_date", ""),
    }


def dedupe(songs):
    seen, out = set(), []
    for s in songs:
        if s and s["uri"] not in seen:
            seen.add(s["uri"])
            out.append(s)
    return out


def load_wheel_songs():
    """Top TOP_N songs; topped up with recently played ones if the account is new."""
    top = sp.current_user_top_tracks(limit=TOP_N, time_range=TIME_RANGE)["items"]
    songs = dedupe(to_song(t) for t in top)
    if len(songs) < TOP_N:
        recent = sp.current_user_recently_played(limit=50)["items"]
        songs = dedupe(songs + [to_song(item["track"]) for item in recent])
    songs = songs[:TOP_N]
    random.shuffle(songs)
    return songs


from FrontEnd.UI.loader import LoadingScreen          # noqa: E402

lang = st.session_state.get("lang", "en")              # set by the intro's language step
loader = LoadingScreen(lang)                           # full-screen loader for the fetches below

if "wheel" not in st.session_state:
    try:
        loader.show(0)
        st.session_state.wheel = load_wheel_songs()
    except (spotipy.SpotifyException, requests.exceptions.RequestException) as e:
        loader.hide()
        st.error(f"Couldn't get your songs from Spotify: {e}")
        st.button("Retry")
        st.stop()

wheel = st.session_state.wheel
if not wheel:
    loader.hide()
    st.warning("Your Spotify account doesn't have listening history yet. "
               "Play a few songs on Spotify, then refresh this page.")
    st.stop()


# ---------------------------------------------------------------------------
# 3. Roast (P4) — profile + stats + AI roast, once per login and language
# ---------------------------------------------------------------------------
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
if any("bg" not in song for song in wheel):           # muted page tint per album cover (once per login)
    from FrontEnd.UI.cover_colors import add_colors    # noqa: E402
    add_colors(wheel)
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
  /* page tint follows the playing song's cover (colors come from FrontEnd/UI/cover_colors.py) */
  body { transition: background-color 1.8s ease; }

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
  body.yt #embed-box { opacity: 0; pointer-events: none; left: 0; right: auto; bottom: 0;   /* hidden (team decision on main) */
               width: 356px; height: 200px; }
  body.yt #embed-box iframe { position: absolute; inset: 0; width: 100%; height: 100%; display: block; border: 0;
                             opacity: 0; pointer-events: none; transition: opacity .8s ease; }
  body.yt #embed-box iframe.on { opacity: 1; pointer-events: auto; }

  /* ---- now playing bar: sits in the empty strip UNDER the chat card, same left/right edges ----
     (chat card = left 600u, right 100u, bottom 70u; 1u = 100vh / 800, see roast_chat.py) */
  :root { --u: calc(100vh / 800); --np-accent: #1A1A1A; }
  #np { position: fixed; z-index: 4; left: calc(600 * var(--u)); right: calc(100 * var(--u));
        bottom: calc(14 * var(--u)); height: max(36px, calc(42 * var(--u))); box-sizing: border-box;
        display: flex; align-items: center; gap: calc(12 * var(--u)); padding: 0 calc(14 * var(--u)) 0 calc(6 * var(--u));
        background: rgba(255,255,255,.88); border: 1.5px solid #1A1A1A; border-radius: calc(10 * var(--u));
        opacity: 0; transform: translateY(6px); transition: opacity .6s ease, transform .6s ease; }
  #np.show { opacity: 1; transform: none; }
  #np-cover { flex: none; width: max(26px, calc(30 * var(--u))); aspect-ratio: 1; border-radius: 4px; object-fit: cover;
              background: #E5E5E5; }
  .np-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 5px; transition: opacity .3s ease; }
  .np-text.swap { opacity: 0; }
  .np-line { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: max(12px, calc(13.5 * var(--u))); line-height: 1.2; }
  .np-line b { font-weight: 600; color: #1A1A1A; }
  .np-line span { color: #6B6B6B; }
  .np-label { font-size: max(9px, calc(10 * var(--u))); font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
              color: #6B6B6B; margin-right: 8px; }
  .np-prog { height: 2px; background: rgba(0,0,0,.1); border-radius: 1px; overflow: hidden; }
  .np-prog i { display: block; height: 100%; width: 0; background: var(--np-accent); transition: width .5s linear, background-color 1.8s ease; }

  /* volume lives inside the bar (only players that allow volume control: YouTube) */
  #vol { flex: none; display: none; align-items: center; gap: 6px; padding-left: calc(12 * var(--u));
         border-left: 1px solid rgba(0,0,0,.12); font: 600 11px Inter, system-ui, sans-serif; color: #1A1A1A; }
  body.yt #vol, body.sdk #vol { display: flex; }
  #vol button { all: unset; cursor: pointer; display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; }
  #vol button:focus-visible, #vol input:focus-visible { outline: 2px solid #000; outline-offset: 2px; }
  #vol svg { width: 17px; height: 17px; }
  #vol input { -webkit-appearance: none; appearance: none; width: calc(90 * var(--u)); min-width: 70px; height: 3px; border-radius: 2px; cursor: pointer;
               background: linear-gradient(90deg, #1A1A1A var(--v, 80%), rgba(0,0,0,.15) var(--v, 80%)); }
  #vol input::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; border-radius: 50%;
               background: #fff; border: 2px solid #1A1A1A; }
  #vol input::-moz-range-thumb { width: 10px; height: 10px; border-radius: 50%; background: #fff; border: 2px solid #1A1A1A; }
  #vol .pct { width: 24px; text-align: right; font-variant-numeric: tabular-nums; color: #6B6B6B; }

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
  <div id="hint">Browser blocked autoplay. Tap the wheel to start the music.</div>
  
</div>
<div id="embed-box"><div id="embed"></div></div>
<div id="np" role="status" aria-live="polite">
  <img id="np-cover" alt="">
  <div class="np-text" id="np-text">
    <div class="np-line"><span class="np-label">Now playing</span><b id="np-title"></b> <span id="np-artist"></span></div>
    <div class="np-prog"><i id="np-bar"></i></div>
  </div>
<div id="vol" role="group" aria-label="Volume">
  <button id="vol-btn" type="button" aria-label="Mute">
    <svg viewBox="0 0 24 24" fill="none" stroke="#000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M4 9v6h4l5 4V5L8 9H4z" fill="#000"/>
      <path id="vol-w1" d="M16 9.5a3.5 3.5 0 0 1 0 5"/>
      <path id="vol-w2" d="M18.5 7a7 7 0 0 1 0 10"/>
      <path id="vol-x" d="M16 9l5 6M21 9l-5 6" style="display:none"/>
    </svg>
  </button>
  <input id="vol-range" type="range" min="0" max="100" step="1" value="80" aria-label="Volume">
  <span class="pct" id="vol-pct">80</span>
</div>
</div>

<script>
/* ===================== data from Python ===================== */
const TRACKS   = __TRACKS__;      // shuffled top songs
const CLIP_MS  = __CLIP_MS__;     // how long each song plays
const PROVIDER = __PROVIDER__;    // "spotify" or "youtube" (P7)
const SDK_TOKEN = __SDK_TOKEN__;  // Spotify Premium only: plays through the Web Playback SDK ("" = embed player)

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
let vinylScale = 1;
let lastVizTime = 0;

function setVinylAngle(deg) {
  vinylAngle = ((deg % 360) + 360) % 360;
  vinylEl.style.transform = `rotate(${vinylAngle.toFixed(2)}deg) scale(${vinylScale.toFixed(3)})`;
}

/* ===================== easing ===================== */
// cubic-bezier(x1, y1, x2, y2) like CSS, solved with a few Newton steps
function bezier(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const X = (t) => ((ax * t + bx) * t + cx) * t;
  const Y = (t) => ((ay * t + by) * t + cy) * t;
  const dX = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    let t = x;
    for (let k = 0; k < 6; k++) {
      const d = dX(t);
      if (Math.abs(d) < 1e-6) break;
      t -= (X(t) - x) / d;
    }
    return Y(Math.min(1, Math.max(0, t)));
  };
}
const EASE_SPIN   = bezier(0.42, 0, 0.12, 1);   // gentle start, long smooth landing
const EASE_INOUT  = bezier(0.65, 0, 0.35, 1);   // song-to-song move
const EASE_OUT    = (p) => 1 - Math.pow(1 - p, 3);
const EASE_SETTLE = bezier(0.45, 0, 0.55, 1);   // tiny settle back after the overshoot

/* Smooth float animation helper used by spin(), nextSong(), and drag snap */
function animateToPos(targetPos, duration, onComplete, ease = EASE_OUT) {
  if (animId) cancelAnimationFrame(animId);
  const startPos = pos;
  const startVinyl = vinylAngle;
  const deltaPos = targetPos - startPos;
  const deltaVinyl = deltaPos * 24;
  const t0 = performance.now();

  function step(now) {
    const p = Math.min(1, (now - t0) / duration);
    const eased = ease(p);
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

/* ===================== entrance (right after the loading screen) ===================== */
const ENTER_MS = 1000;        // how long one card takes to swing in
const ENTER_STAGGER = 60;     // delay between cards
let enterStart = null;        // set when the intro starts; null = cards still hidden
function enterAmount(i) {
  if (enterStart === null) return 0;
  const t = (performance.now() - enterStart - i * ENTER_STAGGER) / ENTER_MS;
  return EASE_OUT(Math.min(1, Math.max(0, t)));
}
function entering() {
  return enterStart !== null && performance.now() - enterStart < ENTER_MS + N * ENTER_STAGGER;
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

    const e = enterAmount(i);                          // 0 = not in yet, 1 = in place
    const ang = off * STEP - (1 - e) * 30;             // swings in from above...
    const rad = ang * Math.PI / 180;
    const r = ARC_R + (1 - e) * 140;                   // ...and from outside the arc
    const x = r * Math.cos(rad);
    const y = r * Math.sin(rad);

    const abs = Math.abs(off * STEP);
    const op = (abs <= 65 ? 1 : abs >= 105 ? 0 : (105 - abs) / 40) * e;

    const closeness = Math.max(0, 1 - Math.abs(off));
    const smoothActive = closeness * closeness * (3 - 2 * closeness);
    const sc = (0.94 + smoothActive * 0.2) * Math.max(0.9, 1 - Math.min(Math.abs(off), 4) * 0.02) * (0.85 + 0.15 * e);
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
let pendingStart = null;      // song the wheel landed on before the player was ready

function startPending() {
  if (pendingStart === null || !ctrl) return;
  const i = pendingStart;
  pendingStart = null;
  playAt(i, { immediate: true });
}

/* ===================== now playing bar + page tint ===================== */
const np = {
  box: document.getElementById("np"), text: document.getElementById("np-text"),
  cover: document.getElementById("np-cover"), title: document.getElementById("np-title"),
  artist: document.getElementById("np-artist"), bar: document.getElementById("np-bar"),
};
function showNowPlaying(i) {
  const t = TRACKS[i];
  document.body.style.backgroundColor = t.bg || "#FFFFFF";
  document.documentElement.style.setProperty("--np-accent", t.accent || "#1A1A1A");
  np.bar.style.transition = "none"; np.bar.style.width = "0";          // restart progress
  void np.bar.offsetWidth; np.bar.style.transition = "";
  const fill = () => {
    np.cover.src = t.image || "";
    np.title.textContent = t.name;
    np.artist.textContent = "· " + t.artist;
    np.text.classList.remove("swap");
  };
  if (np.box.classList.contains("show")) { np.text.classList.add("swap"); setTimeout(fill, 300); }
  else { fill(); np.box.classList.add("show"); }
}
function showProgress(position, end) {
  if (end > 0) np.bar.style.width = Math.min(100, (position / end) * 100).toFixed(1) + "%";
}

const XFADE_MS = 3000;        // natural song change: old song fades out while the new one fades in
const QUICK_FADE_MS = 700;    // when the user drags to another song

function playAt(i, { immediate = false, fade = QUICK_FADE_MS } = {}) {
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
    showNowPlaying(i);
    if (!ctrl) { pendingStart = i; return; }          // player not ready yet: start it in startPending()
    if (ctrl.crossfadeTo) {                            // YouTube: true crossfade between two players
      ctrl.crossfadeTo(TRACKS[i].uri, fade);
      setTimeout(() => { if (!started) hintEl.style.display = "block"; }, 2500);
      return;
    }
    ctrl.loadUri(TRACKS[i].uri);
    setTimeout(() => {
      if (!ctrl) return;
      ctrl.play();
      setTimeout(() => { if (!started) hintEl.style.display = "block"; }, 2500);
    }, 250);
  };

  if (immediate || current < 0 || (ctrl && ctrl.crossfadeTo)) {
    if (current < 0) vizGain = 0.25;
    applyTrack();                                      // crossfade players never pause in between
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
  animateToPos(target, 1000, () => {
    playAt(mod(target, N), { fade: XFADE_MS });
  }, EASE_INOUT);
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

  if (typeof d.position === "number") showProgress(d.position, end);
  const lead = (ctrl && ctrl.crossfadeTo) ? XFADE_MS + 1000 : 0;   // wheel move (1 s) + crossfade
  if (!d.isPaused && typeof d.position === "number" && d.position >= end - lead) {
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
  const OVERSHOOT = 0.07;                              // a hair past the song, then settle back

  animateToPos(targetPos + OVERSHOOT, 4200, () => {
    animateToPos(targetPos, 450, () => {
      spinning = false;
      layout(0);
      playAt(mod(targetPos, N), { immediate: true });
    }, EASE_SETTLE);
  }, EASE_SPIN);
}

/* Intro: vinyl fades/scales in, cards swing in one by one, and the wheel starts spinning at once.
   The spin no longer waits for the music player; if the player isn't ready when the wheel lands,
   the song starts as soon as it is (see startPending). */
function intro() {
  enterStart = performance.now();
  const t0 = enterStart;
  (function grow(now) {
    const p = Math.min(1, (now - t0) / 900);
    vinylScale = 0.9 + 0.1 * EASE_OUT(p);
    vinylEl.style.opacity = EASE_OUT(p).toFixed(3);
    setVinylAngle(vinylAngle);
    if (!spinning && !dragging) layout(0);         // keep cards moving if the user grabbed the wheel
    if (p < 1 || entering()) requestAnimationFrame(grow);
  })(t0);
  setTimeout(spin, 150);
}

/* ===================== Spotify Web Playback SDK (Premium) ===================== */
/* Spotify allows ONE stream per account, so two songs can't overlap: the old song fades out,
   then the new one fades in (still smooth, just not overlapping like YouTube's crossfade). */
function startWebPlayback(fallbackToEmbed) {
  let handedOver = false, player = null;
  const fallback = (why) => {
    if (handedOver) return;
    handedOver = true;
    console.warn("[SpotiBai] Web Playback unavailable, using the embed player:", why);
    try { if (player) player.disconnect(); } catch (_) {}
    fallbackToEmbed();
  };
  const giveUp = setTimeout(() => fallback("no response in 10 s"), 10000);

  window.onSpotifyWebPlaybackSDKReady = () => {
    player = new Spotify.Player({ name: "SpotiBai", getOAuthToken: (cb) => cb(SDK_TOKEN), volume: 0 });
    ["initialization_error", "authentication_error", "account_error"].forEach((ev) =>
      player.addListener(ev, ({ message }) => {
        if (!handedOver) { clearTimeout(giveUp); fallback(`${ev}: ${message}`); return; }
        console.warn("[SpotiBai]", ev, message);
        if (ev === "authentication_error") {            // token is 1 hour old
          hintEl.textContent = "Spotify session expired. Refresh the page to keep listening.";
          hintEl.style.display = "block";
        }
      }));
    player.addListener("playback_error", ({ message }) => console.warn("[SpotiBai] playback_error", message));
    player.addListener("autoplay_failed", () => { started = false; hintEl.style.display = "block"; });
    player.addListener("ready", ({ device_id }) => {
      if (handedOver) return;
      handedOver = true;
      clearTimeout(giveUp);
      console.info("[SpotiBai] Web Playback SDK ready: volume + fades on");
      ctrl = makeSdkController(player, device_id);
      document.body.classList.add("sdk");
      startPending();
    });
    player.connect().then((ok) => { if (!ok) { clearTimeout(giveUp); fallback("connect() refused"); } });
  };
  loadScript("https://sdk.scdn.co/spotify-player.js");
}

function makeSdkController(player, deviceId) {
  let loaded = null;          // uri we asked for
  let activated = false;      // browsers only allow sound after a tap/click in this frame
  let gain = 0, rampState = null, seq = 0;
  let lastSent = -1, lastSentAt = 0;

  const activate = () => {
    if (activated) return;
    activated = true;
    try { player.activateElement(); } catch (_) {}
  };
  document.addEventListener("pointerdown", activate, true);   // any tap in the wheel area unlocks audio
  document.addEventListener("keydown", activate, true);

  // volume = slider level x fade level; sent at most ~16 times a second
  (function mix(now) {
    if (rampState) {
      const r = rampState;
      const p = Math.min(1, (now - r.t0) / r.ms);
      const c = r.to > r.from ? Math.sin(p * Math.PI / 2) : 1 - Math.cos(p * Math.PI / 2);
      gain = r.from + (r.to - r.from) * c;
      if (p >= 1) { rampState = null; if (r.done) r.done(); }
    }
    const v = Math.round(volume.level() * gain * 100) / 100;
    if (v !== lastSent && now - lastSentAt > 60) {
      lastSent = v; lastSentAt = now;
      player.setVolume(v).catch(() => {});
    }
    requestAnimationFrame(mix);
  })(performance.now());
  volume.onChange(() => { lastSent = -1; });
  const rampTo = (to, ms, done) => { rampState = { from: gain, to, t0: performance.now(), ms: Math.max(1, ms), done }; };

  async function playUri(uri, tries = 2) {
    const r = await fetch(`https://api.spotify.com/v1/me/player/play?device_id=${encodeURIComponent(deviceId)}`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${SDK_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({ uris: [uri] }),
    }).catch((e) => ({ ok: false, status: 0, e }));
    if (r.ok || r.status === 202 || r.status === 204) return true;
    if (tries > 1 && (r.status === 404 || r.status === 0 || r.status === 502)) {   // device not registered yet
      await new Promise((res) => setTimeout(res, 1200));
      return playUri(uri, tries - 1);
    }
    console.warn("[SpotiBai] play request failed", r.status);
    return false;
  }

  function startTrack(uri, fadeInMs, mySeq) {
    gain = 0; lastSent = -1; rampState = null;
    player.setVolume(0).catch(() => {});
    playUri(uri).then((ok) => { if (ok && mySeq === seq) rampTo(1, fadeInMs); });
  }

  // poll the player like the other providers do (feeds onUpdate: progress, auto-advance)
  setInterval(() => {
    player.getCurrentState().then((st) => {
      if (!st) { onUpdate({ data: { isPaused: true } }); return; }
      const t = st.track_window && st.track_window.current_track;
      const same = t && (t.uri === loaded || (t.linked_from && t.linked_from.uri === loaded));
      onUpdate({ data: {
        isPaused: st.paused,
        position: st.position,
        duration: st.duration,
        playingURI: same ? loaded : (t ? t.uri : null),
      } });
    }).catch(() => {});
  }, 500);

  return {
    loadUri(uri) { loaded = uri; },
    play() {                                   // called on the user's first tap if autoplay was blocked
      activate();
      player.getCurrentState().then((st) => {
        if (st && st.track_window.current_track) { player.resume(); if (gain < 0.05) rampTo(1, 800); }
        else if (loaded) startTrack(loaded, 800, ++seq);
      });
    },
    pause() { player.pause(); },
    crossfadeTo(uri, ms) {                     // fade out -> switch -> fade in
      loaded = uri;
      const mySeq = ++seq;
      const half = Math.max(250, ms / 2);
      if (gain > 0.02) rampTo(0, half, () => { if (mySeq === seq) startTrack(uri, half, mySeq); });
      else startTrack(uri, half, mySeq);
    },
  };
}

/* ===================== volume pill ===================== */
const volume = (() => {
  const range = document.getElementById("vol-range");
  const pct = document.getElementById("vol-pct");
  const btn = document.getElementById("vol-btn");
  const listeners = [];
  let level = 0.8, muted = false;
  try { const v = parseFloat(localStorage.getItem("sb-volume")); if (v >= 0 && v <= 1) level = v; } catch (_) {}
  function render() {
    const shown = muted ? 0 : Math.round(level * 100);
    range.value = shown;
    range.style.setProperty("--v", shown + "%");
    pct.textContent = shown;
    const off = shown === 0;
    document.getElementById("vol-x").style.display = off ? "" : "none";
    document.getElementById("vol-w1").style.display = off ? "none" : "";
    document.getElementById("vol-w2").style.display = off || shown < 50 ? "none" : "";
    btn.setAttribute("aria-label", off ? "Unmute" : "Mute");
    listeners.forEach((f) => f());
  }
  range.addEventListener("input", () => {
    level = range.value / 100; muted = false;
    try { localStorage.setItem("sb-volume", String(level)); } catch (_) {}
    render();
  });
  btn.addEventListener("click", () => { muted = !muted; if (!muted && level === 0) level = 0.5; render(); });
  render();
  return { level: () => (muted ? 0 : level), onChange: (f) => listeners.push(f) };
})();

function loadScript(src) {
  const s = document.createElement("script");
  s.src = src; s.async = true;
  document.body.appendChild(s);
}

if (PROVIDER === "youtube") {
  /* P7: an adapter that makes YouTube look like Spotify's controller (loadUri / play / pause +
     playback_update events), so the wheel code above stays the same.
     It runs TWO players stacked in the same box: the next song starts in the hidden one at volume 0
     and fades in while the current one fades out (crossfadeTo), then they swap. */
  document.body.classList.add("yt");
  const box = document.getElementById("embed-box");
  box.innerHTML = '<div id="yt0"></div><div id="yt1"></div>';

  window.onYouTubeIframeAPIReady = () => {
    const players = [null, null];
    const loaded = [TRACKS[0].uri, null];
    const gain = [0, 0];                 // fade level of each player (0..1)
    const ramps = [null, null];
    const lastSet = [-1, -1];
    let active = 0, readyCount = 0;
    let ytErrors = 0;                    // songs in a row that refused to play

    const apply = (k) => {
      const v = Math.round(volume.level() * gain[k] * 100);
      if (players[k] && v !== lastSet[k]) { try { players[k].setVolume(v); lastSet[k] = v; } catch (_) {} }
    };
    const ramp = (k, to, ms) => { ramps[k] = { from: gain[k], to, t0: performance.now(), ms: Math.max(1, ms) }; };
    (function mix(now) {                 // equal-power curves, so the crossfade doesn't dip in loudness
      for (let k = 0; k < 2; k++) {
        const r = ramps[k];
        if (r) {
          const p = Math.min(1, (now - r.t0) / r.ms);
          const c = r.to > r.from ? Math.sin(p * Math.PI / 2) : 1 - Math.cos(p * Math.PI / 2);
          gain[k] = r.from + (r.to - r.from) * c;
          if (p >= 1) {
            ramps[k] = null;
            if (gain[k] === 0 && k !== active) { try { players[k].pauseVideo(); } catch (_) {} }
          }
        }
        apply(k);
      }
      requestAnimationFrame(mix);
    })(performance.now());
    volume.onChange(() => { lastSet[0] = lastSet[1] = -1; });

    const show = () => players.forEach((p, k) => {
      const f = p && p.getIframe && p.getIframe();
      if (f) f.classList.toggle("on", k === active);
    });

    const onReady = () => {
      if (++readyCount < 2) return;
      ctrl = {
        loadUri(uri) { loaded[active] = uri; players[active].cueVideoById(uri.slice(3)); },
        play() { players[active].playVideo(); },
        pause() { players[active].pauseVideo(); },
        crossfadeTo(uri, ms) {
          const out = active, inc = 1 - active;
          loaded[inc] = uri;
          gain[inc] = 0; ramps[inc] = null; lastSet[inc] = -1; apply(inc);   // start silent
          players[inc].loadVideoById(uri.slice(3));                          // starts playing
          ramp(inc, 1, ms);
          ramp(out, 0, ms);
          active = inc;
          show();
        },
      };
      show();
      setInterval(() => {
        const p = players[active];
        if (p.getPlayerState() === YT.PlayerState.PLAYING) ytErrors = 0;
        onUpdate({ data: {
          isPaused: p.getPlayerState() !== YT.PlayerState.PLAYING,
          position: (p.getCurrentTime() || 0) * 1000,
          duration: (p.getDuration() || 0) * 1000,
          playingURI: loaded[active],
        } });
      }, 500);
      startPending();
    };

    const make = (k) => new YT.Player(`yt${k}`, {
      width: 356, height: 200,
      ...(k === 0 ? { videoId: TRACKS[0].uri.slice(3) } : {}),             // uri = "yt:<videoId>"
      playerVars: {
        playsinline: 1, rel: 0,
        // We run inside Streamlit's iframe, so tell YouTube which site the player is on
        origin: window.parent.location.origin,
        widget_referrer: window.parent.location.href,
      },
      events: {
        onReady,
        // Some music videos don't allow embedding (errors 101/150): skip to the next song
        onError: (e) => {
          if (k !== active) return;                 // only the player you can hear matters
          console.warn("YouTube player error", e.data, "on", loaded[k]);   // 101/150 = embedding blocked, 153 = site not identified
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
    players[0] = make(0);
    players[1] = make(1);
  };
  loadScript("https://www.youtube.com/iframe_api");
} else {
  /* Spotify. Premium (SDK_TOKEN set): Web Playback SDK, with volume + fades.
     Anything goes wrong while it starts up -> quietly fall back to the embed player below. */
  function startEmbed() {
    window.onSpotifyIframeApiReady = (IFrameAPI) => {
      IFrameAPI.createController(
        document.getElementById("embed"),
        { uri: TRACKS[0].uri, width: 300, height: 80 },
        (c) => {
          ctrl = c;
          c.addListener("playback_update", onUpdate);
          startPending();
        }
      );
    };
    loadScript("https://open.spotify.com/embed/iframe-api/v1");
  }
  if (SDK_TOKEN) startWebPlayback(startEmbed);
  else startEmbed();
}
vinylEl.style.opacity = "0";
layout(0);                                            // cards start hidden (enterAmount = 0)
requestAnimationFrame(() => requestAnimationFrame(intro));
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
        .replace("__PROVIDER__", json.dumps(SOURCE))
        .replace("__SDK_TOKEN__", json.dumps(SDK_TOKEN)))
components.html(html, height=800)

chat_panel()