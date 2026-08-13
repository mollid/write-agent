from novel.agents.scorer import ScorerAgent
from novel.models import ReviewDimension, ReviewScore
from novel.providers import FakeProvider, ModelConfig
from novel.scorer_rubrics import RUBRICS, apply_review, decide


def test_rubrics_have_chapter_dimensions():
    assert "structure" in [d.lower() for d in RUBRICS["outline"]]
    assert "pacing" in [d.lower() for d in RUBRICS["chapter"]]

def test_decide_pass_when_all_above_threshold():
    rs = ReviewScore(artifact_ref="x", attempt=1,
                     dimensions=[ReviewDimension(name="a", score=80), ReviewDimension(name="b", score=95)])
    assert decide(rs, score_min=80) is True and rs.passed is True

def test_decide_fail_when_any_below():
    rs = ReviewScore(artifact_ref="x", attempt=1,
                     dimensions=[ReviewDimension(name="a", score=90), ReviewDimension(name="b", score=70, critique="slow")])
    assert decide(rs, score_min=80) is False
    assert "slow" in apply_review(rs, "")

def test_scorer_agent_uses_fake_provider():
    canned = ReviewScore(artifact_ref="outline", attempt=1,
                         dimensions=[ReviewDimension(name="structure", score=88), ReviewDimension(name="pacing", score=72, critique="mid sag")])
    p = FakeProvider(responses={"scorer": canned}, tag_key="agent")
    a = ScorerAgent(provider=p, cfg=ModelConfig("deepseek", "deepseek-chat"))
    rs = a.run(("outline", "some artifact json"))
    assert decide(rs, score_min=80) is False
