"""YouTube Music -> ListeningProfile (P7), via the YouTube Data API v3 (read-only).

There is no official YouTube Music API. What we can read is the user's LIKED videos (liking a
song in YouTube Music likes the same video on YouTube). Each like has the time it was liked, so:
    recent_plays  = recent likes (time = when they LIKED it, not when they played it)
    *_now / *_long = likes from the last 30 days vs older likes (as in the proposal)
Only videos YouTube itself puts in the Music category (categoryId "10") count as songs.
YouTube gives no genres and no reliable release year, so those stay empty / None.

Quota: ~1 unit per call, ~10 calls per login (the default daily quota is 10,000 units).
Secrets: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REDIRECT_URI
"""
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from BackEnd.config import get_secret
from BackEnd.insights import layers
from BackEnd.models import Artist, ListeningProfile, Play, Saved, Track
from BackEnd.sources.spotify import ARTIST_MAX, NAME_MAX

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
MUSIC_CATEGORY = "10"
MAX_LIKES = 200                 # newest 200 likes = 4 pages
NOW_DAYS = 30

_SUFFIX = re.compile(r"\s*[\(\[](official|lyric|lyrics|audio|music video|mv|visualizer)[^\)\]]*[\)\]]", re.I)


class YouTubeError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# OAuth (authorization-code flow, read-only, used once at login)
# ---------------------------------------------------------------------------
def redirect_uri() -> str:
    return get_secret("YOUTUBE_REDIRECT_URI", "http://127.0.0.1:8501/youtube_login")


def authorize_url(state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": get_secret("YOUTUBE_CLIENT_ID"),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    })


def exchange_code(code: str, post=requests.post) -> str:
    """Login code from Google -> access token (valid ~1 hour; we only need it during login)."""
    r = post(TOKEN_URL, timeout=15, data={
        "code": code,
        "client_id": get_secret("YOUTUBE_CLIENT_ID"),
        "client_secret": get_secret("YOUTUBE_CLIENT_SECRET"),
        "redirect_uri": redirect_uri(),
        "grant_type": "authorization_code",
    })
    if not r.ok:
        raise YouTubeError(f"Google login failed ({r.status_code}): {r.text[:200]}")
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def _api(get, token: str, path: str, **params) -> dict:
    r = get(f"{API}/{path}", params=params, timeout=15, headers={"Authorization": f"Bearer {token}"})
    if not r.ok:
        raise YouTubeError(f"YouTube API {path} failed ({r.status_code}): {r.text[:200]}")
    return r.json()


def clean_artist(channel_title: str) -> str:
    """'Ben&Ben - Topic' -> 'Ben&Ben', 'TaylorSwiftVEVO' -> 'TaylorSwift'."""
    name = re.sub(r"\s*-\s*Topic$", "", channel_title or "").strip()
    name = re.sub(r"VEVO$", "", name).strip()
    return name[:ARTIST_MAX] or "Unknown"


def clean_title(title: str) -> str:
    return _SUFFIX.sub("", title or "").strip()[:NAME_MAX]


def _thumb(snippet: dict) -> str:
    th = snippet.get("thumbnails") or {}
    for size in ("medium", "high", "default"):
        if th.get(size, {}).get("url"):
            return th[size]["url"]
    return ""


def fetch_profile(token: str, get=requests.get, now: datetime | None = None) -> ListeningProfile:
    """~10 API calls. `get` and `now` can be swapped in tests."""
    now = now or datetime.now(timezone.utc)
    ch = _api(get, token, "channels", part="snippet,contentDetails", mine="true").get("items") or []
    if not ch:
        raise YouTubeError("This Google account has no YouTube channel, so it has no likes to read.")
    name = ch[0]["snippet"].get("title") or "you"
    likes_id = (ch[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("likes")) or "LL"

    # 1) newest likes (playlist items carry the time each video was liked)
    items, page = [], None
    while len(items) < MAX_LIKES:
        data = _api(get, token, "playlistItems", part="snippet", playlistId=likes_id,
                    maxResults=50, **({"pageToken": page} if page else {}))
        items += data.get("items") or []
        page = data.get("nextPageToken")
        if not page:
            break
    items = items[:MAX_LIKES]

    # 2) keep only what YouTube itself categorises as Music
    ids = [i["snippet"]["resourceId"]["videoId"] for i in items
           if i.get("snippet", {}).get("resourceId", {}).get("videoId")]
    music = {}
    for start in range(0, len(ids), 50):
        data = _api(get, token, "videos", part="snippet", id=",".join(ids[start:start + 50]))
        for v in data.get("items") or []:
            if v["snippet"].get("categoryId") == MUSIC_CATEGORY:
                music[v["id"]] = v["snippet"]

    likes = []           # (liked_at, Track), newest first
    seen = set()
    for it in items:
        sn = it["snippet"]
        vid = sn.get("resourceId", {}).get("videoId")
        if vid not in music or vid in seen:
            continue
        seen.add(vid)
        artist = clean_artist(sn.get("videoOwnerChannelTitle") or music[vid].get("channelTitle", ""))
        track = Track(name=clean_title(sn.get("title", "")), artists=[artist], album="",
                      year=None, uri=f"yt:{vid}", image=_thumb(sn) or _thumb(music[vid]))
        liked_at = datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00"))
        likes.append((liked_at, track))
    likes.sort(key=lambda x: x[0], reverse=True)

    cutoff = now - timedelta(days=NOW_DAYS)
    now_tracks = [t for at, t in likes if at >= cutoff][:50]
    long_tracks = [t for at, t in likes if at < cutoff][:50]

    def ranked_artists(tracks):
        return [Artist(name) for name, _ in Counter(t.artists[0] for t in tracks).most_common(20)]

    return ListeningProfile(
        source="youtube",
        display_name=str(name)[:40],
        top_tracks_now=now_tracks,
        top_tracks_long=long_tracks,
        top_artists_now=ranked_artists(now_tracks),
        top_artists_long=ranked_artists(long_tracks),
        recent_plays=[Play(t, at) for at, t in likes[:50]],
        saved=[Saved(t, at) for at, t in likes],
    )


def wheel_songs(profile: ListeningProfile, n: int = 10) -> list[dict]:
    """The wheel's song dicts (same keys as wheel.py's Spotify songs). uri = 'yt:<videoId>'.

    YouTube has no play counts, so "newest likes" would just be whatever you liked last.
    Instead the wheel follows the same taste layers as the chat: one song per CORE artist,
    then older favourites and the current PHASE in turns, then PAST, then a 2nd song each,
    then the rest of the likes."""
    pool = profile.top_tracks_now + profile.top_tracks_long        # newest likes first
    lay = layers(profile)
    year = [a.name for a in profile.top_artists_long]
    mixed = [a for pair in zip(year, lay["phase"]) for a in pair]          # older top, current phase, ...
    mixed += year[len(lay["phase"]):] + lay["phase"][len(year):]           # whatever is left over
    artists = list(dict.fromkeys(lay["core"] + mixed + lay["past_artists"]))

    picked, used = [], set()
    for rnd in range(2):                        # round 1: 1 song each, round 2: a 2nd song each
        for a in artists:
            if len(picked) >= n:
                break
            t = next((t for t in pool if t.uri not in used and a in t.artists), None)
            if t:
                picked.append(t)
                used.add(t.uri)
    picked += [t for t in pool if t.uri not in used][: n - len(picked)]     # top up

    return [{"name": t.name, "artist": ", ".join(t.artists), "uri": t.uri, "image": t.image,
             "album": t.album, "release_date": ""} for t in picked[:n]]