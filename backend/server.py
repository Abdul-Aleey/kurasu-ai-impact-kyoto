import asyncio
import base64
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from google.genai import types

import form_image_gen
import form_overlay
import image_fetch
import qr_decode
import settings
import shelter_data
import tts
from adk_runtime import content_text, run_agent_stateless
from agents import kurasu_form_decoder_filler
from agents.common import GlobalGemini
from agents.registry import get_agent, list_agents
from orchestrator import get_orchestrator_agent
from schemas import (
  Attachment,
  AgentSummary,
  ChatRequest,
  ChatResponse,
  ConfigResponse,
  GeneratedFile,
  HealthResponse,
  HistoryTurn,
  TtsRequest,
)
from text_utils import extract_marked_json, parse_json_loose

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kurasu")


@asynccontextmanager
async def lifespan(app: FastAPI):
  # Downloads the disaster agent's shelter CSVs from GCS into RAM exactly
  # once per process, before any request is served -- failure here is
  # non-fatal (logged, agent falls back to a degraded web-search mode).
  shelter_data.load_shelter_data()
  yield


app = FastAPI(title="Kurasu AI", lifespan=lifespan)

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_methods=["*"],
  allow_headers=["*"],
)


JST = timezone(timedelta(hours=9))


def _format_jst(iso_string: str | None) -> str:
  """The frontend sends `new Date().toISOString()`, which is always UTC --
  agents reasoning about whether a place is "currently open" need this in
  Japan Standard Time, not UTC, or their open/closed judgement is off by
  up to 9 hours. Always convert and label it explicitly as JST so the model
  can't misread the offset."""
  if not iso_string:
    return "unknown"
  try:
    dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M JST")
  except ValueError:
    return "unknown"


def _turn_to_content(role: str, text: str | None, attachments: list) -> types.Content:
  parts = [
    types.Part.from_bytes(data=base64.b64decode(a.data_base64), mime_type=a.mime_type)
    for a in attachments
  ]
  if text:
    parts.append(types.Part(text=text))
  return types.Content(role=role, parts=parts)


def _latest_image_attachment(turns: list[HistoryTurn]):
  for turn in reversed(turns):
    for attachment in reversed(turn.attachments):
      if attachment.mime_type.startswith("image/"):
        return attachment
  return None


async def _find_image_attachment(turns: list[HistoryTurn]) -> Attachment | None:
  """Direct uploads take priority; otherwise scans the user's own typed
  messages for a link to a photo (e.g. pasted instead of uploaded) and
  fetches it server-side so it can be handed to the specialist the same way
  as an uploaded attachment."""
  direct = _latest_image_attachment(turns)
  if direct:
    return direct

  for turn in reversed(turns):
    if turn.role != "user" or not turn.text:
      continue
    for url in image_fetch.find_urls(turn.text):
      fetched = await image_fetch.try_fetch_image(url)
      if fetched:
        data, mime_type = fetched
        return Attachment(mime_type=mime_type, data_base64=base64.b64encode(data).decode("ascii"))
  return None


def _all_image_attachments(turns: list[HistoryTurn]) -> list[tuple[bytes, str]]:
  """Every image attachment across the whole conversation, in the order it
  was sent -- used to correlate a completed form's page_number (1-indexed,
  in upload order) with the actual photo bytes (and mime type) for the
  image-generation/overlay renderers."""
  return [
    (base64.b64decode(a.data_base64), a.mime_type)
    for turn in turns
    for a in turn.attachments
    if a.mime_type.startswith("image/")
  ]


def _has_specialist_replied(turns: list[HistoryTurn], specialist_id: str) -> bool:
  """Whether `specialist_id` has already produced at least one reply in
  this conversation -- the stateless architecture has no other way to
  know this (nothing persists server-side between requests), and
  HistoryTurn.specialist_used (mirroring ChatResponse.specialist_used) is
  what makes it possible to tell an orchestrator "collecting" reply apart
  from an actual specialist turn just from replayed history."""
  return any(t.role == "model" and t.specialist_used == specialist_id for t in turns)


def _find_form_fields_note(turns: list[HistoryTurn]) -> dict | None:
  """Recovers the field list a prior turn of kurasu_form_decoder_filler
  already established (see FORM_FIELDS_MARKER), searching from the most
  recent turn backwards. Used so a mid-interview turn never needs the
  original photo again -- the field list persists via ordinary
  conversation history instead of being re-derived from the image."""
  for turn in reversed(turns):
    if turn.role == "model" and turn.text and kurasu_form_decoder_filler.FORM_FIELDS_MARKER in turn.text:
      _, fields_data = extract_marked_json(turn.text, kurasu_form_decoder_filler.FORM_FIELDS_MARKER)
      if fields_data:
        return fields_data
  return None


