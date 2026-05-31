"""
Agent 2 — ALGO-ENGINE
Applies the weighted MinMax scoring formula, tracks rank evolution,
and writes the final billboard_current.json consumed by the frontend.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_FILE = DATA_DIR / "raw_metrics.json"
HISTORY_FILE = DATA_DIR / "billboard_history.json"
OUTPUT_FILE = DATA_DIR / "billboard_current.json"

# Scoring weights (must sum to 1.0)
W_SPOTIFY_FOLLOWERS = 0.25
W_SPOTIFY_POPULARITY = 0.15
W_YOUTUBE = 0.35
W_VIRAL = 0.25  # derived from popularity delta as TikTok/Reels proxy


def _minmax_normalize(values: list[float]) -> list[float]:
    lo, hi = min(values), max(values)
    spread = hi - lo
    if spread == 0:
        return [100.0 if hi > 0 else 0.0 for _ in values]
    return [((v - lo) / spread) * 100 for v in values]


def _load_previous_ranks(history_file: Path) -> dict[str, int]:
    if not history_file.exists():
        return {}
    with history_file.open() as f:
        previous = json.load(f)
    return {entry["name"]: entry["rank"] for entry in previous}


def _evolution_label(current_rank: int, previous_rank: int | None) -> str:
    if previous_rank is None:
        return "NEW"
    delta = previous_rank - current_rank  # positive = moved up
    if delta > 0:
        return f"▲ {delta}"
    if delta < 0:
        return f"▼ {abs(delta)}"
    return "="


def normalize_and_score(raw_data: list[dict]) -> list[dict]:
    if not raw_data:
        return []

    followers = [a["spotify_followers"] for a in raw_data]
    popularity = [a["spotify_popularity"] for a in raw_data]
    youtube = [a["youtube_views_estimate"] for a in raw_data]

    # Viralité proxy: followers growth approximated by popularity × followers ratio
    # Scaled independently so isolated viral hits don't dominate
    viral_proxy = [
        a["spotify_popularity"] * (a["spotify_followers"] ** 0.5) for a in raw_data
    ]

    norm_followers = _minmax_normalize(followers)
    norm_popularity = _minmax_normalize(popularity)
    norm_youtube = _minmax_normalize(youtube)
    norm_viral = _minmax_normalize(viral_proxy)

    scored = []
    for i, artist in enumerate(raw_data):
        score = (
            norm_followers[i] * W_SPOTIFY_FOLLOWERS
            + norm_popularity[i] * W_SPOTIFY_POPULARITY
            + norm_youtube[i] * W_YOUTUBE
            + norm_viral[i] * W_VIRAL
        )
        scored.append(
            {
                "name": artist["name"],
                "category": artist["category"],
                "score": round(score, 2),
                "metrics": {
                    "spotify_followers": artist["spotify_followers"],
                    "spotify_popularity": artist["spotify_popularity"],
                    "youtube_views": artist["youtube_views_estimate"],
                },
            }
        )

    return sorted(scored, key=lambda x: x["score"], reverse=True)


def build_ranked_list(scored: list[dict], previous_ranks: dict[str, int]) -> list[dict]:
    ranked = []
    for rank, artist in enumerate(scored, start=1):
        prev = previous_ranks.get(artist["name"])
        ranked.append(
            {
                **artist,
                "rank": rank,
                "previous_rank": prev,
                "evolution": _evolution_label(rank, prev),
            }
        )
    return ranked


def main() -> None:
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Raw metrics not found: {RAW_FILE}. Run scraper.py first.")

    with RAW_FILE.open() as f:
        raw_data = json.load(f)

    previous_ranks = _load_previous_ranks(HISTORY_FILE)
    scored = normalize_and_score(raw_data)
    ranked = build_ranked_list(scored, previous_ranks)

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "week": datetime.now(timezone.utc).strftime("%Y-W%V"),
        "artists": ranked,
    }

    # Save current as next week's history reference
    with HISTORY_FILE.open("w") as f:
        json.dump(ranked, f, ensure_ascii=False, indent=2)

    with OUTPUT_FILE.open("w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(
        "Billboard saved → %s (%d artists, week %s)",
        OUTPUT_FILE,
        len(ranked),
        output["week"],
    )


if __name__ == "__main__":
    main()
