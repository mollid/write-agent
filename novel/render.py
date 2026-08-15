"""Render gate / setup artifacts to displayable text (shared by CLI and UI)."""
from __future__ import annotations

import json

from pydantic import BaseModel


def artifact_text(obj: object) -> str:
    """Render a gate or setup artifact: pydantic BaseModel -> pretty JSON, else -> str."""
    if isinstance(obj, BaseModel):
        try:
            return json.dumps(json.loads(obj.model_dump_json()), ensure_ascii=False, indent=2)
        except Exception:  # noqa: BLE001 - display only
            return str(obj)
    return str(obj)
