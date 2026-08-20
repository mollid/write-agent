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
                                             Mannerism(text="sighs", used_count=0),
                                             Mannerism(text="tugs her braid", used_count=0),
                                             Mannerism(text="counts coins", used_count=1)]))
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet", emotional_turn="doubt", characters=["c1"])
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[ChapterOutline(chapter_no=1, chapter_title="One", beats=[beat])])])
    b.set_outline(outline)
    vm = VectorMemory(proj, embed=hash_embed); vm.add_summary("chapter", "ch0", "prior tavern scene")
    return proj, b, vm, beat

def test_assemble_includes_beat_character_and_low_freq_mannerism(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=4000)
    assert "meet" in ctx.text                       # the beat event
    assert "Ara" in ctx.text                        # appearing character
    assert "sighs" in ctx.text and "bites nail" not in ctx.text  # low-freq mannerism preferred

def test_assemble_respects_token_budget_and_records_drops(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=20)
    assert ctx.tokens <= 20 or ctx.dropped  # either fits or something dropped
    assert estimate_tokens("x" * 300) == 75

def test_assemble_includes_events_and_threads(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    b.append_event(Event(id="e1", chapter=1, summary="the bell rings"))
    b.add_foreshadow(Foreshadow(id="plant-the bell rings", description="the bell rings", planted_ch=1))
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=4000)
    assert "the bell rings" in ctx.text   # event json + thread line
    assert "planted ch1" in ctx.text      # thread line for the OPEN foreshadow


def test_assemble_includes_previous_chapter_ending(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    (proj.root / "chapters").mkdir(exist_ok=True)
    (proj.root / "chapters" / "001.md").write_text("开头。" + "正文。" * 500 + "钟声在夜色里消散。", encoding="utf-8")
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=4000, chapter_no=2)
    assert "Previous chapter ending" in ctx.text
    assert "钟声在夜色里消散" in ctx.text        # the tail survives
    assert "开头。" not in ctx.text              # only the ending, not the whole chapter
    # without chapter_no (or no prior file) the block is absent
    assert "Previous chapter ending" not in assemble_context(
        beats=[beat], bible=b, vector=vm, proj=proj, token_budget=4000).text
    assert "Previous chapter ending" not in assemble_context(
        beats=[beat], bible=b, vector=vm, proj=proj, token_budget=4000, chapter_no=1).text


def test_assemble_includes_style_directives_and_weak_spots(tmp_path):
    from novel.store.notes import WritingNotes
    proj, b, vm, beat = _seed(tmp_path)
    notes = WritingNotes(proj)
    notes.add_feedback("setup:world", "基调更黑暗")
    notes.add_weak(1, {"prose": (76, "对白过多")})
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=4000)
    assert "Style directives" in ctx.text and "基调更黑暗" in ctx.text
    assert "setup:world" in ctx.text              # source label travels with the directive
    assert "Known weak spots" in ctx.text and "对白过多" in ctx.text


def test_new_memory_blocks_yield_to_core_blocks_under_tight_budget(tmp_path):
    from novel.store.notes import WritingNotes
    proj, b, vm, beat = _seed(tmp_path)
    WritingNotes(proj).add_feedback("setup:world", "基调更黑暗")
    # beat/world/characters always outrank the memory blocks; shrink the budget
    # until the memory blocks are the ones dropped
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=300)
    if "Style directives" not in ctx.text:
        assert "style_notes" in ctx.dropped


def test_hierarchy_blocks_rank_above_world_and_characters(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    from novel.models import ChapterSummary
    from novel.store.summaries import SummaryStore
    SummaryStore(proj).put_chapter_summary(ChapterSummary(chapter_no=1, summary="上一章摘要"))
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=20000,
                           chapter_no=2, arc_summary="本卷至今主线",
                           recent_summaries=["ch1: 上一章摘要"],
                           book_digest="全书梗概", target_note="[Target length] 目标约 2500 字")
    assert "本卷至今主线" in ctx.text and "全书梗概" in ctx.text and "上一章摘要" in ctx.text
    assert "Target length" in ctx.text
    # hierarchy blocks rank ABOVE world/characters: they appear earlier in the text
    assert ctx.text.index("本卷至今主线") < ctx.text.index("[World]")


def test_overflow_truncates_instead_of_dropping(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=1200,
                           chapter_no=1, arc_summary="卷摘" * 400, book_digest="梗概" * 400)
    # beat (core) still intact; some low block got truncated, not silently dropped
    assert "meet" in ctx.text
    assert ctx.truncated  # at least one block was cut with a marker
    assert "(truncated)" in ctx.text


def test_threads_capped_at_ten_with_beat_mention_priority(tmp_path):
    proj, b, vm, beat = _seed(tmp_path)
    for i in range(15):
        b.add_foreshadow(Foreshadow(id=f"fs-{i}", description=f"伏笔{i}", planted_ch=i + 1))
    b.add_foreshadow(Foreshadow(id="fs-KEY", description="meet", planted_ch=99))
    ctx = assemble_context(beats=[beat], bible=b, vector=vm, proj=proj, token_budget=20000)
    threads_section = ctx.text.split("[Threads]")[1]
    assert "伏笔14" not in threads_section            # capped at 10
    assert "meet (planted ch99)" in threads_section   # beat-mentioned first
    assert "more open threads omitted" in threads_section


def test_continuity_compact_view_contains_hierarchy_not_world(tmp_path):
    from novel.memory.assembler import continuity_compact_view
    _, b, _, beat = _seed(tmp_path)
    view = continuity_compact_view(beats=[beat], bible=b, arc_summary="本卷至今主线",
                                   recent_summaries=["ch1: 上一章摘要"], book_digest="全书梗概")
    assert "本卷至今主线" in view and "Ara" in view and "[World]" not in view


def test_estimate_tokens_cjk_aware():
    # pure ASCII: 4 chars per token
    assert estimate_tokens("x" * 300) == 75
    # pure CJK: 1.5 tokens per char (conservative)
    assert estimate_tokens("钟" * 100) == 150
    # mixed: ascii part + cjk part computed independently, min 1
    assert estimate_tokens("abcd" + "钟" * 10) == 1 + 15
    assert estimate_tokens("") == 1
