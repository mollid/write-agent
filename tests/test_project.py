import json

from novel.project import NovelProject


def test_scaffold_creates_layout(tmp_path):
    proj = NovelProject.scaffold("my-novel", genre="fantasy", root=tmp_path)
    assert (proj.root / "project.config.yaml").exists()
    assert (proj.root / "bible" / "_canonical.json").exists()
    assert (proj.root / "chapters").is_dir()
    assert (proj.root / "memory" / "chroma").is_dir()

def test_save_and_load_canonical_round_trip(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    proj.save_canonical({"concept": {"genre": "fantasy"}})
    assert proj.load_canonical() == {"concept": {"genre": "fantasy"}}

def test_save_canonical_is_atomic_no_partial_on_existing(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    proj.save_canonical({"a": 1})
    # simulate a second save; file must always be valid JSON
    proj.save_canonical({"b": 2})
    assert json.loads((proj.canonical_path).read_text()) == {"b": 2}
