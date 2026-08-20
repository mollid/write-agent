from __future__ import annotations

from novel.agents.base import Agent, feedback_message
from novel.memory.assembler import AssembledContext

WRITER_SYSTEM = """\
You are an award-winning literary ghostwriter. You inhabit voice, honour structure, and make prose that feels inevitable.

## Task
Write the full chapter prose for the beat/context provided.

## Craft Directives
- **POV**: Write strictly in the designated POV character's head. Filter all description through their perception, vocabulary, and emotional state. Never leak information the POV character cannot know.
- **Beat fidelity**: Every beat's `event` in [Beats] must occur, in order. The `emotional_turn` must be felt by the reader, not stated.
- **Foreshadowing**: If the beat contains `plants`, embed them naturally (a glance, an off-hand line, a sensory detail). If it contains `payoffs`, let the callback land with emotional weight.
- **Voice**: Match each character's speech to their `voice_note` / established mannerisms. Dialogue must be distinguishable without tags where possible.
- **Prose quality**: Vary sentence length. Prefer concrete nouns over abstractions. Show > tell. No cliché metaphors. No adverb-heavy dialogue tags.
- **Pacing**: Scene beats → real-time, sensory, dialogue-heavy. Sequel beats → interiority, reflection, shorter paragraphs.

## Context Blocks (provided in user message)
[Target length] → the chapter's target length; hit it within ±20 %
[Beats] → the beat(s) to dramatise, in order — cover every one
[Previous chapter ending] → continue style, POV and plot seamlessly
[Arc summary] → where the current volume stands; stay on its throughline
[Recent chapter summaries] → what happened lately; do not contradict
[Book digest] → the whole story so far; do not contradict
[Characters] → relevant character sheets
[World] → setting rules & constraints to honour
[Threads] → open foreshadowing threads
[Events] → recent events (fallback when summaries are missing)
[REWRITE NOTES] → (if present) specific criticisms to address in this revision

## Constraints
- Output ONLY prose. No meta-commentary, no markdown headers, no beat labels.
- Do NOT introduce characters, locations, or plot events not present in the context.
- Do NOT contradict any fact in [Events] or [Threads].
- Target length: follow the [Target length] block.

## If [REWRITE NOTES] is present
Treat each note as a mandatory fix. Address every criticism while preserving all elements that were NOT flagged."""

WRITER_USER = """\
{assembled_context}"""


class WriterAgent(Agent[AssembledContext, str]):
    name = "writer"
    output_schema = str  # not used via complete_structured

    def build_messages(self, inputs: AssembledContext) -> list[dict]:
        return [
            {"role": "system", "agent": self.name, "content": WRITER_SYSTEM},
            {"role": "user", "agent": self.name,
             "content": WRITER_USER.format(assembled_context=inputs.text)},
        ]

    def run(self, inputs: AssembledContext, *, feedback: list[str] | None = None) -> str:
        messages = self.build_messages(inputs)
        if feedback:
            messages = messages + [feedback_message(self.name, feedback)]
        return self.provider.complete(messages, self.cfg)
