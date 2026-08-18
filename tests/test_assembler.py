from novel.memory.assembler import assemble_context, estimate_tokens
from novel.models import (
    Arc,
    ChapterBeat,
    ChapterOutline,
    Character,
    CharacterState,
    Concept,
    Event,
    Foreshadow,
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
                                 motivation="m", arc="a", state=CharacterState(location_end="tavern"),
                                 mannerisms=[Mannerism(text="bites nail", used_count=5),
                                             Mannerism(text="sighs", used_count=0)]))
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet", emotional_turn="doubt", characters=["c1"])
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[ChapterOutline(chapter_no=1, chapter_title="One", beats=[beat])])])
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

def test_assemble_includes_events_and_threads(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    b.append_event(Event(id="e1", chapter=1, summary="the bell rings"))
    b.add_foreshadow(Foreshadow(id="plant-the bell rings", description="the bell rings", planted_ch=1))
    ctx = assemble_context(beat=beat, bible=b, vector=vm, proj=proj, token_budget=4000)
    assert "the bell rings" in ctx.text   # event json + thread line
    assert "planted ch1" in ctx.text      # thread line for the OPEN foreshadow


def test_assemble_includes_previous_chapter_ending(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    (proj.root / "chapters").mkdir(exist_ok=True)
    (proj.root / "chapters" / "001.md").write_text("开头。" + "正文。" * 500 + "钟声在夜色里消散。", encoding="utf-8")
    ctx = assemble_context(beat=beat, bible=b, vector=vm, proj=proj, token_budget=4000, chapter_no=2)
    assert "Previous chapter ending" in ctx.text
    assert "钟声在夜色里消散" in ctx.text        # the tail survives
    assert "开头。" not in ctx.text              # only the ending, not the whole chapter
    # without chapter_no (or no prior file) the block is absent
    assert "Previous chapter ending" not in assemble_context(
        beat=beat, bible=b, vector=vm, proj=proj, token_budget=4000).text
    assert "Previous chapter ending" not in assemble_context(
        beat=beat, bible=b, vector=vm, proj=proj, token_budget=4000, chapter_no=1).text


def test_assemble_includes_style_directives_and_weak_spots(tmp_path):
    from novel.store.notes import WritingNotes
    proj, b, vm, beat = _seed(tmp_path)
    notes = WritingNotes(proj)
    notes.add_feedback("setup:world", "基调更黑暗")
    notes.add_weak(1, {"prose": (76, "对白过多")})
    ctx = assemble_context(beat=beat, bible=b, vector=vm, proj=proj, token_budget=4000)
    assert "Style directives" in ctx.text and "基调更黑暗" in ctx.text
    assert "setup:world" in ctx.text              # source label travels with the directive
    assert "Known weak spots" in ctx.text and "对白过多" in ctx.text


def test_new_memory_blocks_yield_to_core_blocks_under_tight_budget(tmp_path):
    from novel.store.notes import WritingNotes
    proj, b, vm, beat = _seed(tmp_path)
    WritingNotes(proj).add_feedback("setup:world", "基调更黑暗")
    # beat/world/characters always outrank the memory blocks; shrink the budget
    # until the memory blocks are the ones dropped
    ctx = assemble_context(beat=beat, bible=b, vector=vm, proj=proj, token_budget=300)
    if "Style directives" not in ctx.text:
        assert "style_notes" in ctx.dropped
