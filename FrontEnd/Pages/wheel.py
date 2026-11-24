"""
SPOTIBAI — Song Wheel + Chat (Streamlit + Spotify)

After login:
  • the user's 10 most-played songs are loaded automatically and shuffled
  • a semi-disk wheel on the left shuffles upward by itself, then plays each song
    for CLIP_SECONDS in wheel order (cards move up, the top card fades out and a
    new one fades in at the bottom); album covers sit on the cards
  • an animated equalizer sits in the wheel's hole; an arrow points at the playing song
  • the SPOTIBAI chat card sits on top of the wheel on the right

Backend hook (left open on purpose):
  • get_opening_messages(songs)  → what SPOTIBAI says first (Python, below)
  • getBotReply(text, history)   → SPOTIBAI's answer to the user (JavaScript, in the HTML)

Run:  streamlit run wheel.py
Open: http://127.0.0.1:8501   (use 127.0.0.1, not localhost — must match the redirect URI)
"""

import json
import random
from pathlib import Path
import tomllib

import requests
import spotipy
import streamlit as st
import streamlit.components.v1 as components
from spotipy.cache_handler import CacheHandler
from spotipy.oauth2 import SpotifyOAuth

# Must be the first Streamlit call.
st.set_page_config(page_title="SPOTIBAI", page_icon="🎡", layout="wide")

# ---- Load secrets manually from .streamlit/secrets.toml (project root) ----
SECRETS_PATH = Path(__file__).resolve().parents[2] / ".streamlit" / "secrets.toml"
try:
    with open(SECRETS_PATH, "rb") as f:
        secrets = tomllib.load(f)
except FileNotFoundError:
    st.error(f"Secrets file not found at expected path: {SECRETS_PATH}")
    st.stop()

SCOPE = "user-top-read user-read-recently-played"

# ---- Settings you can change ------------------------------------------------
TOP_N = 10                  # songs on the wheel
CLIP_SECONDS = 30           # how long each song plays (30 or 60)
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
    client_id=secrets["SPOTIFY_CLIENT_ID"],
    client_secret=secrets["SPOTIFY_CLIENT_SECRET"],
    redirect_uri=secrets.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8501"),
    scope=SCOPE,
    cache_handler=SessionCacheHandler(),
    open_browser=False,
    show_dialog=True,
)

params = st.query_params

if "error" in params:  # user pressed "Cancel" on Spotify's login page
    st.session_state["login_failed"] = True
    st.session_state["login_message"] = f"Spotify login was cancelled ({params['error']})."
    st.query_params.clear()
    st.rerun()

if "code" in params:  # Spotify sent us back with a login code
    try:
        auth.get_access_token(params["code"], as_dict=False, check_cache=False)
        st.session_state["login_failed"] = False
    except Exception as e:
        st.session_state["login_failed"] = True
        st.session_state["login_message"] = f"Login failed: {e}"
    st.query_params.clear()
    st.rerun()

if not auth.validate_token(auth.cache_handler.get_cached_token()):
    spotify_login_url = auth.get_authorize_url()

    # If the last try failed, stop and show why instead of jumping to Spotify again.
    if st.session_state.get("login_failed"):
        st.error(st.session_state.get("login_message", "Login failed."))
        st.link_button("Try Spotify login again", spotify_login_url, type="primary")
        st.stop()

    components.html(
        f"""
        <script>
          const redirectScript = window.parent.document.createElement("script");
          redirectScript.textContent = "window.location.href = " + JSON.stringify({json.dumps(spotify_login_url)}) + ";";
          window.parent.document.head.appendChild(redirectScript);
        </script>
        """,
        height=0,
    )
    st.stop()
    

