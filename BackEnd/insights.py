"""Deeper analysis on top of stats.py: taste LAYERS, listening HABITS, SESSIONS, LIBRARY, PLAYLISTS.

Layers (most stable -> most fleeting) decide what the roast leads with:
  CORE    who they are: artists found in 2+ sources (4-week top, 1-year top, saved songs, own playlists)
  PHASE   this month: 4-week top artists that aren't core
  LATELY  the last few days: most-played in the last 50 plays (an aside, never their identity)
  PAST    what faded: genres whose share dropped + artists only in saves older than a year
Pure functions: no Streamlit, no network. Anything a source doesn't give comes back as None / [].
"""
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import mean

from BackEnd.models import ListeningProfile, Track

MNL_OFFSET = timedelta(hours=8)          # Manila time (no daylight saving)
SESSION_GAP_MIN = 30                     # a pause longer than this starts a new listening session
OLD_SAVE_DAYS = 365
RECENT_SAVE_DAYS = 90

TAGS = {                                 # song-name patterns (lower-case)
    "sped_up": r"sped[\s-]*up|speed[\s-]*up|nightcore",
    "slowed": r"slowed|\breverb\b",
    "remix": r"remix|\bedit\)|\bedit\b|\bmix\)|\bvip\b",
    "live": r"\blive\b",
    "acoustic": r"acoustic|unplugged",
    "taylors_version": r"taylor'?s version",
}


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def _artists_of(tracks) -> Counter:
    return Counter(t.artists[0] for t in tracks if t.artists)


def _pool(p: ListeningProfile) -> list[Track]:
    """Every distinct song we know they play: top lists + recent plays."""
    seen, out = set(), []
    for t in p.top_tracks_now + p.top_tracks_long + [pl.track for pl in p.recent_plays]:
        key = t.uri or (t.name, tuple(t.artists))
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


# ---------------------------------------------------------------------------
# Layers
# ---------------------------------------------------------------------------
def layers(p: ListeningProfile, now: datetime | None = None, n: int = 5) -> dict:
    now = now or datetime.now(timezone.utc)
    sources = {
        "month": [a.name for a in p.top_artists_now],
        "year": [a.name for a in p.top_artists_long],
        "saved": [a for a, _ in _artists_of(s.track for s in p.saved).most_common(20)],
        "playlists": [a for a, _ in _artists_of(t for pl in p.playlists for t in pl.tracks).most_common(20)],
    }
    seen_in = Counter()
    weight = Counter()
    for name_list in sources.values():
        for i, a in enumerate(name_list):
            seen_in[a] += 1
            weight[a] += max(1, 20 - i)
    core = sorted((a for a, c in seen_in.items() if c >= 2), key=lambda a: (-seen_in[a], -weight[a]))[:n]
    if not core:                                     # thin data: fall back to the year's top artists
        core = sources["year"][:n] or sources["month"][:n]

    phase = [a for a in sources["month"] if a not in core][:n]

    recent = Counter(pl.track.artists[0] for pl in p.recent_plays if pl.track.artists)
    lately = [a for a, c in recent.most_common() if a not in core and c >= 2][:n]
    repeats = Counter((pl.track.name, ", ".join(pl.track.artists[:2])) for pl in p.recent_plays)
    on_repeat = [f"{t} - {a}" for (t, a), c in repeats.most_common(5) if c >= 3]

    old_cut = now - timedelta(days=OLD_SAVE_DAYS)
    old_saves = _artists_of(s.track for s in p.saved if s.at < old_cut)
    current_names = set(sources["month"]) | set(sources["year"]) | set(core)
    past_artists = [a for a, _ in old_saves.most_common() if a not in current_names][:n]

    return {"core": core, "phase": phase, "lately": lately, "on_repeat": on_repeat,
            "past_artists": past_artists}


# ---------------------------------------------------------------------------
# Wheel / receipt songs: follow the same layers as the roast
# ---------------------------------------------------------------------------
def taste_tracks(p: ListeningProfile, n: int = 10) -> list[Track]:
    """The n songs that best show who they are, so the wheel and receipt match what the roast says.

    One song per CORE artist first, then older favourites and the current PHASE in turns, then
    PAST, then a 2nd song each, then their most-played songs fill whatever is left."""
    pool, seen = [], set()           # most played first, then saved songs, then playlist songs
    for t in (p.top_tracks_now + p.top_tracks_long + [s.track for s in p.saved]
              + [t for pl in p.playlists for t in pl.tracks]):
        key = (t.name.lower(), (t.artists[0].lower() if t.artists else ""))
        if t.uri and key not in seen:
            seen.add(key)
            pool.append(t)

    lay = layers(p)
    year = [a.name for a in p.top_artists_long]
    mixed = [a for pair in zip(year, lay["phase"]) for a in pair]          # older top, current phase, ...
    mixed += year[len(lay["phase"]):] + lay["phase"][len(year):]           # whatever is left over
    artists = list(dict.fromkeys(lay["core"] + mixed + lay["past_artists"]))

    picked, used = [], set()
    for _ in range(2):                         # round 1: 1 song each, round 2: a 2nd song each
        for a in artists:
            if len(picked) >= n:
                break
            t = next((t for t in pool if t.uri not in used and a in t.artists), None)
            if t:
                picked.append(t)
                used.add(t.uri)
    picked += [t for t in pool if t.uri not in used][: n - len(picked)]     # top up
    return picked[:n]


