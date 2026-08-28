"""Bible read/validate/diff helpers + /bible API endpoints."""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from novel.models import Concept, World
from novel.project import NovelProject
from novel.store.bible import StoryBible
from novel.ui import jobs as J
from novel.ui.app import create_app
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


# ---------- run_bible_chat_job / run_outline_extend_job (demo mode) ----------


def _seed_concept(bible):
    bible.set_concept(Concept(logline="L", genre="g", tone="t",
                              target_length_words=100, audience="a"))


def test_chat_job_demo_echo_applies(bible, monkeypatch):
    _seed_concept(bible)
    seen: list[dict] = []

    def fake_gate(self, label, artifact):
        seen.append({"label": label, "artifact": artifact})
        return True, None

    monkeypatch.setattr(J.Job, "gate_with_feedback", fake_gate)
    events: list[dict] = []
    fn = J.run_bible_chat_job(bible.proj.root, "concept", "让基调更黑暗")
    job = J.Job("n", "bible_chat", fn)
    job._bus = None
    # capture emits by wrapping emit
    orig_emit = job.emit
    job.emit = lambda ev: (events.append(ev), orig_emit(ev))[1]  # type: ignore[method-assign]
    job.thread = threading.Thread(target=job._run, daemon=True)
    job.thread.start()
    job.thread.join(timeout=5)
    assert not job.thread.is_alive()
    assert job.status == "done"
    assert seen[0]["label"] == "bible:concept"
    assert any(e["type"] == "bible_proposal" for e in events)
    assert any(e["type"] == "bible_applied" for e in events)
    # demo echo: content unchanged
    assert bible.get_concept().logline == "L"


def test_chat_job_rejected_without_feedback_keeps_bible(bible, monkeypatch):
    _seed_concept(bible)
    monkeypatch.setattr(J.Job, "gate_with_feedback", lambda self, label, a: (False, None))
    fn = J.run_bible_chat_job(bible.proj.root, "concept", "改")
    job = J.Job("n", "bible_chat", fn)
    job._bus = None
    job.thread = threading.Thread(target=job._run, daemon=True)
    job.thread.start()
    job.thread.join(timeout=5)
    assert bible.get_concept().tone == "t"  # unchanged


def test_extend_job_demo_appends_and_unlocks(bible, monkeypatch, tmp_path):
    _seed_concept(bible)
    bible.set_world(World(setting="city"))
    from novel.models import Arc, ChapterBeat, ChapterOutline, Character, Outline
    beat = ChapterBeat(pov="c1", setting="tavern", event="e", emotional_turn="d",
                       characters=["c1"])
    bible.upsert_character(Character(id="c1", slug="ara", name="Ara", role="protagonist",
                                     backstory="b", motivation="m", arc="a"))
    bible.set_outline(Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])]))
    monkeypatch.setattr(J.Job, "gate_with_feedback", lambda self, label, a: (True, None))
    fn = J.run_outline_extend_job(bible.proj.root, 2)
    job = J.Job("n", "bible_extend", fn)
    job._bus = None
    job.thread = threading.Thread(target=job._run, daemon=True)
    job.thread.start()
    job.thread.join(timeout=5)
    out = bible.get_outline()
    nums = [c.chapter_no for a in out.arcs for c in a.chapters]
    assert nums == [1, 2, 3]
    from novel.resume import next_start_chapter
    from novel.store.reviews import ReviewStore
    # no chapters on disk yet; write one complete to prove unlock
    (bible.proj.root / "chapters" / "001.md").write_text("x" * 80, encoding="utf-8")
    assert next_start_chapter(bible.proj, ReviewStore(bible.proj)) == 2


# ---------- HTTP endpoints ----------


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(tmp_path))


def _seed(client):
    client.post("/api/projects", json={"name": "po"})
    client.put("/api/projects/po/bible/concept", json={
        "logline": "L", "genre": "g", "tone": "t", "target_length_words": 100, "audience": "a"})


