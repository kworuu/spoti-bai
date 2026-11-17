import streamlit as st
from ui import setup_page, card, headline, lede

setup_page("SpotiBai")

with card():
    headline("Is your music taste chud?")
    lede("Your playlist, our judgment.")
    with st.container(key="sb_center"):
        if st.button("Find Out", type="secondary", key="find_out"):
            for k in ("intro_log", "intro_node"):   # start the intro chat fresh
                st.session_state.pop(k, None)
            st.switch_page("pages/0_Intro.py")
