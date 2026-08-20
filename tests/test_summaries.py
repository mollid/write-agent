from novel.models import ArcSummary, BookDigest, ChapterSummary
from novel.project import NovelProject
from novel.store.summaries import SummaryStore, detect_edited_chapters, sha256_text


def _proj(tmp_path):
    return NovelProject.scaffold("n", genre="g", root=tmp_path)


def test_chapter_summary_roundtrip_and_recent(tmp_path):
    store = SummaryStore(_proj(tmp_path))
    for n in range(1, 6):
        store.put_chapter_summary(ChapterSummary(chapter_no=n, arc_name="卷一",
                                                 summary=f"s{n}", prose_sha256=sha256_text(f"p{n}")))
    assert store.get_chapter_summary(3).summary == "s3"
    assert store.get_chapter_summary(99) is None
    recent = store.recent_chapter_summaries(upto=5, k=3)
    assert [cs.chapter_no for cs in recent] == [3, 4, 5]
    assert store.recent_chapter_summaries(upto=2, k=5) == [store.get_chapter_summary(1),
                                                           store.get_chapter_summary(2)]


def test_arc_and_book_digest_storage(tmp_path):
    store = SummaryStore(_proj(tmp_path))
    store.put_arc_summary(ArcSummary(arc_name="卷一", chapter_start=1, chapter_end=30, summary="a1"))
    store.put_arc_summary(ArcSummary(arc_name="卷二", chapter_start=31, chapter_end=60, summary="a2"))
    assert [a.arc_name for a in store.all_arc_summaries()] == ["卷一", "卷二"]
    assert store.get_arc_summary("卷二").summary == "a2"
    store.put_book_digest(BookDigest(chapter_count=60, current_arc="卷二", summary="d"))
    assert store.get_book_digest().summary == "d"
    assert store.get_arc_summary("卷三") is None


def test_detect_edited_chapters(tmp_path):
    proj = _proj(tmp_path)
    store = SummaryStore(proj)
    prose = "正文" * 30
    (proj.root / "chapters" / "001.md").write_text(prose, encoding="utf-8")
    store.put_chapter_summary(ChapterSummary(chapter_no=1, summary="s", prose_sha256=sha256_text(prose)))
    assert detect_edited_chapters(proj, store) == []
    (proj.root / "chapters" / "001.md").write_text(prose + "手改", encoding="utf-8")
    assert detect_edited_chapters(proj, store) == [1]
