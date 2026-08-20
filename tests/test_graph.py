from novel.config import load_config
from novel.graph import run_full_pipeline
from novel.models import (
    Arc,
    ArcSkeleton,
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
    WeakDim,
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


def test_review_event_explains_failure_with_dimension_scores(tmp_path):
    """The pass rule is EVERY dimension >= score_min (not overall >= score_min),
    so a review with overall 82 can still fail. The review event must carry
    the per-dimension scores and the threshold or the GUI log cannot explain
    why「总分 82 ❌ 未达标」."""
    proj, bible, vector, concept, _beat, outline, chars = _one_chapter_setup(tmp_path)
    mixed = ReviewScore(artifact_type="chapter", overall=82,
                        scores={"prose": DimensionScore(score=76, critique="weak"),
                                "pacing": DimensionScore(score=90, critique="")})
    provider = FakeProvider(responses={
        "strategist": concept,
        "worldbuilder": World(setting="city"),
        "character": chars,
        "outliner": outline,
        "writer": "Chapter prose text.",
        "continuity": "[]",
        "editor": "Chapter prose text.",
        "scorer": mixed,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [],
                      "new_information_revealed": []},
    }, tag_key="agent")
    events: list[dict[str, object]] = []
    run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                      proj=proj, premise="a thief", target_chapters=1, max_retries=1,
                      on_event=events.append)
    reviews = [e for e in events if e.get("type") == "review"]
    assert len(reviews) == 1
    assert reviews[0]["overall"] == 82
    assert reviews[0]["passed"] is False  # prose 76 < 80 despite overall 82
    assert reviews[0]["scores"] == {"prose": 76, "pacing": 90}
    assert reviews[0]["score_min"] == 80


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
    # weak-spot memory: both failed attempts persisted (merged per dimension)
    # so later chapters' writer context can avoid the same mistakes
    from novel.store.notes import WritingNotes
    assert WritingNotes(proj).weak_by_chapter() == {
        1: {"beat_adherence": WeakDim(score=40, critique="weak")}}


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


def _two_chapter_arc_setup(tmp_path):
    proj, bible, vector, concept, _beat, _outline, chars = _one_chapter_setup(tmp_path)
    outline = Outline(arcs=[Arc(arc_name="卷一", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[ChapterBeat(
            pov="Ara", setting="t", event=f"event-{i}", emotional_turn="d",
            characters=["c1"])]) for i in (1, 2)])])
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = _RecordingWriterProvider(responses={
        "strategist": concept, "worldbuilder": World(setting="city"), "character": chars,
        "outliner": outline, "writer": "Chapter prose text.", "continuity": "[]",
        "editor": "Chapter prose text.", "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": [],
                      "chapter_summary": "第二章摘要。"}})
    return proj, bible, vector, provider


def test_chapter_summaries_written_with_sha(tmp_path):
    from novel.store.summaries import SummaryStore
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=2)
    assert state.error is None
    store = SummaryStore(proj)
    cs2 = store.get_chapter_summary(2)
    assert cs2.summary == "第二章摘要。" and cs2.arc_name == "卷一"
    assert cs2.prose_sha256 == __import__("hashlib").sha256(
        b"Chapter prose text.").hexdigest()


def test_writer_receives_all_beats_and_target_note(tmp_path):
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    # give chapter 1 three beats; all must reach the writer context
    provider.responses["outliner"] = Outline(arcs=[Arc(arc_name="卷一", chapters=[
        ChapterOutline(chapter_no=1, chapter_title="T1", beats=[
            ChapterBeat(pov="Ara", setting="t", event=f"multi-{j}", emotional_turn="d",
                        characters=["c1"]) for j in (1, 2, 3)]),
        ChapterOutline(chapter_no=2, chapter_title="T2", beats=[ChapterBeat(
            pov="Ara", setting="t", event="event-2", emotional_turn="d", characters=["c1"])]),
    ])])
    run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                      proj=proj, premise="a thief", target_chapters=1,
                      language="zh", chapter_target_length=3000)
    ctx0 = provider.writer_contexts[0]
    assert "[Beats" in ctx0 and "[Target length] 本章目标约 3000 字" in ctx0
    assert all(f"event=multi-{j}" in ctx0 for j in (1, 2, 3))  # ALL beats, not just beats[0]
    assert "[Arc summary]" not in ctx0   # no arc summary yet (Task 12 adds them)


def test_summary_lazy_backfill(tmp_path):
    from novel.store.summaries import SummaryStore
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    state1 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="a thief", target_chapters=1)
    assert state1.error is None
    SummaryStore(proj)._chapter_path(1).unlink()      # simulate a lost summary
    provider.responses["summarizer"] = {
        "chapter_no": 1, "arc_name": "卷一", "summary": "补生成的第一章摘要。",
        "characters_involved": [], "threads_advanced": []}
    state2 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="", target_chapters=2, start_chapter=2,
                               min_chapter_chars=10)  # canned prose is 19 chars; ch1 has a
    # passed review on disk, so with the default threshold of 50 the backfill's
    # is_chapter_complete guard would (wrongly for this scenario) see it as incomplete
    assert state2.error is None
    assert SummaryStore(proj).get_chapter_summary(1).summary == "补生成的第一章摘要。"


