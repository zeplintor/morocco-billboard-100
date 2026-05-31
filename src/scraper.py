"""
Agent 1 — DATA-COLLECTOR
Fetches real streaming metrics from Spotify and YouTube for each artist.
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
    auth = SpotifyClientCredentials(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
    )
    return Spotify(auth_manager=auth)


def get_spotify_data(sp: Spotify, artist_name: str) -> dict:
    """
    Search returns a simplified artist object (no followers).
    We need a second call to sp.artist(id) to get the full object.
    """
    try:
        results = sp.search(q=artist_name, type="artist", limit=1)
        items = results["artists"]["items"]
        if not items:
            log.warning("Spotify: not found — %s", artist_name)
            return {"spotify_followers": 0, "spotify_popularity": 0, "spotify_image": ""}

        artist_id = items[0]["id"]
        # Full artist object includes followers
        full = sp.artist(artist_id)
        return {
            "spotify_followers": full["followers"]["total"],
            "spotify_popularity": full["popularity"],
            "spotify_image": full["images"][0]["url"] if full["images"] else "",
        }
    except Exception as exc:
        log.error("Spotify error for %s: %s", artist_name, exc)
        return {"spotify_followers": 0, "spotify_popularity": 0, "spotify_image": ""}


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
        return {"youtube_views_estimate": 0}
    try:
        video_ids = _youtube_video_ids(api_key, artist_name)
        views = _youtube_total_views(api_key, video_ids)
        log.info("  YouTube: %s → %d views", artist_name, views)
        return {"youtube_views_estimate": views}
    except Exception as exc:
        log.error("YouTube error for %s: %s", artist_name, exc)
        return {"youtube_views_estimate": 0}


def collect_all(artists: list) -> list:
    sp = _spotify_client()
    raw_data = []
    for artist in artists:
        name = artist["name"]
        log.info("Collecting — %s", name)
        spotify_metrics = get_spotify_data(sp, name)
        log.info("  Spotify: followers=%d, popularity=%d",
                 spotify_metrics["spotify_followers"],
                 spotify_metrics["spotify_popularity"])
        youtube_metrics = get_youtube_views(name)
        raw_data.append({
            "name": name,
            "category": artist["category"],
            **spotify_metrics,
            **youtube_metrics,
        })
        time.sleep(0.2)
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

    found = sum(1 for a in raw_data if a["spotify_followers"] > 0)
    log.info("Raw metrics saved → %s (%d/%d artists found on Spotify)",
             RAW_OUTPUT_FILE, found, len(raw_data))


if __name__ == "__main__":
    main()
