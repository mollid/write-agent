"""Resume rules: the filesystem is the single source of truth for chapter
completeness. A chapter counts as complete only when its file is long enough
AND (post-reviews-era) it has a passed scoring record on disk."""
from __future__ import annotations

from novel.project import NovelProject
from novel.store.reviews import ReviewStore


def is_chapter_complete(proj: NovelProject, reviews: ReviewStore,
                        n: int, min_chars: int = 50) -> bool:
    path = proj.root / "chapters" / f"{n:03d}.md"
    if not path.is_file() or len(path.read_text(encoding="utf-8").strip()) < min_chars:
        return False
    if not reviews.path().is_file():
        return True  # legacy project predating review history: file rule only
    return any(r.passed for r in reviews.list_for_chapter(n))


def next_start_chapter(proj: NovelProject, reviews: ReviewStore,
                       min_chars: int = 50) -> int:
    """Smallest chapter number that is missing or incomplete."""
    n = 1
    for existing in sorted(int(p.stem) for p in
                           (proj.root / "chapters").glob("[0-9][0-9][0-9].md")):
        if existing == n and is_chapter_complete(proj, reviews, n, min_chars):
            n += 1
        else:
            break
    return n
