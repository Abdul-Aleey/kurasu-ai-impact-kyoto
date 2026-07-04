# Kurasu AI

A mobile-first assistant for living in Japan. Pick one of six panels -- **Clinic Finder**, **Delivery Scheduler**, **Restaurant Guide**, **Disaster Help**, **Ingredient Checker**, or **Form Decoder & Filler** -- and a Kurasu AI orchestrator gathers what it needs (by text or voice) before handing your request to a specialist Google ADK agent that searches the web (or, for Disaster Help, looks up real GCS shelter data) and answers in one shot. You can keep asking follow-up questions about the same answer afterward -- the backend always sees the full conversation, not just the latest message.

Built as a React PWA + FastAPI backend in a single Cloud Run service, powered by Gemini via Vertex AI.

## Quickstart (local dev)

**Backend**
```bash
cd backend
pip install -r requirements.txt
```
Create `backend/.env.local` (gitignored):
```
API_BACKEND_PORT=5000
GOOGLE_API_KEY=AIza...       # a Gemini API key, from https://aistudio.google.com/apikey
```
```bash
uvicorn server:app --host 127.0.0.1 --port 5000 --reload
```

**Frontend** (separate terminal)
```bash
cd frontend
npm install
```
Create `frontend/.env` (gitignored):
```
VITE_BACKEND_URL=http://localhost:5000
```
```bash
npm run dev
```
Open http://localhost:5173.

No API key configured yet? The app still loads and shows a clear "backend not configured" banner instead of crashing -- useful for frontend-only work.

## One-time GCP setup (for deployment)

1. Enable the **Vertex AI API** on your GCP project.
2. Grant the Cloud Run runtime service account the `roles/aiplatform.user` role.
3. For the Disaster Help agent: grant the same service account `roles/storage.objectViewer` on the `kurasu-ai-shelter` bucket, so it can read the two shelter CSVs at startup. Without this, the agent still works, just in a degraded web-search-only mode (logged, not a crash).

There's no separate TTS service to enable; speech synthesis rides the same Vertex AI client as chat.

## Deploy

```bash
gcloud builds submit --config cloudbuild.yaml
```

This builds the Docker image (frontend built to static assets, served by the same FastAPI backend), pushes it, and deploys to Cloud Run as `kurasu-ai` in `asia-northeast1`, with `GOOGLE_GENAI_USE_VERTEXAI=true` set so it authenticates via the service account's ADC -- no API key needed in production, and nothing secret is ever committed to git.

## Architecture

See [DEVELOPMENT.md](./DEVELOPMENT.md) for the full architecture writeup: the orchestrator/handoff protocol, the stateless request model, voice I/O, and how to add a new agent.
