from typing import ClassVar

from novel.agents.continuity import (
    CONTINUITY_RETRY,
    CONTINUITY_SYSTEM,
    CONTINUITY_USER,
    ContinuityAgent,
)
from novel.agents.editor import EDITOR_SYSTEM, EDITOR_USER, EditorAgent
from novel.agents.writer import WRITER_SYSTEM, WRITER_USER, WriterAgent
from novel.memory.assembler import AssembledContext
from novel.providers import FakeProvider, ModelConfig


def test_writer_returns_prose():
    ctx = AssembledContext(blocks=["[Beat] event=meet", "[Character] Ara"])
    p = FakeProvider(responses={"writer": "Ara walked into the tavern."}, tag_key="agent")
    out = WriterAgent(p, ModelConfig("zhipu", "x")).run(ctx)
    assert "Ara" in out

def test_continuity_returns_issues():
    p = FakeProvider(responses={"continuity": '["Ara was in docks but beat says tavern"]'}, tag_key="agent")
    out = ContinuityAgent(p, ModelConfig("deepseek", "x")).run(("some prose", "{}"))
    assert isinstance(out, list) and out

def test_editor_polishes():
    p = FakeProvider(responses={"editor": "polished prose"}, tag_key="agent")
    assert EditorAgent(p, ModelConfig("zhipu", "x")).run("rough") == "polished prose"


def test_writer_build_messages_uses_v2_prompt():
    p = FakeProvider(responses={"writer": "prose"}, tag_key="agent")
    agent = WriterAgent(p, ModelConfig("zhipu", "x"))
    ctx = AssembledContext(blocks=["[Beat] event=meet", "[Character] Ara"])
    msgs = agent.build_messages(ctx)
    system, user = msgs[0]["content"], msgs[1]["content"]
    # v2 identity + craft directives verbatim from spec §5
    assert "award-winning literary ghostwriter" in system
    assert "Beat fidelity" in system
    assert "Foreshadowing" in system
    assert "[REWRITE NOTES]" in system
    assert system.rstrip().endswith("preserving all elements that were NOT flagged.")
    # WRITER_USER is exactly {assembled_context} → user message == ctx.text
    assert user == ctx.text


def test_continuity_build_messages_uses_v2_prompt():
    p = FakeProvider(responses={"continuity": "[]"}, tag_key="agent")
    agent = ContinuityAgent(p, ModelConfig("deepseek", "x"))
    msgs = agent.build_messages(("the chapter prose", '{"world": {}}'))
    system, user = msgs[0]["content"], msgs[1]["content"]
    # v2 identity + checklist verbatim from spec §7
    assert "continuity supervisor on a long-running television series" in system
    assert "Character knowledge" in system
    assert "World rules" in system
    assert system.rstrip().endswith("Quote the offending text when possible.")
    # CONTINUITY_USER wraps bible + prose in XML blocks (§7); bible_json then prose order
    assert "<bible>" in user and "</bible>" in user
    assert "<chapter>" in user and "</chapter>" in user
    assert '{"world": {}}' in user
    assert "the chapter prose" in user
    assert user.rstrip().endswith("</chapter>")


def test_editor_build_messages_uses_v2_prompt():
    p = FakeProvider(responses={"editor": "polished"}, tag_key="agent")
    agent = EditorAgent(p, ModelConfig("zhipu", "x"))
    msgs = agent.build_messages("some rough prose")
    system, user = msgs[0]["content"], msgs[1]["content"]
    # v2 identity + editorial scope verbatim from spec §8
    assert "line editor at a top-five publishing house" in system
    assert "Editorial Scope (DO)" in system
    assert "Editorial Scope (DO NOT)" in system
    assert system.rstrip().endswith("no markdown.")
    # EDITOR_USER is exactly {prose} → user message == input prose
    assert user == "some rough prose"


def test_writer_prompts_match_spec_shape():
    # Verbatim identity anchors + placeholder shape from spec §5.
    assert WRITER_SYSTEM.startswith("You are an award-winning literary ghostwriter.")
    assert "{assembled_context}" in WRITER_USER
    assert WRITER_USER.strip() == "{assembled_context}"


def test_continuity_prompts_match_spec_shape():
    # Verbatim identity anchors + placeholder shape from spec §7.
    assert CONTINUITY_SYSTEM.startswith(
        "You are a continuity supervisor on a long-running television series."
    )
    assert "{bible_json}" in CONTINUITY_USER
    assert "{prose}" in CONTINUITY_USER
    assert "{error}" in CONTINUITY_RETRY
    assert "[TIMELINE]" in CONTINUITY_RETRY


def test_editor_prompts_match_spec_shape():
    # Verbatim identity anchors + placeholder shape from spec §8.
    assert EDITOR_SYSTEM.startswith("You are a line editor at a top-five publishing house.")
    assert "{prose}" in EDITOR_USER
    assert EDITOR_USER.strip() == "{prose}"


def test_continuity_retry_appends_v2_retry_text():
    # ContinuityAgent.run retries on invalid JSON; the retry user message must be
    # CONTINUITY_RETRY.format(error=e) verbatim from spec §7.
    class _RetryProvider:
        tag_key = "agent"
        captured: ClassVar[list[list[dict[str, object]]]] = []

        def complete(self, messages, cfg, *, seed=None):
            self.captured.append([dict(m) for m in messages])
            if len(self.captured) == 1:
                return "not valid json"
            return '["[TIMELINE] inconsistency found"]'

    p = _RetryProvider()
    out = ContinuityAgent(p, ModelConfig("deepseek", "x")).run(("prose", "{}"))
    assert out == ["[TIMELINE] inconsistency found"]
    # second call appended the retry user message as the last user role in messages
    retry_user_msgs = [m for m in p.captured[1] if m["role"] == "user"]
    retry = retry_user_msgs[-1]["content"]
    assert retry.startswith("⚠ Your previous output was not valid JSON:")
    assert "Return ONLY a JSON array of issue strings" in retry
    assert "[TIMELINE]" in retry
    assert retry.rstrip().endswith("No other text.")
