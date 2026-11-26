"""Spotify -> ListeningProfile.

Only uses endpoints that still work for Development Mode apps (Feb 2026 changes):
  /me, /me/top/tracks, /me/top/artists, /me/player/recently-played      (scopes: user-top-read,
  /me/tracks (saved songs)                                                user-read-recently-played,
  /me/playlists, /playlists/{id}/items (only playlists they own/collab)   user-library-read,
                                                                          playlist-read-private,
                                                                          playlist-read-collaborative)
Never reads `popularity` (removed from tracks, albums and artists).
About 17 API calls per login; everything after the first 6 is optional and skipped on error.
"""
from datetime import datetime

from BackEnd.models import Artist, ListeningProfile, Play, Playlist, Saved, Track

SCOPE = ("user-top-read user-read-recently-played user-library-read "
         "playlist-read-private playlist-read-collaborative")
NAME_MAX, ARTIST_MAX = 120, 80   # cap untrusted text before it ever reaches a prompt
SAVED_PAGES = 4                 # 4 x 50 = newest 200 saved songs
PLAYLISTS_READ = 5               # read the contents of their 5 biggest own playlists
PLAYLIST_ITEMS = 100             # first 100 songs of each


def _year(release_date: str | None) -> int | None:
    head = (release_date or "")[:4]
    return int(head) if head.isdigit() else None


def _image(images: list[dict] | None, target: int = 300) -> str:
    """Pick the image closest to `target` px wide (Spotify gives 640/300/64)."""
    if not images:
        return ""
    return min(images, key=lambda im: abs((im.get("width") or target) - target))["url"]


def _time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


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
                 image=_image(album.get("images")),
                 explicit=t.get("explicit"),
                 duration_ms=t.get("duration_ms"),
                 album_type=str(album.get("album_type") or ""))


def to_artist(a: dict) -> Artist:
    return Artist(name=str(a.get("name", ""))[:ARTIST_MAX], genres=list(a.get("genres") or []))


def _dedupe(tracks) -> list[Track]:
    seen, out = set(), []
    for t in tracks:
        if t and t.uri not in seen:
            seen.add(t.uri)
            out.append(t)
    return out


def fetch_saved(sp) -> list[Saved]:
    """Newest saved songs first, each with the date they saved it (up to SAVED_PAGES x 50)."""
    out = []
    for page in range(SAVED_PAGES):
        items = sp.current_user_saved_tracks(limit=50, offset=page * 50).get("items") or []
        for it in items:
            tr = to_track(it.get("track"))
            if tr and it.get("added_at"):
                out.append(Saved(tr, _time(it["added_at"])))
        if len(items) < 50:
            break
    return out


def fetch_playlists(sp, my_id: str) -> list[Playlist]:
    """Their playlists (names!) + the contents of their biggest own ones."""
    raw = sp.current_user_playlists(limit=50).get("items") or []
    lists = []
    for pl in raw:
        if not pl:
            continue
        count = (pl.get("items") or pl.get("tracks") or {}).get("total", 0)   # "tracks" was renamed "items"
        lists.append((pl, Playlist(name=str(pl.get("name", ""))[:NAME_MAX],
                                   description=str(pl.get("description") or "")[:200],
                                   owned=(pl.get("owner") or {}).get("id") == my_id,
                                   collaborative=bool(pl.get("collaborative")),
                                   total=int(count or 0))))
    # contents: only playlists they own or collaborate on (Spotify hides the rest anyway)
    readable = sorted((x for x in lists if x[1].owned or x[1].collaborative), key=lambda x: -x[1].total)
    for raw_pl, pl in readable[:PLAYLISTS_READ]:
        try:
            # spotipy's playlist_items() still calls the removed /tracks endpoint, so call /items directly
            data = sp._get(f"playlists/{raw_pl['id']}/items", limit=PLAYLIST_ITEMS)
            pl.tracks = _dedupe(to_track(it.get("item") or it.get("track")) for it in data.get("items") or [])
        except Exception:
            pass
    return [pl for _, pl in lists]


def fetch_profile(sp) -> ListeningProfile:
    """6 required calls (~1-2 s) + optional library/playlist calls (~2-4 s)."""
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
            ctx = str((item.get("context") or {}).get("type") or "")
            plays.append(Play(track, _time(item["played_at"]), ctx))

    profile = ListeningProfile(
        source="spotify",
        display_name=str(me.get("display_name") or "you")[:40],
        top_tracks_now=top_tracks("short_term"),
        top_tracks_long=top_tracks("long_term"),
        top_artists_now=top_artists("short_term"),
        top_artists_long=top_artists("long_term"),
        recent_plays=plays,
    )
    # Optional extras: an old login without the new scopes (or any hiccup) must not break the roast
    try:
        profile.saved = fetch_saved(sp)
    except Exception:
        pass
    try:
        profile.playlists = fetch_playlists(sp, me.get("id", ""))
    except Exception:
        pass
    return profile