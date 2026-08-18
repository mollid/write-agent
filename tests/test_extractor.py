import pytest

from novel.memory.extractor import (
    EXTRACTOR_SYSTEM,
    EXTRACTOR_USER,
    ChapterUpdates,
    extract_updates,
)
from novel.models import Character, CharacterState, KeyEvent
from novel.providers import FakeProvider, ModelConfig


def _chars():
    return [Character(id="c1", slug="ara", name="Ara", role="protagonist",
                      backstory="", motivation="", arc="")]


def test_extract_updates_via_fake_provider():
    upd = ChapterUpdates(
        character_states={"c1": CharacterState(
            emotional_state="afraid", physical_state="wounded",
            knowledge_gained=["the bell is cracked"],
            relationships_shifted={"ant-voss": "trust -> suspicion"},
            location_end="docks")},
        voice_samples={"c1": "speaks in short clipped sentences"},
        mannerisms_used={"c1": ["clenches fist", "avoids eye contact"]},
        key_events=[KeyEvent(event="Ara flees the guild",
                              significance="first open act of rebellion",
                              affected_characters=["c1"])],
        threads_advanced=["fs-01"],
        new_information_revealed=["Voss is the traitor"],
    )
    p = FakeProvider(responses={"extractor": upd}, tag_key="agent")
    out = extract_updates(chapter_no=3, prose="some prose", characters=_chars(),
                          provider=p, cfg=ModelConfig("zhipu", "x"))
    assert out.character_states["c1"].emotional_state == "afraid"
    assert out.character_states["c1"].location_end == "docks"
    assert out.mannerisms_used["c1"] == ["clenches fist", "avoids eye contact"]
    assert out.key_events[0].event == "Ara flees the guild"
    assert out.key_events[0].affected_characters == ["c1"]
    assert out.threads_advanced == ["fs-01"]
    assert out.new_information_revealed == ["Voss is the traitor"]


def test_extract_updates_dropped_events_field():
    # v2 payload no longer carries an `events` field; key_events is the analog.
    upd = ChapterUpdates(mannerisms_used={"c1": ["taps the table"]},
                         key_events=[KeyEvent(event="the bell rings")])
    assert not hasattr(upd, "events")
    assert upd.key_events[0].event == "the bell rings"


def test_chapter_updates_defaults_empty():
    upd = ChapterUpdates()
    assert upd.character_states == {}
    assert upd.voice_samples == {}
    assert upd.mannerisms_used == {}
    assert upd.key_events == []
    assert upd.threads_advanced == []
    assert upd.new_information_revealed == []


def test_extractor_build_messages_injects_roster_and_prose():
    p = FakeProvider(responses={"extractor": ChapterUpdates()}, tag_key="agent")
    msgs = extract_updates(chapter_no=7, prose="Ara stood by the bell.",
                           characters=_chars(), provider=p,
                           cfg=ModelConfig("zhipu", "x"))
    _ = msgs  # returned ChapterUpdates; build_messages exercised inside
    # Inspect the underlying messages the provider saw by replaying the call path
    # via a capturing provider.
    captured: list[dict[str, object]] = []

    class _Capture:
        tag_key = "agent"

        def complete_structured(self, messages, schema, cfg, *, seed=None):
            captured.extend(messages)
            return schema.model_validate({})

    extract_updates(chapter_no=7, prose="Ara stood by the bell.", characters=_chars(),
                    provider=_Capture(), cfg=ModelConfig("zhipu", "x"))  # type: ignore[arg-type]
    system, user = captured[0]["content"], captured[1]["content"]
    assert "narrative state-tracker" in system
    assert "ID discipline" in system
    assert '"key_events"' in system
    assert '"mannerisms_used"' in system
    # roster_block for extractor is id+name only (no role)
    assert "- c1 (Ara)" in system
    assert "- c1 (Ara): protagonist" not in system
    assert system.rstrip().endswith("Return ONLY the JSON object.")
    assert "<chapter_number>7</chapter_number>" in user
    assert "<roster>" in user and "</roster>" in user
    assert "- c1 (Ara)" in user
    assert "Ara stood by the bell." in user
    assert user.rstrip().endswith("</prose>")


def test_extract_updates_retries_on_malformed_json_then_succeeds():
    # live models occasionally emit JSON with syntax slips (missing ':',
    # trailing commas); one bad payload must not kill the chapter job.
    calls: list[list[dict[str, object]]] = []

    class _Flaky:
        tag_key = "agent"

        def __init__(self) -> None:
            self.n = 0

        def complete_structured(self, messages, schema, cfg, *, seed=None):
            calls.append(list(messages))
            self.n += 1
            if self.n == 1:
                # syntax error inside the JSON body — same failure mode as the
                # reported ValidationError (expected `:` at line/column)
                return schema.model_validate_json(
                    '{\n "character_states": {\n  "c1"\n }\n}')
            return schema.model_validate({"new_information_revealed": ["the bell is cracked"]})

    out = extract_updates(chapter_no=2, prose="prose", characters=_chars(),
                          provider=_Flaky(), cfg=ModelConfig("zhipu", "x"))  # type: ignore[arg-type]
    assert out.new_information_revealed == ["the bell is cracked"]
    assert len(calls) == 2
    # the retry carries the validation error back to the model as feedback
    assert "failed validation" in str(calls[1][-1]["content"])


def test_extract_updates_raises_after_exhausted_retries():
    class _AlwaysBad:
        tag_key = "agent"

        def complete_structured(self, messages, schema, cfg, *, seed=None):
            return schema.model_validate_json("{not json")

    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        extract_updates(chapter_no=2, prose="prose", characters=_chars(),
                        provider=_AlwaysBad(), cfg=ModelConfig("zhipu", "x"))  # type: ignore[arg-type]


def test_extractor_prompts_match_spec_shape():
    # Verbatim identity anchors from spec §9.
    assert EXTRACTOR_SYSTEM.startswith(
        "You are a narrative state-tracker maintaining a living story database."
    )
    assert "{roster_block}" in EXTRACTOR_SYSTEM  # placeholder still present pre-injection
    assert '"emotional_state"' in EXTRACTOR_SYSTEM
    assert '"physical_state"' in EXTRACTOR_SYSTEM
    assert '"knowledge_gained"' in EXTRACTOR_SYSTEM
    assert '"relationships_shifted"' in EXTRACTOR_SYSTEM
    assert '"location_end"' in EXTRACTOR_SYSTEM
    assert '"key_events"' in EXTRACTOR_SYSTEM
    assert '"threads_advanced"' in EXTRACTOR_SYSTEM
    assert '"new_information_revealed"' in EXTRACTOR_SYSTEM
    assert EXTRACTOR_USER.startswith("<chapter_number>{chapter_no}</chapter_number>")
    assert "{roster_block}" in EXTRACTOR_USER
    assert "{prose}" in EXTRACTOR_USER
