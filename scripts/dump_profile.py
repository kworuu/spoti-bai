"""Log in to Spotify OUTSIDE Streamlit and save your real profile for backend testing.

Run from the spoti-bai folder (stop `streamlit run` first, it uses the same port):
    python scripts/dump_profile.py

Writes tests/fixtures/my_profile.json  (gitignored: it's your listening history).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import spotipy                                   # noqa: E402
from spotipy.oauth2 import SpotifyOAuth          # noqa: E402

from BackEnd.config import get_secret            # noqa: E402
from BackEnd.sources.spotify import fetch_profile  # noqa: E402
from BackEnd.stats import compute_all            # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "my_profile.json"

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=get_secret("SPOTIFY_CLIENT_ID"),
    client_secret=get_secret("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=get_secret("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8501"),
    scope="user-top-read user-read-recently-played",
    cache_path=str(ROOT / ".cache-dev"),
))

profile = fetch_profile(sp)
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(profile.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

stats = compute_all(profile)
print(f"Saved {profile.display_name}: {len(profile.top_tracks_now)} recent top tracks, "
      f"{len(profile.recent_plays)} plays -> {OUT.relative_to(ROOT)}")
print("Gauges:", stats["gauges"])