
import streamlit as st
import base64
from pathlib import Path

# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="Music Store Placeholder",
    layout="wide"
)

BASE_DIR = Path(__file__).resolve().parent.parent
ALBUM_DIR = BASE_DIR / "AlbumCover"


# ==========================================
# ALBUM IMAGE LOADER
# ==========================================

def load_image(filename):

    image_path = ALBUM_DIR / filename

    if not image_path.exists():
        return None

    encoded = base64.b64encode(
        image_path.read_bytes()
    ).decode("utf-8")

    return f"data:image/jpeg;base64,{encoded}"


# ==========================================
# ALBUM HTML GENERATOR
# ==========================================

def album_image(filename, delay):

    image_src = load_image(filename)

    if image_src is None:
        st.warning(f"Missing album image: {filename}")
        return ""

    return (
        f'<div class="album-item" style="animation-delay:{delay}s;">'
        f'<img src="{image_src}" alt="Album cover">'
        f'</div>'
    )


def album_column(content, spacer=0):

    return (
        f'<div class="album-column">'
        f'<div style="height:{spacer}px;"></div>'
        f'{content}'
        f'</div>'
    )


# ==========================================
# CUSTOM CSS
# ==========================================

st.markdown("""
<style>

/* ======================================
   GENERAL
====================================== */

.stApp {
    background-color: #FFFFFF;
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
    padding-left: 3.5rem;
    padding-right: 3.5rem;
    max-width: 100%;
}

header[data-testid="stHeader"] {
    display: none;
}

/* ======================================
   HERO SECTION
====================================== */

.hero-container {
    padding-top: 6rem;
    padding-left: 1.5rem;
    overflow: hidden;
}

/* SUBTITLE */

.hero-subtitle {
    font-size: 0.7rem;
    letter-spacing: 2px;
    color: #B0B0B0;
    text-transform: uppercase;
    margin-bottom: 1rem;

    opacity: 0;

    animation: fadeIn 1.2s ease 0.2s forwards;
}

/* ======================================
   TYPEWRITER
====================================== */

.hero-title {
    display: inline-block;
    font-family: Georgia, serif;
    font-size: clamp(3.5rem, 4.2vw, 4.4rem);
    line-height: 1.25;
    color: #1A1A1A;
    margin-bottom: 2rem;

    white-space: nowrap;

    clip-path: inset(0 100% 0 0);

    animation: typing 2.8s steps(27, end) 0.6s forwards;
}

@keyframes typing {
    from {
        clip-path: inset(0 100% 0 0);
    }

    to {
        clip-path: inset(0 0 0 0);
    }
}

/* YELLOW HIGHLIGHT */

.highlight {
    background: linear-gradient(
        180deg,
        transparent 65%,
        #FCE38A 65%
    );

    padding: 0 4px;
}

/* ======================================
   FADE IN
====================================== */

@keyframes fadeIn {
    from {
        opacity: 0;
    }

    to {
        opacity: 1;
    }
}

/* ======================================
   BUTTON
====================================== */

div[data-testid="stButton"] button {
    background-color: #1A1A1A;
    color: #FFFFFF;

    border-radius: 0;
    border: none;

    padding: 0.65rem 2rem;

    font-size: 0.75rem;
    letter-spacing: 1.5px;

    text-transform: uppercase;

    opacity: 0;

    animation: fadeIn 1.5s ease 3.4s forwards;

    transition:
        background-color 0.3s ease,
        transform 0.3s ease;
}

div[data-testid="stButton"] button:hover {
    background-color: #333333;
    color: #FFFFFF;
    transform: translateY(-3px);
}

/* ======================================
   ALBUM GRID
====================================== */

.album-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));

    gap: 10px;

    width: 100%;
    min-width: 0;

    overflow: hidden;
}

.album-column {
    display: flex;
    flex-direction: column;
    min-width: 0;
}

/* ======================================
   ALBUM IMAGES
====================================== */

.album-item {
    width: 100%;
    margin-bottom: 12px;

    opacity: 0;

    animation: albumSlide 1.8s
        cubic-bezier(0.22, 1, 0.36, 1)
        both;
}

.album-item img {
    display: block;

    width: 100%;
    height: auto;

    object-fit: cover;

    box-shadow: 0 10px 25px rgba(0,0,0,0.08);
}

/* ======================================
   SLIDE ANIMATION
====================================== */

@keyframes albumSlide {
    from {
        transform: translateX(100px);
        opacity: 0;
    }

    to {
        transform: translateX(0);
        opacity: 1;
    }
}

/* ======================================
   VINYL RECORD
====================================== */

.vinyl-record {
    width: 100%;
    aspect-ratio: 1 / 1;

    border-radius: 50%;

    background: radial-gradient(
        circle,
        #FF5733 0%,
        #FF5733 18%,
        #111111 19%,
        #111111 25%,
        #252525 26%,
        #111111 60%,
        #222222 61%,
        #111111 100%
    );

    margin-bottom: 12px;

    box-shadow: 0 10px 25px rgba(0,0,0,0.12);

    opacity: 0;

    animation: albumSlide 1.8s
        cubic-bezier(0.22, 1, 0.36, 1)
        1.45s both;
}

/* ======================================
   RESPONSIVE
====================================== */

@media (max-width: 768px) {

    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
    }

    .hero-container {
        padding-top: 2rem;
        padding-left: 0;
    }

    .hero-title {
        font-size: 1.7rem;
        white-space: normal;
        clip-path: none;

        animation: fadeIn 1.5s ease 0.6s both;
    }

    .album-grid {
        gap: 6px;
    }
}

/* ======================================
   REDUCED MOTION
====================================== */

@media (prefers-reduced-motion: reduce) {

    *,
    *::before,
    *::after {
        animation-duration: 0.01ms !important;
        animation-delay: 0ms !important;
        transition-duration: 0.01ms !important;
    }
}

</style>
""", unsafe_allow_html=True)


