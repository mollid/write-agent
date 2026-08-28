"""Per-volume cast seeding for rolling longform outlines (spec §4.3).

Before each volume is detailed, CastPlannerAgent proposes 0–5 NEW characters the
upcoming volume needs (antagonists, allies, mentors, catalysts). Proposals pass
the `arc_cast` human gate before being upserted, so the volume's detailer sees
an already-extended roster. The message tag is "cast_planner" for provider
routing, but the model slot stays "character" (same casting-director model).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from novel.agents.base import Agent, feedback_message
from novel.models import (
    ArcSkeleton,
    ChapterSummary,
    Character,
    Concept,
    World,
)
from novel.providers import _extract_json

CAST_PLANNER_SYSTEM = """\
You are a casting director extending the cast of an ONGOING long novel for ONE
upcoming volume (卷).

## Task
Propose the 0–5 NEW characters this volume needs: new antagonists, allies,
mentors, catalysts, or recurring supporting players. Return an empty array if
the volume works with the existing cast alone.

## Output Schema (strict JSON array)
Return a JSON array of Character objects with ALL required fields:
{character_schema}

Field guidelines:
- id:  short kebab-case identifier, unique and NEW (never reuse an existing roster id)
- slug: identical to id
- name: Full in-world name
- role: "antagonist" | "deuteragonist" | "support" | "mentor" | "catalyst"
- backstory: 3–5 sentences, consistent with the World's era, rules and factions.
  Include ONE formative wound and ONE secret.
- motivation: 1–2 concrete, actionable sentences.
- arc: "Start state → Midpoint shift → End state" in one sentence, tied to THIS
  volume's premise.

## Critical Rules
1. NEVER propose a new protagonist — the existing lead stays the lead.
2. Every id MUST differ from the existing roster ids and from each other.
3. Tie each character's arc to the volume premise below; introduce them where
   the volume's plot needs them, not for flavor.
4. No placeholder names; no commentary outside the JSON array.

## Output
Return ONLY the JSON array."""

CAST_PLANNER_USER = """\
<volume_skeleton>
arc_name: {arc_name}
chapter_range: {chapter_start}–{chapter_end}
premise: {premise}
</volume_skeleton>

<concept>
{concept_json}
</concept>

<world>
{world_json}
</world>

<existing_roster>
{roster_block}
</existing_roster>

<recent_chapter_summaries>
{summaries_block}
</recent_chapter_summaries>"""

CAST_PLANNER_RETRY = """\
⚠ Your previous output failed validation: {error}

Return ONLY a valid JSON array of Character objects (all required fields), or []
if no new cast is needed."""


@dataclass
class CastPlanInput:
    skeleton: ArcSkeleton
    concept: Concept
    world: World
    characters: list[Character]
    recent_summaries: list[ChapterSummary]


class CastPlannerAgent(Agent[CastPlanInput, list[Character]]):
    name = "cast_planner"   # message tag; model slot stays "character"
    output_schema = list    # list-typed output: parse the array ourselves (see run)

    def build_messages(self, inputs: CastPlanInput) -> list[dict]:
        roster_block = "\n".join(f"- {c.id} ({c.name}): {c.role}" for c in inputs.characters)
        summaries_block = "\n".join(f"- ch{cs.chapter_no}: {cs.summary}"
                                    for cs in inputs.recent_summaries) or "(none)"
        schema = json.dumps(Character.model_json_schema(), ensure_ascii=False)
        return [
            {"role": "system", "agent": self.name,
             "content": CAST_PLANNER_SYSTEM.format(character_schema=schema)},
            {"role": "user", "agent": self.name,
             "content": CAST_PLANNER_USER.format(
                 arc_name=inputs.skeleton.arc_name,
                 chapter_start=inputs.skeleton.chapter_start,
                 chapter_end=inputs.skeleton.chapter_end,
                 premise=inputs.skeleton.premise or "(no premise)",
                 concept_json=inputs.concept.model_dump_json(),
                 world_json=inputs.world.model_dump_json(),
                 roster_block=roster_block or "(empty roster)",
                 summaries_block=summaries_block)},
        ]

    def run(self, inputs: CastPlanInput,
            *, feedback: list[str] | None = None) -> list[Character]:
        # same array-parse contract as CharacterAgent.run: raw complete + json parse
        msgs = self.build_messages(inputs)
        if feedback:
            msgs = msgs + [feedback_message(self.name, feedback)]
        last_err: Exception | None = None
        for _attempt in range(self.max_retries + 1):
            try:
                text = self.provider.complete(msgs, self.cfg)
                data = json.loads(_extract_json(text))
                return [Character.model_validate(c) for c in data]
            except (ValidationError, ValueError) as e:
                last_err = e
                msgs = msgs + [
                    {"role": "assistant", "content": "<invalid output>"},
                    {"role": "user", "agent": self.name,
                     "content": CAST_PLANNER_RETRY.format(error=e)},
                ]
        assert last_err is not None
        raise last_err
