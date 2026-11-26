"""Layers, habits, sessions, library, playlists + the new Spotify fields. Fake data only: 0 AK, no network."""
from datetime import datetime, timedelta, timezone

from BackEnd import insights
from BackEnd.models import Artist, ListeningProfile, Play, Playlist, Saved, Track
from BackEnd.sources import spotify

NOW = datetime(2026, 11, 26, 4, 0, tzinfo=timezone.utc)          # Thursday, 12:00 noon in Manila


def t(name, artist, explicit=False, ms=200_000, kind="album", n=0, extra_artist=None):
    return Track(name, [artist] + ([extra_artist] if extra_artist else []), "Alb", 2024,
                 f"spotify:track:{name}{n}", "", explicit, ms, kind)


def profile(**kw):
    return ListeningProfile(source=kw.pop("source", "spotify"), display_name="tester", **kw)


# ---------- layers ----------
def test_core_needs_two_sources_and_lately_is_not_identity():
    p = profile(
        top_artists_now=[Artist("Phase Band"), Artist("Core Band")],
        top_artists_long=[Artist("Core Band"), Artist("Old Band")],
        saved=[Saved(t("s", "Core Band"), NOW - timedelta(days=5)),
               Saved(t("o", "Forgotten Band"), NOW - timedelta(days=800))],
        recent_plays=[Play(t("Viral", "Yesterday Artist"), NOW - timedelta(hours=h)) for h in range(4)])
    L = insights.layers(p, NOW)
    assert L["core"][0] == "Core Band"                    # month + year + saved = 3 sources
    assert "Phase Band" in L["phase"] and "Phase Band" not in L["core"]
    assert L["lately"] == ["Yesterday Artist"]            # played 4x in the last plays, but NOT core
    assert L["on_repeat"] == ["Viral - Yesterday Artist"]
    assert L["past_artists"] == ["Forgotten Band"]        # only in saves older than a year


def test_core_falls_back_to_year_when_data_is_thin():
    p = profile(top_artists_long=[Artist("Only Year")])
    assert insights.layers(p, NOW)["core"] == ["Only Year"]


# ---------- habits ----------
def test_habits_from_song_details():
    pool = [t("Ditto (Sped Up)", "A", explicit=True, ms=120_000, kind="single", n=1),
            t("Ditto - Slowed + Reverb", "A", ms=180_000, kind="single", n=2),
            t("Kathang Isip", "Ben&Ben", ms=300_000, n=3, extra_artist="Moira"),
            t("Love Story (Taylor's Version)", "Taylor Swift", ms=240_000, n=4)]
    h = insights.habits(profile(top_tracks_now=pool))
    assert h["tags"]["sped_up"]["pct"] == 25 and h["tags"]["slowed"]["pct"] == 25
    assert "taylors_version" in h["tags"]
    assert h["explicit_pct"] == 25
    assert h["avg_length"] == "3:30"                       # (120+180+300+240)/4 = 210 s
    assert h["singles_pct"] == 50
    assert h["collab_pct"] == 25


def test_habits_unknown_on_youtube():
    yt = [Track("Song", ["A"], uri="yt:1"), Track("Other (Sped Up)", ["B"], uri="yt:2")]
    h = insights.habits(profile(source="youtube", top_tracks_now=yt))
    assert h["explicit_pct"] is None and h["avg_length"] is None
    assert h["tags"]["sped_up"]["pct"] == 50               # names still work on YouTube


# ---------- sessions ----------
def test_sessions_find_the_binge():
    start = datetime(2026, 11, 21, 14, 0, tzinfo=timezone.utc)   # Saturday 10 pm Manila
    binge = [Play(t(f"b{i}", "A", ms=180_000, n=i), start + timedelta(minutes=3 * i), "playlist")
             for i in range(10)]
    single = [Play(t("x", "B"), start - timedelta(days=2), "album")]
    s = insights.sessions(profile(recent_plays=binge + single))
    assert s["longest_songs"] == 10 and s["longest_minutes"] == 30
    assert s["longest_day"] == "Saturday"
    assert s["weekend_pct"] == 91                         # 10 of 11 plays on the weekend (Manila time)
    assert s["context"]["playlist"] == 91


def test_sessions_skip_youtube():
    yt = profile(source="youtube", recent_plays=[Play(Track("x", ["A"]), NOW)])
    assert insights.sessions(yt)["longest_songs"] is None


# ---------- library + playlists ----------
def test_library_timeline():
    saved = [Saved(t("new", "New Act"), NOW - timedelta(days=3)),
             Saved(t("old", "Emo Band"), NOW - timedelta(days=900)),
             Saved(t("old2", "Emo Band", n=2), NOW - timedelta(days=950))]
    lib = insights.library(profile(saved=saved), NOW)
    assert lib["read"] == 3 and lib["days_since_last_save"] == 3
    assert lib["recent_saves_artists"] == ["New Act"] and lib["old_saves_artists"] == ["Emo Band"]
    assert lib["oldest_read_year"] == 2024


