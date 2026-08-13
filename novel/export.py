from __future__ import annotations

from pathlib import Path

from novel.project import NovelProject


def export_markdown(proj: NovelProject, title: str = "Untitled Novel") -> Path:
    chapters_dir = proj.root / "chapters"
    files = sorted(chapters_dir.glob("[0-9][0-9][0-9].md"))
    parts = [f"# {title}\n"]
    for f in files:
        parts.append(f"\n## {f.stem}\n\n" + f.read_text(encoding="utf-8").strip() + "\n")
    out = proj.root / "novel.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
