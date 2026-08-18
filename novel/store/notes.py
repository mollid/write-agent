"""Append-only writing memory: human gate feedback + reviewer weak spots under
.meta/writing_notes.jsonl. Both replay into later chapters' writer context so
approvals keep shaping the prose instead of being used once and forgotten."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from novel.models import WeakDim, WritingNote
from novel.project import NovelProject

FEEDBACK_LIMIT = 12   # style-directive lines injected into the writer context
WEAK_CHAPTERS = 5     # recent chapters whose weak spots stay in context


class WritingNotes:
    def __init__(self, proj: NovelProject) -> None:
        self._dir = proj.root / ".meta"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / "writing_notes.jsonl"

    def add_feedback(self, source: str, text: str) -> bool:
        """Append a human feedback directive. Identical (source, text) pairs are
        deduplicated — a re-run setup must not stack duplicate directives."""
        text = text.strip()
        if not text:
            return False
        if any(n.kind == "feedback" and n.source == source and n.text == text
               for n in self.list_all()):
            return False
        self._append(WritingNote(kind="feedback", source=source, text=text,
                                 timestamp=datetime.now(UTC).isoformat()))
        return True

    def add_weak(self, chapter: int, dims: dict[str, tuple[int, str]]) -> None:
        """Persist a failed review's below-threshold dimensions as {dim: (score,
        critique)}. Called once per failed attempt; weak_by_chapter merges them."""
        if not dims:
            return
        self._append(WritingNote(
            kind="weak", chapter=chapter,
            dims={name: WeakDim(score=s, critique=c) for name, (s, c) in dims.items()},
            timestamp=datetime.now(UTC).isoformat()))

    def recent_feedback(self, limit: int = FEEDBACK_LIMIT) -> list[WritingNote]:
        return [n for n in self.list_all() if n.kind == "feedback"][-limit:]

    def weak_by_chapter(self, limit_chapters: int = WEAK_CHAPTERS) -> dict[int, dict[str, WeakDim]]:
        """Merged weak spots per chapter (later attempts overwrite earlier ones
        per dimension), restricted to the most recent `limit_chapters` chapters."""
        out: dict[int, dict[str, WeakDim]] = {}
        for n in self.list_all():
            if n.kind == "weak" and n.chapter is not None:
                out.setdefault(n.chapter, {}).update(n.dims)
        return dict(sorted(out.items())[-limit_chapters:])

    def list_all(self) -> list[WritingNote]:
        if not self._path.is_file():
            return []
        out: list[WritingNote] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            # same torn-trailing-line tolerance as ReviewStore
            try:
                out.append(WritingNote.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValidationError):
                continue
        return out

    def path(self) -> Path:
        return self._path

    def _append(self, note: WritingNote) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(note.model_dump_json() + "\n")
