from google.adk.agents import LlmAgent
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

USER_ID = "kurasu-user"


async def run_agent_stateless(
    agent: LlmAgent,
    app_name: str,
    history: list[types.Content],
    new_message: types.Content,
) -> types.Content:
  """Runs one turn of `agent` with no server-side session state.

  Builds a fresh InMemorySessionService per call, replays `history` as
  already-happened events (no re-invoking the model for past turns), then
  runs `new_message` once. Nothing persists after this returns, so this is
  safe across concurrent requests and Cloud Run instances, and each request
  is fully self-contained.
  """
  session_service = InMemorySessionService()
  session = await session_service.create_session(app_name=app_name, user_id=USER_ID)

  for turn in history:
    author = "user" if turn.role == "user" else agent.name
    await session_service.append_event(session, Event(author=author, content=turn))

  runner = Runner(agent=agent, app_name=app_name, session_service=session_service)

  final_content: types.Content | None = None
  async for event in runner.run_async(user_id=USER_ID, session_id=session.id, new_message=new_message):
    if event.is_final_response() and event.content:
      final_content = event.content

  if final_content is None:
    raise RuntimeError(f"Agent {agent.name} produced no final response")
  return final_content


def content_text(content: types.Content) -> str:
  """Concatenates all text parts of a Content into one string."""
  return "".join(part.text or "" for part in (content.parts or []))
