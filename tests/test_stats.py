from BackEnd import stats
from tests.conftest import play_at_manila_hour, track


def test_night_owl_all_night(make_profile):
    p = make_profile(recent_plays=[play_at_manila_hour(23) for _ in range(10)])
    h = stats.active_hours(p)
    assert h["night_owl"] == 100
    assert h["peak_hour"] == 23
    assert h["counts"][23] == 10 and h["total_plays"] == 10


def test_night_owl_uses_manila_time(make_profile):
    # 2 am Manila = 18:00 UTC the day before; must count as night
    p = make_profile(recent_plays=[play_at_manila_hour(2), play_at_manila_hour(14)])
    assert stats.active_hours(p)["night_owl"] == 50


def test_no_plays_is_safe(make_profile):
    h = stats.active_hours(make_profile())
    assert h == {"counts": [0] * 24, "total_plays": 0, "peak_hour": None, "night_owl": 0}


def test_then_vs_now(sample_profile):
    t = stats.then_vs_now(sample_profile)
    assert t["new_obsessions"] == ["New 0"]
    assert t["dropped"] == ["Gone Artist"]
    assert t["loyal"] == ["Old Band"]
    assert t["shift"] == 67            # 2 of 3 distinct artists aren't in both lists


def test_decades(sample_profile):
    d = stats.decades(sample_profile)
    # now (4×2024) + long (6×1995 + 4×2024) = 14 years
    assert d["distribution"] == {1990: 6, 2020: 8}
    assert d["home"] == 2020 and d["share"] == 57


def test_decades_without_years(make_profile):
    p = make_profile(top_tracks_now=[track(year=None)])
    assert stats.decades(p)["home"] is None


def test_genres(sample_profile):
    g = stats.genres(sample_profile)
    assert g["top"][0] in {"opm", "rock"}       # each appears twice
    assert g["distinct"] == 4


def test_gauges_known_values(sample_profile):
    s = stats.compute_all(sample_profile, this_year=2026)
    g = s["gauges"]
    assert g["Night Owl"] == 100
    assert g["Loyalty"] == 80          # top 3 lead artists = Old Band(6) + 2 singles → 8/10
    assert g["Time Travel"] == 60      # 6 of 10 long-term tracks are 1995
    assert g["Genre Range"] == 16      # 4 / 25
    assert g["Era Shift"] == 67
    assert all(0 <= v <= 100 for v in g.values())


def test_empty_profile_never_crashes(make_profile):
    s = stats.compute_all(make_profile(), this_year=2026)
    assert s["gauges"]["Genre Range"] is None        # no genres = unknown, not zero
    assert all(v == 0 for k, v in s["gauges"].items() if k != "Genre Range")
    assert s["top"] == {"artists": [], "tracks": []}



# ---------- "current obsession": used to love one genre, now into another ----------
def make_shifted_listener(make_profile):
    """All year: 10 rock artists. Last 4 weeks: K-pop. Last 50 plays: one K-pop song 6x, one rock song 2x."""
    from BackEnd.models import Artist, Play
    rock = [Artist(f"Rock {i}", ["rock", "alt rock"]) for i in range(10)]
    kpop = [Artist("NewJeans", ["k-pop"]), Artist("IVE", ["k-pop"]), Artist("Rock 0", ["rock", "alt rock"])]
    plays = ([Play(track("Ditto", "NewJeans", 2022), play_at_manila_hour(21).at) for _ in range(6)]
             + [Play(track("Rock song", "Rock 3", 2005), play_at_manila_hour(9).at) for _ in range(2)])
    return make_profile(top_artists_now=kpop, top_artists_long=rock,
                        top_tracks_now=[track("Ditto", "NewJeans", 2022)],
                        top_tracks_long=[track(f"r{i}", f"Rock {i}", 2005, i) for i in range(10)],
                        recent_plays=plays)


def test_current_obsession_beats_old_favourites(make_profile):
    p = make_shifted_listener(make_profile)
    cur = stats.current_obsession(p)
    assert cur["artists"][0] == "NewJeans"                 # #1 now AND 6 recent plays
    assert "Ditto - NewJeans" in cur["on_repeat"]          # 6 plays in the last 50 = on repeat
    assert "Rock song - Rock 3" not in cur["on_repeat"]    # only 2 plays


def test_genres_split_keeps_old_genre_out_of_now(make_profile):
    p = make_shifted_listener(make_profile)
    g = stats.genres_split(p)
    assert g["now"][0] == "k-pop"                          # combined counting would put rock first
    assert "rock" in g["then"] and "k-pop" not in g["then"]


def test_decade_split(make_profile):
    p = make_shifted_listener(make_profile)
    assert stats.decade_split(p) == {"now": 2020, "then": 2000}


def test_prompt_puts_current_in_now_and_old_in_past(make_profile):
    from BackEnd import prompts
    p = make_shifted_listener(make_profile)
    data = prompts.data_block(p, stats.compute_all(p, this_year=2026))
    assert data["NOW"]["obsession"][0] == "NewJeans"
    assert data["NOW"]["genres"][0] == "k-pop"
    assert "rock" in data["PAST"]["genres"]