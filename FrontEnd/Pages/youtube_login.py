"""YouTube Music login (P7). Google sends the user back HERE (YOUTUBE_REDIRECT_URI = .../youtube_login).

1st visit: redirect to Google's login (read-only YouTube access).
Back from Google (?code=...): read their liked music, build the profile + wheel songs, then open the wheel.
The roast language travels through Google's `state` parameter, because leaving the site for the
login page starts a NEW Streamlit session (everything in st.session_state is gone when they return).
"""
import json

import streamlit as st
import streamlit.components.v1 as components

from BackEnd.config import get_secret
from BackEnd.sources import youtube
from BackEnd.stats import compute_all

st.set_page_config(page_title="SPOTIBAI", page_icon="🎡", layout="centered")
ss, params = st.session_state, st.query_params

if not get_secret("YOUTUBE_CLIENT_ID") or not get_secret("YOUTUBE_CLIENT_SECRET"):
    st.error("YouTube login isn't set up yet: add YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET "
             "to .streamlit/secrets.toml (see the guide, Phase 7).")
    st.stop()

if "error" in params:                                   # user pressed Cancel on Google's page
    st.error(f"YouTube login was cancelled ({params['error']}).")
    if st.button("Back to start", type="primary"):
        st.query_params.clear()
        st.switch_page("FrontEnd/Pages/intro.py")
    st.stop()

if "code" in params:                                    # back from Google with a login code
    lang = params.get("state", "en")
    try:
        with st.spinner("Reading your YouTube Music likes…"):
            token = youtube.exchange_code(params["code"])
            profile = youtube.fetch_profile(token)
    except (youtube.YouTubeError, Exception) as e:      # noqa: BLE001 — show any login problem
        st.error(f"Couldn't read your YouTube Music: {e}")
        if st.button("Try again", type="primary"):
            st.query_params.clear()
            st.rerun()
        st.stop()
    st.query_params.clear()

    wheel = youtube.wheel_songs(profile)
    if not wheel:
        st.warning("We couldn't find any liked songs on this account. Like a few songs in "
                   "YouTube Music, then try again.")
        st.stop()

    ss.source = "youtube"
    ss.lang = lang if lang in ("en", "ceb") else "en"
    ss.profile = profile
    ss.stats = compute_all(profile)
    ss.wheel = wheel
    ss.me = {"display_name": profile.display_name}       # wheel.py skips the Spotify user call
    st.switch_page("FrontEnd/Pages/wheel.py")

# First visit: send them to Google (the language rides along in `state`)
url = youtube.authorize_url(state=ss.get("lang", "en"))
components.html(
    "<script>const s=window.parent.document.createElement('script');"
    f"s.textContent='window.location.href='+{json.dumps(json.dumps(url))};"
    "window.parent.document.head.appendChild(s);</script>",
    height=0,
)
st.caption("Taking you to Google…")