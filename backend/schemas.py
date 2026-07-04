from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
  """Base for all wire models: Python stays snake_case, JSON is camelCase."""

  model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Attachment(CamelModel):
  mime_type: str
  data_base64: str


class HistoryTurn(CamelModel):
  role: Literal["user", "model"]
  text: Optional[str] = None
  attachments: list[Attachment] = []
  input_mode: Optional[Literal["typed", "voice"]] = None
  # Set only on a model turn that was a specialist's final answer (mirrors
  # ChatResponse.specialist_used) -- None means it was the orchestrator's
  # own "collecting" reply. Lets the backend tell, from history alone,
  # whether the specialist has already replied at least once in this
  # conversation, which the stateless architecture has no other way to
  # know (nothing persists server-side between requests).
  specialist_used: Optional[str] = None


class NewTurn(CamelModel):
  text: Optional[str] = None
  attachments: list[Attachment] = []
  input_mode: Literal["typed", "voice"] = "typed"


class DeviceContext(CamelModel):
  lat: Optional[float] = None
  lng: Optional[float] = None
  current_time_iso: Optional[str] = None


class ChatRequest(CamelModel):
  agent_id: str
  history: list[HistoryTurn] = []
  new_turn: NewTurn
  device_context: DeviceContext = DeviceContext()


class GeneratedFile(CamelModel):
  filename: str
  mime_type: str
  data_base64: str


class ChatResponse(CamelModel):
  status: Literal["collecting", "final_answer"]
  text: str
  specialist_used: Optional[str] = None
  generated_files: list[GeneratedFile] = []


class AgentSummary(CamelModel):
  id: str
  title: str
  subtitle: str
  icon: str
  has_image_input: bool
  uses_location: bool
  welcome_message: str
  max_images: int
  long_wait_message: str


class ConfigResponse(CamelModel):
  backend_ready: bool
  using_vertex_ai: bool


class HealthResponse(CamelModel):
  model_connected: bool
  detail: str


class TtsRequest(CamelModel):
  text: str
