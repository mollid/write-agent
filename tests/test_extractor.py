from novel.memory.extractor import ChapterUpdates, extract_updates
from novel.models import Character, CharacterState, Event
from novel.providers import FakeProvider, ModelConfig


def test_extract_updates_via_fake_provider():
    upd = ChapterUpdates(
        character_states={"c1": CharacterState(location="docks", emotion="afraid")},
        voice_samples={"c1": "speaks in short clipped sentences"},
        mannerisms_used={"c1": "clenches fist"},
        events=[Event(id="e9", chapter=3, summary="Ara flees the guild")],
    )
    p = FakeProvider(responses={"extractor": upd}, tag_key="agent")
    chars = [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                       backstory="", motivation="", arc="")]
    out = extract_updates(chapter_no=3, prose="some prose", characters=chars,
                          provider=p, cfg=ModelConfig("zhipu", "x"))
    assert out.character_states["c1"].location == "docks"
    assert out.events[0].id == "e9"
