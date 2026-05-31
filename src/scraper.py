"""
Agent 1 — DATA-COLLECTOR
Sources:
  - Deezer public API (no key) → fans, albums, artist image
  - YouTube Data API v3 → views of last 3 clips
  - Spotify link (via Deezer external_urls) → for UI display only
    Note: Spotify removed popularity/followers from Client Credentials
    responses in 2024. Deezer covers the same data reliably.
  - Anghami: no public API available.
"""

import os
import json
import time
import logging
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
ARTISTS_FILE = DATA_DIR / "initial_artists.json"
RAW_OUTPUT_FILE = DATA_DIR / "raw_metrics.json"

DEEZER_SEARCH_URL = "https://api.deezer.com/search/artist"
DEEZER_ARTIST_URL = "https://api.deezer.com/artist"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


# ─── DEEZER ──────────────────────────────────────────────────────────────────

def get_deezer_data(artist_name: str) -> dict:
    """Deezer public API — zero API key required."""
    try:
        resp = requests.get(
            DEEZER_SEARCH_URL,
            params={"q": artist_name, "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get("data", [])
        if not items:
            log.warning("Deezer: not found — %s", artist_name)
            return _empty_deezer()

        artist_id = items[0]["id"]
        full = requests.get(f"{DEEZER_ARTIST_URL}/{artist_id}", timeout=10).json()
        fans = full.get("nb_fan", 0)
        albums = full.get("nb_album", 0)
        image = full.get("picture_medium", "")
        deezer_link = full.get("link", "")
        log.info("  Deezer: fans=%d, albums=%d", fans, albums)
        return {
            "deezer_fans": fans,
            "deezer_albums": albums,
            "artist_image": image,
            "deezer_link": deezer_link,
        }
    except Exception as exc:
        log.error("Deezer error for %s: %s", artist_name, exc)
        return _empty_deezer()


def _empty_deezer() -> dict:
    return {"deezer_fans": 0, "deezer_albums": 0, "artist_image": "", "deezer_link": ""}


# ─── YOUTUBE ─────────────────────────────────────────────────────────────────

def _youtube_video_ids(api_key: str, artist_name: str, max_results: int = 3) -> list:
    params = {
        "part": "id",
        "q": f"{artist_name} clip officiel",
        "type": "video",
        "maxResults": max_results,
        "key": api_key,
    }
    resp = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=10)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return [item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})]


def _youtube_total_views(api_key: str, video_ids: list) -> int:
    if not video_ids:
        return 0
    params = {
        "part": "statistics",
        "id": ",".join(video_ids),
        "key": api_key,
    }
    resp = requests.get(YOUTUBE_VIDEOS_URL, params=params, timeout=10)
    resp.raise_for_status()
    total = 0
    for item in resp.json().get("items", []):
        total += int(item.get("statistics", {}).get("viewCount", 0))
    return total


def get_youtube_views(artist_name: str) -> dict:
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        log.warning("YOUTUBE_API_KEY not set — defaulting to 0 for %s", artist_name)
        return {"youtube_views": 0}
    try:
        video_ids = _youtube_video_ids(api_key, artist_name)
        views = _youtube_total_views(api_key, video_ids)
        log.info("  YouTube: %d views (%d videos)", views, len(video_ids))
        return {"youtube_views": views}
    except Exception as exc:
        log.error("YouTube error for %s: %s", artist_name, exc)
        return {"youtube_views": 0}


# ─── MAIN ────────────────────────────────────────────────────────────────────

def collect_all(artists: list) -> list:
    raw_data = []
    for artist in artists:
        name = artist["name"]
        log.info("Collecting — %s", name)
        deezer = get_deezer_data(name)
        youtube = get_youtube_views(name)
        # Build Spotify search link for UI display (no data fetched)
        spotify_search_link = (
            f"https://open.spotify.com/search/{requests.utils.quote(name)}"
        )
        anghami_search_link = (
            f"https://play.anghami.com/search/{requests.utils.quote(name)}"
        )
        raw_data.append({
            "name": name,
            "category": artist["category"],
            **deezer,
            **youtube,
            "spotify_link": spotify_search_link,
            "anghami_link": anghami_search_link,
        })
        time.sleep(0.3)
    return raw_data


def main() -> None:
    if not ARTISTS_FILE.exists():
        raise FileNotFoundError(f"Artist list not found: {ARTISTS_FILE}")

    with ARTISTS_FILE.open() as f:
        artists = json.load(f)

    raw_data = collect_all(artists)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with RAW_OUTPUT_FILE.open("w") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)

    found = sum(1 for a in raw_data if a["deezer_fans"] > 0)
    log.info(
        "Raw metrics saved → %s (%d/%d artists found on Deezer)",
        RAW_OUTPUT_FILE, found, len(raw_data),
    )


if __name__ == "__main__":
    main()
