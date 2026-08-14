"""Resume rules: disk is the source of truth for chapter completeness."""
from __future__ import annotations

from novel.models import DimensionScore, ReviewRecord
from novel.project import NovelProject
from novel.resume import is_chapter_complete, next_start_chapter
from novel.store.reviews import ReviewStore

LONG = "Ara stepped into the tavern and the long night began. " * 2  # > 50 chars


def _proj(tmp_path):
    return NovelProject.scaffold("n", genre="fantasy", root=tmp_path)


def _pass_review(chapter: int) -> ReviewRecord:
    return ReviewRecord(chapter=chapter, attempt=1, artifact_type="chapter", overall=90,
                        summary="ok", passed=True, timestamp="2026-08-14T00:00:00+00:00",
                        scores={"beat_adherence": DimensionScore(score=90, critique="ok")})


def _write_chapter(proj, n: int, text: str) -> None:
    (proj.root / "chapters" / f"{n:03d}.md").write_text(text, encoding="utf-8")


def test_complete_needs_file_length_and_pass(tmp_path):
    proj = _proj(tmp_path)
    reviews = ReviewStore(proj)
    # missing file -> incomplete
    assert is_chapter_complete(proj, reviews, 1) is False
    # too short -> incomplete
    _write_chapter(proj, 1, "tiny")
    assert is_chapter_complete(proj, reviews, 1) is False
    # long enough; reviews.jsonl not created yet (no review ever persisted)
    # -> legacy fallback: file rule only (pinned in test_legacy_project_without_reviews_jsonl)
    _write_chapter(proj, 1, LONG)
    assert is_chapter_complete(proj, reviews, 1) is True
    # failed (not passed) review on record -> incomplete
    failed = _pass_review(1)
    failed.passed = False
    reviews.append(failed)
    assert is_chapter_complete(proj, reviews, 1) is False
    # long enough + passed record -> complete
    reviews.append(_pass_review(1))
    assert is_chapter_complete(proj, reviews, 1) is True


def test_legacy_project_without_reviews_jsonl(tmp_path):
    """Projects predating review history: file rule only, no rewrite-everything."""
    proj = _proj(tmp_path)
    reviews = ReviewStore(proj)
    reviews.path().unlink(missing_ok=True)
    _write_chapter(proj, 1, LONG)
    assert is_chapter_complete(proj, reviews, 1) is True
    _write_chapter(proj, 1, "")
    assert is_chapter_complete(proj, reviews, 1) is False


def test_next_start_chapter_positions(tmp_path):
    proj = _proj(tmp_path)
    reviews = ReviewStore(proj)
    # empty project -> 1
    assert next_start_chapter(proj, reviews) == 1
    # chapters 1-2 complete -> 3
    for n in (1, 2):
        _write_chapter(proj, n, LONG)
        reviews.append(_pass_review(n))
    assert next_start_chapter(proj, reviews) == 3
    # hole: 003 exists but empty -> resume at 3 even though it is the last file
    _write_chapter(proj, 3, "")
    assert next_start_chapter(proj, reviews) == 3
    # middle hole: 004 complete, 003 empty -> resume at 3
    _write_chapter(proj, 4, LONG)
    reviews.append(_pass_review(4))
    assert next_start_chapter(proj, reviews) == 3
    # min_chars override: 62-char demo prose vs threshold 100
    reviews.path().unlink()
    _write_chapter(proj, 1, "x" * 62)
    assert next_start_chapter(proj, reviews, min_chars=100) == 1
    # at 50, chapters 1 (62 chars) and 2 (LONG) are complete; 003 is empty -> 3
    assert next_start_chapter(proj, reviews, min_chars=50) == 3


def test_torn_trailing_line_in_reviews_jsonl(tmp_path):
    """A crash mid-append can leave a partial trailing line; resume must not crash."""
    proj = _proj(tmp_path)
    reviews = ReviewStore(proj)
    _write_chapter(proj, 1, LONG)
    reviews.append(_pass_review(1))
    # simulate a torn write: append a partial JSON line directly to the file
    with reviews.path().open("a", encoding="utf-8") as f:
        f.write('{"chapter": 3, "att')
    assert [r.chapter for r in reviews.list_all()] == [1]
    assert is_chapter_complete(proj, reviews, 1) is True
    assert next_start_chapter(proj, reviews) == 2


def _run_pipeline(tmp_path, prose: str, target: int, start: int = 1,
                  proj: NovelProject | None = None):
    """Demo-mode pipeline run with FakeProvider; pass `proj` back in to rerun."""
    from novel.graph import run_full_pipeline
    from novel.models import (
        Arc,
        ChapterBeat,
        ChapterOutline,
        Character,
        Concept,
        DimensionScore,
        Outline,
        ReviewScore,
        World,
    )
    from novel.providers import FakeProvider, ModelConfig
    from novel.store.bible import StoryBible
    from novel.store.vector import VectorMemory, hash_embed

    if proj is None:
        proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    bible = StoryBible(proj)
    vector = VectorMemory(proj, embed=hash_embed)
    concept = Concept(logline="L", genre="fantasy", tone="grim", themes=["x"],
                      target_length_words=9000, audience="a")
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant",
                       emotional_turn="doubt", characters=["c1"])
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat])
        for i in range(1, target + 1)])])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = FakeProvider(responses={
        "strategist": concept, "worldbuilder": World(setting="city"),
        "character": chars, "outliner": outline,
        "writer": prose, "continuity": "[]", "editor": prose, "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": []},
    }, tag_key="agent")
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    state = run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
                              proj=proj, premise="a thief", target_chapters=target,
                              start_chapter=start)
    return proj, state


