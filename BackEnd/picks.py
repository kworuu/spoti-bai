"""resolve_picks(): keep only AI song picks that really exist on Spotify (P6).

The model can invent songs, so every pick is checked with Spotify search (works in Development
Mode, no extra login scope). Picks that aren't found are dropped. Read-only: nothing is saved.
"""
from BackEnd.guard import MAX_PICKS


def resolve_picks(sp, picks: list[dict]) -> list[dict]:
    """[{"artist", "track"}] -> [{"name", "artist", "url", "image"}] for the ones Spotify knows."""
    found, seen = [], set()
    for p in picks[:MAX_PICKS]:
        q = f'track:{p.get("track", "")[:80]} artist:{p.get("artist", "")[:80]}'
        try:
            items = sp.search(q=q, type="track", limit=1)["tracks"]["items"]
        except Exception:                 # network / rate limit: just skip this pick
            continue
        if not items or items[0]["uri"] in seen:
            continue
        t = items[0]
        seen.add(t["uri"])
        imgs = (t.get("album") or {}).get("images") or []
        found.append({"name": t["name"][:120],
                      "artist": ", ".join(a["name"] for a in t.get("artists", [])[:2])[:120],
                      "url": (t.get("external_urls") or {}).get("spotify", ""),
                      "image": imgs[-1]["url"] if imgs else ""})
    return found