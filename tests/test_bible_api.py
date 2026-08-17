"""Bible read/validate/diff helpers + /bible API endpoints."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from novel.models import Concept, World
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.ui.jobs import (
    json_diff,
    read_bible_section,
    save_bible_section,
    validate_bible_section,
)


@pytest.fixture()
def bible(tmp_path):
    proj = NovelProject.scaffold("n", genre="fantasy", root=tmp_path)
    return StoryBible(proj)


def test_read_concept_missing_returns_none(bible):
    assert read_bible_section(bible, "concept") is None


def test_validate_roundtrip(bible):
    concept = validate_bible_section("concept", {
        "logline": "L", "genre": "g", "tone": "t", "target_length_words": 100, "audience": "a"})
    assert isinstance(concept, Concept)
    save_bible_section(bible, "concept", concept)
    back = read_bible_section(bible, "concept")
    assert isinstance(back, Concept) and back.logline == "L"


def test_validate_rejects_bad_section_and_readonly(bible):
    with pytest.raises(ValueError, match="unknown section"):
        validate_bible_section("events", {})
    with pytest.raises(ValueError, match="unknown section"):
        validate_bible_section("nope", {})


def test_validate_reports_pydantic_error(bible):
    with pytest.raises(ValidationError):
        validate_bible_section("world", {"rules": "not-a-list"})


def test_json_diff_marks_changed_lines():
    old = World(setting="cold city").model_dump()
    new = World(setting="cold city", era="winter").model_dump()
    d = json_diff(old, new)
    assert "-  \"era\": \"\"," in d
    assert "+  \"era\": \"winter\"," in d
    assert "\"setting\": \"cold city\"" in d
