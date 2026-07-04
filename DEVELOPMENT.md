# Development Guide

Architecture and conventions for working on this codebase.

## Development Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 5000 --reload
```

Requires `backend/.env.local` for local dev (gitignored):
```
API_BACKEND_PORT=5000
GOOGLE_API_KEY=AIza...
```
No `GOOGLE_GENAI_USE_VERTEXAI` locally -- its absence is what puts `settings.py` into API-key mode.

### Frontend
```bash
cd frontend
npm install
npm run dev       # dev server at http://localhost:5173
npm run build     # production build -> dist/
npm run preview   # preview production build
```

Requires `frontend/.env` for local dev (gitignored):
```
VITE_BACKEND_URL=http://localhost:5000
```

There are no automated tests in this repository. TypeScript type-checking: `cd frontend && npx tsc -b --noEmit`.

**Backend module convention:** every `backend/*.py` file uses flat, top-level imports (`import settings`, `from agents.registry import ...`), never `from . import ...`. This is required because the Dockerfile flattens `backend/` into the image's `/app/`, and `uvicorn server:app` is always run with `backend/` (or `/app/`) as the working directory -- there is no parent `backend` *package* at runtime. Imports *within* `backend/agents/` (a real subpackage) may still use relative dots since that nesting is stable either way.

## Architecture

### Multi-agent system (backend)

Six independent Google ADK **specialist agents**, each a self-contained module under `backend/agents/`:

- `kurasu_clinic_finder.py` -- finds nearby medical care matching symptoms
- `kurasu_delivery_scheduler.py` -- reschedules a missed courier delivery (accepts a typed tracking number or a photo of the notice slip); for Japan Post specifically, actually attempts real automated submission (see `backend/automation/japan_post.py`) rather than just linking out
- `kurasu_restaurant_finder.py` -- finds restaurants matching a craving/cuisine/dietary restriction
- `kurasu_disaster_agent.py` -- finds the nearest emergency shelter from real GCS-hosted government open data (see "Disaster agent" below)
- `kurasu_ingredient_checker.py` -- reads a product's ingredient label (photo, typed text, or a named product to search for) and rates halal/vegetarian/allergy suitability with a three-state ✅/❌/⚠️ system, deliberately erring toward ⚠️ or ❌ (never a false ✅) when an ingredient's source is ambiguous (margarine, unspecified gelatin, emulsifier, etc.)
- `kurasu_form_decoder_filler.py` -- reads 1-5 photos of a Japanese form and either explains it (decode mode) or runs a real one-field-at-a-time interview and produces a completed bilingual form as two downloadable PDFs (see "Form Decoder & Filler" below)

Each file exports a `root_agent` (`LlmAgent` with Google Search + URL-context sub-agent tools, one-shot search behavior, structured markdown output) and an `AGENT_METADATA` (`AgentMetadata`, declared in `backend/agents/schemas.py`) describing its id/title/icon and the `RequiredField`s the orchestrator must collect before handoff.

**Adding agent #4+**: create a new file following the same pattern (prompt/tools copied from Google's Agent Builder export, plus one `AGENT_METADATA` block), then add its module name to `AGENT_MODULES` in `backend/agents/registry.py`. Nothing in `orchestrator.py`, `server.py`, or any shared frontend component needs to change -- `/api/agents` and the orchestrator prompts are both generated dynamically from the registry.

`backend/agents/common.py` holds the one shared piece of logic, `GlobalGemini`: it pins Vertex AI calls to the `global` location (gemini-3.x is only served from there) and falls back to plain API-key mode when `settings.USE_VERTEX` is false.

### Orchestrator (`backend/orchestrator.py`)

The app is **not** "pick a panel, talk to that agent." Selecting a panel starts a conversation with a generic **intake orchestrator** (one `LlmAgent` per panel, built once at startup from that panel's `AgentMetadata` -- no per-panel code). Its instruction is assembled purely from `required_fields`; it asks one or two questions at a time and is explicitly told not to answer the user's real request or use any tools.

It responds every turn with a structured `OrchestratorDecision` (just `status` + `reply_to_user`), enforced via ADK's `output_schema` (Gemini native structured output). Earlier versions had it also extract and structure field values into a `collected` dict -- that was removed after proving unreliable (Gemini's structured output is much better at a fixed set of named fields than an open-ended dict, and even then, re-deriving already-given info from raw history every turn led to repeated re-asking). The orchestrator's only job now is deciding whether enough has been said to proceed. `backend/text_utils.parse_json_loose()` is a defensive fallback (strips ```json fences, then a regex `{...}` extraction) in case a model ever doesn't comply.

**Handoff, concretely** (`server.py: POST /api/chat`): every call runs the orchestrator once. If `status == "ready"` (or a hard turn-count ceiling forces it regardless -- see "Important invariants"), the *same request* immediately calls the specialist `root_agent` with the **full real conversation** (history + this turn, device context included) -- not a compiled/extracted summary -- returning its final markdown in the same HTTP response. There is no separate "handoff" round trip. Passing the actual conversation instead of an extracted summary is deliberate: it eliminates the whole class of bugs where the orchestrator's own re-extraction failed to notice something the user already said.

Device context (GPS + current time) is invisible to the orchestrator by default -- it only ever sees conversation text. `server.py` explicitly appends a `[Device context...]` note to the new-turn `Content` sent to the orchestrator on every call so it can honor its own "use device GPS silently, don't ask" instruction. That note is never shown in the frontend (the frontend renders its own local turn history, independent of what the backend sends to Gemini).

### Stateless ADK invocation (`backend/adk_runtime.py`)

The backend is **stateless REST**, not WebSocket -- deliberately, so it scales horizontally on Cloud Run with no sticky sessions. There is no server-side session store. The client (frontend) holds the full conversation and sends it every call; `run_agent_stateless()` builds a **fresh** `InMemorySessionService` per request, replays prior turns as already-happened `Event`s via `append_event`, then runs the new turn once. `LlmAgent` objects (orchestrators + specialists) are built once at import time and safely reused across concurrent requests -- only the lightweight `Runner`/session pair is per-request.

### Disaster agent (`backend/shelter_data.py`, `backend/agents/kurasu_disaster_agent.py`)

Two Japanese government open-data CSVs (matching the real GSI/国土地理院 schema for 指定緊急避難場所/指定避難所) live in a GCS bucket (`kurasu-ai-shelter`, `asia-northeast1`) and are downloaded into pandas DataFrames **once**, at process startup, via a FastAPI `lifespan` context manager -- not per-request, so nearest-shelter lookups never hit the network. Encoding is tried as `utf-8` then `shift_jis` per the source data's convention. If GCS access fails for any reason (missing IAM role, bucket typo, bad encoding), it's logged and the DataFrames stay `None` -- the app still boots, and the agent falls back to a single web search instead of a nearest-shelter lookup.

Finding the nearest shelters is **not** delegated to the LLM -- `shelter_data.find_nearest_shelters()` computes a vectorized Haversine distance (numpy, not a Python loop) across both DataFrames and returns the real top-3 by distance. This is injected into the specialist's context as a verified note (same mechanism as the QR-decode note below), the same way GPS/QR data is handled elsewhere in this codebase: precise, deterministic computation happens in Python; the LLM only synthesizes a response from already-verified data, never invents or recomputes it.

One safety-driven addition beyond a plain nearest-3: the emergency-sites file flags, per site, which specific disaster types (地震/津波/大規模な火事/etc.) it's designated safe for -- a site good for a fire is not necessarily safe ground for a tsunami. `find_nearest_shelters()` best-effort filters by the user's stated crisis type against that flag before computing distance, falling back to unfiltered if the crisis type isn't recognized or filtering leaves nothing. This is why the closest emergency site by raw distance is sometimes correctly *not* the one recommended.

### Form Decoder & Filler (`backend/form_image_gen.py`, `backend/form_overlay.py`, `backend/agents/kurasu_form_decoder_filler.py`)

Users send 1-5 photos of a Japanese form (one per page) and either "decode" (a one-shot explanation of what the form is/asks) or "fill" it. Fill mode is a genuine multi-turn interview: the specialist asks one field at a time, in the form's own order, and re-reads the whole conversation on every call to know which fields are already answered -- there's no separate interview state machine, it falls out of the same "give the specialist the full conversation" architecture used everywhere else. It also recognizes that not every field is fill-in-the-blank: a field's `fill_type` (`write`/`circle`/`check`/`shade`) is read from the photo, and choice-type fields are asked as an explicit choice (e.g. "Male or Female?") so the answer maps cleanly onto one of the form's real printed options. Decode mode never produces a file of any kind -- only fill mode does, and only once the interview is fully complete.

**Completion signal vs. structured extraction are two separate calls, on purpose.** The interview agent's only job is to conduct the interview and, once genuinely done, end its reply with a short literal tag (`FORM_COMPLETE_MARKER = "[FORM_COMPLETE]"`) -- no JSON, no field list. A **separate** call (`extraction_agent`, its own `LlmAgent` with `output_schema=FormExtractionOutput`) then reads the whole conversation and produces the structured data. This mirrors how `orchestrator.py` already gets a dependable structured decision out of Gemini: asking one free-flowing conversational reply to also emit precisely-formatted JSON inline, on its own initiative, is exactly the kind of instruction models don't reliably comply with, and was the actual root cause the first version of this feature shipped with (the JSON silently never showed up). `output_schema` enforcement on a dedicated call is far more dependable than hoping a chat reply free-types valid JSON in the right shape.

**The completed form is delivered as real images, not a PDF, and never AI-recreated from scratch -- always based on the user's own photo.** For every page the user uploaded, two images are produced (one English, one Japanese) via `backend/form_image_gen.py`: the user's actual photo is passed to Gemini's native image-editing model (`settings.FORM_IMAGE_MODEL_NAME`, e.g. `gemini-3.1-flash-image`) alongside a prompt asking it to redraw that same photo cleanly -- deskewed, same layout/colors/structure -- with each field filled in per its `fill_type` (write the answer, circle the option, check the box, or shade the bubble), and with printed labels translated to English for the English version while the Japanese version keeps the original text. This is a deliberate trade-off the user asked for over a plainer, more conservative typeset/overlay-only design: a generative model can still misplace or garble a mark (Google's own guidance is that dense text rendering is not fully reliable in one shot, though form answers are typically short strings, not paragraphs), in exchange for a result that actually looks like a filled-in version of the real form rather than a plain reference sheet.

Because that's a real, unavoidable reliability trade-off, every page/language combination has an independent fallback: `backend/form_overlay.py` overlays the translated answer directly onto a copy of the same uploaded photo at the model-estimated `x_pct`/`y_pct` position (inside a solid white box with a contrasting border so it stays legible against whatever's printed underneath), using a fill_type-aware label style (`( answer )` for circle, `[✓] answer` for check, `■ answer` for shade). This only kicks in per page/language if the AI image edit fails for that one (no image part returned, a safety block, an API error) -- so one bad page never costs the user the whole result. The bundled Noto Sans JP font (`backend/assets/fonts/`, OFL-licensed) covers both Japanese and Latin glyphs, so one font serves the overlay fallback for both languages.

`backend/server.py`'s `_all_image_attachments()` gathers every image across the *whole* conversation, in upload order, so a completed form's `page_number` (1-indexed) correctly maps back to the actual photo bytes (and mime type) even when the photos were sent across multiple earlier turns.

The generated images are returned to the frontend as base64 in `ChatResponse.generated_files`, not via a download-token endpoint -- this backend has no server-side session/storage by design (see "Stateless ADK invocation" below), and a token store would silently break the moment Cloud Run scales to a second instance. Embedding the bytes directly in the same stateless response has no such failure mode. `ChatBubble.tsx` renders each one as a real inline `<img>` thumbnail wrapped in an `<a download href="data:...">` (not through `react-markdown` -- its default link sanitizer does not allow `data:` URIs, so a markdown-embedded link would silently vanish), so a completed form appears the same way a dropped-in photo would, not as a plain text button.

This agent is also the first to need more than one photo per message: `AgentMetadata.max_images` (default `1`) drives `ComposerBar`'s photo picker generically -- images are staged with previews and a remove option instead of firing off a captionless message the instant one is picked, so multiple pages (plus optional caption text) go out together in one turn. No backend changes were needed for multi-image handling itself: `_turn_to_content()` already turns every attachment in a turn into its own `Part`, and full conversation replay already carries images across turns, so "add two more pages later in the same conversation" works without any special-casing.

### Voice I/O

- **Input**: the frontend records raw audio (`MediaRecorder`) and sends it as a base64 attachment. The backend feeds it straight into the Gemini call as a native `types.Part.from_bytes(...)` -- there is no separate speech-to-text step or service.
- **Output**: `POST /api/tts` synthesizes speech **on demand**, via Gemini's native TTS (`backend/tts.py`, using the same `google-genai` `Client`/auth branch as chat -- no separate TTS service, no extra IAM role). It's a separate endpoint from `/api/chat` so synthesis latency never blocks the visible text reply. Gemini TTS returns raw PCM; `tts.py` wraps it in a minimal WAV container so browsers can play it directly.
- The frontend always shows a tap-to-play speaker icon on every reply, and auto-plays it only when that turn's *input* was voice (`inputMode === "voice"`).

### WebSocket server -- correction, there isn't one

Unlike some earlier reference projects, this backend has **no WebSocket**. `backend/server.py` is a small stateless FastAPI app: `/config`, `/api/agents`, `/api/chat`, `/api/tts`, plus a static mount for the built frontend. In production (Cloud Run) `backend/static/` holds the built React app (copied there by the Dockerfile) and FastAPI serves it directly from the same origin. In local dev the two run separately (Vite dev server + `uvicorn --reload`).

**SPA fallback**: `StaticFiles(html=True)` only serves `index.html` at the exact mount root, not for client-side routes -- a deep link or refresh on `/chat/clinic_finder` would 404 without help. `server.py` registers a `404` exception handler that serves `static/index.html` for any unmatched `GET` that isn't under `/api/` or `/config`, letting React Router take over client-side.

### Frontend (`frontend/`)

Mobile-first React + Vite + TypeScript PWA (installable to home screen), Tailwind for styling, `react-markdown` for specialist replies, `react-router-dom` for `/` and `/chat/:agentId`.

- **`App.tsx`** wraps the router in `LocationProvider` (`src/context/LocationContext.tsx`), which requests device geolocation once, as soon as the app opens (Home screen) -- not lazily inside a chat -- so it's already available by the time an agent needs it, and location-aware agents (clinic finder, restaurant guide) can use it silently instead of asking for a landmark.
- **`ChatScreen.tsx`** owns the only meaningful client state: `turns: Turn[]`. Every panel visit starts fresh (`turns = []`); the backend is stateless so this array *is* the conversation. Falls back to fetching `/api/agents` and looking up by id if entered via a direct link/refresh/PWA shortcut with no router state.
- **`useAudioRecorder`** / **`useTtsPlayer`** hooks wrap `MediaRecorder` and on-demand `/api/tts` playback respectively; both are feature-detected so the app degrades to text-only where unsupported.
- Image attach (delivery scheduler's notice-slip photo) is shown/hidden purely from the `hasImageInput` flag on `/api/agents` -- no per-agent frontend file.
- PWA manifest/icons via `vite-plugin-pwa`; the manifest's `shortcuts` list is the one place that has to be manually updated when adding an agent (it's generated at frontend build time, before the backend registry exists to query).

### Key data flow

```
frontend -> POST /api/chat {agentId, history, newTurn, deviceContext}
          -> server.py runs the orchestrator (history replayed, device-context note appended)
          -> status "collecting": returns orchestrator's next question
          -> status "ready": server.py compiles collected fields + device context,
             runs the specialist root_agent one-shot, returns its final markdown
             (status "final_answer") in the SAME response
frontend -> POST /api/tts {text} -> raw audio bytes, on demand
```

### Auth modes

- **Local dev**: `GOOGLE_API_KEY` in `backend/.env.local`; `GlobalGemini` and `tts.py` both branch on `settings.USE_VERTEX` (false locally) to construct a plain API-key `google.genai.Client`.
- **Cloud Run**: `GOOGLE_GENAI_USE_VERTEXAI=true` + `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION` (set in `cloudbuild.yaml`); the attached service account's ADC transparently backs Vertex AI calls for both chat and TTS, and (given `roles/storage.objectViewer`) GCS access for the disaster agent's shelter data. Zero secrets committed, zero token setup required after `git push` + `gcloud builds submit` -- contingent only on enabling the Vertex AI API and granting the runtime service account `roles/aiplatform.user` (and, for Disaster Help, `roles/storage.objectViewer` on `kurasu-ai-shelter`) -- one-time, not git-tracked.
- `.dockerignore` explicitly excludes `backend/.env.local` from the build context -- without it, a developer's local API key would get baked into the image via `COPY backend/ .`.

### Agent IDs

`"clinic_finder"`, `"delivery_scheduler"`, `"restaurant_guide"`, `"disaster_agent"`, `"ingredient_checker"`, `"form_decoder_filler"` -- the `id` field of each `AGENT_METADATA`, used as the `agentId` in `/api/chat` and as the frontend route param (`/chat/:agentId`).

## Important invariants

- **`parse_json_loose`** (`backend/text_utils.py`) strips markdown fences before `json.loads` as a fallback under the orchestrator's `output_schema` -- belt-and-suspenders, not the primary mechanism.
- **`strip_markdown_for_speech`** removes markdown symbols before TTS so `**bold**`/`### headers`/links aren't read literally.
- **Stateless by design**: nothing about a conversation lives on the server between requests. If a bug looks like "the model forgot something," check whether the frontend is actually sending it back in `history`.
- **Follow-up questions work for free, for every agent**: the frontend never resets `turns` or disables the composer after `status: "final_answer"` (only after an explicit "Start a new request" tap), and every `/api/chat` call replays the *entire* history -- including the specialist's own prior reply -- before running the new turn. So a user can keep asking about the same answer (e.g., "why exactly is it not halal?") and the specialist sees its own earlier reasoning as real conversation history, not a fresh, context-less question. No per-agent code makes this happen; it falls out of the stateless full-history design.
- **Hard turn ceiling**: `server.py`'s `MAX_COLLECTING_TURNS` (4) forces handoff to the specialist regardless of what the orchestrator says once exceeded -- specialist agents are the entire point of the app, so the user can never get stuck endlessly re-answering the same question.
- **Deterministic-computation-then-inject pattern**: anywhere the app needs a precise, verifiable answer (QR code content via `backend/qr_decode.py`, a pasted image link via `backend/image_fetch.py`, nearest shelters via `backend/shelter_data.py`, JST time conversion in `server.py`), the computation happens in Python and is injected into the specialist's context as a verified note it's told to trust directly -- never left to the LLM to read/guess/recompute from a raw photo or timestamp.
- **Windows**: avoid non-ASCII characters (including emoji) in Python `print`/`log` statements -- reproducibly hits `UnicodeEncodeError` on Windows consoles (`cp932` codec) during local dev.
