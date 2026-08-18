"""Chapter rewriter: existing chapter prose + NL instruction -> rewritten draft.

Two modes (the user picks in the UI): `polish` (surgical edits, structure
preserved) and `rearrange` (creative re-arrangement, free to restructure while
honouring continuity constraints)."""
from __future__ import annotations

from dataclasses import dataclass, field

from novel.agents.base import Agent
from novel.config import ModelConfig
from novel.models import RewrittenChapter
from novel.providers import ModelProvider

REWRITER_SYSTEM = """\
You are a chapter rewriter working on ONE existing chapter of a novel.

## Modes
- polish: apply the user's instruction with surgical edits. Preserve the chapter's structure, scene order, plot events and voice unless the instruction explicitly targets them.
- rearrange: creative re-arrangement. You MAY restructure scenes, reorder or merge beats, shift emphasis and rewrite passages freely — while keeping story facts consistent with the constraints below.

## Hard constraints (both modes)
1. Continuity: the chapter must still connect naturally to the previous chapter's ending and leave the story in a state the NEXT chapter can build on.
2. Respect the beat's foreshadowing plants/payoffs — they must still happen (polish) or happen in an equivalent form (rearrange).
3. Obey the style directives and avoid the known weak spots.
4. Same language and POV as the original chapter.
5. Return the COMPLETE chapter as running prose — no headings, no commentary.

## Chapter info
chapter {chapter_no}: {title}
beat: {beat_json}

## Style directives (accumulated human approvals; obey throughout)
{style_block}

## Known weak spots (recent review failures; avoid repeating)
{weak_block}

## Previous chapter ending
{prev_ending}

## Original chapter
{original}

## Earlier turns of this editing session
{history_block}

## Output
Return ONLY the JSON object."""

REWRITER_USER = """\
Mode: {mode}
Rewrite the chapter above according to this instruction:
{instruction}"""


@dataclass
class RewriteInput:
    chapter_no: int
    title: str
    mode: str            # "polish" | "rearrange"
    instruction: str
    original: str
    beat_json: str = ""  # outline beat for this chapter, "" if none
    style_block: str = ""
    weak_block: str = ""
    prev_ending: str = ""
    history: list[tuple[str, str]] = field(default_factory=list)


def _history_block(history: list[tuple[str, str]]) -> str:
    if not history:
        return "(none)"
    return "\n".join(f"- user: {i} -> {o}" for i, o in history[-6:])


class ChapterRewriteAgent(Agent[RewriteInput, RewrittenChapter]):
    name = "rewriter"
    output_schema = RewrittenChapter

    def __init__(self, provider: ModelProvider, cfg: ModelConfig) -> None:
        super().__init__(provider, cfg)

    def build_messages(self, inputs: RewriteInput) -> list[dict]:
        content = (
            REWRITER_SYSTEM.replace("{chapter_no}", str(inputs.chapter_no))
            .replace("{title}", inputs.title)
            .replace("{beat_json}", inputs.beat_json or "(no beat on record)")
            .replace("{style_block}", inputs.style_block or "(none)")
            .replace("{weak_block}", inputs.weak_block or "(none)")
            .replace("{prev_ending}", inputs.prev_ending or "(this is the first chapter)")
            .replace("{original}", inputs.original)
            .replace("{history_block}", _history_block(inputs.history))
        )
        user = REWRITER_USER.replace("{mode}", inputs.mode) \
            .replace("{instruction}", inputs.instruction)
        return [
            {"role": "system", "agent": self.name, "content": content},
            {"role": "user", "agent": self.name, "content": user},
        ]
