"""Shared runtime helpers for CLI and GUI: provider selection (demo vs live)."""
from __future__ import annotations

import os

from novel.config import ProjectConfig
from novel.models import Arc
from novel.providers import FakeProvider, ModelProvider

AGENT_NAMES = [
    "strategist", "worldbuilder", "character", "outliner", "writer",
    "continuity", "editor", "scorer", "extractor", "setting_editor",
]


def is_live_mode() -> bool:
    return os.environ.get("NOVEL_LIVE") == "1"


class _DemoSeqProvider(FakeProvider):
    """FakeProvider serving queued arc_detailer responses so each volume in
    demo mode gets its own correctly-sized detail (spec §4.3)."""

    def __init__(self, responses: dict[str, object], arcs: list[Arc], tag_key: str = "agent") -> None:
        super().__init__(responses, tag_key=tag_key)
        self._arcs = list(arcs)

    def _lookup(self, messages: list[dict[str, object]]) -> object:
        from novel.providers import _agent_tag
        if _agent_tag(messages, self.tag_key) == "arc_detailer":
            return self._arcs.pop(0)
        return super()._lookup(messages)


def make_provider(cfg: ProjectConfig) -> ModelProvider:
    if is_live_mode():
        from novel.providers import LiteLLMProvider
        return LiteLLMProvider(language=cfg.language)
    return demo_provider()


def demo_provider() -> ModelProvider:
    from novel.models import (
        ArcPlan,
        ArcSkeleton,
        BookDigest,
        ChapterBeat,
        ChapterOutline,
        Character,
        Concept,
        DimensionScore,
        Outline,
        ReviewScore,
        World,
    )
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
    arc_queue = [
        Arc(arc_name="第一卷", chapters=[
            ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in range(1, 7)]),
        Arc(arc_name="第二卷", chapters=[
            ChapterOutline(chapter_no=900 + i, chapter_title=f"X{i}", beats=[beat])
            for i in range(1, 7)]),
    ]
    return _DemoSeqProvider({
        "strategist": concept, "worldbuilder": World(setting="city of bells"),
        "character": chars, "outliner": outline,
        "arc_planner": ArcPlan(arcs=[ArcSkeleton(arc_name="第一卷", chapter_start=1,
                                                  chapter_end=6, premise="demo"),
                                     ArcSkeleton(arc_name="第二卷", chapter_start=7,
                                                 chapter_end=12, premise="demo2")],
                               planned_total_chapters=12),
        "summarizer": {"chapter_no": 1, "arc_name": "第一卷", "summary": "演示摘要。",
                       "chapter_start": 1, "chapter_end": 6, "major_developments": []},
        "digestor": BookDigest(chapter_count=6, current_arc="第一卷", summary="演示梗概。"),
        "writer": "Ara stepped into the tavern. The thief's work was about to begin.",
        "continuity": "[]", "editor": "Ara stepped into the tavern.",
        "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
              "key_events": [], "threads_advanced": [], "new_information_revealed": []},
    }, arcs=arc_queue, tag_key="agent")
