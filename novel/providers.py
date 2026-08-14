from __future__ import annotations

import json
from typing import ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel

from novel.config import ModelConfig


@runtime_checkable
class ModelProvider(Protocol):
    def complete(self, messages: list[dict[str, object]], cfg: ModelConfig, *, seed: int | None = None) -> str: ...

    def complete_structured(
        self,
        messages: list[dict[str, object]],
        schema: type[BaseModel],
        cfg: ModelConfig,
        *,
        seed: int | None = None,
    ) -> BaseModel: ...


def _agent_tag(messages: list[dict[str, object]], tag_key: str) -> str:
    for m in messages:
        if tag_key in m:
            return str(m[tag_key])
    raise KeyError(f"no agent tag '{tag_key}' in messages")


def _jsonable(obj: object) -> object:
    """Coerce Pydantic models (nested in dict/list) into JSON-serializable forms."""
    if isinstance(obj, BaseModel):
        return json.loads(obj.model_dump_json())
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def _extract_json(text: str) -> str:
    """Strip markdown fences / surrounding prose; return the outermost JSON payload.

    Real models often wrap JSON in ```json ... ``` or add prose around it. This picks
    the outermost object (``{``) or array (``[``) by whichever opens first, then takes
    up to the last matching closer.
    """
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        s = s.removesuffix("```")
        s = s.strip()
    obj_start = s.find("{")
    arr_start = s.find("[")
    if obj_start == -1:
        start, close = arr_start, "]"
    elif arr_start == -1:
        start, close = obj_start, "}"
    elif arr_start < obj_start:
        start, close = arr_start, "]"
    else:
        start, close = obj_start, "}"
    if start == -1:
        return s
    end = s.rfind(close)
    if end > start:
        return s[start:end + 1]
    return s


class FakeProvider:
    """Deterministic provider for tests. Responses keyed by agent name in messages."""

    def __init__(self, responses: dict[str, object], tag_key: str = "agent") -> None:
        self.responses = responses
        self.tag_key = tag_key

    def _lookup(self, messages: list[dict[str, object]]) -> object:
        return self.responses[_agent_tag(messages, self.tag_key)]

    def complete(self, messages: list[dict[str, object]], cfg: ModelConfig, *, seed: int | None = None) -> str:
        val = self._lookup(messages)
        if isinstance(val, str):
            return val
        if isinstance(val, (dict, list)):
            return json.dumps(val, default=_jsonable, ensure_ascii=False)
        return str(val)

    def complete_structured(
        self,
        messages: list[dict[str, object]],
        schema: type[BaseModel],
        cfg: ModelConfig,
        *,
        seed: int | None = None,
    ) -> BaseModel:
        val = self._lookup(messages)
        if isinstance(val, BaseModel):
            assert isinstance(val, schema), f"canned response is {type(val)}, expected {schema}"
            return val
        return schema.model_validate(val)


class LiteLLMProvider:
    """Production provider wrapping litellm. Imported lazily so tests never need it."""

    # Map config language code -> natural-language output directive (appended as a
    # system message to every call so all 9 agents emit the same language).
    _LANG_DIRECTIVES: ClassVar[dict[str, str]] = {
        "zh": "用简体中文生成所有自然语言文本（包括 JSON 字段值里的 logline、genre、tone、"
              "themes、audience、summary、critique、issue、event、description 等描述性内容）。"
              "Enum 既定值（如 id、role 枚举）与 JSON 键名保持英文不变。",
        "en": "Generate all natural-language text in English.",
    }

    def __init__(self, api_keys: dict[str, str] | None = None, language: str = "en") -> None:
        self.api_keys = api_keys or {}
        self.language = language.strip().lower() or "en"

    def _lang_message(self) -> list[dict[str, object]]:
        directive = self._LANG_DIRECTIVES.get(self.language, self._LANG_DIRECTIVES["en"])
        return [{"role": "system", "content": f"[Language] {directive}"}]

    def complete(self, messages: list[dict[str, object]], cfg: ModelConfig, *, seed: int | None = None) -> str:
        import litellm  # local import: keeps tests import-free of network libs

        resp = litellm.completion(model=f"{cfg.provider}/{cfg.model}",
                                  messages=self._lang_message() + messages, seed=seed)
        return str(resp["choices"][0]["message"]["content"])

    def complete_structured(
        self,
        messages: list[dict[str, object]],
        schema: type[BaseModel],
        cfg: ModelConfig,
        *,
        seed: int | None = None,
    ) -> BaseModel:
        import litellm  # noqa: F401

        schema_json = schema.model_json_schema()
        sys_msg: list[dict[str, object]] = [
            {
                "role": "system",
                "content": f"Reply with ONE JSON object matching this schema. No prose.\n{schema_json}",
            }
        ]
        text = self.complete(sys_msg + messages, cfg, seed=seed)
        return schema.model_validate_json(_extract_json(text))
