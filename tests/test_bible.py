from novel.models import Character, Concept, Event, Foreshadow
from novel.project import NovelProject
from novel.store.bible import StoryBible


def _bible(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    return StoryBible(proj)

def test_concept_round_trip_and_md_mirror(tmp_path):
    b = _bible(tmp_path)
    c = Concept(logline="L", genre="fantasy", tone="grim", themes=["x"], target_length_words=30000, audience="a")
    b.set_concept(c)
    assert b.get_concept() == c
    assert "fantasy" in (b.proj.root / "bible" / "concept.md").read_text(encoding="utf-8")

def test_character_upsert_and_state_update(tmp_path):
    b = _bible(tmp_path)
    ch = Character(id="c1", slug="ara", name="Ara", role="protagonist", backstory="b",
                   motivation="m", arc="a")
    b.upsert_character(ch)
    ch.state.emotion = "angry"
    b.upsert_character(ch)
    assert b.get_character("c1").state.emotion == "angry"

def test_foreshadow_and_events(tmp_path):
    b = _bible(tmp_path)
    b.add_foreshadow(Foreshadow(id="f1", description="a dagger"))
    b.append_event(Event(id="e1", chapter=1, summary="meeting"))
    assert b.list_foreshadow()[0].id == "f1"
    assert b.list_events()[0].id == "e1"