def test_atomic_write_no_tmp_residue(tmp_path):
    proj, state = _run_pipeline(tmp_path, LONG, target=1)
    assert state.error is None
    assert (proj.root / "chapters" / "001.md").read_text(encoding="utf-8") == LONG
    assert list((proj.root / "chapters").glob("*.tmp")) == []


def test_stale_tmp_cleaned_on_rerun(tmp_path):
    proj, state = _run_pipeline(tmp_path, LONG, target=1)
    assert state.error is None
    # a crashed run left a partial tmp behind; the next pipeline start must remove it
    (proj.root / "chapters" / ".002.md.tmp").write_text("partial", encoding="utf-8")
    proj, state2 = _run_pipeline(tmp_path, LONG, target=2, start=2, proj=proj)
    assert state2.error is None
    assert (proj.root / "chapters" / "002.md").read_text(encoding="utf-8") == LONG
    assert list((proj.root / "chapters").glob("*.tmp")) == []


class _CountingProvider:
    """Wraps FakeProvider, counting calls per agent tag (protocol-compatible)."""

    def __init__(self, responses: dict[str, object]) -> None:
        from collections import Counter

        from novel.providers import FakeProvider, _agent_tag
        self._inner = FakeProvider(responses, tag_key="agent")
        self._agent_tag = _agent_tag
        self.counts: Counter[str] = Counter()

    def complete(self, messages, cfg, *, seed=None):
        self.counts[self._agent_tag(messages, "agent")] += 1
        return self._inner.complete(messages, cfg, seed=seed)

    def complete_structured(self, messages, schema, cfg, *, seed=None):
        self.counts[self._agent_tag(messages, "agent")] += 1
        return self._inner.complete_structured(messages, schema, cfg, seed=seed)


def _run_counting(tmp_path, target: int, start: int = 1):
    """Like _run_pipeline but with a counting provider; returns (proj, state, provider)."""
    from novel import graph
    from novel.models import (
        Arc,
        ChapterBeat,
        ChapterOutline,
        Character,
        Concept,
        DimensionScore,
        Outline,
        ReviewScore,
        World,
    )
    from novel.providers import ModelConfig
    from novel.store.bible import StoryBible
    from novel.store.vector import VectorMemory, hash_embed

    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    bible = StoryBible(proj)
    vector = VectorMemory(proj, embed=hash_embed)
    concept = Concept(logline="L", genre="fantasy", tone="grim", themes=["x"],
                      target_length_words=9000, audience="a")
    beat = ChapterBeat(pov="Ara", setting="tavern", event="meet informant",
                       emotional_turn="doubt", characters=["c1"])
    outline = Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat])
        for i in range(1, target + 1)])])
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="b", motivation="m", arc="a")]
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = _CountingProvider({
        "strategist": concept, "worldbuilder": World(setting="city"),
        "character": chars, "outliner": outline,
        "writer": LONG, "continuity": "[]", "editor": LONG, "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": []},
    })
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    state = graph.run_full_pipeline(
        provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
        proj=proj, premise="a thief", target_chapters=target, start_chapter=start)
    return proj, state, provider


def _rerun(proj, provider, target: int, start: int = 1, min_chars: int | None = None,
           events: list | None = None):
    from novel import graph
    from novel.providers import ModelConfig
    from novel.store.bible import StoryBible
    from novel.store.vector import VectorMemory, hash_embed
    kwargs = {}
    if min_chars is not None:
        kwargs["min_chapter_chars"] = min_chars
    return graph.run_full_pipeline(
        provider=provider,
        cfg_map={name: ModelConfig("zhipu", "x") for name in
                 ["strategist", "worldbuilder", "character", "outliner", "writer",
                  "continuity", "editor", "scorer", "extractor"]},
        bible=StoryBible(proj), vector=VectorMemory(proj, embed=hash_embed),
        proj=proj, premise="a thief", target_chapters=target, start_chapter=start,
        on_event=events.append if events is not None else None, **kwargs)


def test_complete_chapters_skipped_on_rerun(tmp_path):
    proj, state, provider = _run_counting(tmp_path, target=3)
    assert state.error is None
    assert provider.counts["writer"] == 3
    events: list[dict] = []
    state2 = _rerun(proj, provider, target=3, start=1, events=events)
    assert state2.error is None
    assert provider.counts["writer"] == 3  # no extra writer calls
    skips = [e for e in events if e["type"] == "chapter_skipped"]
    assert [e["chapter"] for e in skips] == [1, 2, 3]
    assert all(e["reason"] == "already complete" for e in skips)


def test_pipeline_rewrites_invalid_hole(tmp_path):
    proj, _state, provider = _run_counting(tmp_path, target=3)
    assert provider.counts["writer"] == 3
    # chapter 2 got truncated by a crash: rerun must rewrite ONLY chapter 2
    (proj.root / "chapters" / "002.md").write_text("", encoding="utf-8")
    events: list[dict] = []
    state2 = _rerun(proj, provider, target=3, start=2, events=events)
    assert state2.error is None
    assert provider.counts["writer"] == 4  # exactly one rewrite (chapter 2)
    assert (proj.root / "chapters" / "002.md").read_text(encoding="utf-8") == LONG
    skips = [e for e in events if e["type"] == "chapter_skipped"]
    assert [e["chapter"] for e in skips] == [3]  # chapter 3 untouched
    assert list((proj.root / "chapters").glob("*.tmp")) == []


def test_min_chapter_chars_param_gates_completeness(tmp_path):
    proj, _state, provider = _run_counting(tmp_path, target=1)
    assert provider.counts["writer"] == 1
    events: list[dict] = []
    # LONG (~110 chars) is complete at min_chars=50 but not at 500
    state2 = _rerun(proj, provider, target=1, start=1, min_chars=500, events=events)
    assert state2.error is None
    assert provider.counts["writer"] == 2  # rewritten under the stricter threshold
