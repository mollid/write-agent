from __future__ import annotations

import json
from pathlib import Path

from novel.models import (
    Character,
    Concept,
    Event,
    Foreshadow,
    Outline,
    World,
)
from novel.project import NovelProject


class StoryBible:
    def __init__(self, proj: NovelProject):
        self.proj = proj
        self._mirror_dir = proj.root / "bible"

    def _load(self) -> dict:
        return self.proj.load_canonical()

    def _save(self, data: dict) -> None:
        self.proj.save_canonical(data)
        self._write_mirrors(data)

    def _write_mirrors(self, data: dict) -> None:
        def md(path: Path, title: str, body: str) -> None:
            path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")

        if "concept" in data:
            c = data["concept"]
            md(
                self._mirror_dir / "concept.md",
                "Concept",
                f"**Logline:** {c['logline']}\n\n"
                f"- genre: {c['genre']}\n- tone: {c['tone']}\n- audience: {c['audience']}",
            )
        if "world" in data:
            w = data["world"]
            md(
                self._mirror_dir / "world.md",
                "World",
                f"setting: {w.get('setting','')}\n\nrules: {w.get('rules', [])}",
            )
        if "outline" in data:
            md(
                self._mirror_dir / "outline.md",
                "Outline",
                json.dumps(data["outline"], ensure_ascii=False, indent=2),
            )
        cdir = self._mirror_dir / "characters"
        cdir.mkdir(exist_ok=True)
        for ch in data.get("characters", []):
            (cdir / f"{ch['slug']}.md").write_text(
                f"# {ch['name']} ({ch['role']})\n\n"
                f"{ch['backstory']}\n\nmotivation: {ch['motivation']}\narc: {ch['arc']}\n",
                encoding="utf-8",
            )

    # ---- concept / world / outline ----
    def set_concept(self, c: Concept) -> None:
        d = self._load()
        d["concept"] = c.model_dump()
        self._save(d)

    def get_concept(self) -> Concept:
        return Concept.model_validate(self._load()["concept"])

    def set_world(self, w: World) -> None:
        d = self._load()
        d["world"] = w.model_dump()
        self._save(d)

    def get_world(self) -> World | None:
        raw = self._load().get("world")
        return World.model_validate(raw) if raw else None

    def set_outline(self, o: Outline) -> None:
        d = self._load()
        d["outline"] = o.model_dump()
        self._save(d)

    def get_outline(self) -> Outline | None:
        raw = self._load().get("outline")
        return Outline.model_validate(raw) if raw else None

    # ---- characters ----
    def upsert_character(self, ch: Character) -> None:
        d = self._load()
        chars = d.setdefault("characters", [])
        for i, existing in enumerate(chars):
            if existing["id"] == ch.id:
                chars[i] = ch.model_dump()
                break
        else:
            chars.append(ch.model_dump())
        self._save(d)

    def get_character(self, cid: str) -> Character | None:
        for c in self._load().get("characters", []):
            if c["id"] == cid:
                return Character.model_validate(c)
        return None

    def all_characters(self) -> list[Character]:
        return [Character.model_validate(c) for c in self._load().get("characters", [])]

    # ---- foreshadowing (separate json file) ----
    def add_foreshadow(self, f: Foreshadow) -> None:
        path = self._mirror_dir / "foreshadowing.json"
        items = json.loads(path.read_text(encoding="utf-8") or "[]")
        items = [i for i in items if i["id"] != f.id] + [f.model_dump()]
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_foreshadow(self) -> list[Foreshadow]:
        path = self._mirror_dir / "foreshadowing.json"
        items = json.loads(path.read_text(encoding="utf-8") or "[]")
        return [Foreshadow.model_validate(i) for i in items]

    # ---- events (jsonl append-only) ----
    def append_event(self, e: Event) -> None:
        path = self._mirror_dir / "events.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(e.model_dump_json() + "\n")

    def list_events(self) -> list[Event]:
        path = self._mirror_dir / "events.jsonl"
        if not path.exists():
            return []
        return [
            Event.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
