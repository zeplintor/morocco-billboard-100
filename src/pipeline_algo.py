"""
Agent 2 — ALGO-ENGINE
Applies the weighted MinMax scoring formula, tracks rank evolution,
and writes the final billboard_current.json consumed by the frontend.

Sources: Deezer (fans, albums) + YouTube (views)
Weights: YouTube 40% | Deezer fans 35% | Viralité proxy 25%
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

# Weights (must sum to 1.0)
W_YOUTUBE = 0.40       # dominant in Morocco
W_DEEZER_FANS = 0.35   # loyal fanbase size
W_VIRAL = 0.25         # fans × (views / fans ratio) — rewards recent explosive growth


def _minmax_normalize(values: list) -> list:
    lo, hi = min(values), max(values)
    spread = hi - lo
    if spread == 0:
        return [100.0 if hi > 0 else 0.0 for _ in values]
    return [((v - lo) / spread) * 100 for v in values]


def _load_previous_ranks(history_file: Path) -> dict:
    if not history_file.exists():
        return {}
    with history_file.open() as f:
        previous = json.load(f)
    return {entry["name"]: entry["rank"] for entry in previous}


def _evolution_label(current_rank: int, previous_rank) -> str:
    if previous_rank is None:
        return "NEW"
    delta = previous_rank - current_rank
    if delta > 0:
        return f"▲ {delta}"
    if delta < 0:
        return f"▼ {abs(delta)}"
    return "="


def normalize_and_score(raw_data: list) -> list:
    if not raw_data:
        return []

    fans = [a["deezer_fans"] for a in raw_data]
    views = [a["youtube_views"] for a in raw_data]

    # Viralité: views-per-fan ratio rewards artists exploding recently
    # Use sqrt to dampen extreme outliers
    viral_proxy = [
        (a["youtube_views"] / max(a["deezer_fans"], 1)) ** 0.5
        for a in raw_data
    ]

    norm_fans = _minmax_normalize(fans)
    norm_views = _minmax_normalize(views)
    norm_viral = _minmax_normalize(viral_proxy)

    scored = []
    for i, artist in enumerate(raw_data):
        score = (
            norm_views[i] * W_YOUTUBE
            + norm_fans[i] * W_DEEZER_FANS
            + norm_viral[i] * W_VIRAL
        )
        scored.append({
            "name": artist["name"],
            "category": artist["category"],
            "score": round(score, 2),
            "artist_image": artist.get("artist_image", ""),
            "links": {
                "deezer": artist.get("deezer_link", ""),
                "spotify": artist.get("spotify_link", ""),
                "anghami": artist.get("anghami_link", ""),
            },
            "metrics": {
                "deezer_fans": artist["deezer_fans"],
                "youtube_views": artist["youtube_views"],
                "deezer_albums": artist.get("deezer_albums", 0),
            },
        })

    return sorted(scored, key=lambda x: x["score"], reverse=True)


def build_ranked_list(scored: list, previous_ranks: dict) -> list:
    ranked = []
    for rank, artist in enumerate(scored, start=1):
        prev = previous_ranks.get(artist["name"])
        ranked.append({
            **artist,
            "rank": rank,
            "previous_rank": prev,
            "evolution": _evolution_label(rank, prev),
        })
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

    with HISTORY_FILE.open("w") as f:
        json.dump(ranked, f, ensure_ascii=False, indent=2)

    with OUTPUT_FILE.open("w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(
        "Billboard saved → %s (%d artists, week %s)",
        OUTPUT_FILE, len(ranked), output["week"],
    )


if __name__ == "__main__":
    main()
