"""The one data shape every source (Spotify, YouTube) produces and every feature reads."""
from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class Track:
    name: str
    artists: list[str]
    album: str = ""
    year: int | None = None      # first 4 chars of the album release_date
    uri: str = ""                # spotify:track:… (or a YouTube video id later)
    image: str = ""


@dataclass
class Artist:
    name: str
    genres: list[str] = field(default_factory=list)


@dataclass
class Play:
    track: Track
    at: datetime                 # timezone-aware, UTC


@dataclass
class ListeningProfile:
    source: str                  # "spotify" | "youtube"
    display_name: str
    top_tracks_now: list[Track] = field(default_factory=list)    # ~4 weeks
    top_tracks_long: list[Track] = field(default_factory=list)   # ~1 year
    top_artists_now: list[Artist] = field(default_factory=list)
    top_artists_long: list[Artist] = field(default_factory=list)
    recent_plays: list[Play] = field(default_factory=list)       # Spotify: last 50 plays

    # ---- save / load (used by scripts/dump_profile.py and tests) ----
    def to_dict(self) -> dict:
        d = asdict(self)
        for p in d["recent_plays"]:
            p["at"] = p["at"].isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ListeningProfile":
        tracks = lambda xs: [Track(**t) for t in xs]
        artists = lambda xs: [Artist(**a) for a in xs]
        plays = [Play(Track(**p["track"]), datetime.fromisoformat(p["at"]))
                 for p in d.get("recent_plays", [])]
        return cls(source=d["source"], display_name=d["display_name"],
                   top_tracks_now=tracks(d.get("top_tracks_now", [])),
                   top_tracks_long=tracks(d.get("top_tracks_long", [])),
                   top_artists_now=artists(d.get("top_artists_now", [])),
                   top_artists_long=artists(d.get("top_artists_long", [])),
                   recent_plays=plays)

    def is_empty(self) -> bool:
        return not (self.top_tracks_now or self.top_tracks_long or self.recent_plays)