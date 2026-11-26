"""Every number the roast talks about. Pure functions: no Streamlit, no network.

The LLM never computes stats; it only writes jokes about what this module returns.
"""
from collections import Counter
from datetime import date
from statistics import median
from zoneinfo import ZoneInfo

from BackEnd.insights import compute_insights
from BackEnd.models import ListeningProfile

MNL = ZoneInfo("Asia/Manila")
NIGHT_HOURS = {22, 23, 0, 1, 2, 3}      # 10 pm – 3:59 am
GENRE_RANGE_FULL = 25                    # this many distinct genres = Genre Range 100
FADED_SHARE = 0.15
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


def _rank_points(names: list[str], top: int = 20) -> Counter:
    """Rank 1 gets `top` points, rank 2 gets top-1, ... (Spotify's lists are already ranked)."""
    return Counter({name: max(1, top - i) for i, name in enumerate(names)})


def current_obsession(p: ListeningProfile, n: int = 5) -> dict:
    """What they're into RIGHT NOW, strongest signal first.

    Score per artist = 2 x plays in the last 50 plays (real repeats, the freshest data Spotify gives)
                     + rank points in the ~4-week top artists (20 for #1 ... 1 for #20).
    "on_repeat" = songs played 3+ times in the last 50 plays.
    """
    plays = Counter(pl.track.artists[0] for pl in p.recent_plays if pl.track.artists)
    score = Counter({a: 2 * c for a, c in plays.items()})
    score.update(_rank_points([a.name for a in p.top_artists_now]))
    track_plays = Counter((pl.track.name, ", ".join(pl.track.artists[:2])) for pl in p.recent_plays)
    on_repeat = [f"{name} - {artist}" for (name, artist), c in track_plays.most_common(5) if c >= 3]
    return {"artists": [a for a, _ in score.most_common(n)], "on_repeat": on_repeat}


def genres_split(p: ListeningProfile, n: int = 5) -> dict:
    """Genres weighted by rank, kept apart: 'now' (~4 weeks) vs 'then' (~1 year).

    'then' = genres that FADED: their share of the year is clearly bigger than their share of this month.
    (A genre they still play a bit now can still count as faded if it used to dominate.)
    """
    def weighted(artists):
        g = Counter()
        for i, a in enumerate(artists):
            for tag in a.genres:
                g[tag] += max(1, 20 - i)
        return g
    now, then = weighted(p.top_artists_now), weighted(p.top_artists_long)
    share = lambda g, tag: g[tag] / (sum(g.values()) or 1)
    faded = [tag for tag, _ in then.most_common() if share(then, tag) - share(now, tag) >= FADED_SHARE]
    return {"now": [tag for tag, _ in now.most_common(n)], "then": faded[:n],
            "year": [tag for tag, _ in then.most_common(n * 2)]}


def decade_split(p: ListeningProfile) -> dict:
    """Home decade of the ~4-week top tracks vs the ~1-year ones."""
    def home(tracks):
        years = [t.year for t in tracks if t.year]
        return Counter(y // 10 * 10 for y in years).most_common(1)[0][0] if years else None
    return {"now": home(p.top_tracks_now), "then": home(p.top_tracks_long)}


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
        "Genre Range": min(100, _pct(gen["distinct"], GENRE_RANGE_FULL)) if gen["distinct"] else None,  # None = unknown
        "Time Travel": time_travel,
        "Era Shift": tvn["shift"],
    }


def compute_all(p: ListeningProfile, this_year: int | None = None) -> dict:
    hours, tvn, dec, gen = active_hours(p), then_vs_now(p), decades(p), genres(p)
    return {"hours": hours, 
            "then_vs_now": tvn, 
            "decades": dec, 
            "genres": gen, 
            "top": top_names(p), 
            "gauges": gauges(p, hours, tvn, gen, this_year),
            "current": current_obsession(p), 
            "genres_split": genres_split(p),
            "decade_split": decade_split(p), **compute_insights(p)}