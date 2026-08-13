from novel.config import load_config
from novel.graph import run_full_pipeline
from novel.models import (
    Arc,
    ChapterBeat,
    ChapterOutline,
    Character,
    CharacterState,
    Concept,
    Event,
    ForeshadowStatus,
    Outline,
    ReviewDimension,
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
    outline = Outline(arcs=[Arc(id="a1", title="A", chapters=[
        ChapterOutline(id=f"ch{i}", title=f"T{i}", beats=[beat]) for i in range(1, 4)])])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    passing = ReviewScore(artifact_ref="x", attempt=1,
                          dimensions=[ReviewDimension(name="q", score=90)], passed=True)
    provider = FakeProvider(responses={
        "strategist": concept,
        "worldbuilder": World(setting="city"),
        "character": chars,
        "outliner": outline,
        "writer": "Chapter prose text.",
        "continuity": "[]",
        "editor": "Chapter prose text.",
        "scorer": passing,
        # R2: dict matching _UpdatePayload so complete_structured takes model_validate(dict) cleanly.
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {}, "events": []},
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
    outline = Outline(arcs=[Arc(id="a1", title="A", chapters=[
        ChapterOutline(id="ch1", title="T1", beats=[beat])])])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    return proj, bible, vector, concept, beat, outline, chars


def test_scorer_cap_escalates_no_hard_pass(tmp_path):
    proj, bible, vector, concept, _beat, outline, chars = _one_chapter_setup(tmp_path)
    failing = ReviewScore(artifact_ref="x", attempt=1,
                          dimensions=[ReviewDimension(name="q", score=40)], passed=False)
    provider = FakeProvider(responses={
        "strategist": concept,
        "worldbuilder": World(setting="city"),
        "character": chars,
        "outliner": outline,
        "writer": "Chapter prose text.",
        "continuity": "[]",
        "editor": "Chapter prose text.",
        "scorer": failing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {}, "events": []},
    }, tag_key="agent")
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=1, max_retries=2)
    assert state.error == "chapter 1 rejected after 2 attempts"
    assert not (proj.root / "chapters" / "001.md").exists()


def test_scorer_cap_human_approves(tmp_path):
    proj, bible, vector, concept, _beat, outline, chars = _one_chapter_setup(tmp_path)
    failing = ReviewScore(artifact_ref="x", attempt=1,
                          dimensions=[ReviewDimension(name="q", score=40)], passed=False)
    provider = FakeProvider(responses={
        "strategist": concept,
        "worldbuilder": World(setting="city"),
        "character": chars,
        "outliner": outline,
        "writer": "Chapter prose text.",
        "continuity": "[]",
        "editor": "Chapter prose text.",
        "scorer": failing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {}, "events": []},
    }, tag_key="agent")
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=1, max_retries=2,
                              on_gate=lambda label, artifact: True)
    assert state.error is None
    assert (proj.root / "chapters" / "001.md").exists()


def test_voice_mannerisms_and_events_persist(tmp_path):
    proj, bible, vector, concept, _beat, outline, chars = _one_chapter_setup(tmp_path)
    passing = ReviewScore(artifact_ref="x", attempt=1,
                          dimensions=[ReviewDimension(name="q", score=90)], passed=True)
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
            "character_states": {"c1": CharacterState(location="tavern", emotion="hopeful")},
            "voice_samples": {"c1": "low gravelly drawl"},
            "mannerisms_used": {"c1": "taps the table"},
            "events": [Event(id="e1", chapter=1, summary="the bell rings in the tower")],
        },
    }, tag_key="agent")
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=1)
    assert state.error is None
    c1 = bible.get_character("c1")
    assert c1 is not None
    assert c1.voice_fingerprint.get("sample_1") == "low gravelly drawl"
    assert any(m.text == "taps the table" and m.used_count == 1 for m in c1.mannerisms)
    assert any(e.id == "e1" for e in bible.list_events())
    assert any(f.description == "the bell rings" and f.status == ForeshadowStatus.OPEN
               and f.planted_ch == 1 for f in bible.list_foreshadow())
