from novel.config import load_config
from novel.graph import run_full_pipeline
from novel.models import (
    Arc,
    ChapterBeat,
    ChapterOutline,
    Character,
    CharacterState,
    Concept,
    DimensionScore,
    ForeshadowLedgerEntry,
    ForeshadowStatus,
    Outline,
    ReviewScore,
    World,
)
from novel.project import NovelProject
from novel.providers import FakeProvider, ModelConfig
from novel.store.bible import StoryBible
from novel.store.vector import VectorMemory, hash_embed


def test_smoke_three_chapter_micro_novel(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    bible = StoryBible(proj)
    vector = VectorMemory(proj, embed=hash_embed)
    cfg = load_config(proj.config_path)
    assert cfg.thresholds.score_min == 80  # smoke: config parses
    concept = Concept(logline="L", genre="fantasy", tone="grim", themes=["x"],
                      target_length_words=9000, audience="a")
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant",
                       emotional_turn="doubt", characters=["c1"])
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in range(1, 4)])])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = FakeProvider(responses={
        "strategist": concept,
        "worldbuilder": World(setting="city"),
        "character": chars,
        "outliner": outline,
        "writer": "Chapter prose text.",
        "continuity": "[]",
        "editor": "Chapter prose text.",
        "scorer": passing,
        # v2 extractor payload: dict[str,list[str]] mannerisms; key_events list; drop events.
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [],
                      "new_information_revealed": []},
    }, tag_key="agent")
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    state = run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=3)
    assert state is not None
    assert bible.get_concept().genre == "fantasy"
    assert len(bible.all_characters()) == 1
    assert (proj.root / "chapters" / "001.md").exists()
    assert (proj.root / "chapters" / "003.md").exists()


def _cfg_map():
    return {name: ModelConfig("zhipu", "x") for name in
            ["strategist", "worldbuilder", "character", "outliner", "writer",
             "continuity", "editor", "scorer", "extractor"]}


def _one_chapter_setup(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    bible = StoryBible(proj)
    vector = VectorMemory(proj, embed=hash_embed)
    concept = Concept(logline="L", genre="fantasy", tone="grim", themes=["x"],
                      target_length_words=9000, audience="a")
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant",
                       emotional_turn="doubt", characters=["c1"], plants=["the bell rings"])
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    return proj, bible, vector, concept, beat, outline, chars


def test_scorer_cap_escalates_no_hard_pass(tmp_path):
    proj, bible, vector, concept, _beat, outline, chars = _one_chapter_setup(tmp_path)
    failing = ReviewScore(artifact_type="chapter", overall=40,
                          scores={"beat_adherence": DimensionScore(score=40, critique="weak")})
    provider = FakeProvider(responses={
        "strategist": concept,
        "worldbuilder": World(setting="city"),
        "character": chars,
        "outliner": outline,
        "writer": "Chapter prose text.",
        "continuity": "[]",
        "editor": "Chapter prose text.",
        "scorer": failing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [],
                      "new_information_revealed": []},
    }, tag_key="agent")
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=1, max_retries=2)
    assert state.error == "chapter 1 rejected after 2 attempts"
    assert not (proj.root / "chapters" / "001.md").exists()


def test_scorer_cap_human_approves(tmp_path):
    proj, bible, vector, concept, _beat, outline, chars = _one_chapter_setup(tmp_path)
    failing = ReviewScore(artifact_type="chapter", overall=40,
                          scores={"beat_adherence": DimensionScore(score=40, critique="weak")})
    provider = FakeProvider(responses={
        "strategist": concept,
        "worldbuilder": World(setting="city"),
        "character": chars,
        "outliner": outline,
        "writer": "Chapter prose text.",
        "continuity": "[]",
        "editor": "Chapter prose text.",
        "scorer": failing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [],
                      "new_information_revealed": []},
    }, tag_key="agent")
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=1, max_retries=2,
                              on_gate=lambda label, artifact: True)
    assert state.error is None
    assert (proj.root / "chapters" / "001.md").exists()


def test_voice_mannerisms_and_events_persist(tmp_path):
    proj, bible, vector, concept, _beat, outline, chars = _one_chapter_setup(tmp_path)
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = FakeProvider(responses={
        "strategist": concept,
        "worldbuilder": World(setting="city"),
        "character": chars,
        "outliner": outline,
        "writer": "Chapter prose text.",
        "continuity": "[]",
        "editor": "Chapter prose text.",
        "scorer": passing,
        "extractor": {
            "character_states": {"c1": CharacterState(
                emotional_state="hopeful", physical_state="uninjured",
                knowledge_gained=["learned the guild's name"],
                relationships_shifted={}, location_end="tavern")},
            "voice_samples": {"c1": "low gravelly drawl"},
            "mannerisms_used": {"c1": ["taps the table", "cracks knuckles"]},
            "key_events": [{"event": "the bell rings in the tower",
                            "significance": "signals the pivot",
                            "affected_characters": ["c1"]}],
            "threads_advanced": [],
            "new_information_revealed": [],
        },
    }, tag_key="agent")
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=1)
    assert state.error is None
    c1 = bible.get_character("c1")
    assert c1 is not None
    assert c1.voice_fingerprint.get("sample_1") == "low gravelly drawl"
    assert c1.state.emotional_state == "hopeful"
    assert c1.state.location_end == "tavern"
    # mannerisms_used is dict[str, list[str]]: both mannerisms persisted with used_count==1.
    assert {m.text for m in c1.mannerisms} >= {"taps the table", "cracks knuckles"}
    assert all(m.used_count == 1 for m in c1.mannerisms
               if m.text in ("taps the table", "cracks knuckles"))
    # key_events mapped to rich Event model: id=evt_{ch}_{i+1}, chapter, summary, characters.
    events = bible.list_events()
    assert any(e.id == "evt_1_1" for e in events)
    mapped = next(e for e in events if e.id == "evt_1_1")
    assert mapped.chapter == 1
    assert mapped.summary == "the bell rings in the tower"
    assert mapped.characters == ["c1"]
    assert any(f.description == "the bell rings" and f.status == ForeshadowStatus.OPEN
               and f.planted_ch == 1 for f in bible.list_foreshadow())


