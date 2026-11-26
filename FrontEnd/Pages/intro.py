import sys
from pathlib import Path

# Needed for directory structure sa python 
# kay dli siya ma recognize if wala ni siya

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


import streamlit as st
from FrontEnd.UI.editorial import setup_editorial_page, editorial_card, editorial_header, choice_buttons, pushy_css, dark_css, horror_music
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
                    {"label": "No, why would should I?", "next": "no"},
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
                    {"label": "I said no!", "next": "No"}],
    },                    
    "No": {   # loops on itself; each loop the yes button grows and the bot gets more desperate
            "say": ("Are you sure?\n"
                    "Click no one more time, I dare you."),
            "says": [   # picked by how many times they've said no (the last one repeats)
                ("Are you sure?\n"
                 "Click no one more time, I dare you."),
                ("Okay, that's three times.\n"
                 "You see that button getting bigger, right? That's a sign."),
                ("Look at the size of that button.\n"
                 "There's only one button left. Funny how that works."),
            ],
            "options": [{"label": "Alright, you win", "next": "lang", "primary": True},
                        {"label": "I said no!", "next": "No"}],
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
                "options": [{"label": "Log in with Spotify", "go": GOOD, "set": ("source", "spotify"),
                     "brand": "spotify", "primary": True},
                    {"label": "Log in with YouTube", "go": "FrontEnd/Pages/youtube_login.py",
                     "set": ("source", "youtube"), "brand": "youtube"}],   # P7
    },
    "youtube": {   # YouTube Music is still in development, so the button works but explains that
        "step": "02",
        "say": ("YouTube Music is still in the oven, so it's Spotify only for now.\n"
                "Mind if we roll with that?"),
        "options": [{"label": "Log in with Spotify", "go": GOOD, "brand": "spotify", "primary": True}],
    },
}

ss = st.session_state
ss.setdefault("intro_log", [])       # finished messages and past choices
ss.setdefault("intro_node", "intro")  # where we are in FLOW
ss.setdefault("no_clicks", 0)         # how many times they've said no (drives the yes-button meme)
node = FLOW[ss.intro_node]
step = len(ss.intro_log)
says = node.get("says")
say = says[min(max(ss.no_clicks - 2, 0), len(says) - 1)] if says else node["say"]
REJECT_NODES = ("no", "No")           # options leading here count as a "no"
DARK_AFTER = 3                        # from the 3rd "no" on, the page goes black

# Meme + dark styles go into the page's FIRST style tag, so they're active before anything redraws.
meme = ss.intro_node in REJECT_NODES
angry = meme and ss.no_clicks >= DARK_AFTER

def flash_css(step):
    """Crispy red flash: snaps on, holds, snaps off, rests."""
    return f"""
.stApp::after {{
  content: "";
  position: fixed;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background: #FF3B30;
  opacity: 0;
  animation: angry-flash-{step} 0.2s linear infinite;
}}
@keyframes angry-flash-{step} {{
  0%   {{ opacity: 0; }}
  5%   {{ opacity: 0.5; }}
  45%  {{ opacity: 0.5; }}
  50%  {{ opacity: 0; }}
  100% {{ opacity: 0; }}
}}
header[data-testid="stHeader"] {{ z-index: 1 !important; }}
@media (prefers-reduced-motion: reduce) {{
  .stApp::after {{ animation: none; opacity: 0.15; }}
}}
"""

setup_editorial_page("SpotiBai", extra_css=(
    (pushy_css(step, yes_index=0, no_index=1, no_clicks=ss.no_clicks) if meme else "")
    + dark_css(angry)
    + (flash_css(step) if angry else "")))

horror_music(angry, step)             # plays while dark, fades out after "Alright, you win"

with editorial_card():
    editorial_header(node.get("step", "01"))
    for item in ss.intro_log:
        if item[0] == "ai":
            ai_said(item[1])
        else:
            chosen_pills(item[1], item[2])
    secs = ai_say(say, step)                  # typed out; reply buttons appear when it finishes
    follow_scroll(secs + 1.5, step)
    picked = choice_buttons(node["options"], step)

if picked is not None:
    opt = node["options"][picked]
    ss.intro_log += [("ai", say), ("choices", [o["label"] for o in node["options"]], picked)]
    if opt.get("next") in REJECT_NODES:
        ss.no_clicks += 1
    elif opt.get("next") == "lang":
        ss.no_clicks = 0                      # they gave in; reset for next time
    if "set" in opt:
        ss[opt["set"][0]] = opt["set"][1]
        if opt["set"][0] == "source":
            for k in ("profile", "stats", "wheel", "me", "roast", "chat", "beat", "token_info"):
                ss.pop(k, None)
    if "go" in opt:
        st.switch_page(opt["go"])
    ss.intro_node = opt["next"]
    st.rerun()



