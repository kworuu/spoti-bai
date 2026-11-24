import streamlit as st

st.set_page_config(
    page_title="Music Store Placeholder",
    layout="wide"
)

pages = [
    st.Page("Pages/home.py", title="Home", default=True),
    st.Page("Pages/intro.py", title="Intro"),
    st.Page("Pages/wheel.py", title="Wheel"),
    st.Page("Pages/roastChat.py", title="Roast Chat"),
]

navigation = st.navigation(pages, position="hidden")
navigation.run()