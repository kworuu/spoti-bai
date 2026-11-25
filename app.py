import streamlit as st

st.set_page_config(
    page_title="Music Store Placeholder",
    layout="wide"
)

pages = [
    st.Page("FrontEnd/Pages/home.py", title="Home", default=True),
    st.Page("FrontEnd/Pages/intro.py", title="Intro"),
    st.Page("FrontEnd/Pages/wheel.py", title="Wheel"),
    st.Page("FrontEnd/Pages/youtube_login.py", title="YouTube login", url_path="youtube_login"),
    st.Page("FrontEnd/Pages/roastChat.py", title="Roast Chat"),
]

navigation = st.navigation(pages, position="hidden")
navigation.run()