from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ForeshadowStatus(str, Enum):
    OPEN = "open"
    PLANTED = "planted"
    PAID_OFF = "paid_off"


class EventStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class Concept(BaseModel):
    logline: str
    genre: str
    tone: str
    themes: list[str] = Field(default_factory=list)
    target_length_words: int
    audience: str


class StyleGuide(BaseModel):
    tone: str = ""
    pov: str = ""
    prose_notes: str = ""


class Faction(BaseModel):
    name: str
    ideology: str = ""
    resources: str = ""
    conflict_with: str = ""


class Location(BaseModel):
    name: str
    description: str = ""
    narrative_function: str = ""


class World(BaseModel):
    setting: str
    era: str = ""
    rules: list[str] = Field(default_factory=list)
    power_system: str = ""
    factions: list[Faction] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)


class CharacterState(BaseModel):
    location: str = ""
    knowledge: list[str] = Field(default_factory=list)
    relationships: dict[str, str] = Field(default_factory=dict)
    emotion: str = ""
    inventory: list[str] = Field(default_factory=list)


class Mannerism(BaseModel):
    text: str
    used_count: int = 0


class Character(BaseModel):
    id: str
    slug: str
    name: str
    role: str
    backstory: str
    motivation: str
    arc: str
    voice_fingerprint: dict[str, str] = Field(default_factory=dict)
    mannerisms: list[Mannerism] = Field(default_factory=list)
    description_history: list[str] = Field(default_factory=list)
    relationships: dict[str, str] = Field(default_factory=dict)
    state: CharacterState = Field(default_factory=CharacterState)


class ChapterBeat(BaseModel):
    beat_id: str = ""
    pov: str
    setting: str
    event: str
    emotional_turn: str
    characters: list[str] = Field(default_factory=list)
    plants: list[str] = Field(default_factory=list)
    payoffs: list[str] = Field(default_factory=list)


class ChapterOutline(BaseModel):
    chapter_no: int
    chapter_title: str = ""
    beats: list[ChapterBeat] = Field(default_factory=list)


class Arc(BaseModel):
    arc_name: str
    chapters: list[ChapterOutline] = Field(default_factory=list)


class ForeshadowLedgerEntry(BaseModel):
    id: str
    planted_in: str = ""
    paid_off_in: str = ""
    description: str = ""


class Outline(BaseModel):
    arcs: list[Arc] = Field(default_factory=list)
    foreshadow_ledger: list[ForeshadowLedgerEntry] = Field(default_factory=list)


class Foreshadow(BaseModel):
    id: str
    description: str
    planted_ch: int | None = None
    payoff_ch: int | None = None
    status: ForeshadowStatus = ForeshadowStatus.OPEN


class Event(BaseModel):
    id: str
    chapter: int
    characters: list[str] = Field(default_factory=list)
    location: str = ""
    summary: str
    consequences: list[str] = Field(default_factory=list)
    secrets_revealed: list[str] = Field(default_factory=list)
    caused_by: list[str] = Field(default_factory=list)
    leads_to: list[str] = Field(default_factory=list)
    status: EventStatus = EventStatus.OPEN
    foreshadow_tags: list[str] = Field(default_factory=list)


class DimensionScore(BaseModel):
    score: int
    critique: str = ""


class ReviewScore(BaseModel):
    artifact_type: str = ""
    scores: dict[str, DimensionScore] = Field(default_factory=dict)
    overall: int = 0
    summary: str = ""
    attempt: int = 1          # pipeline-managed
    passed: bool = False      # set by decide()
