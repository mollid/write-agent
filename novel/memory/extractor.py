from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from novel.config import ModelConfig
from novel.models import Character, CharacterState, Event
from novel.providers import ModelProvider


class _UpdatePayload(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    character_states: dict[str, CharacterState] = Field(default_factory=dict)
    voice_samples: dict[str, str] = Field(default_factory=dict)
    mannerisms_used: dict[str, str] = Field(default_factory=dict)
    events: list[Event] = Field(default_factory=list)


@dataclass
class ChapterUpdates:
    character_states: dict[str, CharacterState] = field(default_factory=dict)
    voice_samples: dict[str, str] = field(default_factory=dict)
    mannerisms_used: dict[str, str] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)


def extract_updates(
    chapter_no: int,
    prose: str,
    characters: list[Character],
    provider: ModelProvider,
    cfg: ModelConfig,
) -> ChapterUpdates:
    roster = "\n".join(f"- {c.id} ({c.name})" for c in characters)
    messages: list[dict[str, object]] = [
        {
            "role": "system",
            "agent": "extractor",
            "content": (
                "Extract structured updates from this chapter: each involved character's new state, "
                "a voice sample, any mannerism used, and the key events that happened."
            ),
        },
        {
            "role": "user",
            "agent": "extractor",
            "content": f"chapter {chapter_no}\ncharacters:\n{roster}\n\nprose:\n{prose}",
        },
    ]
    payload = provider.complete_structured(messages, _UpdatePayload, cfg)
    assert isinstance(payload, _UpdatePayload)
    return ChapterUpdates(
        character_states=payload.character_states,
        voice_samples=payload.voice_samples,
        mannerisms_used=payload.mannerisms_used,
        events=payload.events,
    )
