from __future__ import annotations

from novel.models import ReviewScore

RUBRICS: dict[str, list[str]] = {
    "concept":    ["originality", "conflict", "genre_fit", "expandability"],
    "world":      ["internal_consistency", "novelty", "concept_fit", "extensibility"],
    "character":  ["motivation", "depth", "world_fit", "uniqueness"],
    "outline":    ["structure", "pacing", "foreshadow_plan", "consistency", "executability"],
    "chapter":    ["beat_adherence", "continuity", "character_voice", "prose", "pacing", "emotion"],
}


def decide(score: ReviewScore, score_min: int) -> bool:
    score.passed = all(d.score >= score_min for d in score.dimensions)
    return score.passed


def apply_review(score: ReviewScore, _existing: str) -> str:
    """Format dimension-level critique feedback to feed back to the producer."""
    low = [d for d in score.dimensions if d.critique]
    return "; ".join(f"{d.name}({d.score}): {d.critique}" for d in low)
