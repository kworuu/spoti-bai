"""Talk to the REAL chat in the terminal (1 AK per message you send; the roast itself is the free template).

    python scripts/try_chat.py          # English
    python scripts/try_chat.py ceb      # Bisaya
Type a message and press Enter. Empty line = quit. Needs tests/fixtures/my_profile.json.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from BackEnd.chat import reply                 # noqa: E402
from BackEnd.models import ListeningProfile    # noqa: E402
from BackEnd.roast import fallback_roast       # noqa: E402
from BackEnd.stats import compute_all          # noqa: E402

lang = sys.argv[1] if len(sys.argv) > 1 else "en"
fixture = ROOT / "tests" / "fixtures" / "my_profile.json"
if not fixture.exists():
    sys.exit("No saved profile yet. Run: python scripts/dump_profile.py")
profile = ListeningProfile.from_dict(json.loads(fixture.read_text(encoding="utf-8")))
stats = compute_all(profile)
roast = fallback_roast(profile, stats, lang)
history = [{"role": "bot", "text": b["text"]} for b in roast["beats"]]

print("Chatting with SpotiBai (1 AK per message). Empty line to quit.\n")
while True:
    text = input("you> ").strip()
    if not text:
        break
    r = reply(profile, stats, roast, history, text, lang)
    print(f"spotibai [{r['source']}]> {r['reply']}")
    for p in r["picks"]:
        print(f"   pick: {p['track']} - {p['artist']}   (checked against Spotify in the app)")
    if r.get("error"):
        print("   (fell back because:", r["error"], ")")
    history += [{"role": "user", "text": text}, {"role": "bot", "text": r["reply"]}]