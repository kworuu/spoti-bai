"""fetch_profile() against a fake spotipy client: no network, no login."""
from BackEnd.models import ListeningProfile
from BackEnd.sources.spotify import fetch_profile, to_track


def sp_track(name, uri=None, year="2019-05-01", artist="Artist"):
    return {"name": name, "uri": uri or f"spotify:track:{name}", "is_local": False,
            "artists": [{"name": artist}],
            "album": {"name": "Alb", "release_date": year,
                      "images": [{"url": "big", "width": 640}, {"url": "mid", "width": 300},
                                 {"url": "small", "width": 64}]}}


class FakeSpotify:
    def current_user(self):
        return {"display_name": "Bisakol"}

    def current_user_top_tracks(self, limit, time_range):
        dup = sp_track("A")
        return {"items": [dup, dup, sp_track("B", year="1998"),
                          {"name": "pod", "uri": "spotify:episode:x"}, None]}

    def current_user_top_artists(self, limit, time_range):
        return {"items": [{"name": "Artist", "genres": ["opm"]}, {"name": "No Genre"}]}

    def current_user_recently_played(self, limit):
        return {"items": [{"track": sp_track("A"), "played_at": "2026-11-20T15:30:00.123Z"},
                          {"track": {"is_local": True, "uri": "spotify:local:x"},
                           "played_at": "2026-11-20T15:00:00Z"}]}


def test_fetch_profile_normalizes():
    p = fetch_profile(FakeSpotify())
    assert p.display_name == "Bisakol" and p.source == "spotify"
    assert [t.name for t in p.top_tracks_now] == ["A", "B"]          # deduped, episode/None dropped
    assert p.top_tracks_now[1].year == 1998                           # "1998" only, no month
    assert p.top_tracks_now[0].image == "mid"                         # closest to 300 px
    assert p.top_artists_now[1].genres == []                          # missing genres OK
    assert len(p.recent_plays) == 1                                   # local file dropped
    assert p.recent_plays[0].at.utcoffset().total_seconds() == 0      # timezone-aware UTC


def test_long_titles_are_capped():
    t = to_track(sp_track("x" * 500))
    assert len(t.name) == 120


def test_profile_json_roundtrip():
    p = fetch_profile(FakeSpotify())
    again = ListeningProfile.from_dict(p.to_dict())
    assert again == p
