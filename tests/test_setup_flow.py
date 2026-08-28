"""Guided setup flow: stage generation, feedback threading, persistence."""
from __future__ import annotations

from novel.config import ModelConfig
from novel.project import NovelProject
from novel.providers import FakeProvider
from novel.runtime import AGENT_NAMES, demo_provider
from novel.setup_flow import SETUP_STAGES, approve_stage, generate_stage, stage_done
from novel.store.bible import StoryBible


def _proj_bible(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    return proj, StoryBible(proj)


def _cfg_map() -> dict[str, ModelConfig]:
    return {name: ModelConfig("zhipu", "x") for name in AGENT_NAMES}


class _RecordingProvider:
    """FakeProvider wrapper that records the messages sent for each agent."""

    def __init__(self) -> None:
        self._inner: FakeProvider = demo_provider()
        self.messages: list[tuple[str, list[dict]]] = []

    def complete(self, messages, cfg, *, seed=None):  # pragma: no cover
        self.messages.append(("raw", messages))
        return self._inner.complete(messages, cfg, seed=seed)

    def complete_structured(self, messages, schema, cfg, *, seed=None):
        agent = str(next(m.get("agent", "?") for m in messages if "agent" in m))
        self.messages.append((agent, messages))
        return self._inner.complete_structured(messages, schema, cfg, seed=seed)


def test_stage_done_progression(tmp_path):
    _proj, bible = _proj_bible(tmp_path)
    assert [stage_done(s, bible) for s in SETUP_STAGES] == [False, False, False, False]
    concept = generate_stage("concept", provider=demo_provider(), cfg_map=_cfg_map(),
                             bible=bible, premise="a thief")
    approve_stage("concept", concept, bible)
    assert stage_done("concept", bible) and not stage_done("world", bible)
    world = generate_stage("world", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("world", world, bible)
    chars = generate_stage("characters", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("characters", chars, bible)
    assert stage_done("characters", bible)
    outline = generate_stage("outline", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("outline", outline, bible)
    assert all(stage_done(s, bible) for s in SETUP_STAGES)
    assert bible.get_outline() is not None and bible.get_concept() is not None
    assert bible.get_world() is not None and bible.all_characters()


def test_feedback_threaded_into_agent_messages(tmp_path):
    _proj, bible = _proj_bible(tmp_path)
    provider = _RecordingProvider()
    generate_stage("concept", provider=provider, cfg_map=_cfg_map(), bible=bible,
                   premise="a thief", feedback=["主角改成女性", "基调更黑暗"])
    (agent, messages), = provider.messages
    assert agent == "strategist"
    assert "主角改成女性" in messages[-1]["content"]
    assert "基调更黑暗" in messages[-1]["content"]


def test_unknown_stage_raises(tmp_path):
    import pytest
    _proj, bible = _proj_bible(tmp_path)
    with pytest.raises(ValueError):
        stage_done("nope", bible)
    with pytest.raises(ValueError):
        generate_stage("nope", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)


def test_generate_outline_two_phase_when_target_chapters_set(tmp_path):
    from novel.config import ModelConfig
    from novel.memory.extractor import ChapterUpdates  # noqa: F401  (fixture symmetry)
    from novel.models import Character, Concept, World
    from novel.project import NovelProject
    from novel.providers import FakeProvider
    from novel.setup_flow import generate_stage
    from novel.store.bible import StoryBible

    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    bible = StoryBible(proj)
    bible.set_concept(Concept(logline="L", genre="g", tone="t", target_length_words=9000, audience="a"))
    bible.set_world(World(setting="city"))
    bible.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist",
                                     backstory="b", motivation="m", arc="a"))
    cfg_map = {n: ModelConfig("zhipu", "x") for n in
               ("strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor")}
    provider = FakeProvider({
        "arc_planner": {"arcs": [
            {"arc_name": "卷一", "chapter_start": 1, "chapter_end": 2, "premise": "p1"},
            {"arc_name": "卷二", "chapter_start": 3, "chapter_end": 4, "premise": "p2"}],
            "planned_total_chapters": 4},
        "arc_detailer": {"arc_name": "卷一", "chapters": [
            {"chapter_no": 1, "chapter_title": "T1",
             "beats": [{"pov": "c1", "setting": "s", "event": "e1",
                        "emotional_turn": "d", "characters": ["c1"]}]},
            {"chapter_no": 2, "chapter_title": "T2",
             "beats": [{"pov": "c1", "setting": "s", "event": "e2",
                        "emotional_turn": "d", "characters": ["c1"]}]}]}})
    outline = generate_stage("outline", provider=provider, cfg_map=cfg_map, bible=bible,
                             target_chapters=4)
    assert [a.arc_name for a in outline.arcs] == ["卷一"]
    assert [s.arc_name for s in outline.arc_plan] == ["卷二"]   # 待明细骨架队列


def _seeded_bible(tmp_path):
    """Scaffold + concept/world/character seeded: ready for the outline stage."""
    from novel.models import Character, Concept, World
    _proj, bible = _proj_bible(tmp_path)
    bible.set_concept(Concept(logline="L", genre="g", tone="t",
                              target_length_words=9000, audience="a"))
    bible.set_world(World(setting="city"))
    bible.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist",
                                     backstory="b", motivation="m", arc="a"))
    return bible


