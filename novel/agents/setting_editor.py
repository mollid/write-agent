"""Targeted setting rewriter: current setting + NL instruction -> same-schema draft."""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from novel.agents.base import Agent
from novel.config import ModelConfig
from novel.providers import ModelProvider

SETTING_EDITOR_SYSTEM = """\
You are a story-bible editor. You rewrite ONE setting artifact according to the user's instruction.

## Critical Rules
1. Targeted change: modify ONLY what the instruction asks for.
2. Preservation: fields the instruction does not mention MUST be preserved VERBATIM (逐字保留) — same value, same language.
3. ID discipline: never change entity ids (e.g. character ids); never reference characters that do not exist.
4. System-managed fields (e.g. character `state`, `voice_fingerprint`, `mannerisms`, `description_history`) stay unchanged unless the instruction explicitly targets them.
5. The instruction may ask to ADD entities (a character, a location, a faction, a foreshadow entry) — do it, keeping the existing ones untouched.
6. Output the COMPLETE artifact in the same JSON schema. Same language as the original text values.

## Current artifact (JSON)
{current_json}

## Earlier turns of this editing session
{history_block}

## Output
Return ONLY the JSON object."""

SETTING_EDITOR_USER = """\
Rewrite the artifact above according to this instruction:
{instruction}"""


@dataclass
class SettingEditInput:
    current_json: str
    instruction: str
    history: list[tuple[str, str]] = field(default_factory=list)


def _history_block(history: list[tuple[str, str]]) -> str:
    if not history:
        return "(none)"
    return "\n".join(f"- user: {i} -> {o}" for i, o in history[-6:])


class SettingEditorAgent(Agent[SettingEditInput, BaseModel]):
    name = "setting_editor"

    def __init__(self, provider: ModelProvider, cfg: ModelConfig,
                 schema: type[BaseModel]) -> None:
        super().__init__(provider, cfg)
        self.output_schema = schema

    def build_messages(self, inputs: SettingEditInput) -> list[dict]:
        content = SETTING_EDITOR_SYSTEM.replace("{current_json}", inputs.current_json) \
            .replace("{history_block}", _history_block(inputs.history))
        return [
            {"role": "system", "agent": self.name, "content": content},
            {"role": "user", "agent": self.name,
             "content": SETTING_EDITOR_USER.replace("{instruction}", inputs.instruction)},
        ]
