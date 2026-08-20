"""Three-tier story summaries: per-chapter files under chapters/_summaries/,
arc summaries + whole-book digest in .meta/summaries.json (spec §4.1)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from novel.models import ArcSummary, BookDigest, ChapterSummary
from novel.project import NovelProject


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SummaryStore:
    def __init__(self, proj: NovelProject) -> None:
        self.proj = proj
        self._chapter_dir = proj.root / "chapters" / "_summaries"
        self._chapter_dir.mkdir(parents=True, exist_ok=True)
        self._meta_path = proj.root / ".meta" / "summaries.json"

    # ---- chapter summaries: one JSON file per chapter ----
    def _chapter_path(self, n: int) -> Path:
        return self._chapter_dir / f"{n:03d}.json"

    def put_chapter_summary(self, cs: ChapterSummary) -> None:
        path = self._chapter_path(cs.chapter_no)
        path.write_text(cs.model_dump_json(), encoding="utf-8")

    def get_chapter_summary(self, n: int) -> ChapterSummary | None:
        path = self._chapter_path(n)
        if not path.is_file():
            return None
        return ChapterSummary.model_validate_json(path.read_text(encoding="utf-8"))

    def recent_chapter_summaries(self, upto: int, k: int) -> list[ChapterSummary]:
        """Last k existing summaries for chapters <= upto (oldest → newest)."""
        out: list[ChapterSummary] = []
        n = upto
        while n >= 1 and len(out) < k:
            cs = self.get_chapter_summary(n)
            if cs is not None:
                out.append(cs)
            n -= 1
        return list(reversed(out))

    # ---- arc summaries + book digest: one small meta file ----
    def _load_meta(self) -> dict:
        if not self._meta_path.is_file():
            return {"arcs": [], "book": None}
        data: dict = json.loads(self._meta_path.read_text(encoding="utf-8"))
        return data

    def _save_meta(self, data: dict) -> None:
        self._meta_path.parent.mkdir(parents=True, exist_ok=True)
        data["arcs"] = sorted(data.get("arcs", []), key=lambda a: a["chapter_start"])
        self._meta_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def put_arc_summary(self, a: ArcSummary) -> None:
        data = self._load_meta()
        data["arcs"] = [x for x in data.get("arcs", []) if x["arc_name"] != a.arc_name] \
            + [a.model_dump()]
        self._save_meta(data)

    def get_arc_summary(self, arc_name: str) -> ArcSummary | None:
        for raw in self._load_meta().get("arcs", []):
            if raw["arc_name"] == arc_name:
                return ArcSummary.model_validate(raw)
        return None

    def all_arc_summaries(self) -> list[ArcSummary]:
        return [ArcSummary.model_validate(raw) for raw in self._load_meta().get("arcs", [])]

    def put_book_digest(self, d: BookDigest) -> None:
        data = self._load_meta()
        data["book"] = d.model_dump()
        self._save_meta(data)

    def get_book_digest(self) -> BookDigest | None:
        raw = self._load_meta().get("book")
        return BookDigest.model_validate(raw) if raw else None


def detect_edited_chapters(proj: NovelProject, store: SummaryStore) -> list[int]:
    """Chapters whose prose file hash no longer matches the recorded
    prose_sha256 — i.e. manually edited outside the pipeline (spec §4.5/§5)."""
    edited: list[int] = []
    for path in sorted((proj.root / "chapters" / "_summaries").glob("[0-9][0-9][0-9].json")):
        cs = ChapterSummary.model_validate_json(path.read_text(encoding="utf-8"))
        chapter_file = proj.root / "chapters" / f"{cs.chapter_no:03d}.md"
        if not chapter_file.is_file() or not cs.prose_sha256:
            continue
        if sha256_text(chapter_file.read_text(encoding="utf-8")) != cs.prose_sha256:
            edited.append(cs.chapter_no)
    return edited
