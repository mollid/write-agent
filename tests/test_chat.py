"""Chat session layer: append-only jsonl + one orchestrator turn + job dispatch."""
from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient  # noqa: F401  (keeps env consistent with test_ui)

from novel.config import ModelConfig
from novel.providers import FakeProvider
from novel.ui.chat import ChatSessionStore, TurnResult, run_turn
from novel.ui.jobs import JobManager

CFG = ModelConfig("demo", "fake")


def _decision(reply: str = "好的", action: dict | None = None) -> dict:
    return {"reply": reply, "action": action}


def _provider(action: dict | None = None) -> FakeProvider:
    return FakeProvider({"orchestrator": _decision(action=action)})


def _setup(tmp_path: Path) -> tuple[Path, JobManager, str]:
    from novel.project import NovelProject
    from novel.store.bible import StoryBible
    proj = NovelProject.scaffold("p1", genre="g", root=tmp_path, target_chapters=2)
    bible = StoryBible(proj)
    from novel.models import Arc, ChapterBeat, ChapterOutline, Character, Concept, Outline, World
    beat = ChapterBeat(pov="c1", setting="s", event="e", emotional_turn="t", characters=["c1"])
    bible.set_concept(Concept(logline="L", genre="g", tone="t", themes=["x"],
                              target_length_words=100, audience="a"))
    bible.set_world(World(setting="S"))
    bible.set_characters([Character(id="c1", slug="a", name="A", role="protagonist",
                                    backstory="b", motivation="m", arc="a")])
    bible.set_outline(Outline(arcs=[Arc(arc_name="A", chapters=[
        ChapterOutline(chapter_no=i, chapter_title=f"T{i}", beats=[beat]) for i in (1, 2)])]))
    root = tmp_path / "p1"
    manager = JobManager()
    store = ChatSessionStore(root)
    return root, manager, store.create()


def test_store_crud(tmp_path: Path) -> None:
    store = ChatSessionStore(tmp_path / "p1")
    sid = store.create()
    assert [s["id"] for s in store.list_sessions()] == [sid]
    assert store.list_sessions()[0]["title"] == "(空会话)"
    store.append(sid, {"type": "user", "text": "帮我写一本小说"})
    assert store.list_sessions()[0]["title"] == "帮我写一本小说"
    entries = store.entries(sid)
    assert entries is not None and entries[0]["type"] == "user" and entries[0]["seq"] == 0
    assert store.entries("nosuch") is None


def test_turn_pure_chat(tmp_path: Path) -> None:
    root, manager, sid = _setup(tmp_path)
    result = run_turn(root, "p1", sid, "你好", manager, provider=_provider())
    assert isinstance(result, TurnResult)
    assert result.reply == "好的" and result.action is None and result.job_id is None
    entries = ChatSessionStore(root).entries(sid)
    assert entries is not None
    assert [e["type"] for e in entries] == ["user", "assistant"]


def test_turn_dispatches_write_chapters(tmp_path: Path) -> None:
    root, manager, sid = _setup(tmp_path)
    action = {"type": "write_chapters", "args": {"n": 1}}
    result = run_turn(root, "p1", sid, "写一章", manager, provider=_provider(action))
    assert result.job_id is not None
    job = manager.get(result.job_id)
    assert job is not None and job.kind == "write-chapter"
    store = ChatSessionStore(root)
    entries = store.entries(sid)
    assert entries is not None
    deadline = time.time() + 30
    while time.time() < deadline:
        entries = store.entries(sid) or []
        if entries and entries[-1]["type"] == "system":
            break
        time.sleep(0.05)
    assert entries and entries[-1]["type"] == "system"
    # action entry sits right before the job-end system entry (user → assistant → action
    # → system, per spec §5; checked here because the job runs ~1s past run_turn's return)
    assert entries[-2]["type"] == "action" and entries[-2]["job_id"] == result.job_id
    assert (root / "chapters" / "001.md").is_file()


def test_turn_rejects_when_job_active(tmp_path: Path) -> None:
    root, manager, sid = _setup(tmp_path)
    started = manager.start("p1", "sleeper", lambda job: time.sleep(2))
    action = {"type": "write_chapters", "args": {"n": 1}}
    result = run_turn(root, "p1", sid, "再写一章", manager, provider=_provider(action))
    assert result.job_id is None
    entries = ChatSessionStore(root).entries(sid)
    assert entries is not None and entries[-1]["type"] == "system"
    assert "已有任务在运行" in str(entries[-1]["text"])
    manager.cancel(started.id)


def test_turn_invalid_args_value_error(tmp_path: Path) -> None:
    root, manager, sid = _setup(tmp_path)
    # write_chapters 是当前计划的 next_action(过了计划授权),但 n 越界 -> 参数校验拒绝
    action = {"type": "write_chapters", "args": {"n": 0}}
    import pytest
    with pytest.raises(ValueError):
        run_turn(root, "p1", sid, "开始", manager, provider=_provider(action))
    entries = ChatSessionStore(root).entries(sid)
    assert entries is not None and entries[-1]["type"] == "system"
    assert "动作未启动" in str(entries[-1]["text"])
    assert manager.active_job("p1") is None


def test_turn_rejects_action_not_in_plan(tmp_path: Path) -> None:
    """计划是唯一授权来源:零章项目上 rewrite_chapter 不在 next_action ∪
    available_actions 里 -> 拒绝派发(API 422),不启动任何任务。"""
    root, manager, sid = _setup(tmp_path)
    action = {"type": "rewrite_chapter",
              "args": {"chapter": 1, "mode": "polish", "instruction": "tighten"}}
    import pytest
    with pytest.raises(ValueError, match="未获计划授权"):
        run_turn(root, "p1", sid, "把第 1 章润色一下", manager, provider=_provider(action))
    entries = ChatSessionStore(root).entries(sid)
    assert entries is not None and entries[-1]["type"] == "system"
    assert "未获计划授权" in str(entries[-1]["text"])
    assert "next_action=write_chapters" in str(entries[-1]["text"])
    assert manager.active_job("p1") is None


def test_turn_prompt_contains_user_message_once(tmp_path: Path) -> None:
    """live 提示词里当前用户消息只出现一次(末尾 user 消息),history_tail 不再重复它。"""
    root, manager, sid = _setup(tmp_path)

    class _Recording(FakeProvider):
        def __init__(self) -> None:
            super().__init__({"orchestrator": _decision()})
            self.seen: list[list[dict]] = []

        def complete_structured(self, messages, schema, cfg, *, seed=None):
            self.seen.append(messages)
            return super().complete_structured(messages, schema, cfg, seed=seed)

    prov = _Recording()
    run_turn(root, "p1", sid, "你好呀", manager, provider=prov)
    content = "\n".join(str(m.get("content", "")) for m in prov.seen[0])
    assert content.count("你好呀") == 1
