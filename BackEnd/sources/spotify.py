"""Spotify -> ListeningProfile.

Only uses endpoints that still work for Development Mode apps (Feb 2026 changes):
/me, /me/top/tracks, /me/top/artists, /me/player/recently-played.
Never reads `popularity` (removed from tracks, albums and artists).
Scopes needed: user-top-read user-read-recently-played
"""
from datetime import datetime

from BackEnd.models import Artist, ListeningProfile, Play, Track

NAME_MAX, ARTIST_MAX = 120, 80   # cap untrusted text before it ever reaches a prompt


def _year(release_date: str | None) -> int | None:
    head = (release_date or "")[:4]
    return int(head) if head.isdigit() else None


def _image(images: list[dict] | None, target: int = 300) -> str:
    """Pick the image closest to `target` px wide (Spotify gives 640/300/64)."""
    if not images:
        return ""
    return min(images, key=lambda im: abs((im.get("width") or target) - target))["url"]


def to_track(t: dict | None) -> Track | None:
    """Spotify track object -> Track, or None for local files / podcast episodes."""
    if not t or t.get("is_local") or not str(t.get("uri", "")).startswith("spotify:track:"):
        return None
    album = t.get("album") or {}
    return Track(name=str(t.get("name", ""))[:NAME_MAX],
                 artists=[str(a.get("name", ""))[:ARTIST_MAX] for a in t.get("artists", [])],
                 album=str(album.get("name", ""))[:NAME_MAX],
                 year=_year(album.get("release_date")),
                 uri=t["uri"],
                 image=_image(album.get("images")))


def to_artist(a: dict) -> Artist:
    return Artist(name=str(a.get("name", ""))[:ARTIST_MAX], genres=list(a.get("genres") or []))


def _dedupe(tracks) -> list[Track]:
    seen, out = set(), []
    for t in tracks:
        if t and t.uri not in seen:
            seen.add(t.uri)
            out.append(t)
    return out


def fetch_profile(sp) -> ListeningProfile:
    """6 API calls, ~1-2 s. `sp` is a logged-in spotipy.Spotify client."""
    me = sp.current_user()

    def top_tracks(time_range: str) -> list[Track]:
        items = sp.current_user_top_tracks(limit=50, time_range=time_range)["items"]
        return _dedupe(to_track(t) for t in items)

    def top_artists(time_range: str) -> list[Artist]:
        items = sp.current_user_top_artists(limit=20, time_range=time_range)["items"]
        return [to_artist(a) for a in items]

    plays = []
    for item in sp.current_user_recently_played(limit=50)["items"]:
        track = to_track(item.get("track"))
        if track and item.get("played_at"):
            at = datetime.fromisoformat(item["played_at"].replace("Z", "+00:00"))
            plays.append(Play(track, at))

    return ListeningProfile(
        source="spotify",
        display_name=str(me.get("display_name") or "you")[:40],
        top_tracks_now=top_tracks("short_term"),
        top_tracks_long=top_tracks("long_term"),
        top_artists_now=top_artists("short_term"),
        top_artists_long=top_artists("long_term"),
        recent_plays=plays,
    )