def test_foreshadow_ledger_registered_on_setup(tmp_path):
    proj, bible, vector, concept, beat, _outline, chars = _one_chapter_setup(tmp_path)
    # rebuild outline carrying an explicit foreshadow_ledger entry
    outline = Outline(
        arcs=[Arc(arc_name="A", chapters=[ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])],
        foreshadow_ledger=[ForeshadowLedgerEntry(
            id="fs-99", planted_in="c03-b02", paid_off_in="c10-b01",
            description="the cracked bell")],
    )
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = FakeProvider(responses={
        "strategist": concept,
        "worldbuilder": World(setting="city"),
        "character": chars,
        "outliner": outline,
        "writer": "Chapter prose text.",
        "continuity": "[]",
        "editor": "Chapter prose text.",
        "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [],
                      "new_information_revealed": []},
    }, tag_key="agent")
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=1)
    assert state.error is None
    # ledger entry registered as an OPEN foreshadow, planted_ch parsed from "c03-b02" -> 3
    fs = [f for f in bible.list_foreshadow() if f.id == "fs-99"]
    assert len(fs) == 1
    assert fs[0].status == ForeshadowStatus.OPEN
    assert fs[0].planted_ch == 3
    assert fs[0].description == "the cracked bell"


class _RecordingWriterProvider(FakeProvider):
    """FakeProvider that records the assembled context handed to the writer."""

    def __init__(self, responses: dict[str, object]) -> None:
        super().__init__(responses, tag_key="agent")
        self.writer_contexts: list[str] = []

    def complete(self, messages: list[dict[str, object]], cfg: ModelConfig,
                 *, seed: int | None = None) -> str:
        if any(m.get("agent") == "writer" for m in messages):
            self.writer_contexts.append(str(messages[-1]["content"]))
        return super().complete(messages, cfg, seed=seed)


def _resume_setup(tmp_path):
    proj, bible, vector, concept, _beat, _outline, chars = _one_chapter_setup(tmp_path)
    # 3-chapter outline with a distinct, identifiable beat per chapter
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(
            chapter_no=i, chapter_title=f"T{i}",
            beats=[ChapterBeat(pov="Ara", setting=f"s{i}", event=f"event-{i}",
                               emotional_turn="doubt", characters=["c1"], plants=[f"seed-{i}"])])
        for i in (1, 2, 3)])])
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = _RecordingWriterProvider(responses={
        "strategist": concept,
        "worldbuilder": World(setting="city"),
        "character": chars,
        "outliner": outline,
        "writer": "Chapter prose text.",
        "continuity": "[]",
        "editor": "Chapter prose text.",
        "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [],
                      "new_information_revealed": []},
    })
    return proj, bible, vector, provider


def test_resume_uses_next_outline_chapter_not_first(tmp_path):
    """Regression: write-chapter after existing chapters must continue the outline.

    Previously the generation loop always started from the FIRST outline chapter
    while numbering files from start_chapter, so `write-chapter 2` with 001.md
    present rewrote chapter 1's beat into 002.md (story restarted from the top).
    """
    proj, bible, vector, provider = _resume_setup(tmp_path)
    # run 1: chapter 1 (fresh project, runs SETUP)
    state1 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="a thief", target_chapters=1)
    assert state1.error is None
    assert "event=event-1" in provider.writer_contexts[0]
    assert state1.written == [1]

    # run 2: chapters 2-3 (resume)
    provider.writer_contexts.clear()
    state2 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="", target_chapters=3, start_chapter=2)
    assert state2.error is None
    assert (proj.root / "chapters" / "002.md").exists()
    assert (proj.root / "chapters" / "003.md").exists()
    # chapter 2 written from outline chapter 2's beat; chapter 3 from chapter 3's
    assert "event=event-2" in provider.writer_contexts[0]
    assert "event=event-3" in provider.writer_contexts[1]
    assert state2.written == [2, 3]
    # plants registered under the correct chapter numbers
    fs2 = next(f for f in bible.list_foreshadow() if f.id == "plant-seed-2")
    fs3 = next(f for f in bible.list_foreshadow() if f.id == "plant-seed-3")
    assert fs2.planted_ch == 2
    assert fs3.planted_ch == 3


def test_resume_beyond_outline_reports_exhaustion(tmp_path):
    proj, bible, vector, provider = _resume_setup(tmp_path)
    state1 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="a thief", target_chapters=3)
    assert state1.error is None
    assert state1.written == [1, 2, 3]
    # outline only has 3 chapters: asking for chapter 4 must not restart beats
    state2 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="", target_chapters=5, start_chapter=4)
    assert state2.error is not None and "exhausted" in state2.error
    assert state2.written == []
    assert not (proj.root / "chapters" / "004.md").exists()
