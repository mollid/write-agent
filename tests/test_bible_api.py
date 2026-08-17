"""Bible read/validate/diff helpers + /bible API endpoints."""
from __future__ import annotations

import threading

import pytest
from pydantic import ValidationError

from novel.models import Concept, World
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.ui import jobs as J
from novel.ui.jobs import (
    json_diff,
    read_bible_section,
    save_bible_section,
    validate_bible_section,
)


@pytest.fixture()
def bible(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    return StoryBible(proj)


def test_read_concept_missing_returns_none(bible):
    assert read_bible_section(bible, "concept") is None


def test_validate_roundtrip(bible):
    concept = validate_bible_section("concept", {
        "logline": "L", "genre": "g", "tone": "t", "target_length_words": 100, "audience": "a"})
    assert isinstance(concept, Concept)
    save_bible_section(bible, "concept", concept)
    back = read_bible_section(bible, "concept")
    assert isinstance(back, Concept) and back.logline == "L"


def test_validate_rejects_bad_section_and_readonly(bible):
    with pytest.raises(ValueError, match="unknown section"):
        validate_bible_section("events", {})
    with pytest.raises(ValueError, match="unknown section"):
        validate_bible_section("nope", {})


def test_validate_reports_pydantic_error(bible):
    with pytest.raises(ValidationError):
        validate_bible_section("world", {"rules": "not-a-list"})


def test_json_diff_marks_changed_lines():
    old = World(setting="cold city").model_dump()
    new = World(setting="cold city", era="winter").model_dump()
    d = json_diff(old, new)
    assert "-  \"era\": \"\"," in d
    assert "+  \"era\": \"winter\"," in d
    assert "\"setting\": \"cold city\"" in d


# ---------- run_bible_chat_job / run_outline_extend_job (demo mode) ----------


def _seed_concept(bible):
    bible.set_concept(Concept(logline="L", genre="g", tone="t",
                              target_length_words=100, audience="a"))


def test_chat_job_demo_echo_applies(bible, monkeypatch):
    _seed_concept(bible)
    seen: list[dict] = []

    def fake_gate(self, label, artifact):
        seen.append({"label": label, "artifact": artifact})
        return True, None

    monkeypatch.setattr(J.Job, "gate_with_feedback", fake_gate)
    events: list[dict] = []
    fn = J.run_bible_chat_job(bible.proj.root, "concept", "让基调更黑暗")
    job = J.Job("n", "bible_chat", fn)
    job._bus = None
    # capture emits by wrapping emit
    orig_emit = job.emit
    job.emit = lambda ev: (events.append(ev), orig_emit(ev))[1]  # type: ignore[method-assign]
    job.thread = threading.Thread(target=job._run, daemon=True)
    job.thread.start()
    job.thread.join(timeout=5)
    assert not job.thread.is_alive()
    assert job.status == "done"
    assert seen[0]["label"] == "bible:concept"
    assert any(e["type"] == "bible_proposal" for e in events)
    assert any(e["type"] == "bible_applied" for e in events)
    # demo echo: content unchanged
    assert bible.get_concept().logline == "L"


def test_chat_job_rejected_without_feedback_keeps_bible(bible, monkeypatch):
    _seed_concept(bible)
    monkeypatch.setattr(J.Job, "gate_with_feedback", lambda self, label, a: (False, None))
    fn = J.run_bible_chat_job(bible.proj.root, "concept", "改")
    job = J.Job("n", "bible_chat", fn)
    job._bus = None
    job.thread = threading.Thread(target=job._run, daemon=True)
    job.thread.start()
    job.thread.join(timeout=5)
    assert bible.get_concept().tone == "t"  # unchanged


def test_extend_job_demo_appends_and_unlocks(bible, monkeypatch, tmp_path):
    _seed_concept(bible)
    bible.set_world(World(setting="city"))
    from novel.models import Arc, ChapterBeat, ChapterOutline, Character, Outline
    beat = ChapterBeat(pov="c1", setting="tavern", event="e", emotional_turn="d",
                       characters=["c1"])
    bible.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist",
                                     backstory="b", motivation="m", arc="a"))
    bible.set_outline(Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])]))
    monkeypatch.setattr(J.Job, "gate_with_feedback", lambda self, label, a: (True, None))
    fn = J.run_outline_extend_job(bible.proj.root, 2)
    job = J.Job("n", "bible_extend", fn)
    job._bus = None
    job.thread = threading.Thread(target=job._run, daemon=True)
    job.thread.start()
    job.thread.join(timeout=5)
    out = bible.get_outline()
    nums = [c.chapter_no for a in out.arcs for c in a.chapters]
    assert nums == [1, 2, 3]
    from novel.resume import next_start_chapter
    from novel.store.reviews import ReviewStore
    # no chapters on disk yet; write one complete to prove unlock
    (bible.proj.root / "chapters" / "001.md").write_text("x" * 80, encoding="utf-8")
    assert next_start_chapter(bible.proj, ReviewStore(bible.proj)) == 2
