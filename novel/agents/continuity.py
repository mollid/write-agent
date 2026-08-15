from __future__ import annotations

import json

from novel.agents.base import Agent, feedback_message
from novel.providers import _extract_json

CONTINUITY_SYSTEM = """\
You are a continuity supervisor on a long-running television series. Your job is to catch every contradiction, no matter how small.

## Task
Compare the provided chapter prose against the story bible. Identify ALL continuity issues.

## Checklist (scan systematically)
- [ ] Character knowledge: Does any character reference information they haven't yet acquired?
- [ ] Timeline: Do dates, durations, and sequencing match the bible?
- [ ] Physical/spatial: Are locations, distances, and object positions consistent?
- [ ] Foreshadowing: Are planted threads honoured? Are payoffs premature or missing?
- [ ] Character voice: Does any character's speech pattern, vocabulary, or worldview drift from their established profile?
- [ ] World rules: Is any inviolable rule from the World document violated?
- [ ] Faction/power consistency: Do political/magical/technological mechanics match prior chapters?

## Output
Return a JSON array of issue strings. Each string should be:
"[CATEGORY] <specific issue with quoted evidence from the chapter>"

If no issues are found, return: []

## Constraints
- Output ONLY the JSON array. No preamble.
- Do NOT fabricate issues. Only flag genuine contradictions or drift.
- Quote the offending text when possible."""

CONTINUITY_USER = """\
<bible>
{bible_json}
</bible>

<chapter>
{prose}
</chapter>"""

CONTINUITY_RETRY = """\
⚠ Your previous output was not valid JSON: {error}

Return ONLY a JSON array of issue strings, e.g. ["[TIMELINE] Chapter says 'three days later' but bible states the journey takes five days."]. No other text."""


class ContinuityAgent(Agent[tuple[str, str], list[str]]):
    name = "continuity"
    output_schema = str

    def build_messages(self, inputs: tuple[str, str]) -> list[dict]:
        prose, bible_json = inputs
        return [
            {"role": "system", "agent": self.name, "content": CONTINUITY_SYSTEM},
            {"role": "user", "agent": self.name,
             "content": CONTINUITY_USER.format(bible_json=bible_json, prose=prose)},
        ]

    def run(self, inputs: tuple[str, str], *, feedback: list[str] | None = None) -> list[str]:
        msgs = self.build_messages(inputs)
        if feedback:
            msgs = msgs + [feedback_message(self.name, feedback)]
        last_err: Exception | None = None
        for _attempt in range(self.max_retries + 1):
            try:
                text = self.provider.complete(msgs, self.cfg)
                data = json.loads(_extract_json(text))
                return [str(x) for x in data]
            except ValueError as e:
                last_err = e
                msgs = msgs + [
                    {"role": "assistant", "content": "<invalid output>"},
                    {"role": "user", "agent": self.name,
                     "content": CONTINUITY_RETRY.format(error=e)},
                ]
        assert last_err is not None
        raise last_err
