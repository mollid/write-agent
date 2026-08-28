"""Tests for the FastAPI GUI: project CRUD, demo-mode pipeline e2e, gate bridging."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel.ui import jobs
from novel.ui.app import DIST_DIR, create_app


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def _wait_job(client: TestClient, job_id: str, timeout: float = 30.0) -> dict[str, object]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200
        data = r.json()
        if data["status"] != "running":
            return data
        time.sleep(0.05)
    raise AssertionError("job did not finish in time")


def test_write_req_cap_raised() -> None:
    """WriteReq.n accepts up to 2000; values above the cap are rejected."""
    from novel.ui.app import WriteReq

    req = WriteReq(n=2000)
    assert req.n == 2000
    with pytest.raises(ValueError):
        WriteReq(n=2001)


def test_create_and_list_projects(client: TestClient, tmp_path: Path) -> None:
    r = client.get("/api/projects")
    assert r.status_code == 200 and r.json() == []
    r = client.post("/api/projects", json={"name": "demo", "genre": "sci-fi"})
    assert r.status_code == 201
    assert (tmp_path / "demo" / "bible").is_dir()
    assert {p["name"] for p in client.get("/api/projects").json()} == {"demo"}
    # duplicate name -> 409
    assert client.post("/api/projects", json={"name": "demo"}).status_code == 409
    # illegal names -> 400
    for bad in ("../evil", "a/b", "."):
        assert client.post("/api/projects", json={"name": bad}).status_code == 400


def test_unknown_project_404(client: TestClient) -> None:
    assert client.get("/api/projects/none/status").status_code == 404


def test_status_on_fresh_project(client: TestClient) -> None:
    """A scaffolded project has no concept yet; /status must not crash (regression)."""
    client.post("/api/projects", json={"name": "fresh"})
    r = client.get("/api/projects/fresh/status")
    assert r.status_code == 200
    data = r.json()
    assert data["has_concept"] is False
    assert data["has_world"] is False
    assert data["has_outline"] is False
    assert data["chapters"] == []


def test_premise_flow(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "p1"})
    r = client.post("/api/projects/p1/premise", json={"text": "a thief who steals time"})
    assert r.status_code == 202
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    status = client.get("/api/projects/p1/status").json()
    assert status["has_concept"] is True
    assert status["has_outline"] is False


def test_write_chapter_demo_e2e(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "p2"})
    job_id = client.post("/api/projects/p2/premise", json={"text": "x"}).json()["job_id"]
    assert _wait_job(client, job_id)["status"] == "done"

    r = client.post("/api/projects/p2/write-chapter", json={"n": 2})
    assert r.status_code == 202
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job["error"]

    status = client.get("/api/projects/p2/status").json()
    assert status["chapters"] == [1, 2]
    assert status["has_outline"] is True

    r = client.get("/api/projects/p2/chapters/1")
    assert r.status_code == 200 and r.json()["chapter"] == 1
    assert "Ara" in r.json()["content"]
    assert client.get("/api/projects/p2/chapters/9").status_code == 404

    threads = client.get("/api/projects/p2/threads").json()
    assert isinstance(threads, list)

    reviews = client.get("/api/projects/p2/reviews").json()
    assert len(reviews) == 2  # one per generated chapter
    assert {r["chapter"] for r in reviews} == {1, 2}
    assert reviews[0]["passed"] is True
    assert reviews[0]["scores"]["beat_adherence"]["score"] == 90
    assert reviews[0]["timestamp"]

    r = client.post("/api/projects/p2/export")
    assert r.status_code == 200
    assert Path(r.json()["path"]).is_file()


def test_concurrent_job_rejected(client: TestClient) -> None:
    import threading
    client.post("/api/projects", json={"name": "p3"})
    release = threading.Event()

    def blocking(job: jobs.Job) -> object:
        release.wait(timeout=10)
        return None

    m = jobs.JobManager()  # separate manager: app's manager is closure-private
    job = m.start("p3", "custom", blocking)
    try:
        # same-manager conflict
        with pytest.raises(RuntimeError):
            m.start("p3", "custom", blocking)
        # via API on a different project is fine, unknown job 404
        assert client.post("/api/jobs/nope/cancel").status_code == 404
    finally:
        release.set()
        job.thread.join(timeout=5)


def test_gate_bridge_approve_and_reject() -> None:
    m = jobs.JobManager()
    q = m.bus.subscribe("proj")

    def gate_job(job: jobs.Job) -> object:
        a = job.gate("outline", {"kind": "outline"})
        job.emit({"type": "custom", "value": a})
        return a

    job = m.start("proj", "custom", gate_job)
    gate_ev = None
    deadline = time.time() + 5
    while gate_ev is None and time.time() < deadline:
        for ev in jobs.drain(q, timeout=0.1):
            if ev.get("type") == "gate":
                gate_ev = ev
    assert gate_ev is not None
    assert m.resolve_gate(gate_ev["gate_id"], approved=True) is True
    job.thread.join(timeout=5)
    assert job.status == "done"

    # resolve twice -> False
    assert m.resolve_gate(gate_ev["gate_id"], approved=True) is False


def test_gate_cancel_unblocks() -> None:
    m = jobs.JobManager()
    q = m.bus.subscribe("proj2")

    def gate_job(job: jobs.Job) -> object:
        return job.gate("chapter", 3)

    job = m.start("proj2", "custom", gate_job)
    gate_ev = None
    deadline = time.time() + 5
    while gate_ev is None and time.time() < deadline:
        for ev in jobs.drain(q, timeout=0.1):
            if ev.get("type") == "gate":
                gate_ev = ev
    assert gate_ev is not None
    assert m.cancel(job.id) is True
    job.thread.join(timeout=5)
    assert job.status == "cancelled"


def test_mode_endpoint(client: TestClient) -> None:
    r = client.get("/api/mode")
    assert r.status_code == 200
    assert r.json() == {"live": False}


def test_write_chapter_rewrites_empty_chapter(client: TestClient, tmp_path: Path) -> None:
    client.post("/api/projects", json={"name": "px"})
    job_id = client.post("/api/projects/px/premise", json={"text": "x"}).json()["job_id"]
    assert _wait_job(client, job_id)["status"] == "done"
    r = client.post("/api/projects/px/write-chapter", json={"n": 2})
    assert _wait_job(client, r.json()["job_id"])["status"] == "done"

    root = tmp_path / "px"
    ch1 = root / "chapters" / "001.md"
    ch2 = root / "chapters" / "002.md"
    good2 = ch2.read_text(encoding="utf-8")
    ch1.write_text("", encoding="utf-8")  # simulate a crashed write

    r2 = client.post("/api/projects/px/write-chapter", json={"n": 1})
    job = _wait_job(client, r2.json()["job_id"])
    assert job["status"] == "done", job["error"]

    assert len(ch1.read_text(encoding="utf-8")) > 50  # rewritten
    assert ch2.read_text(encoding="utf-8") == good2  # complete chapter untouched
    status = client.get("/api/projects/px/status").json()
    assert status["chapters"] == [1, 2]


def test_run_setup_job_feedback_then_approve(tmp_path: Path) -> None:
    """Jobs layer: feedback regenerates the stage, approvals persist everything."""
    from novel.project import NovelProject
    from novel.store.bible import StoryBible

    proj = NovelProject.scaffold("sp", genre="fantasy", root=tmp_path)
    m = jobs.JobManager()
    q = m.bus.subscribe("sp")
    job = m.start("sp", "setup", jobs.run_setup_job(proj.root, "a thief"))
    try:
        import time
        deadline = time.time() + 30.0
        sent_feedback = False
        while job.thread.is_alive() and time.time() < deadline:
            gate_id = _next_gate(q, job.id)
            if gate_id is None:
                break  # job_end: all stages resolved
            if not sent_feedback:
                m.resolve_gate(gate_id, False, "主角改成女性")  # regenerate once
                sent_feedback = True
            else:
                m.resolve_gate(gate_id, True)  # approve everything else
        assert job.status == "done", job.error
        bible = StoryBible(proj)
        assert bible.get_concept() is not None and bible.get_outline() is not None
        assert bible.get_world() is not None and bible.all_characters()
    finally:
        job.thread.join(timeout=5)
    assert job.status == "done"


def _next_gate(q, job_id: str, timeout: float = 10.0) -> str | None:
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ev in jobs.drain(q, timeout=0.05):
            if ev.get("job_id") != job_id:
                continue
            if ev.get("type") == "gate":
                return str(ev["gate_id"])
            if ev.get("type") == "job_end":
                return None
        time.sleep(0.02)
    raise AssertionError("no gate event in time")


def test_setup_endpoint_requires_premise_or_concept(client: TestClient) -> None:
    """Empty premise on a fresh project (no concept) -> 422."""
    client.post("/api/projects", json={"name": "sf"})
    r = client.post("/api/projects/sf/setup", json={"premise": ""})
    assert r.status_code == 422
    assert "缺少创意" in r.json()["detail"]


def test_setup_endpoint_full_flow(client: TestClient, tmp_path: Path) -> None:
    client.post("/api/projects", json={"name": "sx"})
    r = client.post("/api/projects/sx/setup", json={"premise": "a thief"})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    gate_id = _poll_gate_via_http(client, job_id)
    # feedback -> regenerate (gate for attempt 2 of the same stage)
    assert client.post("/api/gates/" + gate_id,
                       json={"approve": False, "feedback": "基调更黑暗"}).status_code == 200
    gate_id2 = _poll_gate_via_http(client, job_id)
    assert gate_id2 != gate_id
    assert client.post("/api/gates/" + gate_id2, json={"approve": True}).status_code == 200
    # approve the remaining stages (world / characters / outline) until the job ends
    import time
    deadline = time.time() + 30.0
    data = client.get(f"/api/jobs/{job_id}").json()
    while data["status"] == "running" and time.time() < deadline:
        gates = data.get("gates", [])
        if gates:
            client.post(f"/api/gates/{gates[0]['id']}", json={"approve": True})
        time.sleep(0.05)
        data = client.get(f"/api/jobs/{job_id}").json()
    assert data["status"] == "done", data.get("error")
    status = client.get("/api/projects/sx/status").json()
    assert status["has_concept"] is True and status["has_outline"] is True
    # the human feedback persisted into writing memory: later chapters' writer
    # context will carry it as a style directive
    from novel.project import NovelProject
    from novel.store.notes import WritingNotes
    fb = WritingNotes(NovelProject(root=tmp_path / "sx")).recent_feedback()
    assert [n.text for n in fb] == ["基调更黑暗"]
    assert fb[0].source == "setup:concept"


def _poll_gate_via_http(client: TestClient, job_id: str, timeout: float = 10.0) -> str:
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/jobs/{job_id}").json()
        for g in data.get("gates", []):
            return str(g["id"])
        time.sleep(0.05)
    raise AssertionError("job exposed no pending gate")


def test_job_pending_gates_carry_artifact(client: TestClient) -> None:
    """A browser reload restores the gate modal from GET /api/jobs/{id};
    each pending gate must carry its full artifact or the modal renders
    「产物内容不可用」with nothing to approve."""
    client.post("/api/projects", json={"name": "ga"})
    job_id = client.post("/api/projects/ga/setup", json={"premise": "a thief"}).json()["job_id"]
    gate: dict[str, object] | None = None
    deadline = time.time() + 10.0
    while gate is None and time.time() < deadline:
        for g in client.get(f"/api/jobs/{job_id}").json().get("gates", []):
            gate = g
        time.sleep(0.05)
    assert gate is not None
    assert str(gate["artifact"]).lstrip().startswith("{")
    # drain the job so its thread exits before the fixture tears down
    data = client.get(f"/api/jobs/{job_id}").json()
    while data["status"] == "running":
        gates = data.get("gates", [])
        if gates:
            client.post(f"/api/gates/{gates[0]['id']}", json={"approve": True})
        time.sleep(0.05)
        data = client.get(f"/api/jobs/{job_id}").json()


def test_chapter_rewrite_flow(client: TestClient, tmp_path: Path) -> None:
    """Rewrite proposal gate: feedback round → approve → chapter updated, old
    prose backed up, vector memory upserted with the new prose."""
    client.post("/api/projects", json={"name": "rw"})
    ch = tmp_path / "rw" / "chapters" / "001.md"
    ch.write_text("第一章原文。", encoding="utf-8")
    # error paths: missing chapter / unknown mode
    assert client.post("/api/projects/rw/chapter-rewrite",
                       json={"chapter": 9, "mode": "polish", "instruction": "x"},
                       ).status_code == 404
    assert client.post("/api/projects/rw/chapter-rewrite",
                       json={"chapter": 1, "mode": "hack", "instruction": "x"},
                       ).status_code == 422
    r = client.post("/api/projects/rw/chapter-rewrite",
                    json={"chapter": 1, "mode": "polish", "instruction": "更克制"})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    gate_id = _poll_gate_via_http(client, job_id)
    # feedback → a fresh gate for round 2
    assert client.post("/api/gates/" + gate_id,
                       json={"approve": False, "feedback": "再短一点"}).status_code == 200
    gate_id2 = _poll_gate_via_http(client, job_id)
    assert gate_id2 != gate_id
    assert client.post("/api/gates/" + gate_id2, json={"approve": True}).status_code == 200
    data = _wait_job(client, job_id)
    assert data["status"] == "done", data.get("error")
    assert "演示模式改写稿" in ch.read_text(encoding="utf-8")
    backups = list((tmp_path / "rw" / ".meta" / "chapter_versions").glob("001-*.md"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "第一章原文。"
    # vector memory upserted: ch1 now carries the rewritten prose
    from novel.project import NovelProject
    from novel.store.vector import VectorMemory
    docs = VectorMemory(NovelProject(root=tmp_path / "rw")).retrieve("第1章", k=10)
    assert any("演示模式改写稿" in d for d in docs)


def test_chapter_rewrite_abandon_leaves_chapter_intact(client: TestClient, tmp_path: Path) -> None:
    client.post("/api/projects", json={"name": "rwa"})
    ch = tmp_path / "rwa" / "chapters" / "001.md"
    ch.write_text("原文保持不变。", encoding="utf-8")
    job_id = client.post("/api/projects/rwa/chapter-rewrite",
                         json={"chapter": 1, "mode": "rearrange", "instruction": "重排"}
                         ).json()["job_id"]
    gate_id = _poll_gate_via_http(client, job_id)
    # reject without feedback = abandon: nothing changes, no backup
    assert client.post("/api/gates/" + gate_id, json={"approve": False}).status_code == 200
    data = _wait_job(client, job_id)
    assert data["status"] == "done"
    assert ch.read_text(encoding="utf-8") == "原文保持不变。"
    assert not (tmp_path / "rwa" / ".meta" / "chapter_versions").exists()


def test_chapter_manual_edit(client: TestClient, tmp_path: Path) -> None:
    """PUT /chapters/{n}: manual edit saves with backup + vector upsert; guards
    404 (unknown), 422 (too short), 409 (job running)."""
    client.post("/api/projects", json={"name": "me"})
    ch = tmp_path / "me" / "chapters" / "001.md"
    ch.write_text("第一版正文。", encoding="utf-8")
    assert client.put("/api/projects/me/chapters/9",
                      json={"content": "x" * 60}).status_code == 404
    assert client.put("/api/projects/me/chapters/1",
                      json={"content": "太短"}).status_code == 422
    r = client.put("/api/projects/me/chapters/1",
                   json={"content": "手写修订后的第二版正文。" * 6})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert "手写修订" in ch.read_text(encoding="utf-8")
    backups = list((tmp_path / "me" / ".meta" / "chapter_versions").glob("001-*.md"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "第一版正文。"
    from novel.project import NovelProject
    from novel.store.vector import VectorMemory
    docs = VectorMemory(NovelProject(root=tmp_path / "me")).retrieve("第1章", k=10)
    assert any("手写修订" in d for d in docs)
    # 409 while a job is running: leave the rewrite job's gate pending
    job_id = client.post("/api/projects/me/chapter-rewrite",
                         json={"chapter": 1, "mode": "polish", "instruction": "再改"}
                         ).json()["job_id"]
    _poll_gate_via_http(client, job_id)
    assert client.put("/api/projects/me/chapters/1",
                      json={"content": "y" * 60}).status_code == 409
    for g in client.get(f"/api/jobs/{job_id}").json().get("gates", []):
        client.post(f"/api/gates/{g['id']}", json={"approve": False})
    assert _wait_job(client, job_id)["status"] == "done"


def test_outline_endpoint(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "po"})
    job_id = client.post("/api/projects/po/premise", json={"text": "x"}).json()["job_id"]
    assert _wait_job(client, job_id)["status"] == "done"
    r = client.post("/api/projects/po/write-chapter", json={"n": 1})
    assert _wait_job(client, r.json()["job_id"])["status"] == "done"
    outline = client.get("/api/projects/po/outline").json()
    titles = [c["chapter_title"] for arc in outline["arcs"] for c in arc["chapters"]]
    assert titles == [f"T{i}" for i in range(1, 7)][: len(titles)] and len(titles) == 6
    assert set(outline["arcs"][0]["chapters"][0]) == {"chapter_no", "chapter_title"}
    assert client.get("/api/projects/nope/outline").status_code == 404


@pytest.mark.skipif(not DIST_DIR.is_dir(), reason="ui-v2/dist not built (requires Node)")
def test_ui_v2_dist_served(tmp_path: Path) -> None:
    """With a built ui-v2 dist, / serves the SPA, /legacy the old UI, deep links fall back."""
    client = TestClient(create_app(tmp_path))
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="root"' in r.text
    assert "小说生成控制台" in r.text
    r = client.get("/legacy/")
    assert r.status_code == 200
    assert "多智能体小说生成" in r.text
    r = client.get("/api/mode")
    assert r.status_code == 200 and r.json() == {"live": False}
    # SPA deep link (no such file on disk) must serve the SPA shell, not 404
    r = client.get("/p/x/overview")
    assert r.status_code == 200
    assert 'id="root"' in r.text
    # API 404s must stay JSON 404s, never the SPA shell
    r = client.get("/api/nope")
    assert r.status_code == 404 and "detail" in r.json()


# ---------- longform: creation-time / runtime target_chapters wiring ----------

def test_create_project_with_target_chapters(client: TestClient, tmp_path: Path) -> None:
    """Creation carries the whole-book plan straight into project.config.yaml."""
    r = client.post("/api/projects",
                    json={"name": "long", "genre": "fantasy", "target_chapters": 660})
    assert r.status_code == 201
    cfg = (tmp_path / "long" / "project.config.yaml").read_text(encoding="utf-8")
    assert "target_chapters: 660" in cfg
    r = client.post("/api/projects", json={"name": "bad", "target_chapters": 0})
    assert r.status_code == 422


def test_project_config_get_and_put(client: TestClient, tmp_path: Path) -> None:
    """GET exposes a secret-free subset; PUT updates target_chapters surgically
    (set → write key, null → remove key) without touching model credentials."""
    client.post("/api/projects", json={"name": "cfg"})
    r = client.get("/api/projects/cfg/config")
    assert r.status_code == 200
    body = r.json()
    assert body["target_chapters"] is None
    assert "models" not in body and "api_key" not in body  # secrets never leave the server

    r = client.put("/api/projects/cfg/config", json={"target_chapters": 660})
    assert r.status_code == 200
    assert client.get("/api/projects/cfg/config").json()["target_chapters"] == 660
    cfg_path = tmp_path / "cfg" / "project.config.yaml"
    assert "target_chapters: 660" in cfg_path.read_text(encoding="utf-8")
    assert "zhipu" in cfg_path.read_text(encoding="utf-8")  # models section untouched

    assert client.put("/api/projects/cfg/config",
                      json={"target_chapters": None}).status_code == 200
    assert client.get("/api/projects/cfg/config").json()["target_chapters"] is None
    assert "target_chapters" not in cfg_path.read_text(encoding="utf-8")
    assert client.put("/api/projects/cfg/config",
                      json={"target_chapters": -1}).status_code == 422


def test_run_setup_job_two_phase_when_target_chapters_configured(tmp_path: Path) -> None:
    """Guided setup must honor generation.target_chapters: the demo planner's
    第一卷 gets detailed while 第二卷 stays queued in arc_plan (two-phase)."""
    from novel.project import NovelProject
    from novel.store.bible import StoryBible

    proj = NovelProject.scaffold("lf", genre="fantasy", root=tmp_path)
    raw = proj.config_path.read_text(encoding="utf-8")
    proj.config_path.write_text(raw.replace(
        "  context_token_budget: 24000\n",
        "  context_token_budget: 24000\n  target_chapters: 12\n"), encoding="utf-8")
    m = jobs.JobManager()
    q = m.bus.subscribe("lf")
    job = m.start("lf", "setup", jobs.run_setup_job(proj.root, "a thief"))
    try:
        deadline = time.time() + 30.0
        while job.thread.is_alive() and time.time() < deadline:
            gate_id = _next_gate(q, job.id)
            if gate_id is None:
                break  # job_end
            m.resolve_gate(gate_id, True)  # approve every stage artifact
        assert job.status == "done", job.error
        outline = StoryBible(proj).get_outline()
        assert outline is not None
        assert [a.arc_name for a in outline.arcs] == ["第一卷"]
        assert [s.arc_name for s in outline.arc_plan] == ["第二卷"]  # queue ≠ one-shot
    finally:
        job.thread.join(timeout=5)


# ---------- Work 模式聊天(spec §4.4)----------

class _OrchestratorAction:
    """Canned orchestrator decisions injected via monkeypatched make_provider."""

    def __init__(self, action: dict | None) -> None:
        from novel.providers import FakeProvider
        self.provider = FakeProvider(
            {"orchestrator": {"reply": "收到", "action": action}})


def test_chat_session_crud(client: TestClient) -> None:
    client.post("/api/projects", json={"name": "cp"})
    r = client.post("/api/projects/cp/chat/sessions")
    assert r.status_code == 201
    sid = r.json()["session_id"]
    assert [s["id"] for s in client.get("/api/projects/cp/chat/sessions").json()] == [sid]
    assert client.get("/api/projects/cp/chat/sessions/nosuch").status_code == 404


def test_chat_turn_dispatch_and_history(client: TestClient,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    from novel.ui import chat as chat_mod
    monkeypatch.setattr(chat_mod, "make_provider",
                        lambda cfg, skills=None: _OrchestratorAction(
                            {"type": "write_premise", "args": {"text": "一个关于时间小偷的故事"}}).provider)
    client.post("/api/projects", json={"name": "cp2"})
    sid = client.post("/api/projects/cp2/chat/sessions").json()["session_id"]
    r = client.post(f"/api/projects/cp2/chat/sessions/{sid}/messages", json={"text": "开始"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "收到" and body["job_id"]
    job = _wait_job(client, body["job_id"])
    assert job["status"] == "done"
    data = client.get(f"/api/projects/cp2/chat/sessions/{sid}").json()
    kinds = [e["type"] for e in data["entries"]]
    assert kinds[:3] == ["user", "assistant", "action"]
    assert kinds[-1] == "system"
    # premise 真的写进了 bible
    status = client.get("/api/projects/cp2/status").json()
    assert status["has_concept"] is True


def test_chat_turn_invalid_action_422(client: TestClient,
                                      monkeypatch: pytest.MonkeyPatch) -> None:
    from novel.ui import chat as chat_mod
    monkeypatch.setattr(chat_mod, "make_provider",
                        lambda cfg, skills=None: _OrchestratorAction(
                            {"type": "write_premise", "args": {}}).provider)
    client.post("/api/projects", json={"name": "cp3"})
    sid = client.post("/api/projects/cp3/chat/sessions").json()["session_id"]
    r = client.post(f"/api/projects/cp3/chat/sessions/{sid}/messages", json={"text": "开始"})
    assert r.status_code == 422


def test_chat_get_session_malformed_sid_422(client: TestClient) -> None:
    """非法会话 id("..")在 GET 会话路由里是 422 而不是 500,与 POST 路由一致。"""
    client.post("/api/projects", json={"name": "cp4"})
    r = client.get("/api/projects/cp4/chat/sessions/%2E%2E")
    assert r.status_code == 422
