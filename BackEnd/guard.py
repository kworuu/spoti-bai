"""Safety checks around the LLM: clean untrusted text going in, validate what comes out.

Proposal "Safety Protocols": input sanitization, never reveal the system prompt,
no hate speech / diagnoses (handled by the prompt; this file is the code-side backstop).
"""
import re
import secrets

from BackEnd.llm import LLMError

BEAT_IDS = ["greet", "artists", "decade", "hours", "then_now", "persona"]
MAX_BEAT_CHARS = 400
MAX_REPLY_CHARS = 40
MAX_PERSONA_CHARS = 80
MAX_USER_MESSAGE = 500

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")
_SPACES = re.compile(r"\s+")


def clean_text(text, max_len: int = 120) -> str:
    """Strip control/invisible characters, collapse whitespace, cap length."""
    text = _CONTROL.sub("", str(text or ""))
    return _SPACES.sub(" ", text).strip()[:max_len]


def clean_user_message(text) -> str:
    """What the user types in the chat (used in P6)."""
    return clean_text(text, MAX_USER_MESSAGE)


def make_canary() -> str:
    """Random marker hidden in the system prompt. If it ever shows up in output, the prompt leaked."""
    return f"SB-{secrets.token_hex(4)}"


def leaked(text: str, canary: str) -> bool:
    return bool(canary) and canary.lower() in (text or "").lower()


def clamp_score(value, low: int = 1, high: int = 10) -> int:
    try:
        return max(low, min(high, int(round(float(value)))))
    except (TypeError, ValueError):
        return (low + high) // 2


def validate_roast(data: dict, canary: str, refusal: str) -> dict:
    """Turn raw model JSON into the exact shape the frontend expects, or raise LLMError.

    Output:
      {"beats": [{"id", "text", "replies": [str, str]} × 6 in BEAT_IDS order],
       "persona": {"aesthetic", "vibe"},
       "aux_cord": {"score": 1-10, "reason"}}
    """
    if not isinstance(data, dict):
        raise LLMError("Roast is not a JSON object")

    by_id = {}
    for beat in data.get("beats") or []:
        if isinstance(beat, dict) and beat.get("id") in BEAT_IDS and beat["id"] not in by_id:
            by_id[beat["id"]] = beat
    missing = [b for b in BEAT_IDS if b not in by_id]
    if missing:
        raise LLMError(f"Roast is missing beats: {missing}")

    beats = []
    for beat_id in BEAT_IDS:
        raw = by_id[beat_id]
        text = clean_text(raw.get("text"), MAX_BEAT_CHARS)
        if not text:
            raise LLMError(f"Beat '{beat_id}' has no text")
        if leaked(text, canary):
            text = refusal
        replies = [clean_text(r, MAX_REPLY_CHARS) for r in (raw.get("replies") or [])]
        replies = [r for r in replies if r and not leaked(r, canary)][:2]
        while len(replies) < 2:
            replies.append(["Go on", "Okay..."][len(replies)])
        beats.append({"id": beat_id, "text": text, "replies": replies})

    persona = data.get("persona") if isinstance(data.get("persona"), dict) else {}
    aux = data.get("aux_cord") if isinstance(data.get("aux_cord"), dict) else {}
    out = {
        "beats": beats,
        "persona": {"aesthetic": clean_text(persona.get("aesthetic"), MAX_PERSONA_CHARS),
                    "vibe": clean_text(persona.get("vibe"), MAX_PERSONA_CHARS)},
        "aux_cord": {"score": clamp_score(aux.get("score")),
                     "reason": clean_text(aux.get("reason"), 200)},
    }
    for key in ("aesthetic", "vibe"):
        if leaked(out["persona"][key], canary):
            out["persona"][key] = ""
    if leaked(out["aux_cord"]["reason"], canary):
        out["aux_cord"]["reason"] = ""
    return out



MAX_CHAT_REPLY_CHARS = 900       # ~150 words
MAX_PICKS = 5


def validate_chat(data: dict, canary: str, refusal: str) -> dict:
    """Raw model JSON -> {"reply": str, "picks": [{"artist", "track"}]} or raise LLMError."""
    if not isinstance(data, dict):
        raise LLMError("Chat reply is not a JSON object")
    reply = clean_text(data.get("reply"), MAX_CHAT_REPLY_CHARS)
    if not reply:
        raise LLMError("Chat reply is empty")
    if leaked(reply, canary):
        return {"reply": refusal, "picks": []}
    picks = []
    for p in data.get("picks") or []:
        if not isinstance(p, dict):
            continue
        artist, track = clean_text(p.get("artist"), 80), clean_text(p.get("track"), 120)
        if artist and track and not leaked(artist + track, canary):
            picks.append({"artist": artist, "track": track})
    return {"reply": reply, "picks": picks[:MAX_PICKS]}