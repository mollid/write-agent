from novel.models import (
    Arc,  # noqa: F401
    ChapterBeat,
    Character,
    CharacterState,
    Concept,
    Event,  # noqa: F401
    EventStatus,  # noqa: F401
    Foreshadow,  # noqa: F401
    ForeshadowStatus,
    Outline,  # noqa: F401
    ReviewDimension,
    ReviewScore,
    World,  # noqa: F401
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

def test_foreshadow_status_enum():
    assert ForeshadowStatus("open") == ForeshadowStatus.OPEN

def test_review_score_pass_logic_data():
    rs = ReviewScore(artifact_ref="outline", attempt=1,
                     dimensions=[ReviewDimension(name="structure", score=85, critique=""),
                                 ReviewDimension(name="pacing", score=70, critique="slow")])
    assert min(d.score for d in rs.dimensions) == 70
