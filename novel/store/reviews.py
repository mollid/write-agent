"""Append-only review history: persisted scoring events under .meta/reviews/."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from novel.models import ReviewRecord
from novel.project import NovelProject


class ReviewStore:
    def __init__(self, proj: NovelProject) -> None:
        self._dir = proj.root / ".meta" / "reviews"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "reviews.jsonl"

    def append(self, rec: ReviewRecord) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(rec.model_dump_json() + "\n")

    def list_all(self) -> list[ReviewRecord]:
        if not self._path.is_file():
            return []
        out: list[ReviewRecord] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            # Append-only store: a crash mid-append can leave a torn trailing
            # line; skip unparseable/partial records instead of crashing resume.
            try:
                out.append(ReviewRecord.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValidationError):
                continue
        return out

    def list_for_chapter(self, chapter: int) -> list[ReviewRecord]:
        return [r for r in self.list_all() if r.chapter == chapter]

    def path(self) -> Path:
        return self._path
