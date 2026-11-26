"""The one data shape every source (Spotify, YouTube) produces and every feature reads.

Fields a source can't provide stay at their defaults (None / "" / []), and every stat treats
that as "unknown" instead of zero. Old saved profiles (tests/fixtures/*.json) still load.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Track:
    name: str
    artists: list[str]
    album: str = ""
    year: int | None = None          # first 4 chars of the album release_date
    uri: str = ""                    # spotify:track:… or yt:<videoId>
    image: str = ""
    # extra Spotify fields (unknown on YouTube)
    explicit: bool | None = None
    duration_ms: int | None = None
    album_type: str = ""             # "single" | "album" | "compilation"
    isrc: str = ""                   # first 2 letters = country where the recording was registered


@dataclass
class Artist:
    name: str
    genres: list[str] = field(default_factory=list)


@dataclass
class Play:
    track: Track
    at: datetime                     # timezone-aware, UTC
    context: str = ""                # what they played it from: "playlist" | "album" | "artist" | "" (none)


@dataclass
class Saved:
    """A song in their library (Spotify saved/liked songs, YouTube likes) and WHEN they saved it."""
    track: Track
    at: datetime


@dataclass
class Playlist:
    name: str
    description: str = ""
    owned: bool = True               # made by them (vs followed)
    collaborative: bool = False
    total: int = 0                   # number of songs
    tracks: list[Track] = field(default_factory=list)   # contents (only read for their own playlists)


@dataclass
class ListeningProfile:
    source: str                      # "spotify" | "youtube"
    display_name: str
    top_tracks_now: list[Track] = field(default_factory=list)    # ~4 weeks
    top_tracks_long: list[Track] = field(default_factory=list)   # ~1 year
    top_artists_now: list[Artist] = field(default_factory=list)
    top_artists_long: list[Artist] = field(default_factory=list)
    recent_plays: list[Play] = field(default_factory=list)       # Spotify: last 50 plays
    saved: list[Saved] = field(default_factory=list)             # library, newest first (years of history)
    playlists: list[Playlist] = field(default_factory=list)

    # ---- save / load (used by scripts/dump_profile.py and tests) ----
    def to_dict(self) -> dict:
        d = asdict(self)
        for p in d["recent_plays"] + d["saved"]:
            p["at"] = p["at"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ListeningProfile":
        tracks = lambda xs: [Track(**t) for t in xs]
        return cls(
            source=d["source"], display_name=d["display_name"],
            top_tracks_now=tracks(d.get("top_tracks_now", [])),
            top_tracks_long=tracks(d.get("top_tracks_long", [])),
            top_artists_now=[Artist(**a) for a in d.get("top_artists_now", [])],
            top_artists_long=[Artist(**a) for a in d.get("top_artists_long", [])],
            recent_plays=[Play(Track(**p["track"]), datetime.fromisoformat(p["at"]), p.get("context", ""))
                          for p in d.get("recent_plays", [])],
            saved=[Saved(Track(**s["track"]), datetime.fromisoformat(s["at"])) for s in d.get("saved", [])],
            playlists=[Playlist(**{**pl, "tracks": tracks(pl.get("tracks", []))})
                       for pl in d.get("playlists", [])],
        )

    def is_empty(self) -> bool:
        return not (self.top_tracks_now or self.top_tracks_long or self.recent_plays or self.saved)