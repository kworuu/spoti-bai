"""Every number the roast talks about. Pure functions: no Streamlit, no network.

The LLM never computes stats; it only writes jokes about what this module returns.
"""
from collections import Counter
from datetime import date
from statistics import median
from zoneinfo import ZoneInfo

from BackEnd.models import ListeningProfile

MNL = ZoneInfo("Asia/Manila")
NIGHT_HOURS = {22, 23, 0, 1, 2, 3}      # 10 pm – 3:59 am
GENRE_RANGE_FULL = 25                    # this many distinct genres = Genre Range 100
OLD_SONG_YEARS = 10                      # "Time Travel" counts songs at least this old


def _pct(part: float, whole: float) -> int:
    return round(100 * part / whole) if whole else 0


def active_hours(p: ListeningProfile) -> dict:
    hours = Counter(play.at.astimezone(MNL).hour for play in p.recent_plays)
    counts = [hours.get(h, 0) for h in range(24)]
    total = sum(counts)
    return {
        "counts": counts,
        "total_plays": total,
        "peak_hour": max(range(24), key=counts.__getitem__) if total else None,
        "night_owl": _pct(sum(counts[h] for h in NIGHT_HOURS), total),
    }


def then_vs_now(p: ListeningProfile) -> dict:
    now = [a.name for a in p.top_artists_now]
    then = [a.name for a in p.top_artists_long]
    union, both = set(now) | set(then), set(now) & set(then)
    return {
        "new_obsessions": [a for a in now if a not in then][:5],
        "dropped": [a for a in then if a not in now][:5],
        "loyal": [a for a in now if a in both][:5],
        "shift": _pct(len(union) - len(both), len(union)),
    }


def decades(p: ListeningProfile) -> dict:
    years = [t.year for t in p.top_tracks_now + p.top_tracks_long if t.year]
    if not years:
        return {"distribution": {}, "home": None, "share": 0, "median_year": None}
    dist = Counter(y // 10 * 10 for y in years)
    home, n = dist.most_common(1)[0]
    return {"distribution": dict(sorted(dist.items())), "home": home,
            "share": _pct(n, len(years)), "median_year": int(median(years))}


def genres(p: ListeningProfile) -> dict:
    g = Counter(x for a in p.top_artists_now + p.top_artists_long for x in a.genres)
    return {"top": [name for name, _ in g.most_common(5)], "distinct": len(g)}


def top_names(p: ListeningProfile, n: int = 5) -> dict:
    tracks = p.top_tracks_now or p.top_tracks_long
    artists = p.top_artists_now or p.top_artists_long
    return {"artists": [a.name for a in artists[:n]],
            "tracks": [f"{t.name} - {', '.join(t.artists[:2])}" for t in tracks[:n]]}


def gauges(p: ListeningProfile, hours: dict, tvn: dict, gen: dict,
           this_year: int | None = None) -> dict:
    this_year = this_year or date.today().year
    pool = p.top_tracks_long or p.top_tracks_now

    lead = Counter(t.artists[0] for t in pool if t.artists)
    top3 = {name for name, _ in lead.most_common(3)}
    loyalty = _pct(sum(1 for t in pool if t.artists and t.artists[0] in top3), len(pool))

    years = [t.year for t in pool if t.year]
    time_travel = _pct(sum(1 for y in years if y <= this_year - OLD_SONG_YEARS), len(years))

    return {
        "Night Owl": hours["night_owl"],
        "Loyalty": loyalty,
        "Genre Range": min(100, _pct(gen["distinct"], GENRE_RANGE_FULL)),
        "Time Travel": time_travel,
        "Era Shift": tvn["shift"],
    }


def compute_all(p: ListeningProfile, this_year: int | None = None) -> dict:
    hours, tvn, dec, gen = active_hours(p), then_vs_now(p), decades(p), genres(p)
    return {"hours": hours, "then_vs_now": tvn, "decades": dec, "genres": gen,
            "top": top_names(p), "gauges": gauges(p, hours, tvn, gen, this_year)}