def _seed_full(client):
    _seed(client)
    client.put("/api/projects/po/bible/world", json={"setting": "city"})
    client.put("/api/projects/po/bible/characters", json=[
        {"id": "c1", "slug": "ara", "name": "Ara", "role": "protagonist",
         "backstory": "b", "motivation": "m", "arc": "a"}])
    client.put("/api/projects/po/bible/outline", json={
        "arcs": [{"arc_name": "A", "chapters": [
            {"chapter_no": 1, "chapter_title": "T1", "beats": [
                {"pov": "c1", "setting": "tavern", "event": "e",
                 "emotional_turn": "d", "characters": ["c1"]}]}]}]})


def test_get_bible_full_shape(client):
    client.post("/api/projects", json={"name": "po"})
    r = client.get("/api/projects/po/bible")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"concept", "world", "characters", "outline", "foreshadows", "events"}
    assert data["concept"] is None and data["events"] == []


def test_put_section_validates_and_persists(client):
    _seed(client)
    assert client.get("/api/projects/po/bible").json()["concept"]["logline"] == "L"
    bad = client.put("/api/projects/po/bible/concept", json={"logline": "x"})
    assert bad.status_code == 422
    ro = client.put("/api/projects/po/bible/events", json=[])
    assert ro.status_code == 400
    unk = client.put("/api/projects/po/bible/nope", json={})
    assert unk.status_code == 400


def _wait_job_like(client, job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["gates"] or data["status"] != "running":
            return data
        time.sleep(0.05)
    raise AssertionError("gate never appeared")


def _poll_done(client, job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["status"] != "running":
            return data["status"]
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def test_chat_and_extend_endpoints_202(client):
    _seed(client)
    r = client.post("/api/projects/po/bible/chat",
                    json={"section": "concept", "instruction": "更黑暗"})
    assert r.status_code == 202 and "job_id" in r.json()
    job_id = r.json()["job_id"]
    # demo mode: no auto-approve — the job blocks on its gate
    data = _wait_job_like(client, job_id)
    assert client.post(f"/api/gates/{data['gates'][0]['id']}",
                       json={"approve": True}).status_code == 200
    assert _poll_done(client, job_id) == "done"

    _seed_full(client)
    r2 = client.post("/api/projects/po/outline/extend", json={"n": 2})
    assert r2.status_code == 202 and "job_id" in r2.json()
    j2 = r2.json()["job_id"]
    data2 = _wait_job_like(client, j2)
    assert data2["gates"][0]["label"] == "bible:outline_extend"
    assert client.post(f"/api/gates/{data2['gates'][0]['id']}",
                       json={"approve": True}).status_code == 200
    assert _poll_done(client, j2) == "done"
    outline = client.get("/api/projects/po/bible").json()["outline"]
    nums = [c["chapter_no"] for a in outline["arcs"] for c in a["chapters"]]
    assert nums == [1, 2, 3]


def test_chat_endpoint_gate_flow(client):
    _seed(client)
    job_id = client.post("/api/projects/po/bible/chat",
                         json={"section": "concept", "instruction": "更黑暗"}).json()["job_id"]
    data = _wait_job_like(client, job_id)
    assert data["gates"][0]["label"] == "bible:concept"
    assert client.post(f"/api/gates/{data['gates'][0]['id']}",
                       json={"approve": True}).status_code == 200
    status = _poll_done(client, job_id)
    assert status == "done"
    # demo echo: content unchanged, still applied
    assert client.get("/api/projects/po/bible").json()["concept"]["logline"] == "L"


def test_chat_rejects_bad_section_and_empty_instruction(client):
    _seed(client)
    assert client.post("/api/projects/po/bible/chat",
                       json={"section": "nope", "instruction": "x"}).status_code == 422
    assert client.post("/api/projects/po/bible/chat",
                       json={"section": "concept", "instruction": " "}).status_code == 422


def test_chat_foreshadows_rejected(client):
    _seed_full(client)
    r = client.post("/api/projects/po/bible/chat",
                    json={"section": "foreshadows", "instruction": "x"})
    assert r.status_code == 422
    assert r.json()["detail"] == "伏笔暂不支持对话改写，请使用编辑 JSON"


def test_chat_characters_requires_character_id(client):
    _seed_full(client)
    r = client.post("/api/projects/po/bible/chat",
                    json={"section": "characters", "instruction": "x"})
    assert r.status_code == 422
    assert r.json()["detail"] == "请先选择人物"
    r2 = client.post("/api/projects/po/bible/chat",
                     json={"section": "characters", "instruction": "x",
                           "character_id": "  "})
    assert r2.status_code == 422
    assert r2.json()["detail"] == "请先选择人物"


def test_chat_characters_unknown_id_rejected(client):
    _seed_full(client)
    r = client.post("/api/projects/po/bible/chat",
                    json={"section": "characters", "instruction": "x",
                          "character_id": "nope"})
    assert r.status_code == 422
    assert r.json()["detail"] == "人物不存在: nope"


def test_chat_missing_section_rejected(client):
    client.post("/api/projects", json={"name": "po"})  # concept empty too
    r = client.post("/api/projects/po/bible/chat",
                    json={"section": "concept", "instruction": "x"})
    assert r.status_code == 422
    assert r.json()["detail"] == "该设定尚未生成，无法对话改写"
    _seed(client)  # concept only, world still missing
    r2 = client.post("/api/projects/po/bible/chat",
                     json={"section": "world", "instruction": "x"})
    assert r2.status_code == 422
    assert r2.json()["detail"] == "该设定尚未生成，无法对话改写"


def test_extend_job_demo_with_empty_roster(bible, monkeypatch):
    _seed_concept(bible)
    bible.set_world(World(setting="city"))
    from novel.models import Arc, ChapterBeat, ChapterOutline, Outline
    beat = ChapterBeat(pov="c1", setting="tavern", event="e", emotional_turn="d",
                       characters=["c1"])
    bible.set_outline(Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=1, chapter_title="T1", beats=[beat])])]))
    monkeypatch.setattr(J.Job, "gate_with_feedback", lambda self, label, a: (True, None))
    fn = J.run_outline_extend_job(bible.proj.root, 1)
    job = J.Job("n", "bible_extend", fn)
    job._bus = None
    job.thread = threading.Thread(target=job._run, daemon=True)
    job.thread.start()
    job.thread.join(timeout=5)
    assert job.status == "done"
    nums = [c.chapter_no for a in bible.get_outline().arcs for c in a.chapters]
    assert nums == [1, 2]