# ==========================================
# MAIN LAYOUT
# ==========================================

left_hero, right_grid = st.columns(
    [4, 6],
    gap="large"
)


# ==========================================
# LEFT: HERO SECTION
# ==========================================

with left_hero:
    st.markdown("")
    st.markdown("")
    hero_html = (
        '<div class="hero-container">'
        '<div class="hero-subtitle">'
        'Your playlist our judgment.'
        '</div>'
        '<div class="hero-title">'
        'IS YOUR MUSIC </br>TASTE A'
        '<span class="highlight">CHUD?</span>'
        '</div>'
        '</div>'
    )

    st.markdown(
        hero_html,
        unsafe_allow_html=True
    )

    _, btn_col = st.columns([0.5, 9.5])

    with btn_col:

        if st.button("Find Out", key="find_out_button"):
            st.switch_page("FrontEnd/Pages/intro.py")


# ==========================================
# RIGHT: ALBUM GRID
# ==========================================

with right_grid:

    # COLUMN 1

    col1 = album_column(
        album_image("01.jpg", 0.25),
        spacer=220
    )

    # COLUMN 2

    col2 = album_column(
        album_image("02.jpg", 0.37) +
        album_image("03.jpg", 0.49),
        spacer=110
    )

    # COLUMN 3

    col3 = album_column(
        album_image("04.jpg", 0.61) +
        album_image("05.jpg", 0.73) +
        album_image("06.jpg", 0.85),
        spacer=45
    )

    # COLUMN 4

    col4 = album_column(
        album_image("07.jpg", 0.97) +
        album_image("08.jpg", 1.09) +
        '<div class="vinyl-record"></div>' +
        album_image("09.jpg", 1.45),
        spacer=15
    )

    # COLUMN 5

    col5 = album_column(
        album_image("10.jpg", 1.21) +
        album_image("11.jpg", 1.33) +
        album_image("12.jpg", 1.45) +
        album_image("13.jpg", 1.57)
    )

    # COMBINE HTML WITHOUT INDENTATION

    album_html = (
        '<div class="album-grid">'
        + col1
        + col2
        + col3
        + col4
        + col5
        + '</div>'
    )

    st.markdown(
        album_html,
        unsafe_allow_html=True
    )
