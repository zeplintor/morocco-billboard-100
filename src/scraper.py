"""
Agent 1 — DATA-COLLECTOR
Fetches streaming metrics from Spotify and YouTube for each artist.
"""

import os
import json
import time
import logging
from pathlib import Path

import requests
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
ARTISTS_FILE = DATA_DIR / "initial_artists.json"
RAW_OUTPUT_FILE = DATA_DIR / "raw_metrics.json"

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _spotify_client() -> Spotify:
    client_id = os.environ["SPOTIFY_CLIENT_ID"]
    client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
    auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
    return Spotify(auth_manager=auth)


def get_spotify_data(sp: Spotify, artist_name: str) -> dict:
    try:
        results = sp.search(q=artist_name, type="artist", limit=1)
        items = results["artists"]["items"]
        if not items:
            log.warning("Spotify: artist not found — %s", artist_name)
            return {"spotify_followers": 0, "spotify_popularity": 0}
        artist = items[0]
        return {
            "spotify_followers": artist["followers"]["total"],
            "spotify_popularity": artist["popularity"],
        }
    except Exception as exc:
        log.error("Spotify error for %s: %s", artist_name, exc)
        return {"spotify_followers": 0, "spotify_popularity": 0}


def _youtube_video_ids(api_key: str, artist_name: str, max_results: int = 3) -> list[str]:
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


def _youtube_total_views(api_key: str, video_ids: list[str]) -> int:
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
        stats = item.get("statistics", {})
        total += int(stats.get("viewCount", 0))
    return total


def get_youtube_views(artist_name: str) -> dict:
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        log.warning("YOUTUBE_API_KEY not set — defaulting to 0 for %s", artist_name)
        return {"youtube_views_estimate": 0}
    try:
        video_ids = _youtube_video_ids(api_key, artist_name)
        views = _youtube_total_views(api_key, video_ids)
        return {"youtube_views_estimate": views}
    except Exception as exc:
        log.error("YouTube error for %s: %s", artist_name, exc)
        return {"youtube_views_estimate": 0}


def collect_all(artists: list[dict]) -> list[dict]:
    sp = _spotify_client()
    raw_data = []
    for artist in artists:
        name = artist["name"]
        log.info("Collecting — %s", name)
        spotify_metrics = get_spotify_data(sp, name)
        youtube_metrics = get_youtube_views(name)
        raw_data.append(
            {
                "name": name,
                "category": artist["category"],
                **spotify_metrics,
                **youtube_metrics,
            }
        )
        time.sleep(0.3)  # stay within API rate limits
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

    log.info("Raw metrics saved → %s (%d artists)", RAW_OUTPUT_FILE, len(raw_data))


if __name__ == "__main__":
    main()
