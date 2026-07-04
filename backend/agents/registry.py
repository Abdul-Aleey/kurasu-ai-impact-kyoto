import importlib

from .schemas import AgentMetadata

# Adding agent #4+: add one new agent file (following the pattern of the
# existing files -- root_agent + AGENT_METADATA) and add its module name
# here. Nothing else in this file, orchestrator.py, server.py, or the
# frontend shell needs to change.
AGENT_MODULES = [
  "kurasu_ask_kurasu",
  "kurasu_clinic_finder",
  "kurasu_delivery_scheduler",
  "kurasu_restaurant_finder",
  "kurasu_disaster_agent",
  "kurasu_ingredient_checker",
  "kurasu_form_decoder_filler",
  "kurasu_waste_guide",
]


def _load(module_name: str):
  return importlib.import_module(f".{module_name}", __package__)


def list_agents() -> list[AgentMetadata]:
  return [_load(m).AGENT_METADATA for m in AGENT_MODULES]


def get_agent(agent_id: str):
  """Returns (AgentMetadata, root_agent) for the given agent id."""
  for module_name in AGENT_MODULES:
    module = _load(module_name)
    if module.AGENT_METADATA.id == agent_id:
      return module.AGENT_METADATA, module.root_agent
  raise KeyError(f"Unknown agent id: {agent_id}")