def test_extend_requires_outline(client):
    client.post("/api/projects", json={"name": "po"})
    r = client.post("/api/projects/po/outline/extend", json={"n": 2})
    assert r.status_code == 422


def test_put_conflicts_with_active_job(client):
    _seed(client)
    job_id = client.post("/api/projects/po/bible/chat",
                         json={"section": "concept", "instruction": "改"}).json()["job_id"]
    _wait_job_like(client, job_id)  # job now parked on its gate
    r = client.put("/api/projects/po/bible/concept", json={
        "logline": "L2", "genre": "g", "tone": "t", "target_length_words": 1, "audience": "a"})
    assert r.status_code == 409
    assert client.get(f"/api/jobs/{job_id}").json()["gates"]  # still parked


def test_bible_put_characters_snapshots_previous_roster(client, tmp_path):
    """Manual roster replacement via PUT leaves a recoverable snapshot under
    .meta/bible_versions/ — settings overwrites are never silent again."""
    client.post("/api/projects", json={"name": "vb"})
    _seed(client)
    first = [{"id": "c1", "slug": "ara", "name": "Ara", "role": "protagonist",
              "backstory": "b", "motivation": "m", "arc": "a"}]
    assert client.put("/api/projects/vb/bible/characters", json=first).status_code == 200
    replaced = [{"id": "c1", "slug": "ara", "name": "Ara-v2", "role": "protagonist",
                 "backstory": "b", "motivation": "m", "arc": "a"}]
    assert client.put("/api/projects/vb/bible/characters", json=replaced).status_code == 200
    import json as _json
    backups = list((tmp_path / "vb" / ".meta" / "bible_versions").glob("characters-*.json"))
    assert len(backups) == 1
    roster = _json.loads(backups[0].read_text(encoding="utf-8"))
    assert roster[0]["name"] == "Ara"
