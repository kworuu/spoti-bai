import streamlit as st
from ui import setup_page, card, wordmark, bot_say

setup_page("SpotiBai | Roast")
step = st.session_state.setdefault("step", 0)

with card():
    wordmark()
    if step == 0:
        bot_say("Is this you, “Bisakol”? nice username.")
        with st.container(key="sb_replies"):
            if st.button("Yes, that’s me", type="primary"):
                st.session_state.step = 1
                st.rerun()
            st.button("No, who’s that?", type="secondary")
    else:
        bot_say("Damn, you got some good taste. There’s a lot of K-pop here. "
                "Is your favourite group NewJeans?")
        with st.container(key="sb_replies"):
            st.button("Yessir!!!", type="primary")
            if st.button("No, you got it wrong.", type="secondary"):
                st.session_state.step = 0
                st.rerun()
