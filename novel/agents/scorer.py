from __future__ import annotations

from novel.agents.base import Agent
from novel.models import ReviewScore

SCORER_SYSTEM = """\
You are a rigorous developmental editor and rubric-based assessor. You score with calibration, not generosity. A 50 is competent but unremarkable; 80+ is publishable; 95+ is exceptional.

## Task
Score the provided '{artifact_type}' on each dimension listed below.

## Dimensions & Weight Guidance
{rubric_dimensions}

## Scoring Protocol
1. Read the artifact twice: once for overall impression, once for each dimension.
2. For each dimension, cite ONE specific example from the artifact as evidence.
3. Assign an integer score 0–100.
4. Write a 1–2 sentence critique that is actionable (what to fix, not just what's wrong).

## Output Schema (strict JSON)
{
  "artifact_type": "{artifact_type}",
  "scores": {
    "<dimension_name>": {
      "score": 72,
      "critique": "..."
    }
  },
  "overall": 71,
  "summary": "One-paragraph editorial note."
}

## Constraints
- Be specific. "Prose could be stronger" is unacceptable; name the weak passage.
- Do NOT inflate. If the work is mediocre, say so.
- Do NOT change the artifact; only evaluate it.
- Output ONLY the JSON object."""

SCORER_USER = """\
<artifact type="{artifact_type}">
{artifact_json}
</artifact>"""


class ScorerAgent(Agent[tuple[str, str], ReviewScore]):
    name = "scorer"
    output_schema = ReviewScore

    def build_messages(self, inputs: tuple[str, str]) -> list[dict]:
        artifact_type, artifact_json = inputs
        from novel.scorer_rubrics import RUBRICS
        rubric_dimensions = "\n".join(f"- {d}" for d in RUBRICS.get(artifact_type, ["quality"]))
        # SCORER_SYSTEM carries literal JSON-schema braces, so inject via str.replace.
        system = (SCORER_SYSTEM
                  .replace("{artifact_type}", artifact_type)
                  .replace("{rubric_dimensions}", rubric_dimensions))
        return [
            {"role": "system", "agent": self.name, "content": system},
            {"role": "user", "agent": self.name,
             "content": SCORER_USER.format(artifact_type=artifact_type, artifact_json=artifact_json)},
        ]
