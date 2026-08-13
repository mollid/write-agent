from novel.memory.assembler import assemble_context, estimate_tokens
from novel.models import (
    Arc,
    ChapterBeat,
    ChapterOutline,
    Character,
    CharacterState,
    Concept,
    Mannerism,
    Outline,
    World,
)
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.store.vector import VectorMemory, hash_embed


def _seed(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    b = StoryBible(proj)
    b.set_concept(Concept(logline="L", genre="fantasy", tone="grim", themes=[], target_length_words=10000, audience="a"))
    b.set_world(World(setting="city"))
    b.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist", backstory="b",
                                 motivation="m", arc="a", state=CharacterState(location="tavern"),
                                 mannerisms=[Mannerism(text="bites nail", used_count=5),
                                             Mannerism(text="sighs", used_count=0)]))
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet", emotional_turn="doubt", characters=["c1"])
    outline = Outline(arcs=[Arc(id="a1", title="A", chapters=[ChapterOutline(id="ch1", title="One", beats=[beat])])])
    b.set_outline(outline)
    vm = VectorMemory(proj, embed=hash_embed); vm.add_summary("chapter", "ch0", "prior tavern scene")
    return proj, b, vm, beat

def test_assemble_includes_beat_character_and_low_freq_mannerism(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    ctx = assemble_context(beat=beat, bible=b, vector=vm, proj=proj, token_budget=4000)
    assert "meet" in ctx.text                       # the beat event
    assert "Ara" in ctx.text                        # appearing character
    assert "sighs" in ctx.text and "bites nail" not in ctx.text  # low-freq mannerism preferred

def test_assemble_respects_token_budget_and_records_drops(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    ctx = assemble_context(beat=beat, bible=b, vector=vm, proj=proj, token_budget=20)
    assert ctx.tokens <= 20 or ctx.dropped  # either fits or something dropped
    assert estimate_tokens("x" * 300) == 100
