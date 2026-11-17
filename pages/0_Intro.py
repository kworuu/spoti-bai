import streamlit as st
from ui import setup_page, card, wordmark
from ui.chat import ai_said, ai_say, chosen_pills, choice_buttons, follow_scroll

# ---- The conversation. Each node = one AI message + the reply options under it. ----
# option: label (what the user "says"), next (node to go to), go (page to open), brand (hover color)
GOOD = "pages/1_Roast_Chat.py"   # TODO: replace with the real Spotify OAuth redirect
FLOW = {
    "intro": {
        "say": ("Hi, I am SpotiBai, your AI chatbot that will evaluate your music taste.\n"
                "To get started, I'll need to see your Spotify or YouTube Music.\n\n"
                "I'm just gonna look at what you listen to.\n"
                "I won't post or change anything."),
        "options": [{"label": "Sounds good to me", "next": "login"},
                    {"label": "Oh, okay then", "next": "login"},
                    {"label": "Is this safe?", "next": "safe"}],
    },
    "safe": {
        "say": ("Yeah, for sure. We ain't stealing your data, but we're training ours.\n"
                "If you're done, we can continue."),
        "options": [{"label": "Bet, let's go", "next": "login"},
                    {"label": "Sure, why not", "next": "login"},
                    {"label": "No, thanks", "next": "no"}],
    },
    "no": {
        "say": ("It's your loss, not mine....\n"
                "I'm joking, please come back. Speed, I need thisss."),
        "options": [{"label": "Alright, you win", "next": "login"},
                    {"label": "Okay okay, fine", "next": "login"}],
    },
    "login": {
        "say": "Sweet. Which one are we digging through?",
        "options": [{"label": "Log in with Spotify", "go": GOOD, "brand": "spotify"},
                    {"label": "Log in with YouTube", "next": "youtube", "brand": "youtube"}],
    },
    "youtube": {   # YouTube Music is still in development, so the button works but explains that
        "say": ("YouTube Music is still in the oven, so it's Spotify only for now.\n"
                "Mind if we roll with that?"),
        "options": [{"label": "Log in with Spotify", "go": GOOD, "brand": "spotify"}],
    },
}

setup_page("SpotiBai")
ss = st.session_state
ss.setdefault("intro_log", [])       # finished messages and past choices
ss.setdefault("intro_node", "intro")  # where we are in FLOW
node = FLOW[ss.intro_node]
step = len(ss.intro_log)

with card():
    wordmark()
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
    if "go" in opt:
        st.switch_page(opt["go"])
    ss.intro_node = opt["next"]
    st.rerun()
