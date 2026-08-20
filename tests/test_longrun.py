"""Spec §6 acceptance (1): a 200-chapter micro-novel must run end-to-end on
FakeProvider with bounded memory, rolling outline, and working resume."""
from novel.config import ModelConfig
from novel.graph import run_full_pipeline
from novel.models import (
    Arc,
    ArcPlan,
    ArcSkeleton,
    ChapterBeat,
    ChapterOutline,
    Character,
    Concept,
    DimensionScore,
    Outline,
    ReviewScore,
    World,
)
from novel.project import NovelProject
from novel.providers import FakeProvider
from novel.store.bible import StoryBible
from novel.store.summaries import SummaryStore
from novel.store.vector import VectorMemory, hash_embed

ARC_LEN = 50           # 4 arcs x 50 chapters = 200
TOTAL = 200


class _SeqArcProvider(FakeProvider):
    """Serves queued arc_detailer responses in call order."""

    def __init__(self, responses: dict[str, object], arcs: list[object]) -> None:
        super().__init__(responses, tag_key="agent")
        self._arcs = list(arcs)

    def _lookup(self, messages: list[dict[str, object]]) -> object:
        from novel.providers import _agent_tag
        if _agent_tag(messages, self.tag_key) == "arc_detailer":
            return self._arcs.pop(0)
        return super()._lookup(messages)


def _beat() -> ChapterBeat:
    # characters=[] keeps the 200-chapter outline's JSON under the R2 threshold
    # (< 90_000): the current 9-field ChapterBeat serializes to ~430 bytes/chapter
    # with indent=2, and a populated characters list pushes the canonical past 90K.
    # Voice/mannerism extraction is keyed by canned response ids, not beats, so
    # the voice_fingerprint/mannerism assertions below are unaffected.
    return ChapterBeat(pov="c1", setting="s", event="event", emotional_turn="d",
                       characters=[], plants=[], payoffs=[])


VOLUMES = ["卷一", "卷二", "卷三", "卷四"]


def _provider(concept: Concept, chars: list[Character]) -> _SeqArcProvider:
    beat = _beat()
    skeleton_outline = Outline(
        arcs=[Arc(arc_name="卷一", chapters=[
            ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat])
            for i in range(1, ARC_LEN + 1)])],
        arc_plan=[ArcSkeleton(arc_name=vol, chapter_start=(k - 1) * ARC_LEN + 1,
                              chapter_end=k * ARC_LEN, premise=f"p{k}")
                  for k, vol in enumerate(VOLUMES[1:], start=2)])
    # planned_total routes the SETUP outline stage through generate_two_phase_outline,
    # which calls ArcPlannerAgent FIRST (tag "arc_planner"), then _detail_arc for
    # plan.arcs[0] — so the planner must be canned too, and the _arcs queue must
    # hold ALL four volumes (setup's first detail pops 卷一).
    plan = ArcPlan(
        arcs=[ArcSkeleton(arc_name=vol, chapter_start=(k - 1) * ARC_LEN + 1,
                          chapter_end=k * ARC_LEN, premise=f"p{k}")
              for k, vol in enumerate(VOLUMES, start=1)],
        planned_total_chapters=TOTAL)
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    # 卷一 uses normal chapter numbers; the later volumes use deliberately-wrong
    # numbers (900+i) so _detail_arc's defensive renumbering is exercised.
    arcs: list[object] = []
    for k, vol in enumerate(VOLUMES, start=1):
        base = 1 if k == 1 else 900
        prefix = "T" if k == 1 else "X"
        arcs.append(Arc(arc_name=vol, chapters=[
            ChapterOutline(chapter_no=base + i, chapter_title=f"{prefix}{i}",
                           beats=[_beat()])
            for i in range(ARC_LEN)]))
    return _SeqArcProvider({
        "strategist": concept, "worldbuilder": World(setting="city"), "character": chars,
        "outliner": skeleton_outline, "arc_planner": plan,
        "writer": "Chapter prose text.", "continuity": "[]",
        "editor": "x", "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {"c1": "drawl"},
                      "mannerisms_used": {"c1": ["taps table"]}, "key_events": [],
                      "threads_advanced": [], "new_information_revealed": [],
                      "chapter_summary": "本章推进了主线。"},
        # chapter_no + chapter_start/chapter_end make this one dict valid as BOTH
        # ChapterSummary (summarize_chapter) and ArcSummary (summarize_arc);
        # pydantic ignores the extra fields in either direction.
        "summarizer": {"chapter_no": 1, "arc_name": "卷一", "summary": "卷摘要。",
                       "chapter_start": 1, "chapter_end": ARC_LEN,
                       "major_developments": []},
        "digestor": {"chapter_count": 1, "current_arc": "卷一", "summary": "全书梗概。"},
    }, arcs=arcs)


