import streamlit as st
from ui import setup_page, card, wordmark, lede

setup_page("SpotiBai")

with card():
    wordmark()
    lede("Log in and get your music taste roasted.")
    with st.container(key="sb_stack"):
        if st.button("Continue with Spotify", type="primary", key="btn_spotify"):
            # TODO: replace with the Spotify OAuth redirect
            st.switch_page("pages/1_Roast_Chat.py")
        st.button("YouTube Music (coming soon)", type="secondary", disabled=True, key="btn_youtube")