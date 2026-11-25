"""Generate a REAL roast from your saved profile (uses 1 API call = AK quota).

    python scripts/try_roast.py          # English
    python scripts/try_roast.py ceb      # Bisaya

Needs tests/fixtures/my_profile.json (run scripts/dump_profile.py first).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from BackEnd.models import ListeningProfile  # noqa: E402
from BackEnd.roast import make_roast         # noqa: E402
from BackEnd.stats import compute_all        # noqa: E402

lang = sys.argv[1] if len(sys.argv) > 1 else "en"
data = json.loads((ROOT / "tests" / "fixtures" / "my_profile.json").read_text(encoding="utf-8"))
profile = ListeningProfile.from_dict(data)
stats = compute_all(profile)

roast = make_roast(profile, stats, lang)
print(f"source: {roast['source']}   lang: {roast['lang']}")
if roast.get("error"):
    print("fell back because:", roast["error"])
print()
for beat in roast["beats"]:
    print(f"[{beat['id']}] {beat['text']}")
    print("   buttons:", " | ".join(beat["replies"]))
print()
print("persona:", roast["persona"])
print("aux cord:", roast["aux_cord"])