def _text_only_content(content: types.Content) -> types.Content:
  """Strips any image (or other binary) parts from a Content, keeping only
  its text parts -- used once a multi-turn interview has moved past its
  very first turn, so the original photo doesn't need to be resent to (and
  reprocessed by) the vision model on every subsequent turn; the field
  list already established on turn one covers what the interview needs."""
  return types.Content(role=content.role, parts=[p for p in content.parts if p.text])


async def _extract_form_field_labels(
    image_parts: list[types.Part], app_name: str,
) -> dict:
  """Runs kurasu_form_decoder_filler's labels_agent ONCE, at the very
  start of a fill-mode interview, to identify every field/label/choice-
  option directly from the photos. This is the only point in the
  interview that needs the actual image."""
  trigger = types.Content(role="user", parts=[
    *image_parts,
    types.Part(text="Identify every field on this form now."),
  ])
  labels_reply = await run_agent_stateless(
    kurasu_form_decoder_filler.labels_agent, app_name=f"{app_name}_form_labels",
    history=[], new_message=trigger,
  )
  return parse_json_loose(content_text(labels_reply))


async def _extract_completed_form_data(
    history_content: list[types.Content], new_message: types.Content, specialist_reply: types.Content,
    app_name: str,
) -> dict:
  """Once kurasu_form_decoder_filler's conversational agent signals the
  interview is complete (FORM_COMPLETE_MARKER), a SEPARATE call with
  output_schema enforcement extracts the actual structured data from the
  full conversation -- deliberately not asking the conversational agent to
  also emit precisely-formatted JSON inline itself, since that's exactly
  the kind of instruction a free-flowing chat reply doesn't reliably
  comply with. This mirrors how orchestrator.py already gets a dependable
  structured decision out of Gemini."""
  extraction_trigger = types.Content(role="user", parts=[types.Part(
    text="The interview above is now complete. Extract and structure the completed form data now."
  )])
  extraction_reply = await run_agent_stateless(
    kurasu_form_decoder_filler.extraction_agent, app_name=f"{app_name}_form_extractor",
    history=history_content + [new_message, specialist_reply], new_message=extraction_trigger,
  )
  return parse_json_loose(content_text(extraction_reply))


async def _render_one_page_language(
    page: dict, image_bytes: bytes, image_mime_type: str, language: str, language_label: str,
) -> GeneratedFile:
  try:
    result_bytes, result_mime_type = await asyncio.to_thread(
      form_image_gen.render_form_page_image, page, image_bytes, image_mime_type, language,
    )
  except Exception:
    log.warning(
      "AI image generation failed for page %s (%s), falling back to overlay",
      page["page_number"], language, exc_info=True,
    )
    result_bytes = await asyncio.to_thread(
      form_overlay.render_overlaid_page_image, page, image_bytes, language,
    )
    result_mime_type = "image/png"

  extension = "png" if "png" in result_mime_type else "jpg"
  filename = f"form_page{page['page_number']}_{language_label}.{extension}"
  return GeneratedFile(
    filename=filename, mime_type=result_mime_type,
    data_base64=base64.b64encode(result_bytes).decode("ascii"),
  )


async def _render_filled_form_files(form_data: dict, page_images: list[tuple[bytes, str]]) -> list[GeneratedFile]:
  """Renders the completed form as real images (not PDFs): for every page
  the user uploaded, one English image and one Japanese image, each a
  clean, print-ready redraw of that same page with its answers filled in
  matching each field's fill_type (written text, a circled option, a
  checked box, or a shaded bubble).

  Primary path (`form_image_gen`) uses Gemini's native image-editing model
  to actually regenerate the photo -- deskewed, same layout/colors -- which
  is the only way to get something that looks like "a filled-in version of
  the real form" rather than a typeset sheet. This is inherently less
  guaranteed-accurate than deterministic rendering (a generative model can
  still misplace or garble a mark), so any failure for a given page/
  language -- no image part returned, a safety block, an API error --
  falls back to the deterministic overlay renderer for THAT page/language
  specifically, rather than losing the whole result over one bad page.

  Every page/language combination runs CONCURRENTLY (asyncio.gather), not
  one after another -- a 3-page form used to mean 6 sequential image-model
  calls back to back (each genuinely slow, since image generation is much
  slower than text), which is exactly the kind of multi-minute wait that
  looked like the request had hung. Running them all at once means the
  total wait is roughly the slowest single call, not the sum of all of
  them."""
  tasks = []
  for page in form_data["pages"]:
    index = page["page_number"] - 1
    if index < 0 or index >= len(page_images):
      log.warning("No uploaded photo found for form page %s, skipping it", page["page_number"])
      continue
    image_bytes, image_mime_type = page_images[index]

    for language, language_label in (("en", "english"), ("ja", "japanese")):
      tasks.append(_render_one_page_language(page, image_bytes, image_mime_type, language, language_label))

  return await asyncio.gather(*tasks)


