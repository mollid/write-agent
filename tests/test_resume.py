"""Resume rules: disk is the source of truth for chapter completeness."""
from __future__ import annotations

from novel.models import DimensionScore, ReviewRecord
from novel.project import NovelProject
from novel.resume import is_chapter_complete
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
    from novel.resume import next_start_chapter
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
