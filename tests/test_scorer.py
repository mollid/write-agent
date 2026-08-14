from novel.agents.scorer import SCORER_SYSTEM, SCORER_USER, ScorerAgent
from novel.models import DimensionScore, ReviewScore
from novel.providers import FakeProvider, ModelConfig
from novel.scorer_rubrics import RUBRICS, apply_review, decide


def test_rubrics_have_chapter_dimensions():
    assert "structure" in [d.lower() for d in RUBRICS["outline"]]
    assert "pacing" in [d.lower() for d in RUBRICS["chapter"]]

def test_decide_pass_when_all_above_threshold():
    rs = ReviewScore(artifact_type="x",
                     scores={"a": DimensionScore(score=80), "b": DimensionScore(score=95)})
    assert decide(rs, score_min=80) is True and rs.passed is True

def test_decide_fail_when_any_below():
    rs = ReviewScore(artifact_type="x",
                     scores={"a": DimensionScore(score=90), "b": DimensionScore(score=70, critique="slow")})
    assert decide(rs, score_min=80) is False
    assert "slow" in apply_review(rs, "")

def test_decide_empty_scores_is_false():
    rs = ReviewScore(artifact_type="x", scores={})
    assert decide(rs, score_min=80) is False

def test_scorer_agent_uses_fake_provider():
    canned = ReviewScore(artifact_type="outline",
                         scores={"structure": DimensionScore(score=88),
                                 "pacing": DimensionScore(score=72, critique="mid sag")})
    p = FakeProvider(responses={"scorer": canned}, tag_key="agent")
    a = ScorerAgent(provider=p, cfg=ModelConfig("deepseek", "deepseek-chat"))
    rs = a.run(("outline", "some artifact json"))
    assert decide(rs, score_min=80) is False

def test_scorer_build_messages_injects_rubric_and_artifact_type():
    p = FakeProvider(responses={"scorer": ReviewScore(artifact_type="chapter")}, tag_key="agent")
    a = ScorerAgent(provider=p, cfg=ModelConfig("deepseek", "deepseek-chat"))
    msgs = a.build_messages(("chapter", "{\"prose\": \"...\"}"))
    sys_content = msgs[0]["content"]
    user_content = msgs[1]["content"]
    # artifact_type injected into system (appears in task line and schema)
    assert "Score the provided 'chapter'" in sys_content
    assert '"artifact_type": "chapter"' in sys_content
    # rubric dimensions injected (chapter has beat_adherence)
    assert "- beat_adherence" in sys_content
    # user message wraps the artifact json with the artifact type tag
    assert '<artifact type="chapter">' in user_content
    assert "{\"prose\": \"...\"}" in user_content

def test_scorer_build_messages_unknown_type_defaults_quality():
    p = FakeProvider(responses={"scorer": ReviewScore()}, tag_key="agent")
    a = ScorerAgent(provider=p, cfg=ModelConfig("deepseek", "deepseek-chat"))
    msgs = a.build_messages(("nonesuch", "{}"))
    assert "- quality" in msgs[0]["content"]

def test_scorer_prompts_match_spec_shape():
    # Spec §6 invariants: system has literal JSON-schema braces + placeholders;
    # user has only placeholders. Verbatim anchor strings.
    assert SCORER_SYSTEM.startswith(
        "You are a rigorous developmental editor and rubric-based assessor."
    )
    assert "{artifact_type}" in SCORER_SYSTEM
    assert "{rubric_dimensions}" in SCORER_SYSTEM
    assert '"scores": {' in SCORER_SYSTEM
    assert SCORER_USER.strip().startswith('<artifact type="{artifact_type}">')
