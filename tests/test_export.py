from novel.export import export_markdown
from novel.project import NovelProject


def test_export_concatenates_chapters(tmp_path):
    proj = NovelProject.scaffold("n", genre="g", root=tmp_path)
    (proj.root / "chapters" / "001.md").write_text("first chapter", encoding="utf-8")
    (proj.root / "chapters" / "002.md").write_text("second chapter", encoding="utf-8")
    out = export_markdown(proj)
    text = out.read_text(encoding="utf-8")
    assert "first chapter" in text and "second chapter" in text
    assert out.name == "novel.md"