"""Fetch album-cover URLs for the background (Client Credentials flow, no user login needed).

Speed strategy:
  1. In-memory copy       -> instant on every Streamlit rerun / page switch.
  2. .cache/covers.json   -> instant on app restart (covers are public image URLs, not secrets).
  3. Stale cache          -> shown immediately while a background thread refreshes it.
  4. Cold start           -> the search queries run in PARALLEL (~1 round trip, not ~12).

Only the Search endpoint is used (works for Development Mode apps; capped at 10 results/request).
Avoid: browse/new-releases, browse/categories, batch-get, audio-features, recommendations, related-artists.
"""
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import streamlit as st

TOKEN_URL = "https://accounts.spotify.com/api/token"
SEARCH_URL = "https://api.spotify.com/v1/search"
MARKET = "PH"
QUERIES = ["newjeans", "opm", "bisaya", "k-pop", "indie pop", "hip hop", "r&b", "rock",
           "pop", "lofi", "edm", "jazz", "year:2025", "year:2026"]   # 10 albums each, run in parallel
CACHE_FILE = Path(__file__).parent / ".cache" / "covers.json"
FRESH_FOR = 24 * 3600  # seconds before the cached list is refreshed in the background

log = logging.getLogger("spotibai")
_lock = threading.Lock()
_mem: dict = {}          # {"covers": [...], "ts": float, "fail_until": float}
_refreshing = False


def _search(headers: dict, q: str) -> list[dict]:
    try:
        r = requests.get(SEARCH_URL, headers=headers, timeout=8,
                         params={"q": q, "type": "album", "limit": 10, "market": MARKET})
        if not r.ok:  # includes 429 rate limit: just skip this query
            return []
        out = []
        for album in r.json().get("albums", {}).get("items", []):
            imgs = album.get("images") or []  # [0]=640px, [1]=300px, [2]=64px
            if imgs:
                out.append({"m": imgs[1]["url"] if len(imgs) > 1 else imgs[0]["url"],
                            "s": imgs[-1]["url"]})
        return out
    except requests.RequestException:
        return []


def _fetch_remote(client_id: str, client_secret: str, limit: int) -> list[dict]:
    tok = requests.post(TOKEN_URL, data={"grant_type": "client_credentials"},
                        auth=(client_id, client_secret), timeout=8)
    tok.raise_for_status()
    headers = {"Authorization": f"Bearer {tok.json()['access_token']}"}
    with ThreadPoolExecutor(max_workers=len(QUERIES)) as pool:
        results = list(pool.map(lambda q: _search(headers, q), QUERIES))
    seen, covers = set(), []
    for batch in results:
        for c in batch:
            if c["m"] not in seen:
                seen.add(c["m"])
                covers.append(c)
    if not covers:
        raise RuntimeError("Spotify search returned no album images")
    return covers[:limit]


def _read_disk() -> tuple[list[dict] | None, float, int]:
    try:
        d = json.loads(CACHE_FILE.read_text("utf-8"))
        return d["covers"], float(d["ts"]), int(d.get("limit", 0))
    except Exception:
        return None, 0.0, 0


def _write_disk(covers: list[dict], ts: float, limit: int) -> None:
    try:
        CACHE_FILE.parent.mkdir(exist_ok=True)
        CACHE_FILE.write_text(json.dumps({"ts": ts, "limit": limit, "covers": covers}), "utf-8")
    except OSError as e:
        log.warning("Could not write cover cache: %s", e)


def _refresh(cid: str, secret: str, limit: int) -> None:
    global _refreshing
    try:
        covers = _fetch_remote(cid, secret, limit)
        ts = time.time()
        _mem.update(covers=covers, ts=ts, limit=limit)
        _write_disk(covers, ts, limit)
    except Exception as e:
        log.warning("Background cover refresh failed: %s", e)
    finally:
        _refreshing = False


def _credentials() -> tuple[str, str]:
    """Spotify app credentials. Accepts BOTH secrets layouts so covers and wheel.py share one file:
      [spotify] client_id / client_secret      (original layout)
      SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET (flat keys, as wheel.py uses)"""
    sec = st.secrets
    if "spotify" in sec:
        return sec["spotify"]["client_id"], sec["spotify"]["client_secret"]
    return sec["SPOTIFY_CLIENT_ID"], sec["SPOTIFY_CLIENT_SECRET"]


def get_covers(limit: int = 30) -> list[dict]:
    """Returns [{"m": 300px url, "s": 64px url}, ...] or [] on failure (UI shows empty boxes).
    If the cache holds fewer covers than `limit` (you raised the count), it is refetched once."""
    global _refreshing
    now = time.time()
    if now < _mem.get("fail_until", 0):
        return []
    if not _mem.get("covers"):
        covers, ts, lim = _read_disk()
        if covers:
            _mem.update(covers=covers, ts=ts, limit=lim)
    covers, ts, lim = _mem.get("covers"), _mem.get("ts", 0.0), _mem.get("limit", 0)
    big_enough = lim >= limit
    if covers and big_enough and now - ts < FRESH_FOR:
        return covers[:limit]
    try:
        cid, secret = _credentials()
    except Exception as e:
        log.warning("Spotify secrets not available: %s", e)
        return covers[:limit] if covers else []
    if covers and big_enough:  # stale: show what we have now, refresh without blocking the page
        with _lock:
            if not _refreshing:
                _refreshing = True
                threading.Thread(target=_refresh, args=(cid, secret, limit), daemon=True).start()
        return covers[:limit]
    try:  # nothing cached, or the cache is too small for the new count: wait once
        fresh = _fetch_remote(cid, secret, limit)
    except Exception as e:
        log.warning("Could not load album covers: %s", e)
        _mem["fail_until"] = now + 60  # don't retry on every rerun
        return covers[:limit] if covers else []
    ts = time.time()
    _mem.update(covers=fresh, ts=ts, limit=limit)
    _write_disk(fresh, ts, limit)
    return fresh