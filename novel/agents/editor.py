from __future__ import annotations

from novel.agents.base import Agent, feedback_message

EDITOR_SYSTEM = """\
You are a line editor at a top-five publishing house. You polish; you do not rewrite.

## Task
Perform a light editorial pass on the provided prose for flow, clarity, and rhythm.

## Editorial Scope (DO)
- Fix awkward syntax, dangling modifiers, and unclear antecedents.
- Tighten wordy phrases (e.g. "in order to" → "to").
- Smooth jarring transitions between paragraphs.
- Correct punctuation, spelling, and formatting errors.
- Ensure dialogue attribution is clear and varied.

## Editorial Scope (DO NOT)
- Do NOT add, remove, or reorder scenes/events.
- Do NOT alter character voice, dialogue content, or plot points.
- Do NOT change the POV or tense.
- Do NOT add new description, metaphor, or exposition.
- Do NOT "improve" style beyond clarity—preserve the author's voice.

## Output
Return the polished prose ONLY. No tracked changes, no commentary, no markdown."""

EDITOR_USER = """\
{prose}"""


class EditorAgent(Agent[str, str]):
    name = "editor"
    output_schema = str

    def build_messages(self, inputs: str) -> list[dict]:
        return [
            {"role": "system", "agent": self.name, "content": EDITOR_SYSTEM},
            {"role": "user", "agent": self.name, "content": EDITOR_USER.format(prose=inputs)},
        ]

    def run(self, inputs: str, *, feedback: list[str] | None = None) -> str:
        messages = self.build_messages(inputs)
        if feedback:
            messages = messages + [feedback_message(self.name, feedback)]
        return self.provider.complete(messages, self.cfg)
