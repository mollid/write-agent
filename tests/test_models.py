import pytest
from pydantic import ValidationError

from novel.models import (
    Arc,
    ChapterBeat,
    ChapterOutline,
    Character,
    CharacterState,
    Concept,
    Event,  # noqa: F401
    EventStatus,  # noqa: F401
    Faction,
    Foreshadow,  # noqa: F401
    ForeshadowLedgerEntry,
    ForeshadowStatus,
    Location,
    Outline,
    ReviewDimension,
    ReviewScore,
    World,
)


def test_concept_round_trip():
    c = Concept(logline="A thief steals time.", genre="fantasy", tone="grim",
                themes=["loss"], target_length_words=30000, audience="adult")
    assert c.genre == "fantasy"
    d = c.model_dump()
    assert Concept.model_validate(d) == c

def test_character_has_mutable_state_and_mannerisms():
    ch = Character(id="c1", slug="ara", name="Ara", role="protagonist",
                   backstory="orphan", motivation="revenge", arc="vengeance to forgiveness",
                   voice_fingerprint={"formality": "low"}, mannerisms=[{"text": "bites nail", "used_count": 0}],
                   description_history=[], state=CharacterState(location="tavern"))
    ch.state.emotion = "angry"
    ch.mannerisms[0].used_count = 2
    assert ch.state.emotion == "angry"
    assert ch.mannerisms[0].used_count == 2

def test_chapter_beat_carries_foreshadow_refs():
    b = ChapterBeat(pov="Ara", setting="tavern", event="meets informant",
                    emotional_turn="doubt->resolve", characters=["c1"],
                    plants=["f1"], payoffs=[])
    assert b.plants == ["f1"]


def test_outline_v2_shape_uses_renamed_fields_and_ledger():
    beat = ChapterBeat(beat_id="c01-b01", pov="c1", setting="tavern", event="meet",
                       emotional_turn="doubt", characters=["c1"])
    arc = Arc(arc_name="Act I", chapters=[ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])
    entry = ForeshadowLedgerEntry(id="fs-01", planted_in="c01-b01", paid_off_in="c14-b02",
                                  description="the bell")
    outline = Outline(arcs=[arc], foreshadow_ledger=[entry])
    assert outline.arcs[0].arc_name == "Act I"
    assert outline.arcs[0].chapters[0].chapter_no == 1
    assert outline.arcs[0].chapters[0].chapter_title == "T1"
    assert outline.arcs[0].chapters[0].beats[0].beat_id == "c01-b01"
    assert outline.foreshadow_ledger[0].id == "fs-01"
    assert outline.foreshadow_ledger[0].planted_in == "c01-b01"

def test_foreshadow_status_enum():
    assert ForeshadowStatus("open") == ForeshadowStatus.OPEN

def test_review_score_pass_logic_data():
    rs = ReviewScore(artifact_ref="outline", attempt=1,
                     dimensions=[ReviewDimension(name="structure", score=85, critique=""),
                                 ReviewDimension(name="pacing", score=70, critique="slow")])
    assert min(d.score for d in rs.dimensions) == 70


def test_world_factions_and_locations_are_typed_objects():
    w = World.model_validate({
        "setting": "the splintered empire",
        "factions": [
            {"name": "Throne", "ideology": "order", "resources": "army",
             "conflict_with": "Reformists"},
        ],
        "locations": [
            {"name": "Belltower", "description": "tall spire",
             "narrative_function": "inciting-incident site"},
        ],
    })
    assert isinstance(w.factions[0], Faction)
    assert w.factions[0].name == "Throne"
    assert w.factions[0].conflict_with == "Reformists"
    assert isinstance(w.locations[0], Location)
    assert w.locations[0].narrative_function == "inciting-incident site"


def test_world_rejects_string_factions_and_locations():
    with pytest.raises(ValidationError):
        World(setting="x", factions=["not an object"])
    with pytest.raises(ValidationError):
        World(setting="x", locations=["not an object"])


def test_world_defaults_keep_empty_object_lists():
    w = World(setting="city of bells")
    assert w.factions == []
    assert w.locations == []
    assert all(isinstance(f, Faction) for f in w.factions)
