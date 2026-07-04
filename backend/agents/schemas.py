from typing import Literal

from pydantic import BaseModel


class RequiredField(BaseModel):
  """One piece of information the orchestrator should make sure the user has
  given before handing the conversation off to the specialist agent."""

  name: str  # machine key, e.g. "symptoms"
  label: str  # shown to the orchestrator's own prompt, not the end user
  description: str  # guidance for the orchestrator on what/how to ask
  source: Literal["ask", "device", "either"]
  type: Literal["text", "image"] = "text"
  required: bool = True


class AgentMetadata(BaseModel):
  """Declarative description of one specialist agent, used to drive the
  generic orchestrator and the /api/agents listing without any per-agent
  code in orchestrator.py or the frontend.

  There is no compiled/templated handoff payload -- once the orchestrator
  judges it has enough to proceed, the backend hands the specialist the
  actual conversation directly, so the specialist reads real user context
  instead of a lossy field-by-field extraction."""

  id: str
  title: str
  subtitle: str
  icon: str  # emoji, rendered as-is by the frontend
  required_fields: list[RequiredField]
  welcome_message: str  # shown as the first bubble when a panel is opened, before any user input
  max_images: int = 1  # how many photos the composer lets the user stage in one message
  # What the "thinking" indicator settles on once a reply has taken long
  # enough to reach its final, steady-state phrase. Generic by default;
  # an agent whose slowest step is predictable and specific (e.g. this one
  # generating real images at the end of an interview) can name it
  # honestly instead of leaving the user staring at a generic phrase for
  # however long that particular step actually takes.
  long_wait_message: str = "Still working on it -- this one's taking a bit longer than usual…"

  @property
  def has_image_input(self) -> bool:
    return any(f.type == "image" for f in self.required_fields)

  @property
  def uses_location(self) -> bool:
    # By convention, the one field that can be silently satisfied by device
    # GPS is always source="either" -- this generically detects "this agent
    # benefits from location" from metadata alone, without hardcoding any
    # agent id or field name, so it automatically covers agent #5+ too.
    return any(f.source == "either" for f in self.required_fields)
