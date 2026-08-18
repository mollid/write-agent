"""TTS API 测试：demo 模式端到端（静音 MP3）+ 参数/404/409 校验。"""
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel.ui.app import create_app

BODY = {"chapter": 1, "voice": "zh-CN-YunxiNeural",
        "rate": "+0%", "volume": "+0%", "pitch": "+0Hz"}


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def _wait_job(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/jobs/{job_id}").json()
        if data["status"] != "running":
            return data
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def _mk_chapter(tmp_path: Path, name: str, n: int = 1) -> None:
    (tmp_path / name / "bible").mkdir(parents=True, exist_ok=True)
    client_ch = tmp_path / name / "chapters"
    client_ch.mkdir(parents=True, exist_ok=True)
    (client_ch / f"{n:03d}.md").write_text("第一章正文。" * 10, encoding="utf-8")


def test_tts_demo_e2e(client: TestClient, tmp_path: Path):
    _mk_chapter(tmp_path, "t1")
    r = client.post("/api/projects/t1/tts", json=BODY)
    assert r.status_code == 202, r.text
    assert _wait_job(client, r.json()["job_id"])["status"] == "done"
    mp3 = tmp_path / "t1" / "audio" / "001.mp3"
    assert mp3.is_file() and mp3.read_bytes()[0] == 0xFF
    listing = client.get("/api/projects/t1/audio").json()
    assert listing == [{"chapter": 1, "size": mp3.stat().st_size}]
    r = client.get("/api/projects/t1/audio/1")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/mpeg")


def test_tts_bad_params_422(client: TestClient, tmp_path: Path):
    _mk_chapter(tmp_path, "t2")
    bad = dict(BODY, rate="1.5x")
    assert client.post("/api/projects/t2/tts", json=bad).status_code == 422
    bad = dict(BODY, voice="zh-CN-NotAVoice")
    assert client.post("/api/projects/t2/tts", json=bad).status_code == 422


def test_tts_missing_chapter_404(client: TestClient):
    client.post("/api/projects", json={"name": "t3"})
    assert client.post("/api/projects/t3/tts", json=BODY).status_code == 404


def test_tts_audio_listing_empty_and_missing_file(client: TestClient):
    client.post("/api/projects", json={"name": "t4"})
    assert client.get("/api/projects/t4/audio").json() == []
    assert client.get("/api/projects/t4/audio/1").status_code == 404


def test_tts_conflict_409(client: TestClient, tmp_path: Path, monkeypatch):
    _mk_chapter(tmp_path, "t5")
    from novel.ui import jobs as jobs_mod

    # drive the real manager: a TTS job whose fn blocks forever (no network)
    release = threading.Event()

    def _blocking_job(proj_root, chapter, voice, rate, volume, pitch):
        def fn(job: jobs_mod.Job) -> object:
            release.wait(10)
            return None
        return fn

    monkeypatch.setattr(jobs_mod, "run_tts_job", _blocking_job)
    try:
        r = client.post("/api/projects/t5/tts", json=BODY)
        assert r.status_code == 202
        assert client.post("/api/projects/t5/tts", json=BODY).status_code == 409
    finally:
        release.set()