@app.get("/config", response_model=ConfigResponse)
async def get_config():
  return ConfigResponse(backend_ready=settings.BACKEND_READY, using_vertex_ai=settings.USE_VERTEX)


_HEALTH_CACHE_SECONDS = 60
_health_cache: dict = {"result": None, "checked_at": 0.0}


async def _check_model_connection() -> HealthResponse:
  """Live reachability check, not just a config check -- /config only
  confirms credentials are *set*, not that the model actually responds
  (wrong model name, missing IAM role, region mismatch, etc. would all
  still show backendReady=true but fail here). Cached briefly so repeated
  page loads don't fire a real model call every time."""
  now = time.time()
  cached = _health_cache["result"]
  if cached is not None and (now - _health_cache["checked_at"]) < _HEALTH_CACHE_SECONDS:
    return cached

  if not settings.BACKEND_READY:
    result = HealthResponse(model_connected=False, detail="Backend is not configured with a model provider.")
  else:
    try:
      client = GlobalGemini(model=settings.MODEL_NAME).api_client
      await asyncio.to_thread(client.models.generate_content, model=settings.MODEL_NAME, contents="ping")
      result = HealthResponse(model_connected=True, detail=f"Connected ({settings.MODEL_NAME})")
    except Exception as e:
      log.exception("Model health check failed")
      result = HealthResponse(model_connected=False, detail=str(e)[:300])

  _health_cache["result"] = result
  _health_cache["checked_at"] = now
  return result


@app.get("/api/health", response_model=HealthResponse)
async def get_health():
  return await _check_model_connection()


