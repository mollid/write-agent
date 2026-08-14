from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from typing import Any

from novel.project import NovelProject

EmbedFn = Callable[[str], list[float]]
_DIM = 64


def hash_embed(text: str) -> list[float]:
    """Deterministic, dependency-free embedding for tests."""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vals = [(b - 128) / 128.0 for b in h]
    # pad/truncate to _DIM
    vals = (vals * ((_DIM // len(vals)) + 1))[:_DIM]
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


class VectorMemory:
    def __init__(self, proj: NovelProject, embed: EmbedFn = hash_embed):
        self.proj = proj
        self.embed = embed
        self._client: Any = None
        self._col: Any = None

    def _collection(self) -> Any:
        if self._col is None:
            import chromadb  # local import

            path = str(self.proj.root / "memory" / "chroma")
            self._client = chromadb.PersistentClient(path=path)
            self._col = self._client.get_or_create_collection(name="novel")
        return self._col

    def _add(self, uid: str, text: str, meta: dict) -> None:
        self._collection().upsert(ids=[uid], documents=[text], embeddings=[self.embed(text)], metadatas=[meta])

    def add_chapter(self, chapter_no: int, text: str) -> None:
        self._add(f"ch{chapter_no}", text, {"kind": "chapter", "chapter": chapter_no})

    def add_summary(self, level: str, key: str, text: str) -> None:
        self._add(f"sum:{level}:{key}", text, {"kind": f"summary-{level}", "key": key})

    def retrieve(self, query: str, k: int = 5) -> list[str]:
        res = self._collection().query(query_embeddings=[self.embed(query)], n_results=k)
        docs = res.get("documents") or [[]]
        return list(docs[0])
