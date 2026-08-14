"""Tests for the FastAPI GUI: project CRUD, demo-mode pipeline e2e, gate bridging."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel.ui import jobs
from novel.ui.app import create_app


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
