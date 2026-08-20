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