# ---------------------------------------------------------------------------
# Habits (from song details we already download)
# ---------------------------------------------------------------------------
def habits(p: ListeningProfile) -> dict:
    pool = _pool(p)
    names = [t.name.lower() for t in pool]
    tags = {}
    for tag, pattern in TAGS.items():
        hits = [t.name for t in pool if re.search(pattern, t.name.lower())]
        if hits:
            tags[tag] = {"pct": _pct(len(hits), len(names)), "examples": hits[:2]}

    known_explicit = [t.explicit for t in pool if t.explicit is not None]
    lengths = [t.duration_ms for t in pool if t.duration_ms]
    types = [t.album_type for t in pool if t.album_type]

    avg = round(mean(lengths) / 1000) if lengths else None
    return {
        "tags": tags,                                            # e.g. {"sped_up": {"pct": 12, ...}}
        "explicit_pct": _pct(sum(known_explicit), len(known_explicit)),
        "avg_length": f"{avg // 60}:{avg % 60:02d}" if avg else None,
        "singles_pct": _pct(types.count("single"), len(types)),
        "collab_pct": _pct(sum(1 for t in pool if len(t.artists) > 1), len(pool)),
    }


# ---------------------------------------------------------------------------
# Sessions (last 50 plays)
# ---------------------------------------------------------------------------
def sessions(p: ListeningProfile) -> dict:
    plays = sorted(p.recent_plays, key=lambda pl: pl.at)
    if not plays or p.source != "spotify":            # YouTube "plays" are likes, not listening
        return {"longest_songs": None, "longest_minutes": None, "longest_day": None,
                "weekend_pct": None, "context": {}}
    groups, cur = [], [plays[0]]
    for prev, pl in zip(plays, plays[1:]):
        if (pl.at - prev.at) > timedelta(minutes=SESSION_GAP_MIN):
            groups.append(cur)
            cur = []
        cur.append(pl)
    groups.append(cur)
    longest = max(groups, key=len)
    last_len = (longest[-1].track.duration_ms or 180_000) / 60_000
    minutes = round((longest[-1].at - longest[0].at).total_seconds() / 60 + last_len)
    weekend = sum(1 for pl in plays if (pl.at + MNL_OFFSET).weekday() >= 5)
    ctx = Counter(pl.context or "none" for pl in plays)
    return {
        "longest_songs": len(longest),
        "longest_minutes": minutes,
        "longest_day": (longest[0].at + MNL_OFFSET).strftime("%A"),
        "weekend_pct": _pct(weekend, len(plays)),
        "context": {k: _pct(v, len(plays)) for k, v in ctx.most_common()},   # playlist / album / artist / none
    }


# ---------------------------------------------------------------------------
# Library timeline (saved songs / YouTube likes, with save dates)
# ---------------------------------------------------------------------------
def library(p: ListeningProfile, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if not p.saved:
        return {"read": 0}
    by_year = Counter(s.at.year for s in p.saved)
    recent = [s.track for s in p.saved if s.at >= now - timedelta(days=RECENT_SAVE_DAYS)]
    old = [s.track for s in p.saved if s.at < now - timedelta(days=OLD_SAVE_DAYS)]
    newest = max(s.at for s in p.saved)
    return {
        "read": len(p.saved),                                   # newest N saves we read (not the full library)
        "saves_per_year": dict(sorted(by_year.items())),
        "oldest_read_year": min(by_year),
        "days_since_last_save": (now - newest).days,
        "recent_saves_artists": [a for a, _ in _artists_of(recent).most_common(5)],
        "old_saves_artists": [a for a, _ in _artists_of(old).most_common(5)],
    }


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------
def playlists(p: ListeningProfile) -> dict:
    if not p.playlists:
        return {"count": 0}
    own = [pl for pl in p.playlists if pl.owned]
    biggest = max(own or p.playlists, key=lambda pl: pl.total)
    inside = _artists_of(t for pl in p.playlists for t in pl.tracks)
    return {
                "count": len(p.playlists) if len(p.playlists) < 50 else "50+",
        "own": len(own),
        "followed": len(p.playlists) - len(own),
        "collaborative": sum(1 for pl in p.playlists if pl.collaborative),
        "names": [pl.name for pl in own][:15] or [pl.name for pl in p.playlists][:15],
        "biggest": {"name": biggest.name, "songs": biggest.total},
        "empty": sum(1 for pl in own if pl.total == 0),
        "top_artists_inside": [a for a, _ in inside.most_common(5)],
    }


def compute_insights(p: ListeningProfile, now: datetime | None = None) -> dict:
    return {"layers": layers(p, now), "habits": habits(p), "sessions": sessions(p),
            "library": library(p, now), "playlists": playlists(p)}