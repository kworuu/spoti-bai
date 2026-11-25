import sys
from pathlib import Path

# Needed for directory structure sa python 
# kay dli siya ma recognize if wala ni siya

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


import streamlit as st
from FrontEnd.UI.editorial import setup_editorial_page, editorial_card, editorial_header, choice_buttons
from FrontEnd.UI.chat import ai_said, ai_say, chosen_pills, follow_scroll

# ---- The conversation. Each node = one AI message + the reply options under it. ----
# option: label (what the user "says"), next (node to go to), go (page to open),
#         primary (solid dark button), brand (hover color: spotify / youtube)
# node:   step (the "STEP 0x" in the header, default "01")
GOOD = "FrontEnd/Pages/wheel.py"   # wheel.py handles the Spotify login (see SPOTIFY_REDIRECT_URI in secrets)
FLOW = {
    "intro": {
        "say": ("Hi, I am SpotiBai, your AI chatbot that will evaluate your music taste.\n"
                "To get started, I'll need to see your Spotify or YouTube Music.\n\n"
                "I'm just gonna look at what you listen to.\n"
                "I won't post or change anything."),
        "options": [{"label": "Sounds good to me", "next": "lang", "primary": True},
                    {"label": "Oh, okay then", "next": "lang"},
                    {"label": "Is this safe?", "next": "safe"}],
    },
    "safe": {
        "say": ("Yeah, for sure. We ain't stealing your data, but we're training ours.\n"
                "If you're done, we can continue."),
        "options": [{"label": "Bet, let's go", "next": "lang", "primary": True},
                    {"label": "Sure, why not", "next": "lang"},
                    {"label": "No, thanks", "next": "no"}],
    },
    "no": {
        "say": ("It's your loss, not mine....\n"
                "I'm joking, please come back. Speed, I need thisss."),
        "options": [{"label": "Alright, you win", "next": "lang", "primary": True},
                    {"label": "Okay okay, fine", "next": "lang"}],
    },
        "lang": {      
        "step": "02",
        "say": "Before I judge you: what language do I roast you in?",
        "options": [{"label": "English", "next": "login", "set": ("lang", "en"), "primary": True},
                    {"label": "Bisaya", "next": "login", "set": ("lang", "ceb")}],
    },
    "login": {
        "step": "02",
        "say": "Sweet. Which one are we digging through?",
        "options": [{"label": "Log in with Spotify", "go": GOOD, "brand": "spotify", "primary": True},
                    {"label": "Log in with YouTube", "next": "youtube", "brand": "youtube"}],
    },
    "youtube": {   # YouTube Music is still in development, so the button works but explains that
        "step": "02",
        "say": ("YouTube Music is still in the oven, so it's Spotify only for now.\n"
                "Mind if we roll with that?"),
        "options": [{"label": "Log in with Spotify", "go": GOOD, "brand": "spotify", "primary": True}],
    },
}

setup_editorial_page("SpotiBai")
ss = st.session_state
ss.setdefault("intro_log", [])       # finished messages and past choices
ss.setdefault("intro_node", "intro")  # where we are in FLOW
node = FLOW[ss.intro_node]
step = len(ss.intro_log)

with editorial_card():
    editorial_header(node.get("step", "01"))
    for item in ss.intro_log:
        if item[0] == "ai":
            ai_said(item[1])
        else:
            chosen_pills(item[1], item[2])
    secs = ai_say(node["say"], step)          # typed out; reply buttons appear when it finishes
    follow_scroll(secs + 1.5, step)
    picked = choice_buttons(node["options"], step)

if picked is not None:
    opt = node["options"][picked]
    ss.intro_log += [("ai", node["say"]), ("choices", [o["label"] for o in node["options"]], picked)]
    if "set" in opt:
        ss[opt["set"][0]] = opt["set"][1]
    if "go" in opt:
        st.switch_page(opt["go"])
    ss.intro_node = opt["next"]
    st.rerun()
