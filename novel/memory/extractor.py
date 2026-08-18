from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from novel.config import ModelConfig
from novel.models import Character, CharacterState, KeyEvent
from novel.providers import ModelProvider

EXTRACTOR_SYSTEM = """\
You are a narrative state-tracker maintaining a living story database. You extract only what is explicitly evidenced in the text—never infer beyond what the chapter shows.

## Task
Extract structured updates from the chapter below to update the persistent story state.

## Output Schema (strict JSON)
{
  "character_states": {
    "<character_id>": {
      "emotional_state": "...",
      "physical_state": "...",
      "knowledge_gained": ["..."],
      "relationships_shifted": {"<other_id>": "description of shift"},
      "location_end": "where they are at chapter's end"
    }
  },
  "voice_samples": {
    "<character_id>": "1–2 verbatim sentences from the chapter that best capture this character's voice"
  },
  "mannerisms_used": {
    "<character_id>": ["verbal tic or physical habit observed in this chapter"]
  },
  "key_events": [
    {"event": "...", "significance": "...", "affected_characters": ["<id>"]}
  ],
  "threads_advanced": ["foreshadow_id or brief description of thread moved forward"],
  "new_information_revealed": ["..."]
}

## Critical Rules
1. **ID discipline**: All dict keys in `character_states`, `voice_samples`, and `mannerisms_used` MUST be character ids from the roster below. NEVER key by name, role, or any non-roster figure.
2. **Evidence-based**: Every extracted fact must be directly supported by the text. Do not speculate.
3. **Completeness**: Include every roster character who appears, speaks, or is directly referenced with new information.
4. **Brevity**: Each field value should be concise (1–2 sentences max).

## Roster (authoritative character ids)
{roster_block}

## Output
Return ONLY the JSON object."""

EXTRACTOR_USER = """\
<chapter_number>{chapter_no}</chapter_number>

<roster>
{roster_block}
</roster>

<prose>
{prose}
</prose>"""


class _UpdatePayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    character_states: dict[str, CharacterState] = Field(default_factory=dict)
    voice_samples: dict[str, str] = Field(default_factory=dict)
    mannerisms_used: dict[str, list[str]] = Field(default_factory=dict)
    key_events: list[KeyEvent] = Field(default_factory=list)
    threads_advanced: list[str] = Field(default_factory=list)
    new_information_revealed: list[str] = Field(default_factory=list)


@dataclass
class ChapterUpdates:
    character_states: dict[str, CharacterState] = field(default_factory=dict)
    voice_samples: dict[str, str] = field(default_factory=dict)
    mannerisms_used: dict[str, list[str]] = field(default_factory=dict)
    key_events: list[KeyEvent] = field(default_factory=list)
    threads_advanced: list[str] = field(default_factory=list)
    new_information_revealed: list[str] = field(default_factory=list)


MAX_RETRIES = 2


def extract_updates(
    chapter_no: int,
    prose: str,
    characters: list[Character],
    provider: ModelProvider,
    cfg: ModelConfig,
) -> ChapterUpdates:
    roster_block = "\n".join(f"- {c.id} ({c.name})" for c in characters)
    # EXTRACTOR_SYSTEM carries a literal JSON-schema block plus {roster_block} → str.replace
    # (not .format) to avoid escaping every literal brace.
    system = EXTRACTOR_SYSTEM.replace("{roster_block}", roster_block)
    # EXTRACTOR_USER contains only placeholders, no literal JSON braces → .format is safe.
    user = EXTRACTOR_USER.format(
        chapter_no=chapter_no,
        roster_block=roster_block,
        prose=prose,
    )
    messages: list[dict[str, object]] = [
        {"role": "system", "agent": "extractor", "content": system},
        {"role": "user", "agent": "extractor", "content": user},
    ]
    # Same retry-with-error-feedback contract as Agent.run(): live models
    # occasionally emit JSON with syntax slips, and one malformed payload must
    # not discard an already-written chapter (extraction precedes the file commit).
    last_err: ValidationError | None = None
    for _attempt in range(MAX_RETRIES + 1):
        try:
            payload = provider.complete_structured(messages, _UpdatePayload, cfg)
            assert isinstance(payload, _UpdatePayload)
            return ChapterUpdates(
                character_states=payload.character_states,
                voice_samples=payload.voice_samples,
                mannerisms_used=payload.mannerisms_used,
                key_events=payload.key_events,
                threads_advanced=payload.threads_advanced,
                new_information_revealed=payload.new_information_revealed,
            )
        except ValidationError as e:
            last_err = e
            messages = messages + [
                {"role": "assistant", "agent": "extractor", "content": "<invalid output>"},
                {
                    "role": "user",
                    "agent": "extractor",
                    "content": f"Your output failed validation: {e}. "
                               "Fix the JSON syntax and return ONLY the valid JSON object.",
                },
            ]
    assert last_err is not None
    raise last_err
