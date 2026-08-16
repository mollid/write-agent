"""Render gate / setup artifacts to displayable text (shared by CLI and UI)."""
from __future__ import annotations

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
