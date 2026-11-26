"""make_roast(): one LLM call that writes the whole scripted roast (6 beats + persona + rating).

If the model fails for any reason, a template roast built from the same stats is returned,
so the demo never dead-ends. result["source"] says which one you got: "llm" or "fallback".
"""
from BackEnd import llm
from BackEnd.guard import BEAT_IDS, clamp_score, make_canary, validate_roast
from BackEnd.models import ListeningProfile
from BackEnd.prompts import REFUSAL, roast_system_prompt, roast_user_message


def make_roast(profile: ListeningProfile, stats: dict, lang: str = "en",
               complete=None) -> dict:
    """`complete` lets tests pass a fake model; the app leaves it as None (real GPT call)."""
    lang = lang if lang in REFUSAL else "en"
    complete = complete or llm.complete_json
    canary = make_canary()
    try:
        raw = complete(roast_system_prompt(lang, canary), roast_user_message(profile, stats),
                       max_tokens=1500)
        result = validate_roast(raw, canary, REFUSAL[lang])
        result["source"] = "llm"
    except llm.LLMError as e:
        result = fallback_roast(profile, stats, lang)
        result["error"] = str(e)
    result["lang"] = lang
    return result


# ---------------------------------------------------------------------------
# Fallback: plain templates filled with real stats (no AI). Less funny, never broken.
# ---------------------------------------------------------------------------
def _hour_label(h) -> str:
    if h is None:
        return "?"
    return f"{h % 12 or 12} {'am' if h < 12 else 'pm'}"


def fallback_roast(profile: ListeningProfile, stats: dict, lang: str = "en") -> dict:
    top = (stats.get("layers", {}).get("core") or stats["top"]["artists"])[:1] or ["nobody"]
    dec, hrs, tvn, g = stats["decades"], stats["hours"], stats["then_vs_now"], stats["gauges"]
    name = profile.display_name
    artist = f"**{top[0]}**"
    decade = f"{dec['home']}s" if dec["home"] else None
    newest = tvn["new_obsessions"][0] if tvn["new_obsessions"] else None

    if lang == "ceb":
        texts = [
            f"Hi {name}. Nakita na nako imong library. Mag-istorya ta.",
            f"Imong top artist kay {artist}. Okay ra, pero predictable kaayo, bai.",
            (f"{dec['share']}% sa imong kanta gikan sa {decade}. Sayop nga dekada? Sayop nga playlist."
             if decade else "Wala gani ko kahibalo unsa nga era ka. Misteryo kaayo."),
            (f"Kasagaran nimo paminaw kay mga {_hour_label(hrs['peak_hour'])}. "
             f"{'Katulog na uy.' if hrs['night_owl'] >= 40 else 'Normal ra, boring.'}"
             if hrs["total_plays"] else "Halos wala kay gipaminaw recently. Asa ka?"),
            (f"Karon {f'**{newest}**' if newest else 'lain'} na imong gipaminaw. "
             f"{'Pili na og usa.' if tvn['shift'] >= 50 else 'Pareha ra gihapon. Usab-usab sad.'}"),
            "Aesthetic: playlist nga wala pa nahuman. Vibe: main character sa jeep.",
        ]
        replies = [["Sige, padayon", "Buotan ra ha"], ["Tinuod man", "Unsa man diay?!"],
                   ["Classic baya", "Okay, lolo"], ["Dili gyud", "Unsaon nimo pagkahibalo"],
                   ["Nag-evolve ko", "Phase ra ni"], ["Ipakita verdict", "Sakto kaayo"]]
        persona = {"aesthetic": "playlist nga wala pa nahuman", "vibe": "main character sa jeep"}
        reason = "Gibase sa imong gauges."
    else:
        texts = [
            f"Hi {name}. I've seen your library. We need to talk.",
            f"Your top artist is {artist}. Bold choice. By bold I mean predictable.",
            (f"{dec['share']}% of your songs come from the {decade}. Born in the wrong decade? "
             "Born in the wrong playlist." if decade else "I can't even tell what era you're from. Mysterious."),
            (f"You listen most around {_hour_label(hrs['peak_hour'])}. "
             f"{'Go to sleep.' if hrs['night_owl'] >= 40 else 'Responsible. Boring, but responsible.'}"
             if hrs["total_plays"] else "You've barely played anything lately. Are you okay?"),
            (f"Lately it's {f'**{newest}**' if newest else 'something new'}. "
             f"{'Commit to something.' if tvn['shift'] >= 50 else 'Same artists all year. Touch grass.'}"),
            "Aesthetic: unfinished playlist. Vibe: main character on a jeepney.",
        ]
        replies = [["Go ahead", "Be nice"], ["Fair enough", "Excuse me??"],
                   ["Classics are classics", "Okay boomer"], ["Never", "How did you know"],
                   ["I'm evolving", "It's a phase"], ["Show my verdict", "Too accurate"]]
        persona = {"aesthetic": "unfinished playlist", "vibe": "main character on a jeepney"}
        reason = "Based on your gauges."

    genre_range = 50 if g["Genre Range"] is None else g["Genre Range"]
    score = clamp_score(3 + (genre_range * 0.5 + (100 - g["Loyalty"]) * 0.3
                             + g["Era Shift"] * 0.2) / 100 * 7)
    return {
        "beats": [{"id": b, "text": t, "replies": r} for b, t, r in zip(BEAT_IDS, texts, replies)],
        "persona": persona,
        "aux_cord": {"score": score, "reason": reason},
        "source": "fallback",
    }