@app.get("/api/agents", response_model=list[AgentSummary])
async def get_agents():
  return [
    AgentSummary(
      id=meta.id, title=meta.title, subtitle=meta.subtitle, icon=meta.icon,
      has_image_input=meta.has_image_input, uses_location=meta.uses_location,
      welcome_message=meta.welcome_message, max_images=meta.max_images,
      long_wait_message=meta.long_wait_message,
    )
    for meta in list_agents()
  ]


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
  if not settings.BACKEND_READY:
    raise HTTPException(status_code=503, detail="Backend is not configured with a model provider.")

  try:
    meta, specialist_agent = get_agent(request.agent_id)
  except KeyError:
    raise HTTPException(status_code=404, detail=f"Unknown agentId: {request.agent_id}")

  orchestrator_agent = get_orchestrator_agent(request.agent_id)

  try:
    history_content = [
      _turn_to_content(turn.role, turn.text, turn.attachments) for turn in request.history
    ]
    new_message = _turn_to_content("user", request.new_turn.text, request.new_turn.attachments)

    # The orchestrator only ever sees conversation text, so device-supplied
    # context (GPS, clock) has to be surfaced into the prompt explicitly. This
    # same note is reused for the specialist call below, since specialist
    # prompts expect similar "Context: ..." hints.
    has_location = request.device_context.lat is not None and request.device_context.lng is not None
    location_clause = (
      f"location_available=yes (lat={request.device_context.lat}, lng={request.device_context.lng})"
      if has_location
      else "location_available=no -- ask the user for a nearby station or landmark if location matters here."
    )
    device_note = (
      "[Device context, not from the user -- use silently to reason about things like whether a "
      "place is currently open, NEVER state or repeat this timestamp/coordinates back to the user: "
      f"{location_clause}, current_time={_format_jst(request.device_context.current_time_iso)} "
      "(this is already in Japan Standard Time -- do not convert it, do not treat it as UTC)]"
    )
    new_message.parts.append(types.Part(text=device_note))

    orchestrator_reply = await run_agent_stateless(
      orchestrator_agent, app_name=f"{request.agent_id}_orchestrator",
      history=history_content, new_message=new_message,
    )
    decision = parse_json_loose(content_text(orchestrator_reply))

    # Hard ceiling: never let the user get stuck answering the same question
    # over and over. Specialist agents are the entire point of this app --
    # after a few back-and-forths, hand off regardless of what the
    # orchestrator says, rather than risk looping indefinitely.
    user_turn_count = sum(1 for t in request.history if t.role == "user") + 1
    MAX_COLLECTING_TURNS = 4
    force_handoff = user_turn_count > MAX_COLLECTING_TURNS

    if decision["status"] != "ready" and not force_handoff:
      return ChatResponse(status="collecting", text=decision["reply_to_user"])

    # Handoff: the specialist gets the REAL conversation -- full history plus
    # this turn, device context included -- instead of a field-by-field
    # summary the orchestrator would have had to reconstruct. That
    # reconstruction step was the actual source of the repeated, frustrating
    # re-asking behavior, since it depended on the model reliably
    # re-extracting and re-stating every value itself on every single turn.
    all_turns = list(request.history) + [
      HistoryTurn(role="user", text=request.new_turn.text, attachments=request.new_turn.attachments)
    ]
    if meta.has_image_input:
      current_turn_image = next(
        (a for a in request.new_turn.attachments if a.mime_type.startswith("image/")), None
      )
      # Only fetch from history/URL when this turn's own attachments don't
      # already cover it -- otherwise the image is already in `new_message`
      # and appending it again would just duplicate the same bytes.
      image_attachment = current_turn_image or await _find_image_attachment(all_turns)

      if image_attachment:
        image_bytes = base64.b64decode(image_attachment.data_base64)

        if not current_turn_image:
          new_message.parts.append(types.Part.from_bytes(data=image_bytes, mime_type=image_attachment.mime_type))

        # QR decoding is a precise pixel-grid problem, not something a
        # vision-language model reliably reads just by looking at a photo --
        # give the specialist the deterministically-decoded content directly
        # instead of leaving it to guess at the QR code from the image alone.
        qr_content = qr_decode.decode_qr_code(image_bytes)
        if qr_content:
          new_message.parts.append(types.Part(
            text=f"[QR code detected and decoded from the attached photo -- this is the exact, "
                 f"verified content, use it directly rather than trying to read the QR code "
                 f"yourself from the image: {qr_content}]"
          ))

    if meta.id == "disaster_agent":
      # Precise nearest-shelter math is a deterministic geospatial lookup,
      # not something to leave to an LLM to guess at -- computed here and
      # handed to the specialist as verified context, same pattern as the
      # device-context and QR-decode notes above. The specialist's own
      # instruction expects exactly one of these notes every time it's
      # invoked (to know whether to use the verified data or fall back to
      # search) -- so every branch, including "no location at all" (e.g.
      # the user denied permission and never gave a landmark either, and
      # the hard turn-ceiling forced handoff anyway), must inject something.
      if has_location:
        crisis_type_text = " ".join(t.text or "" for t in all_turns if t.role == "user")
        shelter_result = shelter_data.find_nearest_shelters(
          request.device_context.lat, request.device_context.lng, crisis_type=crisis_type_text,
        )
        if shelter_result["data_available"]:
          new_message.parts.append(types.Part(
            text=f"[Nearest shelters found (verified GPS data, use directly, do not recompute or "
                 f"guess): emergency_sites={shelter_result['emergency_sites']}, "
                 f"evacuation_centers={shelter_result['evacuation_centers']}]"
          ))
        else:
          new_message.parts.append(types.Part(
            text="[Shelter data is currently unavailable -- fall back to a single web search for "
                 "official evacuation guidance for this area.]"
          ))
      else:
        new_message.parts.append(types.Part(
          text="[No device location and no landmark was given -- the app already shows the user "
               "an 'Enable Location' button, but if you haven't already, gently suggest they "
               "enable location access for the most accurate results, or tell you a nearby "
               "station or landmark. Only fall back to a single web search for general "
               "evacuation guidance if they still can't provide either.]"
        ))

    # EXPERIMENTAL: for form_decoder_filler's fill-mode interview, the photo
    # only needs to be seen by a model twice total -- once here to identify
    # every field, once at the very end to generate the completed images --
    # instead of on every single turn. This is a deliberate efficiency
    # tradeoff (fewer image tokens, faster per-turn latency for forms with
    # many fields) at the cost of the model only getting one look at the
    # photo to identify fields, rather than re-examining it each turn.
    carried_fields = None
    if meta.id == "form_decoder_filler":
      if not _has_specialist_replied(request.history, meta.id):
        # First specialist turn of this conversation (decode mode, or the
        # very start of a fill-mode interview): identify every field
        # directly from whatever photo(s) are available so far, once.
        image_parts = [p for p in new_message.parts if p.inline_data] + [
          p for content in history_content for p in content.parts if p.inline_data
        ]
        if image_parts:
          try:
            carried_fields = await _extract_form_field_labels(image_parts, app_name=request.agent_id)
            new_message.parts.append(types.Part(
              text=f"{kurasu_form_decoder_filler.FORM_FIELDS_MARKER} {json.dumps(carried_fields)}"
            ))
          except Exception:
            log.exception("Field-label extraction failed for agentId=%s", request.agent_id)
      else:
        # Interview already underway -- the field list was already
        # established in an earlier reply. Recover it from history instead
        # of re-deriving it from the photo, and stop resending the photo
        # itself to the model on this and future turns.
        carried_fields = _find_form_fields_note(request.history)
        if carried_fields is not None:
          history_content = [_text_only_content(c) for c in history_content]
          new_message = _text_only_content(new_message)
          new_message.parts.append(types.Part(
            text=f"{kurasu_form_decoder_filler.FORM_FIELDS_MARKER} {json.dumps(carried_fields)}"
          ))

    specialist_reply = await run_agent_stateless(
      specialist_agent, app_name=request.agent_id,
      history=history_content, new_message=new_message,
    )

    visible_text = content_text(specialist_reply)
    generated_files = []
    interview_complete = (
      meta.id == "form_decoder_filler"
      and kurasu_form_decoder_filler.FORM_COMPLETE_MARKER in visible_text
    )
    if interview_complete:
      visible_text = visible_text.replace(kurasu_form_decoder_filler.FORM_COMPLETE_MARKER, "").strip()
      try:
        form_data = await _extract_completed_form_data(
          history_content, new_message, specialist_reply, app_name=request.agent_id,
        )
        generated_files = await _render_filled_form_files(form_data, _all_image_attachments(all_turns))
      except Exception:
        log.exception("Failed to extract/render filled-form images for agentId=%s", request.agent_id)
        visible_text += (
          "\n\n(Sorry, I had trouble preparing the completed form images -- but everything you "
          "told me above was recorded correctly. Could you try again?)"
        )
    elif carried_fields is not None:
      # Mid-interview: the field list must persist into the NEXT turn's
      # history too. Appended here deterministically by this code rather
      # than relying on the model to reliably echo it back verbatim on its
      # own initiative -- ChatBubble.tsx hides this from what's actually
      # rendered, but the frontend still stores/resends the full text as
      # this turn's history, which is what makes it available again later
      # without needing the photo.
      visible_text = f"{visible_text}\n\n{kurasu_form_decoder_filler.FORM_FIELDS_MARKER} {json.dumps(carried_fields)}"

    return ChatResponse(
      status="final_answer",
      text=visible_text,
      specialist_used=meta.id,
      generated_files=generated_files,
    )
  except Exception:
    log.exception("chat() failed for agentId=%s", request.agent_id)
    return ChatResponse(
      status="collecting",
      text="Sorry, something went wrong on my end -- could you try that again?",
    )


@app.post("/api/tts")
async def synthesize_speech(request: TtsRequest):
  if not settings.BACKEND_READY:
    raise HTTPException(status_code=503, detail="Backend is not configured with a model provider.")
  audio_bytes, content_type = tts.synthesize(request.text)
  return Response(content=audio_bytes, media_type=content_type)


STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
  # StaticFiles(html=True) only serves index.html at the exact mount root --
  # client-side routes like /chat/clinic_finder (deep links, page refreshes,
  # PWA manifest shortcuts) otherwise 404. Fall back to index.html for any
  # unmatched GET that isn't an API path, so React Router can take over.
  @app.exception_handler(404)
  async def spa_fallback(request, exc):
    if request.method == "GET" and not request.url.path.startswith(("/api/", "/config")):
      index = STATIC_DIR / "index.html"
      if index.exists():
        return FileResponse(index)
    return JSONResponse(status_code=404, content={"detail": "Not Found"})

  app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