def test_playlists_summary():
    pls = [Playlist("sad hours pt. 7", total=120, tracks=[t("a", "Phoebe Bridgers")]),
           Playlist("gym", total=0), Playlist("Today's Top Hits", owned=False, total=50)]
    s = insights.playlists(profile(playlists=pls))
    assert s["own"] == 2 and s["followed"] == 1 and s["empty"] == 1
    assert s["names"] == ["sad hours pt. 7", "gym"]
    assert s["biggest"] == {"name": "sad hours pt. 7", "songs": 120}
    assert s["top_artists_inside"] == ["Phoebe Bridgers"]


def test_empty_profile_never_crashes():
    out = insights.compute_insights(profile(), NOW)
    assert out["library"] == {"read": 0} and out["playlists"] == {"count": 0}


# ---------- Spotify source: new fields, saved songs, playlists ----------
def sp_track(name, explicit=True):
    return {"name": name, "uri": f"spotify:track:{name}", "explicit": explicit, "duration_ms": 123_000,
            "album": {"name": "Alb", "release_date": "2019", "album_type": "single", "images": []}}


class FakeSpotify:
    def current_user(self):
        return {"display_name": "Charles", "id": "me1"}

    def current_user_top_tracks(self, limit, time_range):
        return {"items": [sp_track("A")]}

    def current_user_top_artists(self, limit, time_range):
        return {"items": [{"name": "Ben&Ben", "genres": ["opm"]}]}

    def current_user_recently_played(self, limit):
        return {"items": [{"track": sp_track("A"), "played_at": "2026-11-20T15:30:00Z",
                           "context": {"type": "playlist"}}]}

    def current_user_saved_tracks(self, limit, offset):
        return {"items": [{"track": sp_track("S"), "added_at": "2023-05-01T10:00:00Z"}]}

    def current_user_playlists(self, limit):
        return {"items": [
            {"id": "p1", "name": "kanta sa jeep", "owner": {"id": "me1"}, "items": {"total": 2}},
            {"id": "p2", "name": "Top Hits", "owner": {"id": "spotify"}, "tracks": {"total": 50}}]}

    def _get(self, path, **kw):
        assert path == "playlists/p1/items"                 # never the removed /tracks endpoint
        return {"items": [{"item": sp_track("P")}]}


def test_fetch_profile_reads_new_fields_saved_and_playlists():
    p = spotify.fetch_profile(FakeSpotify())
    tr = p.top_tracks_now[0]
    assert (tr.explicit, tr.duration_ms, tr.album_type) == (True, 123_000, "single")
    assert p.recent_plays[0].context == "playlist"
    assert p.saved[0].track.name == "S" and p.saved[0].at.year == 2023
    own, followed = p.playlists
    assert own.name == "kanta sa jeep" and own.owned and own.total == 2 and own.tracks[0].name == "P"
    assert not followed.owned and followed.total == 50 and followed.tracks == []   # not read: not theirs
    assert ListeningProfile.from_dict(p.to_dict()) == p                             # saves/loads


class OldLoginSpotify(FakeSpotify):
    """A login from before the new scopes: library/playlist calls fail with 403."""
    def current_user_saved_tracks(self, limit, offset):
        raise RuntimeError("403 Insufficient client scope")

    def current_user_playlists(self, limit):
        raise RuntimeError("403 Insufficient client scope")


def test_missing_new_scopes_still_gives_a_profile():
    p = spotify.fetch_profile(OldLoginSpotify())
    assert p.top_tracks_now and p.saved == [] and p.playlists == []


def test_old_saved_fixture_still_loads():
    old = {"source": "spotify", "display_name": "x",
           "top_tracks_now": [{"name": "a", "artists": ["b"], "album": "", "year": 2020, "uri": "u", "image": ""}],
           "recent_plays": [{"track": {"name": "a", "artists": ["b"]}, "at": "2026-11-20T15:30:00+00:00"}]}
    p = ListeningProfile.from_dict(old)
    assert p.top_tracks_now[0].explicit is None and p.recent_plays[0].context == "" and p.saved == []


def test_taste_tracks_follow_the_roast_not_just_recent_plays():
    from BackEnd.insights import taste_tracks
    from BackEnd.models import Artist, ListeningProfile, Track
    song = lambda n, a: Track(name=n, artists=[a], album="", year=None, uri=f"spotify:track:{n}", image="")
    p = ListeningProfile(source="spotify", display_name="x",
                         top_artists_now=[Artist("Slowdive"), Artist("Brainrot")],
                         top_artists_long=[Artist("my bloody valentine"), Artist("Slowdive")],
                         top_tracks_now=[song(f"rot{i}", "Brainrot") for i in range(8)] + [song("sd1", "Slowdive")],
                         top_tracks_long=[song("sd2", "Slowdive"), song("mbv1", "my bloody valentine")])
    names = [t.name for t in taste_tracks(p, 4)]
    assert names[0] == "sd1" and "mbv1" in names      # CORE first, older favourite not crowded out
    assert len(taste_tracks(p, 10)) == 10              # topped up from the rest