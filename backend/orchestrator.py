from typing import Literal

from google.adk.agents import LlmAgent
from pydantic import BaseModel

import settings
from agents.common import GlobalGemini
from agents.registry import list_agents
from agents.schemas import AgentMetadata


class OrchestratorDecision(BaseModel):
  """The orchestrator's only job is deciding whether enough has been said to
  proceed -- it does NOT extract/structure individual field values. Once
  ready, the backend hands the specialist agent the real conversation
  directly, so the specialist reads actual user context instead of a
  lossy field-by-field summary the orchestrator reconstructed."""

  status: Literal["collecting", "ready"]
  reply_to_user: str


def build_orchestrator_agent(meta: AgentMetadata) -> LlmAgent:
  ask_fields = [f for f in meta.required_fields if f.source in ("ask", "either")]
  device_fields = [f for f in meta.required_fields if f.source == "device"]
  optional_names = [f.name for f in meta.required_fields if not f.required]

  field_lines = "\n".join(f"- {f.name} ({f.label}): {f.description}" for f in ask_fields)
  device_lines = ", ".join(f.label for f in device_fields) or "none"
  optional_note = (
    f"\nThese are optional -- do not block on them if the user has nothing to add: {', '.join(optional_names)}."
    if optional_names else ""
  )

  instruction = (
    f'You are Kurasu AI\'s intake assistant for "{meta.title}": {meta.subtitle}.\n'
    "Do NOT answer the user's underlying request yourself and do NOT search the web -- "
    "your only job is deciding whether enough has been said to proceed, asking one or two "
    "friendly questions at a time if not.\n\n"
    "Things that should be covered before proceeding:\n"
    f"{field_lines}\n\n"
    f"Already known automatically -- never ask about these: {device_lines}."
    f"{optional_note}\n\n"
    "Re-read the ENTIRE conversation so far, including the user's very first message, before "
    "asking anything -- people often answer several of these in passing, in their own words, "
    "as part of one message (e.g. \"good halal food nearby\" already covers cuisine, location, "
    "and dietary needs at once). Never ask the user to repeat or restate something they already "
    "said, and never ask about the same thing twice.\n\n"
    "Respond with a JSON object matching your output schema: set status=\"collecting\" and put "
    "your next question in reply_to_user while something important is still genuinely missing; "
    "set status=\"ready\" with a short friendly confirmation in reply_to_user once it's covered. "
    "You do not need to restate or summarize what the user said -- the full conversation is "
    "passed on as-is once you're ready.\n\n"
    "CONTINUING CONVERSATIONS: this conversation does not end after you've handed off once -- "
    "the user may keep talking in the same window, either to follow up on the same request or "
    "to start a new, different one. If their latest message describes a new or different need, "
    "treat it as a fresh request and go through status=\"collecting\" then \"ready\" again for it."
  )

  return LlmAgent(
    name=f"{meta.id}_orchestrator",
    model=GlobalGemini(model=settings.MODEL_NAME),
    description=f"Intake assistant that gathers required info before handing off to {meta.title}.",
    instruction=instruction,
    output_schema=OrchestratorDecision,
  )


_ORCHESTRATOR_AGENTS: dict[str, LlmAgent] = {}


def get_orchestrator_agent(agent_id: str) -> LlmAgent:
  if not _ORCHESTRATOR_AGENTS:
    for meta in list_agents():
      _ORCHESTRATOR_AGENTS[meta.id] = build_orchestrator_agent(meta)
  return _ORCHESTRATOR_AGENTS[agent_id]
