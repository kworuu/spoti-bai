"""YouTube Music source with a FAKE YouTube API: no network, no Google login, no quota."""
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from BackEnd import prompts
from BackEnd.models import ListeningProfile
from BackEnd.sources import youtube
from BackEnd.stats import compute_all

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def item(vid, title, channel, liked):
    return {"snippet": {"title": title, "videoOwnerChannelTitle": channel, "publishedAt": liked,
                        "resourceId": {"videoId": vid},
                        "thumbnails": {"medium": {"url": f"https://i.ytimg.com/{vid}.jpg"}}}}


class FakeResp:
    def __init__(self, data, ok=True):
        self._d, self.ok, self.status_code, self.text = data, ok, 200 if ok else 403, "err"

    def json(self):
        return self._d


class FakeYouTube:
    """Two pages of likes; v3 is a vlog (category 22) and must be ignored."""
    def __init__(self, no_channel=False):
        self.no_channel, self.calls = no_channel, []

    def __call__(self, url, params, timeout, headers):
        path = url.rsplit("/", 1)[1]
        self.calls.append(path)
        assert headers["Authorization"] == "Bearer tok"
        if path == "channels":
            return FakeResp({"items": [] if self.no_channel else [
                {"snippet": {"title": "Cyan"}, "contentDetails": {"relatedPlaylists": {"likes": "LL"}}}]})
        if path == "playlistItems":
            if params.get("pageToken") is None:
                return FakeResp({"nextPageToken": "p2", "items": [
                    item("v1", "Kathang Isip (Official Music Video)", "Ben&Ben - Topic", "2026-11-20T15:00:00Z"),
                    item("v2", "Anti-Hero", "TaylorSwiftVEVO", "2026-11-10T03:00:00Z"),
                    item("v3", "My day vlog", "Some Vlogger", "2026-11-09T03:00:00Z")]})
            return FakeResp({"items": [
                item("v4", "Maybe The Night", "Ben&Ben - Topic", "2025-01-05T10:00:00Z"),
                item("v1", "Kathang Isip (Official Music Video)", "Ben&Ben - Topic", "2026-11-20T15:00:00Z")]})
        if path == "videos":
            ids = params["id"].split(",")
            return FakeResp({"items": [{"id": i, "snippet": {"categoryId": "22" if i == "v3" else "10",
                                                              "channelTitle": "x"}} for i in ids]})
        raise AssertionError(path)


def test_fetch_profile_maps_likes():
    p = youtube.fetch_profile("tok", get=FakeYouTube(), now=NOW)
    assert p.source == "youtube" and p.display_name == "Cyan"
    assert [t.name for t in p.top_tracks_now] == ["Kathang Isip", "Anti-Hero"]   # suffix cleaned, vlog dropped
    assert [t.name for t in p.top_tracks_long] == ["Maybe The Night"]            # liked > 30 days ago
    assert p.top_tracks_now[0].artists == ["Ben&Ben"]                            # " - Topic" removed
    assert p.top_tracks_now[1].artists == ["TaylorSwift"]                        # "VEVO" removed
    assert p.top_tracks_now[0].uri == "yt:v1" and p.top_tracks_now[0].year is None
    assert len(p.recent_plays) == 3                                              # duplicate v1 once
    assert all(a.genres == [] for a in p.top_artists_now)


def test_profile_works_with_stats_and_json():
    p = youtube.fetch_profile("tok", get=FakeYouTube(), now=NOW)
    s = compute_all(p, this_year=2026)
    assert s["gauges"]["Genre Range"] is None            # no genres on YouTube → unknown, not zero
    assert s["decades"]["home"] is None                   # no release years
    assert ListeningProfile.from_dict(p.to_dict()) == p
    data = prompts.data_block(p, s)
    assert "like songs" in data["note"]


def test_no_channel_is_a_clear_error():
    with pytest.raises(youtube.YouTubeError, match="no YouTube channel"):
        youtube.fetch_profile("tok", get=FakeYouTube(no_channel=True), now=NOW)


def test_wheel_songs_shape():
    p = youtube.fetch_profile("tok", get=FakeYouTube(), now=NOW)
    w = youtube.wheel_songs(p)
    assert w[0]["uri"] == "yt:v1" and w[0]["image"].endswith("v1.jpg")
    assert set(w[0]) == {"name", "artist", "uri", "image", "album", "release_date"}


def test_authorize_url_is_read_only_and_carries_language(monkeypatch):
    monkeypatch.setattr(youtube, "get_secret", lambda k, d=None: {"YOUTUBE_CLIENT_ID": "cid"}.get(k, d))
    q = parse_qs(urlparse(youtube.authorize_url(state="ceb")).query)
    assert q["scope"] == ["https://www.googleapis.com/auth/youtube.readonly"]
    assert q["state"] == ["ceb"] and q["client_id"] == ["cid"]
    assert q["redirect_uri"] == ["http://127.0.0.1:8501/youtube_login"]


def test_picks_link_to_youtube_music():
    from BackEnd.picks import resolve_picks

    class Search:
        def search(self, q, type, limit):
            return {"tracks": {"items": [{"name": "Song", "uri": "spotify:track:1",
                                          "artists": [{"name": "Band"}], "album": {"images": []}}]}}
    out = resolve_picks(Search(), [{"artist": "Band", "track": "Song"}], link="youtube")
    assert out[0]["url"] == "https://music.youtube.com/search?q=Song+Band"