"""Shared helpers: build small fake profiles with known answers."""
from datetime import datetime, timezone

import pytest

from BackEnd.models import Artist, ListeningProfile, Play, Track


def track(name="Song", artist="Artist A", year=2020, n=0):
    return Track(name=name, artists=[artist], album="Album", year=year, uri=f"spotify:track:{name}{n}")


def play_at_manila_hour(hour: int) -> Play:
    # Manila is UTC+8 (no daylight saving), so Manila hour h == UTC hour (h - 8) % 24
    return Play(track(), datetime(2026, 11, 20, (hour - 8) % 24, 15, tzinfo=timezone.utc))


@pytest.fixture
def make_profile():
    def _make(**kw) -> ListeningProfile:
        return ListeningProfile(source="spotify", display_name="tester", **kw)
    return _make


@pytest.fixture
def sample_profile(make_profile):
    """10 tracks: 6 by 'Old Band' from 1995, 4 by others from 2024; 10 plays at night."""
    tracks = ([track(f"o{i}", "Old Band", 1995, i) for i in range(6)]
              + [track(f"n{i}", f"New {i}", 2024, i) for i in range(4)])
    return make_profile(
        top_tracks_now=tracks[6:], top_tracks_long=tracks,
        top_artists_now=[Artist("New 0", ["k-pop"]), Artist("Old Band", ["opm", "rock"])],
        top_artists_long=[Artist("Old Band", ["opm", "rock"]), Artist("Gone Artist", ["jazz"])],
        recent_plays=[play_at_manila_hour(23) for _ in range(10)],
    )