"""Preview the wheel page + roast chat WITHOUT Spotify login and WITHOUT using AK.

    streamlit run scripts/preview_chat.py            # English
    open http://127.0.0.1:8501/?lang=ceb             # Bisaya

Uses the template (fallback) roast, your saved profile if tests/fixtures/my_profile.json exists
(otherwise a made-up one), and the real wheel HTML/CSS read straight from FrontEnd/Pages/wheel.py.
"""
import ast
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st                                     # noqa: E402
import streamlit.components.v1 as components               # noqa: E402

from BackEnd.models import Artist, ListeningProfile, Play, Track  # noqa: E402
from BackEnd.roast import fallback_roast                   # noqa: E402
from BackEnd.stats import compute_all                      # noqa: E402
from FrontEnd.UI.roast_chat import chat_panel, init_chat_state  # noqa: E402

st.set_page_config(page_title="SPOTIBAI preview", layout="wide")


def wheel_parts():
    """Read PAGE_HTML and the page CSS out of wheel.py without running it (no login)."""
    tree = ast.parse((ROOT / "FrontEnd" / "Pages" / "wheel.py").read_text(encoding="utf-8"))
    html = css = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "PAGE_HTML":
            html = node.value.value
        if (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "markdown" and node.args
                and isinstance(node.args[0], ast.Constant) and "stHeader" in str(node.args[0].value)):
            css = node.args[0].value
    return html, css


def demo_profile() -> ListeningProfile:
    fixture = ROOT / "tests" / "fixtures" / "my_profile.json"
    if fixture.exists():
        return ListeningProfile.from_dict(json.loads(fixture.read_text(encoding="utf-8")))
    t = lambda n, a, y: Track(n, [a], "Album", y, f"spotify:track:{n}")
    now = datetime.now(timezone.utc)
    return ListeningProfile(
        "spotify", "Preview",
        [t("Song A", "Artist One", 2024), t("Song B", "Artist Two", 2023)],
        [t("Old Song", "Old Band", 1998), t("Song A", "Artist One", 2024)],
        [Artist("Artist One", ["opm"]), Artist("Artist Two", ["k-pop"])],
        [Artist("Old Band", ["rock"]), Artist("Artist One", ["opm"])],
        [Play(t("Song A", "Artist One", 2024), now - timedelta(hours=h)) for h in range(12)])


lang = st.query_params.get("lang", "en")
if st.session_state.get("roast", {}).get("lang") != lang:
    profile = demo_profile()
    roast = fallback_roast(profile, compute_all(profile), lang)   # template roast: 0 AK
    roast["lang"] = lang
    init_chat_state(roast)

html, css = wheel_parts()
if css:
    st.markdown(css, unsafe_allow_html=True)
tracks = [{"name": f"Song {i}", "artist": "Preview", "uri": "", "image": "", "album": "", "release_date": ""}
          for i in range(10)]
components.html(html.replace("__TRACKS__", json.dumps(tracks)).replace("__CLIP_MS__", "30000"), height=800)
chat_panel()