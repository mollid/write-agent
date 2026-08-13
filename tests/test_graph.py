from novel.config import load_config
from novel.graph import run_full_pipeline
from novel.models import (
    Arc,
    ChapterBeat,
    ChapterOutline,
    Character,
    Concept,
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
