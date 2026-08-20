from novel.agents.outliner import ArcDetailerAgent, ArcDetailInput, ArcPlannerAgent
from novel.models import ArcSkeleton, ChapterSummary, Character, Concept, Foreshadow, World
from novel.providers import FakeProvider, ModelConfig

_C = Concept(logline="L", genre="g", tone="t", target_length_words=100000, audience="a")
_W = World(setting="city")
_R = [Character(id="c1", slug="ara", name="Ara", role="protagonist", backstory="b",
                motivation="m", arc="a")]
_CFG = ModelConfig("zhipu", "x")


def test_arc_planner_builds_messages_with_target_chapters():
    provider = FakeProvider({"arc_planner": {
        "arcs": [{"arc_name": "卷一", "chapter_start": 1, "chapter_end": 40, "premise": "p"}],
        "planned_total_chapters": 120}})
    plan = ArcPlannerAgent(provider, _CFG).run((_C, _W, _R, 120))
    assert plan.planned_total_chapters == 120
    assert plan.arcs[0].arc_name == "卷一"


def test_arc_detailer_input_contains_next_chapter_no_and_summaries():
    provider = FakeProvider({"arc_detailer": {
        "arc_name": "卷二", "chapters": [
            {"chapter_no": 41, "chapter_title": "T41",
             "beats": [{"pov": "c1", "setting": "s", "event": "e",
                        "emotional_turn": "d", "characters": ["c1"]}]}]}})
    arc = ArcDetailerAgent(provider, _CFG).run(ArcDetailInput(
        skeleton=ArcSkeleton(arc_name="卷二", chapter_start=41, chapter_end=80, premise="p2"),
        concept=_C, world=_W, characters=_R, prev_arc=None,
        open_foreshadows=[Foreshadow(id="fs-1", description="the bell", planted_ch=3)],
        recent_summaries=[ChapterSummary(chapter_no=40, summary="卷一收尾")],
        next_chapter_no=41))
    assert arc.arc_name == "卷二" and arc.chapters[0].chapter_no == 41
    # the agent's user message must carry the runtime numbering anchor (spec §4.3)
    msgs = ArcDetailerAgent(FakeProvider({}), _CFG).build_messages(ArcDetailInput(
        skeleton=ArcSkeleton(arc_name="卷二", chapter_start=41, chapter_end=80, premise="p2"),
        concept=_C, world=_W, characters=_R, prev_arc=None,
        open_foreshadows=[], recent_summaries=[], next_chapter_no=55))
    user = str(msgs[-1]["content"])
    assert "55" in user and "卷一收尾" not in user   # next_chapter_no present; summaries injected via input build


def test_arc_detailer_includes_recent_summaries():
    detailer = ArcDetailerAgent(FakeProvider({}), _CFG)
    msgs = detailer.build_messages(ArcDetailInput(
        skeleton=ArcSkeleton(arc_name="卷二", chapter_start=41, chapter_end=80, premise="p2"),
        concept=_C, world=_W, characters=_R, prev_arc=None,
        open_foreshadows=[Foreshadow(id="fs-1", description="the bell", planted_ch=3)],
        recent_summaries=[ChapterSummary(chapter_no=40, summary="卷一收尾")],
        next_chapter_no=41))
    user = str(msgs[-1]["content"])
    assert "卷一收尾" in user and "the bell" in user
