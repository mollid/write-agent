from novel.memory.summarizer import digest_book, summarize_arc, summarize_chapter
from novel.models import ArcSummary, ChapterSummary
from novel.providers import FakeProvider, ModelConfig

_CFG = ModelConfig("zhipu", "x")


def test_summarize_chapter_returns_schema_with_no_sha():
    provider = FakeProvider({"summarizer": {
        "chapter_no": 7, "arc_name": "卷一", "summary": "主角潜入钟塔。",
        "characters_involved": ["c1"], "threads_advanced": [], "prose_sha256": ""}})
    cs = summarize_chapter(7, "正文。", "卷一", provider, _CFG)
    assert cs.summary == "主角潜入钟塔。" and cs.prose_sha256 == ""


def test_summarize_arc_passes_prev_and_chapter_summaries():
    captured: list[list[dict[str, object]]] = []

    class _Recording(FakeProvider):
        def complete_structured(self, messages, schema, cfg, *, seed=None):
            captured.append(messages)
            return super().complete_structured(messages, schema, cfg, seed=seed)

    provider = _Recording({"summarizer": {
        "arc_name": "卷一", "chapter_start": 1, "chapter_end": 30,
        "summary": "第一卷：立约与背叛。", "major_developments": ["a", "b"]}})
    prev = ArcSummary(arc_name="卷零", chapter_start=1, chapter_end=0, summary="序")
    a = summarize_arc("卷一", 1, 30,
                      [ChapterSummary(chapter_no=n, summary=f"s{n}") for n in (1, 30)],
                      prev, provider, _CFG)
    assert a.summary == "第一卷：立约与背叛。"
    user = str(captured[0][-1]["content"])
    assert "s1" in user and "s30" in user and "卷零" in user


def test_digest_book_separate_tag():
    provider = FakeProvider({"digestor": {
        "chapter_count": 60, "current_arc": "卷二", "summary": "全书梗概。"}})
    d = digest_book([ArcSummary(arc_name="卷一", chapter_start=1, chapter_end=30, summary="a")],
                    60, "卷二", provider, _CFG)
    assert d.summary == "全书梗概。" and d.chapter_count == 60
