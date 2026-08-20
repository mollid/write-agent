"""Summary-tier LLM calls (spec §4.1): chapter backfill (lazy retry), arc
summaries, whole-book digest. Cheap by construction — inputs are already
bounded summaries, and arc/digest calls happen once per ~20-40 chapters."""
from __future__ import annotations

from pydantic import BaseModel, ValidationError

from novel.config import ModelConfig
from novel.models import ArcSummary, BookDigest, ChapterSummary
from novel.providers import ModelProvider

MAX_RETRIES = 2

_CHAPTER_SYSTEM = """\
You are a story archivist. Summarise the given chapter in 150–250 units (Chinese characters \
or English words): what happened, who was involved, what changed. No teaser language, no \
foreshadow lists. Return ONLY a JSON object matching the ChapterSummary schema \
(chapter_no, arc_name, summary, characters_involved, threads_advanced)."""

_ARC_SYSTEM = """\
You are a story archivist. Given one volume's chapter summaries and the previous volume's \
summary, write a 200–300 unit arc summary: the volume's throughline, major developments \
(3–6 bullets), and the state it leaves the story in. Return ONLY a JSON object matching \
the ArcSummary schema (arc_name, chapter_start, chapter_end, summary, major_developments)."""

_DIGEST_SYSTEM = """\
You are a story archivist. Given ALL volume summaries of a long novel so far, write a \
150–250 unit whole-book digest: premise, where the story stands now, the central tension. \
Return ONLY a JSON object matching the BookDigest schema (chapter_count, current_arc, summary)."""


def _run_structured(system: str, user: str, schema: type, tag: str,
                    provider: ModelProvider, cfg: ModelConfig) -> BaseModel:
    messages: list[dict[str, object]] = [
        {"role": "system", "agent": tag, "content": system},
        {"role": "user", "agent": tag, "content": user},
    ]
    last_err: ValidationError | None = None
    for _attempt in range(MAX_RETRIES + 1):
        try:
            return provider.complete_structured(messages, schema, cfg)
        except ValidationError as e:
            last_err = e
            messages = messages + [
                {"role": "assistant", "agent": tag, "content": "<invalid output>"},
                {"role": "user", "agent": tag,
                 "content": f"Your output failed validation: {e}. Fix the JSON and return "
                            "ONLY the valid JSON object."},
            ]
    assert last_err is not None
    raise last_err


def summarize_chapter(chapter_no: int, prose: str, arc_name: str,
                      provider: ModelProvider, cfg: ModelConfig) -> ChapterSummary:
    cs = _run_structured(
        _CHAPTER_SYSTEM,
        f"<arc_name>{arc_name}</arc_name>\n<chapter_no>{chapter_no}</chapter_no>\n"
        f"<prose>\n{prose}\n</prose>",
        ChapterSummary, "summarizer", provider, cfg)
    assert isinstance(cs, ChapterSummary)
    cs.chapter_no = chapter_no
    cs.arc_name = arc_name
    return cs


def summarize_arc(arc_name: str, chapter_start: int, chapter_end: int,
                  chapter_summaries: list[ChapterSummary], prev: ArcSummary | None,
                  provider: ModelProvider, cfg: ModelConfig) -> ArcSummary:
    summaries_block = "\n".join(f"- ch{cs.chapter_no}: {cs.summary}" for cs in chapter_summaries)
    prev_block = f"{prev.arc_name}: {prev.summary}" if prev else "(none)"
    a = _run_structured(
        _ARC_SYSTEM,
        f"<arc_name>{arc_name}</arc_name>\n<range>{chapter_start}-{chapter_end}</range>\n"
        f"<previous_volume>\n{prev_block}\n</previous_volume>\n"
        f"<chapter_summaries>\n{summaries_block}\n</chapter_summaries>",
        ArcSummary, "summarizer", provider, cfg)
    assert isinstance(a, ArcSummary)
    a.arc_name = arc_name
    a.chapter_start = chapter_start
    a.chapter_end = chapter_end
    return a


def digest_book(arc_summaries: list[ArcSummary], chapter_count: int, current_arc: str,
                provider: ModelProvider, cfg: ModelConfig) -> BookDigest:
    arcs_block = "\n".join(f"- {a.arc_name} (ch{a.chapter_start}-{a.chapter_end}): {a.summary}"
                           for a in arc_summaries)
    d = _run_structured(
        _DIGEST_SYSTEM,
        f"<volume_summaries>\n{arcs_block}\n</volume_summaries>\n"
        f"<chapter_count>{chapter_count}</chapter_count>\n<current_arc>{current_arc}</current_arc>",
        BookDigest, "digestor", provider, cfg)
    assert isinstance(d, BookDigest)
    d.chapter_count = chapter_count
    d.current_arc = current_arc
    return d
