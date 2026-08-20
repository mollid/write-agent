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
    emotional_state: str = ""
    physical_state: str = ""
    knowledge_gained: list[str] = Field(default_factory=list)
    relationships_shifted: dict[str, str] = Field(default_factory=dict)
    location_end: str = ""


class KeyEvent(BaseModel):
    event: str
    significance: str = ""
    affected_characters: list[str] = Field(default_factory=list)


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
    last_updated_chapter: int = 0


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


class ChapterSummary(BaseModel):
    chapter_no: int
    arc_name: str = ""
    summary: str
    characters_involved: list[str] = Field(default_factory=list)
    threads_advanced: list[str] = Field(default_factory=list)
    prose_sha256: str = ""    # set by the pipeline at write time (manual-edit detection)


class ArcSummary(BaseModel):
    arc_name: str
    chapter_start: int
    chapter_end: int
    summary: str
    major_developments: list[str] = Field(default_factory=list)


class BookDigest(BaseModel):
    chapter_count: int
    current_arc: str = ""
    summary: str = ""


class ArcSkeleton(BaseModel):
    """卷骨架：章数为软目标，编号以运行时 next_chapter_no 为准（spec §4.3）。"""
    arc_name: str
    chapter_start: int
    chapter_end: int
    premise: str = ""


class ArcPlan(BaseModel):
    arcs: list[ArcSkeleton] = Field(default_factory=list)
    planned_total_chapters: int = 0


class Outline(BaseModel):
    arcs: list[Arc] = Field(default_factory=list)
    foreshadow_ledger: list[ForeshadowLedgerEntry] = Field(default_factory=list)
    arc_plan: list[ArcSkeleton] = Field(default_factory=list)


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


class ReviewRecord(BaseModel):
    """Persisted scoring event: one record per scorer invocation on a chapter."""
    chapter: int
    attempt: int
    artifact_type: str = ""
    overall: int = 0
    summary: str = ""
    scores: dict[str, DimensionScore] = Field(default_factory=dict)
    passed: bool = False
    timestamp: str = ""       # ISO-8601 UTC


class WeakDim(BaseModel):
    """One below-threshold review dimension inside a weak-spot note."""
    score: int
    critique: str = ""


class WritingNote(BaseModel):
    """Persisted writing-memory record (`.meta/writing_notes.jsonl`): either a
    human approval directive (`feedback`) or a failed review's weak spots
    (`weak`) — both replayed into later chapters' writer context."""
    kind: str                        # "feedback" | "weak"
    source: str = ""                 # feedback: gate label, e.g. "setup:world"
    text: str = ""                   # feedback: the human directive
    chapter: int | None = None       # weak: chapter the review failed on
    dims: dict[str, WeakDim] = Field(default_factory=dict)  # weak: failing dimensions
    timestamp: str = ""              # ISO-8601 UTC


class RewrittenChapter(BaseModel):
    """Chapter-rewrite agent output: the complete new prose (plus a one-line
    summary of what changed, for logs/diffs only)."""
    prose: str = Field(min_length=1)
    changes_summary: str = ""