def _cfg_map() -> dict[str, ModelConfig]:
    return {name: ModelConfig("zhipu", "x") for name in
            ("strategist", "worldbuilder", "character", "outliner", "writer",
             "continuity", "editor", "scorer", "extractor")}


def test_long_run_two_hundred_chapters(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    bible = StoryBible(proj)
    vector = VectorMemory(proj, embed=hash_embed)
    concept = Concept(logline="L", genre="fantasy", tone="grim", themes=[],
                      target_length_words=500000, audience="a")
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    provider = _provider(concept, chars)
    events: list[dict[str, object]] = []
    state = run_full_pipeline(
        provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
        proj=proj, premise="a thief", target_chapters=TOTAL, min_chapter_chars=10,
        planned_total=TOTAL, arc_lookahead=5, on_event=events.append)
    assert state.error is None
    assert len(state.written) == TOTAL

    store = SummaryStore(proj)
    # every chapter has a summary
    assert all(store.get_chapter_summary(n) for n in range(1, TOTAL + 1))
    # arc summaries + digest generated for the four volumes
    assert [a.arc_name for a in store.all_arc_summaries()] == ["卷一", "卷二", "卷三", "卷四"]
    assert store.get_book_digest() is not None
    # rolling outline actually detailed the three skeleton volumes
    assert [a.arc_name for a in bible.get_outline().arcs] == ["卷一", "卷二", "卷三", "卷四"]
    assert bible.get_outline().arc_plan == []
    # bounded bible: voice capped at 10 (earliest + 9 recent), mannerisms merged
    c1 = bible.get_character("c1")
    assert len(c1.voice_fingerprint) == 10
    assert "sample_1" in c1.voice_fingerprint and f"sample_{TOTAL}" in c1.voice_fingerprint
    assert len(c1.mannerisms) == 1          # single distinct mannerism, merged not duplicated
    # canonical file stays bounded relative to chapter count. SDD ruling R2: a
    # 200-chapter outline's inherent JSON volume is already ~55-60KB, so the
    # 60_000 threshold would flake — 90_000 still proves boundedness (uncapped
    # voice/mannerisms would blow far past it).
    canonical_size = proj.canonical_path.stat().st_size
    assert canonical_size < 90_000          # 200 chapters must not inflate the bible
    # progress events carry planned_total
    assert next(e for e in events if e["type"] == "chapter_start")["planned_total"] == TOTAL
    assert any(e["type"] == "arc_detailed" for e in events)

    # resume: delete the last two chapters and re-run — rewritten, not restarted
    for n in (TOTAL - 1, TOTAL):
        (proj.root / "chapters" / f"{n:03d}.md").unlink()
    state2 = run_full_pipeline(
        provider=provider, cfg_map=_cfg_map(), bible=bible, vector=vector,
        proj=proj, premise="", target_chapters=TOTAL, start_chapter=TOTAL - 1,
        min_chapter_chars=10, planned_total=TOTAL, arc_lookahead=5)
    assert state2.error is None and state2.written == [TOTAL - 1, TOTAL]