"""reply(): the talk-back chat after the roast (P6). One LLM call per user message (1 AK).

Never raises on AI problems: returns a short in-character fallback instead, so the chat never breaks.
"""
from BackEnd import llm
from BackEnd.guard import clean_user_message, make_canary, validate_chat
from BackEnd.models import ListeningProfile
from BackEnd.prompts import REFUSAL, chat_system_prompt, chat_user_message

MAX_USER_MESSAGES = 30      # per session: protects the shared AK quota
HISTORY_MESSAGES = 12       # how much of the conversation the model sees

FALLBACK = {
    "en": "My brain buffered like a 2009 YouTube video. Say that again?",
    "ceb": "Nag-buffer akong utok, bai. Balika daw?",
}
LIMIT_REACHED = {
    "en": "That's enough talking back for one session. Refresh if you want round two.",
    "ceb": "Igo na sa karon, bai. I-refresh kung gusto pa ka og round two.",
}


def transcript(chat: list[dict]) -> list[dict]:
    """Session chat (see FrontEnd/UI/roast_chat.py) -> [{"role": "user"|"spotibai", "text"}]."""
    out = []
    for m in chat:
        if m["role"] == "bot":
            out.append({"role": "spotibai", "text": m["text"]})
        elif m["role"] == "choice":
            out.append({"role": "user", "text": m["labels"][m["picked"]]})
        elif m["role"] == "user":
            out.append({"role": "user", "text": m["text"]})
    return out[-HISTORY_MESSAGES:]


def user_message_count(chat: list[dict]) -> int:
    return sum(1 for m in chat if m["role"] == "user")


def reply(profile: ListeningProfile, stats: dict, roast: dict, chat: list[dict], text: str,
          lang: str = "en", complete=None) -> dict:
    """Returns {"reply": str, "picks": [{"artist", "track"}], "source": "llm"|"fallback"|"limit"|"empty"}.

    `chat` is the conversation BEFORE this new message. `complete` lets tests pass a fake model.
    """
    lang = lang if lang in REFUSAL else "en"
    text = clean_user_message(text)
    if not text:
        return {"reply": "", "picks": [], "source": "empty"}
    if user_message_count(chat) >= MAX_USER_MESSAGES:
        return {"reply": LIMIT_REACHED[lang], "picks": [], "source": "limit"}

    complete = complete or llm.complete_json
    canary = make_canary()
    try:
        raw = complete(chat_system_prompt(lang, canary),
                       chat_user_message(profile, stats, roast, transcript(chat), text),
                       max_tokens=600)
        result = validate_chat(raw, canary, REFUSAL[lang])
        result["source"] = "llm"
    except llm.LLMError as e:
        result = {"reply": FALLBACK[lang], "picks": [], "source": "fallback", "error": str(e)}
    return result