sp = spotipy.Spotify(
    auth_manager=auth,
    requests_timeout=20,   # wait up to 20 s instead of 5
    retries=3,             # try again automatically
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
# 2. Load the user's top songs automatically (once per login)
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
    # Album covers come in several sizes (usually 640, 300, 64 px) — pick the one closest to 300.
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


if "wheel" not in st.session_state:
    try:
        with st.spinner("Getting your top songs from Spotify…"):
            st.session_state.wheel = load_wheel_songs()
    except (spotipy.SpotifyException, requests.exceptions.RequestException) as e:
        st.error(f"Couldn't get your songs from Spotify: {e}")
        st.button("Retry")
        st.stop()

wheel = st.session_state.wheel
if not wheel:
    st.warning("Your Spotify account doesn't have listening history yet. "
               "Play a few songs on Spotify, then refresh this page.")
    st.stop()
# ---------------------------------------------------------------------------
# 3. Chat content — BACKEND HOOK
# ---------------------------------------------------------------------------
def get_opening_messages(songs):
    """What SPOTIBAI shows first.

    TODO (backend): replace this with the real AI roast built from `songs`
    (each song has name, artist, album, release_date, uri).
    Return a list of messages:
        {"role": "bot",  "text": "..."}                    → plain text on the left
        {"role": "user", "text": "...", "tone": "dark"}    → black bubble on the right
        {"role": "user", "text": "...", "tone": "grey"}    → grey bubble on the right
    The placeholders below are the Figma copy.
    """
    return [
        {"role": "bot", "text": "You’re pretty much a tiktok music enjoyer bruh…\n"
                                "Have your own personality….\n"
                                "Not that it’s not good."},
        {"role": "bot", "text": "Overall rate would be 7/10"},
        {"role": "user", "text": "Oh, you dont define me", "tone": "dark"},
        {"role": "user", "text": "Thanks I guess.", "tone": "grey"},
        {"role": "bot", "text": "Feisty, I like it!"},
    ]


if "opening_messages" not in st.session_state:
    st.session_state.opening_messages = get_opening_messages(wheel)


# ---------------------------------------------------------------------------
# 4. Page — wheel + music card + chat, all in one HTML block so they can overlap
# ---------------------------------------------------------------------------
# Remove Streamlit's header/padding and let the page fill the whole window,
# so the wheel can size itself to the laptop or monitor.
st.markdown(
    """
    <style>
      [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], footer { display: none !important; }
      .block-container, [data-testid="stMainBlockContainer"] { padding: 0 !important; max-width: 100% !important; }
      [data-testid="stAppViewContainer"], [data-testid="stMain"] { overflow: hidden !important; }
      iframe[title="st.iframe"], iframe[data-testid="stIFrame"] { display: block; height: 100vh !important; }
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
  #stage { position: absolute; left: 0; top: 0; height: 800px; transform-origin: 0 0; }
  #wheel { position: absolute; left: 0; top: 0; overflow: visible; }

  /* Equalizer inside the wheel's white hole (hole radius 200, centre at x 0, y 400) */
  #viz  { position: absolute; left: 0; top: 200px; width: 200px; height: 400px; }
  #hint { position: absolute; left: 12px; top: 520px; width: 150px; font-size: 12px; font-weight: 700;
          line-height: 1.3; color: #000; display: none; }

  /* The Spotify player itself does the playing; it is kept out of sight. */
  #embed-box { position: fixed; right: 0; bottom: 0; width: 300px; height: 80px;
               opacity: 0; pointer-events: none; }

  /* Chat card — sits IN FRONT of the wheel: starts just past the white hole and runs to the right edge */
  #chat { position: absolute; left: 580px; right: 100px; top: 32px; bottom: 32px; box-sizing: border-box;
          border: 3px solid #000; border-radius: 22px; background: #FFF; padding: 44px 56px 40px;
          display: flex; flex-direction: column; gap: 22px; }
  #chat h1 { margin: 0; text-align: center; font-size: 46px; font-weight: 800; letter-spacing: .01em; }
  #log { flex-grow: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 22px; }
  .bot  { margin: 0; font-size: 19px; line-height: 1.4; white-space: pre-line; max-width: 720px; }
  .row  { display: flex; justify-content: flex-end; }
  .bubble { max-width: 560px; padding: 12px 20px; border-radius: 12px; color: #FFF;
            font-size: 19px; line-height: 1.35; white-space: pre-line; }
  .dark { background: #000000; }
  .grey { background: #5F5B5B; }
  #form { display: flex; gap: 12px; margin: 0; }
  #msg  { flex-grow: 1; min-width: 0; height: 56px; box-sizing: border-box; border: none; border-radius: 12px;
          background: #5F5B5B; color: #FFF; padding: 0 22px; font: 400 18px Inter, system-ui, sans-serif; }
  #msg::placeholder { color: #E6E6E6; }
  #send { height: 56px; min-width: 112px; border: none; border-radius: 12px; background: #000;
          color: #FFF; font: 500 18px Inter, system-ui, sans-serif; cursor: pointer; }
  .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
</style>
</head>
<body>
<div id="stage">
  <svg id="wheel" width="800" height="800" viewBox="0 -400 800 800" aria-hidden="true">
    <defs>
      <clipPath id="cardClip" clipPathUnits="userSpaceOnUse">
        <path id="cardClipPath"></path>
      </clipPath>
    </defs>
    <circle cx="0" cy="0" r="640" fill="#D9D9D9" stroke="#000" stroke-width="3"></circle>
    <g id="cards"></g>
    <circle cx="0" cy="0" r="200" fill="#FFFFFF" stroke="#000" stroke-width="3"></circle>
    <!-- Arrow at 3 o'clock pointing at the song that is playing -->
    <g id="arrow">
              <polygon points="191,-18 232,0 191,18" fill="#000" stroke="#FFF" stroke-width="3" stroke-linejoin="round"></polygon>
    </g>
  </svg>

  <canvas id="viz" aria-hidden="true"></canvas>
  <div id="hint">Click anywhere to start the music</div>

  <section id="chat" aria-label="Spotibai chat">
    <h1>SPOTIBAI</h1>
    <div id="log" aria-live="polite"></div>
    <form id="form">
      <label class="sr-only" for="msg">Reply to Spotibai</label>
      <input id="msg" autocomplete="off" placeholder="Type your reply…">
      <button id="send" type="submit">Send</button>
    </form>
  </section>
</div>
<div id="embed-box"><div id="embed"></div></div>

<script>
/* ===================== data from Python ===================== */
const TRACKS   = __TRACKS__;      // shuffled top songs
const CLIP_MS  = __CLIP_MS__;     // how long each song plays
const MESSAGES = __MESSAGES__;    // opening chat messages

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

/* ===================== wheel geometry ===================== */
const N = TRACKS.length;
const STEP = 24;                  // degrees between cards
const C_IN = 120, C_OUT = 880;    // card inner/outer radius (inner end hides under the hole)
const HALF = STEP / 2, RC = 0;    // HALF = STEP/2 → cards touch with no gaps
const HOLE_R = 200;               // keep equal to the white circle's r in the SVG
const NS = "http://www.w3.org/2000/svg";

function pol(r, deg) {
  const t = deg * Math.PI / 180;
  return (r * Math.cos(t)).toFixed(1) + " " + (r * Math.sin(t)).toFixed(1);
}
const DC = RC / C_OUT * 180 / Math.PI;
const CARD_D =
  "M " + pol(C_IN, -HALF) + " L " + pol(C_OUT - RC, -HALF) +
  " Q " + pol(C_OUT, -HALF) + " " + pol(C_OUT, -HALF + DC) +
  " A " + C_OUT + " " + C_OUT + " 0 0 1 " + pol(C_OUT, HALF - DC) +
  " Q " + pol(C_OUT, HALF) + " " + pol(C_OUT - RC, HALF) +
  " L " + pol(C_IN, HALF) + " A " + C_IN + " " + C_IN + " 0 0 0 " + pol(C_IN, -HALF) + " Z";

const mod = (a, m) => ((a % m) + m) % m;

function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

/* Build one <g> per song: the whole card is filled with its album cover. */
document.getElementById("cardClipPath").setAttribute("d", CARD_D);
const ACTIVE_SCALE = 1 + 80 / C_OUT;             // playing card grows ~80 units outward
const VISIBLE_FROM = HOLE_R / ACTIVE_SCALE;      // innermost point that can show
const COVER_SIZE = (C_OUT - VISIBLE_FROM) + 12;  // square big enough to fill the visible part of the card
const COVER_CENTER = (VISIBLE_FROM + C_OUT) / 2;

const cardsLayer = document.getElementById("cards");
const cards = TRACKS.map((t) => {
  const g = el("g", {}, cardsLayer);
  g.style.transformOrigin = "0px 0px";
  g.style.transformBox = "view-box";
  el("path", { d: CARD_D, fill: "#D9D9D9" }, g);                       // grey shows if there's no cover
  if (t.image) {
    const clip = el("g", { "clip-path": "url(#cardClip)" }, g);
    const turn = el("g", { transform: `translate(${COVER_CENTER} 0) rotate(90)` }, clip);
    const img = el("image", { x: -COVER_SIZE / 2, y: -COVER_SIZE / 2, width: COVER_SIZE, height: COVER_SIZE,
                             preserveAspectRatio: "xMidYMid slice" }, turn);
    img.setAttribute("href", t.image);
  }
  const path = el("path", { d: CARD_D, fill: "none", stroke: "#000", "stroke-width": 3, "stroke-linejoin": "round" }, g);
  return { g, path };
});

let pos = 0;              // how far the wheel has turned (in cards)
let playing = false;

/* Place every card for the current `pos`. Cards move UP as pos grows. */
function layout(ms) {
  cards.forEach((c, i) => {
    const off = mod(i - pos + Math.floor(N / 2), N) - Math.floor(N / 2);   // 0 = playing card (3 o'clock)
    const ang = off * STEP, abs = Math.abs(ang);
    const op = abs <= 60 ? 1 : abs >= 100 ? 0 : (100 - abs) / 40;          // fade near top/bottom
    const sc = off === 0 ? ACTIVE_SCALE : 1;                               // playing card grows outward
    c.g.style.transition = `transform ${ms}ms cubic-bezier(.25,.7,.3,1), opacity ${ms}ms linear`;
    c.g.style.transform = `rotate(${ang}deg) scale(${sc})`;
    c.g.style.opacity = op.toFixed(2);
    c.path.setAttribute("stroke-width", off === 0 && playing ? 4 : 3);
  });
}
layout(0);

/* ===================== arrow ===================== */
const arrow = document.getElementById("arrow");
function nudgeArrow() {                          // small kick each time a new song starts
  arrow.animate([{ transform: "translateX(0)" }, { transform: "translateX(10px)" }, { transform: "translateX(0)" }],
                { duration: 450, easing: "ease-out" });
}

/* ===================== equalizer in the hole =====================
   Spotify doesn't let apps read the real audio, so these bars are animated:
   they move while a song plays, settle when it's paused, and each song gets its own pattern. */
const viz = document.getElementById("viz");
const vctx = viz.getContext("2d");
const BARS = 23;                                 // number of bars (more bars would run into the arrow)
const BAR_W = 4.5, BAR_GAP = 3;                  // bar width and gap (design units)
const BAR_MAX = 230;                             // tallest a bar can get
let audioOn = false;                             // true while Spotify is actually playing
let songSeed = 1;
const heights = new Array(BARS).fill(4);

function sizeViz() {                             // keep the canvas sharp at any screen size
  const s = window.innerHeight / 800;
  const r = (window.devicePixelRatio || 1) * s;
  viz.width = 200 * r; viz.height = 400 * r;
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
  vctx.clearRect(0, 0, 200, 400);
  const sec = t / 1000;
  const beat = 0.75 + 0.25 * Math.pow(Math.abs(Math.sin(sec * Math.PI * 2)), 6);   // ~120 bpm pulse
  for (let i = 0; i < BARS; i++) {
    const x = 0 + i * (BAR_W + BAR_GAP);
    // the hole is round, so bars near its edge must be shorter
    const room = 2 * Math.sqrt(Math.max(0, 200 * 200 - (x + BAR_W) * (x + BAR_W))) - 70;
    const maxH = Math.max(6, Math.min(BAR_MAX, room));
    let target = 4;
    if (audioOn) {
      const a = Math.abs(Math.sin(sec * (2.1 + (songSeed % 7) * 0.31) + i * (0.55 + (songSeed % 5) * 0.07)));
      const b = Math.abs(Math.sin(sec * (3.7 + (songSeed % 3) * 0.4) - i * 0.9));
      target = maxH * (0.18 + 0.82 * a * b) * beat;
    } else if (spinning) {
      target = maxH * 0.12 * (1 + Math.sin(sec * 8 - i * 0.6));   // gentle ripple while shuffling
    }
    heights[i] += (target - heights[i]) * 0.25;                    // smooth movement
    const h = Math.max(4, heights[i]);
    vctx.fillStyle = "#000";
    vctx.beginPath();
    vctx.roundRect(x, 200 - h / 2, BAR_W, h, BAR_W / 2);
    vctx.fill();
  }
  requestAnimationFrame(drawViz);
}
requestAnimationFrame(drawViz);

/* ===================== Spotify playback (automatic, no buttons) ===================== */
const hintEl = document.getElementById("hint");
let ctrl = null, current = -1, switchedAt = 0, started = false, spinning = false;

function playAt(i) {
  current = i;
  playing = true;
  songSeed = seedFrom(TRACKS[i].uri);
  nudgeArrow();
  switchedAt = performance.now();
  if (!ctrl) return;
  ctrl.loadUri(TRACKS[i].uri);
  setTimeout(() => {
    ctrl.play();
    // Browsers block sound until the person clicks the page once — ask for one click.
    setTimeout(() => { if (!started) hintEl.style.display = "block"; }, 2500);
  }, 400);
}

function nextSong() {
  pos += 1;
  layout(750);
  playAt(mod(pos, N));
}

// The first click anywhere on the page unlocks sound (the chat still works normally).
document.addEventListener("pointerdown", () => {
  if (ctrl && !started && current >= 0) { switchedAt = performance.now(); ctrl.play(); }
});

function onUpdate(e) {
  const d = e.data;
  if (!d) return;
  audioOn = !d.isPaused;
  if (!d.isPaused && !started) { started = true; hintEl.style.display = "none"; }
  if (current < 0) return;
  if (d.playingURI && d.playingURI !== TRACKS[current].uri) return;   // update from the previous song
  const end = d.duration ? Math.min(CLIP_MS, d.duration - 300) : CLIP_MS;
  if (performance.now() - switchedAt < 1500) return;                  // still loading
  if (!d.isPaused && d.position >= end) nextSong();
}

/* ===================== intro: shuffle upward, slow down, land ===================== */
let spun = false;
function spin() {
  if (spun) return;
  spun = true;
  spinning = true;
  const steps = 14 + Math.floor(Math.random() * N);
  let wait = 300;
  for (let k = 0; k < steps; k++) {
    const ms = Math.round(60 + 560 * Math.pow(k / (steps - 1), 2.4));
    setTimeout(() => { pos += 1; layout(ms); }, wait);
    wait += ms;
  }
  setTimeout(() => { spinning = false; layout(500); playAt(mod(pos, N)); }, wait + 150);
}

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
setTimeout(spin, 6000);   // if the Spotify player never loads, still spin the wheel

/* ===================== chat ===================== */
const log = document.getElementById("log");
const history = [];

function addMessage(m) {
  history.push(m);
  let node;
  if (m.role === "bot") {
    node = document.createElement("p");
    node.className = "bot";
    node.textContent = m.text;
  } else {
    node = document.createElement("div");
    node.className = "row";
    const b = document.createElement("div");
    b.className = "bubble " + (m.tone === "grey" ? "grey" : "dark");
    b.textContent = m.text;
    node.appendChild(b);
  }
  log.appendChild(node);
  log.scrollTop = log.scrollHeight;
}
MESSAGES.forEach(addMessage);

/* TODO (backend): replace with a real call to your AI backend, e.g.
     const res = await fetch("https://your-backend/chat", {
       method: "POST", headers: {"Content-Type": "application/json"},
       body: JSON.stringify({ message: text, history, songs: TRACKS })
     });
     return (await res.json()).reply;
   Return null to show no reply. */
async function getBotReply(text, history) {
  return null;
}

document.getElementById("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("msg");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addMessage({ role: "user", text: text, tone: "dark" });
  try {
    const reply = await getBotReply(text, history);
    if (reply) addMessage({ role: "bot", text: reply });
  } catch (err) {
    addMessage({ role: "bot", text: "Couldn't reach SPOTIBAI right now." });
  }
});
</script>
<script src="https://open.spotify.com/embed/iframe-api/v1" async></script>
</body>
</html>
"""


def to_js(value):
    """JSON that is safe to place inside a <script> tag."""
    return json.dumps(value).replace("</", "<\\/")


html = (PAGE_HTML
        .replace("__TRACKS__", to_js(wheel))
        .replace("__CLIP_MS__", str(CLIP_SECONDS * 1000))
        .replace("__MESSAGES__", to_js(st.session_state.opening_messages)))
components.html(html, height=800)   # the CSS above stretches it to the full window height