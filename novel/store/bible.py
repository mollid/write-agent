from __future__ import annotations

import json
from pathlib import Path

from novel.memory.extractor import ChapterUpdates
from novel.models import (
    ChapterBeat,
    Character,
    Concept,
    Event,
    Foreshadow,
    ForeshadowStatus,
    Mannerism,
    Outline,
    World,
)
from novel.project import NovelProject

VOICE_SAMPLE_K = 10   # earliest 1 (定调) + most recent 9 per character
MANNERISMS_CAP = 8    # keep highest used_count


def _compact_voice(vf: dict[str, str]) -> dict[str, str]:
    if len(vf) <= VOICE_SAMPLE_K:
        return vf

    def ch_no(key: str) -> int:
        suffix = key.rsplit("_", 1)[-1]
        return int(suffix) if suffix.isdigit() else -1

    keys = sorted(vf, key=ch_no)
    keep = {keys[0]} | set(keys[-(VOICE_SAMPLE_K - 1):])
    return {k: vf[k] for k in sorted(keep, key=ch_no)}


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

    def get_concept(self) -> Concept | None:
        raw = self._load().get("concept")
        return Concept.model_validate(raw) if raw else None

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

    # ---- per-chapter batch application (spec §4.4) ----
    def apply_chapter_updates(self, chapter_no: int, upd: ChapterUpdates,
                              beats: list[ChapterBeat]) -> None:
        """All per-chapter state changes in ONE canonical load-modify-save
        (the old per-field path rewrote the whole file 3+ times per chapter)."""
        d = self._load()
        chars = {c["id"]: c for c in d.setdefault("characters", [])}
        for cid, st in upd.character_states.items():
            if cid in chars:
                obj = Character.model_validate(chars[cid])
                obj.state = st
                obj.last_updated_chapter = chapter_no
                chars[cid] = obj.model_dump()
        for cid, sample in upd.voice_samples.items():
            if cid in chars:
                obj = Character.model_validate(chars[cid])
                obj.voice_fingerprint[f"sample_{chapter_no}"] = sample
                obj.voice_fingerprint = _compact_voice(obj.voice_fingerprint)
                chars[cid] = obj.model_dump()
        for cid, man_list in upd.mannerisms_used.items():
            if cid not in chars:
                continue
            obj = Character.model_validate(chars[cid])
            for man in man_list:
                existing = next((m for m in obj.mannerisms if m.text == man), None)
                if existing:
                    existing.used_count += 1
                else:
                    obj.mannerisms.append(Mannerism(text=man, used_count=1))
            if len(obj.mannerisms) > MANNERISMS_CAP:
                obj.mannerisms = sorted(obj.mannerisms, key=lambda m: -m.used_count)[:MANNERISMS_CAP]
            chars[cid] = obj.model_dump()
        d["characters"] = list(chars.values())
        self._save(d)
        for i, ke in enumerate(upd.key_events):
            self.append_event(Event(
                id=f"evt_{chapter_no}_{i + 1}", chapter=chapter_no, summary=ke.event,
                characters=list(ke.affected_characters)))
        self._apply_plants_and_payoffs(chapter_no, beats)

    def _apply_plants_and_payoffs(self, chapter_no: int, beats: list[ChapterBeat]) -> None:
        path = self._mirror_dir / "foreshadowing.json"
        items = json.loads(path.read_text(encoding="utf-8") or "[]")
        resolved_path = self.proj.root / ".meta" / "threads_resolved.jsonl"
        resolved: list[str] = []
        for beat in beats:
            for plant in beat.plants:
                fid = f"plant-{plant}"
                if not any(i["id"] == fid for i in items):
                    items.append(Foreshadow(id=fid, description=plant,
                                            planted_ch=chapter_no).model_dump())
            for payoff in beat.payoffs:
                open_fs = [Foreshadow.model_validate(i) for i in items
                           if i.get("status", ForeshadowStatus.OPEN.value) != ForeshadowStatus.PAID_OFF.value
                           and (payoff in i.get("description", "") or i.get("description", "") in payoff)]
                if open_fs:
                    target = open_fs[0]
                    items = [i for i in items if i["id"] != target.id]
                    target.payoff_ch = chapter_no
                    target.status = ForeshadowStatus.PAID_OFF
                    resolved.append(target.model_dump_json())
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        if resolved:
            resolved_path.parent.mkdir(parents=True, exist_ok=True)
            with resolved_path.open("a", encoding="utf-8") as fh:
                for line in resolved:
                    fh.write(line + "\n")

    # ---- events (jsonl append-only) ----
    def append_event(self, e: Event) -> None:
        path = self._mirror_dir / "events.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(e.model_dump_json() + "\n")

    def list_events(self, last: int | None = None) -> list[Event]:
        path = self._mirror_dir / "events.jsonl"
        if not path.exists():
            return []
        if last is None:
            lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        else:
            from collections import deque
            with path.open(encoding="utf-8") as fh:
                lines = [ln for ln in deque(fh, maxlen=last) if ln.strip()]
        return [Event.model_validate_json(ln) for ln in lines]
