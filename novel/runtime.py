"""Shared runtime helpers for CLI and GUI: provider selection (demo vs live)."""
from __future__ import annotations

import os

from novel.config import ProjectConfig
from novel.providers import ModelProvider

AGENT_NAMES = [
    "strategist", "worldbuilder", "character", "outliner", "writer",
    "continuity", "editor", "scorer", "extractor",
]


def is_live_mode() -> bool:
    return os.environ.get("NOVEL_LIVE") == "1"


def make_provider(cfg: ProjectConfig) -> ModelProvider:
    if is_live_mode():
        from novel.providers import LiteLLMProvider
        return LiteLLMProvider(language=cfg.language)
    return demo_provider()


def demo_provider() -> ModelProvider:
    from novel.models import (
        Arc,
        ChapterBeat,
        ChapterOutline,
        Character,
        Concept,
        DimensionScore,
        Outline,
        ReviewScore,
        World,
    )
    from novel.providers import FakeProvider
    concept = Concept(logline="A thief steals time.", genre="fantasy", tone="grim", themes=["loss"],
                      target_length_words=9000, audience="adult")
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant", emotional_turn="doubt",
                       characters=["c1"])
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in range(1, 7)])],
        foreshadow_ledger=[])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="orphan", motivation="revenge", arc="a")]
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    return FakeProvider(responses={
        "strategist": concept, "worldbuilder": World(setting="city of bells"),
        "character": chars, "outliner": outline,
        "writer": "Ara stepped into the tavern. The thief's work was about to begin.",
        "continuity": "[]", "editor": "Ara stepped into the tavern.",
        "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
              "key_events": [], "threads_advanced": [], "new_information_revealed": []},
    }, tag_key="agent")
