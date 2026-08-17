"""OutlinerExtendAgent: append-only outline continuation."""
from __future__ import annotations

from novel.agents.outliner import OutlineExtendInput, OutlinerExtendAgent
from novel.models import (
    Arc,
    ChapterBeat,
    ChapterOutline,
    Character,
    Concept,
    Event,
    Foreshadow,
    Outline,
    World,
)
from novel.providers import FakeProvider, ModelConfig

CFG = ModelConfig("zhipu", "x")
BEAT = ChapterBeat(pov="c1", setting="tavern", event="meet", emotional_turn="doubt→resolve",
                   characters=["c1"])


def _base(current_max: int) -> OutlineExtendInput:
    current = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[BEAT])
        for i in range(1, current_max + 1)])])
    return OutlineExtendInput(
        concept=Concept(logline="L", genre="g", tone="t", target_length_words=100, audience="a"),
        world=World(setting="city"),
        characters=[Character(id="c1", slug="ara", name="Ara", role="protagonist",
                              backstory="b", motivation="m", arc="a")],
        current=current,
        recent_events=[Event(id="e1", chapter=1, summary="theft")],
        open_foreshadows=[Foreshadow(id="fs-1", description="the watch", planted_ch=1)],
        n_chapters=3,
    )


def test_prompt_carries_continuation_context() -> None:
    agent = OutlinerExtendAgent(FakeProvider({}, tag_key="agent"), CFG)
    msgs = agent.build_messages(_base(current_max=2))
    text = "\n".join(m["content"] for m in msgs)
    assert "T2" in text                    # existing outline tail visible
    assert "fs-1" in text                  # open foreshadow listed
    assert "theft" in text                 # recent event listed
    assert "3" in text                     # n_chapters in prompt
    assert "chapter_no" in text            # numbering rule stated


def test_run_validates_against_outline_schema() -> None:
    extension = Outline(arcs=[Arc(arc_name="B", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[BEAT])
        for i in (3, 4, 5)])])
    agent = OutlinerExtendAgent(FakeProvider({"outliner": extension}), CFG)
    out = agent.run(_base(current_max=2))
    assert isinstance(out, Outline)
    assert [c.chapter_no for c in out.arcs[0].chapters] == [3, 4, 5]