# ---------- longform outline guards (spec §4.3) ----------

def _sparse_mega_outline():
    """The nanwu failure shape: sparse milestone chapters + hallucinated arc_plan."""
    from novel.models import Arc, ChapterBeat, ChapterOutline, Outline

    beat = ChapterBeat(pov="c1", setting="s", event="e", emotional_turn="d", characters=["c1"])
    ch = lambda n: ChapterOutline(chapter_no=n, chapter_title=f"T{n}", beats=[beat])
    return Outline(
        arcs=[
            Arc(arc_name="第一卷", chapters=[ch(n) for n in (1, 2, 3, 4, 5, 120)]),
            Arc(arc_name="第二卷", chapters=[ch(n) for n in (121, 200, 260)]),
        ],
        arc_plan=[
            {"arc_name": "第一卷", "chapter_start": 1, "chapter_end": 120, "premise": "p"},
            {"arc_name": "第二卷", "chapter_start": 121, "chapter_end": 260, "premise": "p"},
        ],
    )


def test_validate_outline_rejects_sparse_numbering():
    import pytest

    from novel.setup_flow import validate_outline
    with pytest.raises(ValueError) as ei:
        validate_outline(_sparse_mega_outline())
    assert "120" in str(ei.value)  # error names the gap so the model can fix it


def test_validate_outline_rejects_arc_plan_overlapping_detailed_arcs():
    import pytest

    from novel.models import Arc
    from novel.setup_flow import validate_outline
    o = _sparse_mega_outline()
    o.arcs = [Arc(arc_name="第一卷", chapters=o.arcs[0].chapters[:1])]  # now consecutive 1..1
    with pytest.raises(ValueError, match="arc_plan"):
        validate_outline(o)


def test_validate_outline_accepts_rolling_two_phase_shape():
    from novel.models import Arc
    from novel.setup_flow import validate_outline
    o = _sparse_mega_outline()
    o.arcs = [Arc(arc_name="第一卷", chapters=o.arcs[0].chapters[:5])]  # 1..5 consecutive
    o.arc_plan = o.arc_plan[1:]  # queue holds only future volumes
    validate_outline(o)  # no raise


def test_approve_stage_rejects_sparse_outline(tmp_path):
    import pytest
    _proj, bible = _proj_bible(tmp_path)
    with pytest.raises(ValueError, match="章节编号"):
        approve_stage("outline", _sparse_mega_outline(), bible)
    assert bible.get_outline() is None  # nothing persisted


def test_one_shot_outline_strips_hallucinated_arc_plan(tmp_path):
    """The one-shot outliner has no business queuing volume skeletons; a model-
    hallucinated arc_plan must be dropped before the artifact reaches the gate."""
    from novel.providers import FakeProvider
    bible = _seeded_bible(tmp_path)
    provider = FakeProvider({"outliner": _sparse_mega_outline()})
    outline = generate_stage("outline", provider=provider, cfg_map=_cfg_map(), bible=bible)
    assert outline.arc_plan == []
    # numbering stays sparse here; generate_stage retries validation (next test),
    # and approve_stage is the hard guard


def test_one_shot_outline_auto_retries_sparse_numbering(tmp_path):
    """Sparse numbering triggers one automatic regeneration carrying the
    validation error as feedback — for all three callers (CLI/GUI/pipeline)."""
    from novel.providers import FakeProvider
    bible = _seeded_bible(tmp_path)
    calls: list[list[dict]] = []

    class _SeqProvider(FakeProvider):
        def __init__(self) -> None:
            super().__init__({})
            self.served = 0

        def complete_structured(self, messages, schema, cfg, *, seed=None):
            from novel.providers import _agent_tag
            tag = _agent_tag(messages, self.tag_key)
            if tag == "outliner":
                calls.append(messages)
                self.served += 1
                return schema.model_validate(
                    _sparse_mega_outline() if self.served == 1 else {
                        "arcs": [{"arc_name": "A", "chapters": [
                            {"chapter_no": i, "chapter_title": f"T{i}",
                             "beats": [{"pov": "c1", "setting": "s", "event": "e",
                                        "emotional_turn": "d", "characters": ["c1"]}]}
                            for i in (1, 2, 3)]}]})
            return super().complete_structured(messages, schema, cfg, seed=seed)

    outline = generate_stage("outline", provider=_SeqProvider(), cfg_map=_cfg_map(), bible=bible)
    assert len(calls) == 2                       # one auto-retry with the error as feedback
    assert "120" in calls[1][-1]["content"]      # validation error fed back to the model
    assert [c.chapter_no for a in outline.arcs for c in a.chapters] == [1, 2, 3]