def test_continuity_receives_compact_view_not_canonical(tmp_path):
    captured: list[dict[str, object]] = []

    class _RecordingContinuity(_RecordingWriterProvider):
        def complete(self, messages, cfg, *, seed=None):
            if any(m.get("agent") == "continuity" for m in messages):
                captured.append(messages[-1])
            return super().complete(messages, cfg, seed=seed)

    proj, bible, vector, concept, beat, _o, chars = _one_chapter_setup(tmp_path)
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = _RecordingContinuity({
        "strategist": concept, "worldbuilder": World(setting="city"), "character": chars,
        "outliner": Outline(arcs=[Arc(arc_name="卷一", chapters=[
            ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])]),
        "writer": "Chapter prose text.", "continuity": "[]", "editor": "x",
        "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": []}})
    run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                      proj=proj, premise="a thief", target_chapters=1)
    user = str(captured[0]["content"])
    assert "[Character" in user        # compact view carries the character card
    assert "_canonical" not in user and '"logline"' not in user   # NOT the raw canonical JSON


def test_gate_every_n_skips_intermediate_chapters(tmp_path):
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    gates: list[tuple[str, object]] = []
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=2,
                              gate_every_n=2, on_gate=lambda label, art: gates.append((label, art)) or True)
    assert state.error is None and state.written == [1, 2]
    # only ch2 (2 % 2 == 0); default N=1 fires every chapter. (The one-shot SETUP
    # branch also fires an "outline" gate on a fresh project — not part of the
    # chapter cadence under test, so filter to chapter gates.)
    assert [g[0] for g in gates if g[0] == "chapter"] == ["chapter"]


def test_chapter_events_carry_planned_total(tmp_path):
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    # planned_total routes one-shot SETUP's outline stage through the two-phase
    # path (generate_stage target_chapters), so it needs the arc planner+detailer
    provider.responses["arc_planner"] = {
        "arcs": [{"arc_name": "卷一", "chapter_start": 1, "chapter_end": 2, "premise": "p1"}],
        "planned_total_chapters": 240}
    provider.responses["arc_detailer"] = {"arc_name": "卷一", "chapters": [
        {"chapter_no": 1, "chapter_title": "T1",
         "beats": [{"pov": "Ara", "setting": "t", "event": "event-1", "emotional_turn": "d",
                    "characters": ["c1"]}]}]}
    events: list[dict[str, object]] = []
    run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                      proj=proj, premise="a thief", target_chapters=1, planned_total=240,
                      on_event=events.append)
    start = next(e for e in events if e["type"] == "chapter_start")
    done = next(e for e in events if e["type"] == "chapter_done")
    assert start["planned_total"] == 240 and done["planned_total"] == 240


def test_edited_chapter_hash_warning(tmp_path):
    proj, bible, vector, provider = _two_chapter_arc_setup(tmp_path)
    state1 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="a thief", target_chapters=1)
    assert state1.error is None
    (proj.root / "chapters" / "001.md").write_text("手改后的正文。", encoding="utf-8")
    events: list[dict[str, object]] = []
    state2 = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                               proj=proj, premise="", target_chapters=2, start_chapter=2,
                               on_event=events.append)
    assert state2.error is None
    warn = [e for e in events if e["type"] == "warning" and e["warning"] == "chapter_edited"]
    assert warn and warn[0]["chapter"] == 1


class _ArcSequenceProvider(_RecordingWriterProvider):
    """FakeProvider serving queued arc_detailer responses in call order."""

    def __init__(self, responses, arcs):
        super().__init__(responses)
        self._arcs = list(arcs)

    def _lookup(self, messages):
        from novel.providers import _agent_tag
        if _agent_tag(messages, self.tag_key) == "arc_detailer":
            return self._arcs.pop(0)
        return super()._lookup(messages)


def test_auto_extend_details_next_arc_and_arc_summary(tmp_path):
    from novel.store.summaries import SummaryStore
    proj, bible, vector, concept, _beat, _o, chars = _one_chapter_setup(tmp_path)
    beat = ChapterBeat(pov="Ara", setting="t", event="e", emotional_turn="d", characters=["c1"])
    skeleton_outline = Outline(
        arcs=[Arc(arc_name="卷一", chapters=[
            ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in (1, 2)])],
        arc_plan=[ArcSkeleton(arc_name="卷二", chapter_start=3, chapter_end=4, premise="p2")])
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    arc2 = Arc(arc_name="卷二", chapters=[
        ChapterOutline(chapter_no=99, chapter_title="T3", beats=[beat]),   # wrong numbers on purpose
        ChapterOutline(chapter_no=100, chapter_title="T4", beats=[beat])])
    provider = _ArcSequenceProvider({
        "strategist": concept, "worldbuilder": World(setting="city"), "character": chars,
        "outliner": skeleton_outline, "writer": "Chapter prose text.", "continuity": "[]",
        "editor": "x", "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": [],
                      "chapter_summary": "摘要。"},
        "summarizer": {"arc_name": "卷一", "chapter_start": 1, "chapter_end": 2,
                       "summary": "卷一摘要。", "major_developments": []},
        "digestor": {"chapter_count": 2, "current_arc": "卷一", "summary": "全书梗概。"},
    }, arcs=[arc2])
    state = run_full_pipeline(provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=4, arc_lookahead=2)
    assert state.error is None and state.written == [1, 2, 3, 4]
    outline = bible.get_outline()
    assert [a.arc_name for a in outline.arcs] == ["卷一", "卷二"]
    assert outline.arc_plan == []
    # defensive renumbering: canned 99/100 became 3/4
    assert [c.chapter_no for c in outline.arcs[1].chapters] == [3, 4]
    assert (proj.root / "chapters" / "003.md").exists()
    store = SummaryStore(proj)
    assert store.get_arc_summary("卷一").summary == "卷一摘要。"
    assert store.get_book_digest().summary == "全书梗概。"
