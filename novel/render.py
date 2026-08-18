"""Render gate / setup artifacts to displayable text (shared by CLI and UI)."""
from __future__ import annotations

import difflib
import json

from pydantic import BaseModel


def artifact_text(obj: object) -> str:
    """Render a gate or setup artifact to displayable text.

    pydantic models (and lists of them, e.g. the character stage) become
    pretty-printed JSON; anything else falls back to str().
    """
    if isinstance(obj, BaseModel):
        try:
            return json.dumps(json.loads(obj.model_dump_json()), ensure_ascii=False, indent=2)
        except Exception:  # noqa: BLE001 - display only
            return str(obj)
    if isinstance(obj, (list, tuple)) and obj and all(isinstance(o, BaseModel) for o in obj):
        try:
            payload = [json.loads(o.model_dump_json()) for o in obj]
            return json.dumps(payload, ensure_ascii=False, indent=2)
        except Exception:  # noqa: BLE001 - display only
            return str(obj)
    return str(obj)


def text_diff(old: str, new: str) -> str:
    """Unified line diff of two texts for proposal panels (prose paragraphs are
    usually one line, so the line diff reads as a paragraph diff)."""
    lines = difflib.unified_diff(old.splitlines(), new.splitlines(),
                                 fromfile="当前章稿", tofile="改写稿", lineterm="")
    return "\n".join(lines)
