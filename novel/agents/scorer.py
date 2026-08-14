from __future__ import annotations

from novel.agents.base import Agent
from novel.models import ReviewScore


class ScorerAgent(Agent[tuple[str, str], ReviewScore]):
    name = "scorer"
    output_schema = ReviewScore

    def build_messages(self, inputs: tuple[str, str]) -> list[dict]:
        artifact_type, artifact_json = inputs
        from novel.scorer_rubrics import RUBRICS
        dims = RUBRICS.get(artifact_type, ["quality"])
        return [
            {"role": "system", "agent": self.name,
             "content": f"Score this '{artifact_type}' on each dimension 0-100 with a short critique. "
                        f"Dimensions: {dims}. Return ReviewScore."},
            {"role": "user", "agent": self.name, "content": artifact_json},
        ]
