"""Work-mode orchestrator: ONE structured decision per turn over the
authoritative workflow plan. The plan (novel.workflow.build_plan) is the
single source of truth; this agent only routes and converses."""
from __future__ import annotations

from pydantic import BaseModel

from novel.agents.base import Agent
from novel.config import ModelConfig
from novel.providers import ModelProvider

ORCHESTRATOR_SYSTEM = """\
You are the production orchestrator of a novel-writing workbench (Work mode).
Each turn you receive: recent chat history, the authoritative workflow plan (JSON),
and the user's new message. You produce a short reply plus AT MOST ONE action.

## Critical Rules
1. The plan is the single authority. You may only execute `next_action`, or an
   action listed in `available_actions`. NEVER infer stages from file names,
   conversation history, or whether artifacts seem to exist.
2. If `next_action.type` is `wait_job`: a job is already running
   (`progress.active_job_id`). Report that; never start anything.
3. Cost-bearing actions (`write_premise`, `run_setup`, `write_chapters`,
   `rewrite_chapter`, `extend_outline`, `run_tts`) require the user to have
   clearly requested them THIS turn. Otherwise ask for confirmation and set
   `action` to null.
4. Missing required arguments -> ask first, action null:
   - write_premise: needs `text` (the user's story idea, >= 10 chars)
   - write_chapters: needs `n` (chapter count; user did not say -> 1)
   - rewrite_chapter: needs `chapter`, `mode` ("polish"|"rearrange"), `instruction`
   - edit_bible: needs `section` ("concept"|"world"|"characters"), `instruction`,
     optional `character_id` (character edits only)
   - extend_outline: needs `n`
   - run_tts: needs `chapter`; `voice` optional
5. Chapter numbers and counts come from the plan's `progress`. Never invent them.
6. Reply in 简体中文 unless the user writes another language. Concise: a few
   sentences at most. Do not fabricate chapter contents or scores.
7. No suitable action, or the user is just chatting / asking about progress ->
   `action` null.

## Workflow plan (JSON)
{plan_json}

## Recent conversation
{history_block}

## Output
Return ONLY the JSON object: {"reply": str, "action": {"type": str, "args": object} | null}"""


class OrchestratorInput(BaseModel):
    history_tail: list[dict[str, str]]
    plan_json: str
    user_message: str


class ChatAction(BaseModel):
    type: str
    args: dict[str, object] = {}


class OrchestratorDecision(BaseModel):
    reply: str
    action: ChatAction | None = None


def _history_block(history: list[dict[str, str]]) -> str:
    if not history:
        return "(none)"
    return "\n".join(f"- {h.get('role', 'user')}: {h.get('text', '')}" for h in history[-20:])


class OrchestratorAgent(Agent[OrchestratorInput, OrchestratorDecision]):
    name = "orchestrator"
    output_schema = OrchestratorDecision

    def __init__(self, provider: ModelProvider, cfg: ModelConfig) -> None:
        super().__init__(provider, cfg)

    def build_messages(self, inputs: OrchestratorInput) -> list[dict]:
        content = ORCHESTRATOR_SYSTEM.replace("{plan_json}", inputs.plan_json) \
            .replace("{history_block}", _history_block(inputs.history_tail))
        return [
            {"role": "system", "agent": self.name, "content": content},
            {"role": "user", "agent": self.name, "content": inputs.user_message},
        ]