def test_two_phase_outline_threads_feedback_to_arc_planner(tmp_path):
    """Guided-setup feedback at the outline stage shapes the volume skeleton."""
    from novel.models import Character, Concept, World
    proj = NovelProject.scaffold("n2", genre="g", root=tmp_path / "n2")
    bible = StoryBible(proj)
    bible.set_concept(Concept(logline="L", genre="g", tone="t", target_length_words=9000, audience="a"))
    bible.set_world(World(setting="city"))
    bible.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist",
                                     backstory="b", motivation="m", arc="a"))
    planner_calls: list[list[dict]] = []

    class _CapProvider:
        def complete(self, messages, cfg, *, seed=None):  # pragma: no cover
            raise AssertionError("raw complete unused")

        def complete_structured(self, messages, schema, cfg, *, seed=None):
            from novel.providers import _agent_tag
            tag = _agent_tag(messages, "agent")
            if tag == "arc_planner":
                planner_calls.append(messages)
                return schema.model_validate({
                    "arcs": [{"arc_name": "卷一", "chapter_start": 1, "chapter_end": 3, "premise": "p1"},
                             {"arc_name": "卷二", "chapter_start": 4, "chapter_end": 6, "premise": "p2"}],
                    "planned_total_chapters": 6})
            assert tag == "arc_detailer", f"unexpected agent: {tag}"
            return schema.model_validate({"arc_name": "卷一", "chapters": [
                {"chapter_no": i, "chapter_title": f"T{i}",
                 "beats": [{"pov": "c1", "setting": "s", "event": "e",
                            "emotional_turn": "d", "characters": ["c1"]}]}
                for i in (1, 2, 3)]})

    generate_stage("outline", provider=_CapProvider(), cfg_map=_cfg_map(),
                   bible=bible, target_chapters=6,
                   feedback=["全书五卷，第一卷收在黑市突围"])
    assert planner_calls, "arc planner was never called"
    assert "全书五卷" in planner_calls[0][-1]["content"]


def test_merge_outline_extension_renumbers_and_drops_draft_arc_plan():
    """Manual 追章 merge is defensive: sparse draft numbering is renumbered onto
    the existing tail and hallucinated arc_plan entries never enter the queue."""
    from novel.models import Arc, ChapterBeat, ChapterOutline, Outline
    from novel.setup_flow import merge_outline_extension
    beat = ChapterBeat(pov="c1", setting="s", event="e", emotional_turn="d", characters=["c1"])
    ch = lambda n: ChapterOutline(chapter_no=n, chapter_title=f"T{n}", beats=[beat])
    existing = Outline(arcs=[Arc(arc_name="A", chapters=[ch(1), ch(2)])],
                       arc_plan=[{"arc_name": "卷九", "chapter_start": 7, "chapter_end": 9,
                                  "premise": "queued"}])
    draft = Outline(arcs=[Arc(arc_name="B", chapters=[ch(50), ch(51), ch(99)])],
                    arc_plan=[{"arc_name": "幻影卷", "chapter_start": 900, "chapter_end": 999,
                               "premise": "hallucinated"}])
    merge_outline_extension(existing, draft)
    assert [c.chapter_no for a in existing.arcs for c in a.chapters] == [1, 2, 3, 4, 5]
    assert [s.arc_name for s in existing.arc_plan] == ["卷九"]  # queue untouched
    assert existing.arcs[-1].arc_name == "B"


def test_pipeline_skips_setup_when_outline_exists(tmp_path):
    """One-shot SETUP must not rerun when the bible already has settings (standard mode)."""
    from novel.graph import run_full_pipeline
    from novel.models import Arc, ChapterBeat, ChapterOutline, DimensionScore, Outline, ReviewScore
    from novel.providers import FakeProvider, ModelConfig
    from novel.store.vector import VectorMemory, hash_embed

    proj, bible = _proj_bible(tmp_path)
    concept = generate_stage("concept", provider=demo_provider(), cfg_map=_cfg_map(),
                             bible=bible, premise="a thief")
    approve_stage("concept", concept, bible)
    world = generate_stage("world", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("world", world, bible)
    chars = generate_stage("characters", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("characters", chars, bible)
    outline = generate_stage("outline", provider=demo_provider(), cfg_map=_cfg_map(), bible=bible)
    approve_stage("outline", outline, bible)

    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant",
                       emotional_turn="doubt", characters=["c1"])
    rewritten = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])])
    bible.set_outline(rewritten)  # single-chapter outline for the run
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    # provider has ONLY chapter-loop agents: any setup agent call raises KeyError
    provider = FakeProvider(responses={
        "writer": "Chapter prose that is long enough to be complete.",
        "continuity": "[]", "editor": "Chapter prose that is long enough to be complete.",
        "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": []},
    }, tag_key="agent")
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    proj = NovelProject(root=proj.root)
    state = run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible,
                              vector=VectorMemory(proj, embed=hash_embed),
                              proj=proj, premise="a thief", target_chapters=1, start_chapter=1)
    assert state.error is None
    assert (proj.root / "chapters" / "001.md").exists()
