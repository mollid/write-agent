"""CastPlannerAgent: per-volume cast seeding for rolling longform outlines."""
from __future__ import annotations

from novel.agents.cast_planner import CastPlanInput, CastPlannerAgent
from novel.models import (
    ArcSkeleton,
    ChapterSummary,
    Character,
    Concept,
    World,
)
from novel.providers import FakeProvider, ModelConfig

CFG = ModelConfig("zhipu", "x")

CHARS = [
    Character(id="c1", slug="ara", name="Ara", role="protagonist",
              backstory="b", motivation="m", arc="a"),
    Character(id="sup-vee", slug="vee", name="Vee", role="support",
              backstory="b", motivation="m", arc="a"),
]

SKELETON = ArcSkeleton(arc_name="卷二 · 荒野远征", chapter_start=19, chapter_end=80,
                       premise="主角深入荒野，遭遇掠夺者军阀")

INPUT = CastPlanInput(
    skeleton=SKELETON,
    concept=Concept(logline="L", genre="g", tone="t", target_length_words=9000, audience="a"),
    world=World(setting="city of bells"),
    characters=CHARS,
    recent_summaries=[ChapterSummary(chapter_no=18, arc_name="卷一", summary="小队逃出地窟")],
)


def test_prompt_carries_skeleton_roster_and_continuity() -> None:
    msgs = CastPlannerAgent(FakeProvider({}, tag_key="agent"), CFG).build_messages(INPUT)
    system = msgs[0]["content"]
    user = msgs[1]["content"]
    assert "protagonist" in system          # forbids replacing the lead
    assert "卷二 · 荒野远征" in user          # skeleton premise/name visible
    assert "c1" in user and "sup-vee" in user  # existing roster ids visible
    assert "小队逃出地窟" in user              # recent continuity visible


def test_run_parses_character_array() -> None:
    proposal = [{
        "id": "ant-mara", "slug": "mara", "name": "Mara", "role": "antagonist",
        "backstory": "a wound and a secret", "motivation": "concrete want", "arc": "s→m→e",
    }]
    agent = CastPlannerAgent(FakeProvider({"cast_planner": proposal}), CFG)
    out = agent.run(INPUT)
    assert [c.id for c in out] == ["ant-mara"]


def test_run_threads_feedback_into_prompt() -> None:
    calls: list[list[dict]] = []

    class _Rec(FakeProvider):
        def complete(self, messages, cfg, *, seed=None):
            calls.append(messages)
            return "[]"

    agent = CastPlannerAgent(_Rec({}), CFG)
    agent.run(INPUT, feedback=["需要一位女性反派，动机与地窟旧怨相关"])
    assert "需要一位女性反派" in calls[0][-1]["content"]
