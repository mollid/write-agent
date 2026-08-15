"""Tests for persisted review history (ReviewStore + pipeline integration)."""
from __future__ import annotations

from novel.graph import run_full_pipeline
from novel.models import DimensionScore, ReviewRecord, ReviewScore
from novel.project import NovelProject
from novel.providers import FakeProvider, ModelConfig
from novel.store.reviews import ReviewStore
from novel.store.vector import VectorMemory, hash_embed
from tests.test_graph import _one_chapter_setup


def test_review_store_roundtrip(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    store = ReviewStore(proj)
    assert store.list_all() == []
    rec = ReviewRecord(chapter=1, attempt=1, artifact_type="chapter", overall=90,
                       summary="solid", passed=True, timestamp="2026-08-14T00:00:00+00:00",
                       scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    store.append(rec)
    rec2 = ReviewRecord(chapter=1, attempt=2, overall=70, passed=False)
    store.append(rec2)
    all_recs = store.list_all()
    assert len(all_recs) == 2
    assert all_recs[0] == rec
    assert all_recs[1] == rec2
    assert [r.attempt for r in store.list_for_chapter(1)] == [1, 2]
    assert store.list_for_chapter(9) == []
    # fresh store over the same project sees the same history
    assert [r.overall for r in ReviewStore(proj).list_all()] == [90, 70]


def test_pipeline_writes_review_records(tmp_path):
    proj, bible, vector, concept, _beat, outline, chars = _one_chapter_setup(tmp_path)
    from novel.models import World
    passing = ReviewScore(artifact_type="chapter", overall=90,
                          scores={"beat_adherence": DimensionScore(score=90, critique="ok")})
    provider = FakeProvider(responses={
        "strategist": concept, "worldbuilder": World(setting="city"),
        "character": chars, "outliner": outline,
        "writer": "Chapter prose text.", "continuity": "[]", "editor": "Chapter prose text.",
        "scorer": passing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": []},
    }, tag_key="agent")
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible, vector=vector,
                      proj=proj, premise="a thief", target_chapters=1)
    recs = ReviewStore(proj).list_all()
    assert len(recs) == 1
    r = recs[0]
    assert r.chapter == 1 and r.attempt == 1
    assert r.passed is True and r.overall == 90
    assert r.scores["beat_adherence"].critique == "ok"
    assert r.timestamp  # ISO timestamp recorded


def test_pipeline_records_every_retry(tmp_path):
    """Failing scores are recorded per attempt, including the final rejected one."""
    proj, bible, _vector, concept, _beat, outline, chars = _one_chapter_setup(tmp_path)
    from novel.models import World
    failing = ReviewScore(artifact_type="chapter", overall=40,
                          scores={"beat_adherence": DimensionScore(score=40, critique="weak")})
    provider = FakeProvider(responses={
        "strategist": concept, "worldbuilder": World(setting="city"),
        "character": chars, "outliner": outline,
        "writer": "Chapter prose text.", "continuity": "[]", "editor": "Chapter prose text.",
        "scorer": failing,
        "extractor": {"character_states": {}, "voice_samples": {}, "mannerisms_used": {},
                      "key_events": [], "threads_advanced": [], "new_information_revealed": []},
    }, tag_key="agent")
    cfg_map = {name: ModelConfig("zhipu", "x") for name in
               ["strategist", "worldbuilder", "character", "outliner", "writer",
                "continuity", "editor", "scorer", "extractor"]}
    state = run_full_pipeline(provider=provider, cfg_map=cfg_map, bible=bible,
                              vector=VectorMemory(proj, embed=hash_embed),
                              proj=proj, premise="a thief", target_chapters=1, max_retries=2)
    assert state.error is not None
    recs = ReviewStore(proj).list_all()
    assert [r.attempt for r in recs] == [1, 2]
    assert all(r.passed is False and r.overall == 40 for r in recs)
    assert recs[0].scores["beat_adherence"].critique == "weak"
