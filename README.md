# SpotiBai 🎧

An AI chatbot that judges your music taste. Log in with Spotify or YouTube Music, spin a wheel of your top songs, get roasted in English or Bisaya, and take home a playlist receipt.

Built with [Streamlit](https://streamlit.io/). SpotiBai only reads your listening data. It never posts or changes anything on your account.

## Features

- **Chatty intro**: a typed-out conversation walks you through login and language choice (with a few easter eggs if you say no).
- **Song wheel**: your top 10 songs on a spinning vinyl wheel. Each song plays for a short clip, and you can drag the wheel to scrub. The page tint follows the current album cover.
- **AI roast chat**: SpotiBai roasts your taste based on your top tracks and stats, then you can talk back.
- **Playlist receipt**: your top 10 as a tilted paper receipt (PNG, 1080x1350). Spotify uses a green background and YouTube uses red.
- **Two languages**: English (`en`) and Bisaya (`ceb`).
- **Two sources**: Spotify and YouTube Music.

## Project structure

```
spoti-bai/
├── app.py                  # entry point
├── .streamlit/
│   ├── config.toml
│   └── secrets.toml        # your keys (never commit this)
├── BackEnd/
│   ├── sources/
│   │   ├── spotify.py      # Spotify data
│   │   └── youtube.py      # YouTube Music data
│   ├── llm.py              # model calls
│   ├── prompts.py          # roast / chat prompts
│   ├── roast.py            # roast generation
│   ├── chat.py             # chat handling
│   ├── guard.py            # input guarding
│   ├── insights.py         # taste layers (core / phase / past)
│   ├── picks.py            # song picks
│   ├── stats.py            # listening stats
│   ├── models.py           # data models
│   └── config.py           # settings and secrets (get_secret)
├── FrontEnd/
│   ├── Pages/
│   │   ├── home.py             # landing page
│   │   ├── intro.py            # chat intro and login choice
│   │   ├── wheel.py            # loading, wheel and roast chat
│   │   ├── youtube_login.py    # YouTube OAuth return page
│   │   ├── roastChat.py        # roast chat demo page
│   │   └── spotify_covers.py   # album covers for backgrounds
│   ├── UI/                     # shared look and components
│   │   ├── theme.py, background.py, chat.py, editorial.py
│   │   ├── loader.py, receipt.py, cover_colors.py, roast_chat.py
│   ├── AlbumCover/             # images for the landing page
│   └── static/                 # fonts and cached covers
├── scripts/
├── tests/
├── requirements.txt
└── requirements-dev.txt
```

## Getting started

### 1. Requirements

- Python 3.10+
- A [Spotify Developer](https://developer.spotify.com/dashboard) app
- A Google Cloud OAuth client with the YouTube Data API enabled (only if you want YouTube login)

### 2. Install

```bash
git clone <your-repo-url>
cd spoti-bai
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

For development (tests, linting):

```bash
pip install -r requirements-dev.txt
```

A `.devcontainer/` is included if you prefer to work in a container.

### 3. Add your secrets

Create `.streamlit/secrets.toml`:

```toml
SPOTIFY_CLIENT_ID = "your-spotify-client-id"
SPOTIFY_CLIENT_SECRET = "your-spotify-client-secret"
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:8501/wheel"

YOUTUBE_CLIENT_ID = "your-google-client-id"
YOUTUBE_CLIENT_SECRET = "your-google-client-secret"
YOUTUBE_REDIRECT_URI = "http://localhost:8501/youtube_login"

# plus the key for the AI provider used in BackEnd/llm.py
```

Register the same redirect URIs in the Spotify dashboard and the Google Cloud console. They must match exactly. The Spotify redirect points at `/wheel` and the YouTube one at `/youtube_login`.

> **Spotify Development Mode:** only accounts added under **Dashboard → Settings → User Management** can log in. Anyone else gets a 403 from Spotify.

On Streamlit Community Cloud, put the same keys in the app's **Secrets** settings instead of the file.

### 4. Run

```bash
streamlit run app.py
```
or:
```bash
python -m streamlit run app.py
```

Open http://localhost:8501 (use `127.0.0.1` if your Spotify redirect URI does).

## Configuration

Settings at the top of `FrontEnd/Pages/wheel.py`:

| Setting | Default | What it does |
| --- | --- | --- |
| `TOP_N` | `10` | Songs on the wheel |
| `CLIP_SECONDS` | `30` | How long each song plays |
| `TIME_RANGE` | `"medium_term"` | Spotify top-tracks window (`short_term`, `medium_term`, `long_term`) |
| `USE_WEB_PLAYBACK` | `False` | Try the Spotify Web Playback SDK (Premium, volume and fades). Free accounts fall back to the embed player |

Background density and size: the settings block at the top of `FrontEnd/UI/background.py`. Typing speed in the chat: `CHAR_SECONDS` in `FrontEnd/UI/chat.py`.

## How it works

1. `intro.py` runs a scripted chat, saves the chosen `source` and `lang` in `st.session_state`, then opens the login page.
2. **Spotify:** `wheel.py` redirects to Spotify, gets the token back on `/wheel` and keeps it in the user's own session.
   **YouTube:** `youtube_login.py` handles the Google redirect, builds the profile and wheel songs, then opens `wheel.py`.
3. A loading screen (`FrontEnd/UI/loader.py`) covers the app while the profile, stats and roast are built. Use **one** `LoadingScreen` per page, because each instance owns its own placeholder.
4. The wheel and the receipt use the same top 10 list (`insights.taste_tracks`), so they always match.

## Testing

```bash
pytest
```

Config is in `pytest.ini`.

## Tech stack

Streamlit, Spotipy, Pillow, Requests, and the YouTube Data API. The wheel is a single HTML/JS/SVG component embedded with `components.html`.

## Privacy

SpotiBai only reads your listening data and does not post or modify anything. Tokens live in your Streamlit session, not on a shared disk cache.

## Acknowledgements

Album art and song data come from Spotify and YouTube. Receipt font: Courier Prime.
