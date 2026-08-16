"""Tests for artifact_text rendering (gate/setup artifacts -> displayable text)."""
from __future__ import annotations

import json

from novel.models import Character
from novel.render import artifact_text


def test_base_model_pretty_json():
    concept = Character(id="c1", slug="ara", name="Ara", role="protagonist",
                        backstory="b", motivation="m", arc="a")
    out = artifact_text(concept)
    data = json.loads(out)
    assert data["id"] == "c1"
    assert "\n" in out and '  "' in out  # pretty-printed, indented


def test_list_of_models_pretty_json_array():
    chars = [
        Character(id="c1", slug="ara", name="Ara", role="protagonist",
                  backstory="b", motivation="m", arc="a"),
        Character(id="c2", slug="bo", name="Bo", role="ally",
                  backstory="b2", motivation="m2", arc="a2"),
    ]
    out = artifact_text(chars)
    data = json.loads(out)
    assert [d["id"] for d in data] == ["c1", "c2"]
    assert "\n" in out  # not a python repr / compact dump
    assert "Character(" not in out


def test_scalar_passthrough():
    assert artifact_text(3) == "3"
    assert artifact_text(None) == "None"
    assert artifact_text([1, 2]) == "[1, 2]"  # non-model list stays str()
