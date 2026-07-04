from functools import cached_property

from google.adk.models import Gemini
from google.genai import Client

import settings


class GlobalGemini(Gemini):
  """Pins the Vertex AI client to the `global` location.

  gemini-3.x models are only served from `global`; the default ADK
  `Gemini` integration constructs a `google.genai.Client` whose location
  defaults to the AgentEngine instance's region (e.g. `us-central1`) and
  fails with model-not-found for these models. Subclassing per the override
  pattern documented on `google.adk.models.google_llm.Gemini` lets the agent
  keep running in its regional AgentEngine instance while routing the model
  request to the global endpoint.

  Falls back to plain API-key mode (no Vertex/ADC needed) for local dev,
  where `settings.USE_VERTEX` is false.
  """

  @cached_property
  def api_client(self) -> Client:
    if settings.USE_VERTEX:
      return Client(vertexai=True, location="global")
    return Client(vertexai=False, api_key=settings.GOOGLE_API_KEY)
