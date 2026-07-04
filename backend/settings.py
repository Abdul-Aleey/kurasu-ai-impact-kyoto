import os

from dotenv import load_dotenv

load_dotenv(".env.local")

USE_VERTEX = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
GOOGLE_CLOUD_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-northeast1")

BACKEND_READY = USE_VERTEX or bool(GOOGLE_API_KEY)

MODEL_NAME = os.environ.get("KURASU_MODEL_NAME", "gemini-3.5-flash")
TTS_MODEL_NAME = os.environ.get("KURASU_TTS_MODEL_NAME", "gemini-2.5-flash-preview-tts")
TTS_VOICE_NAME = os.environ.get("KURASU_TTS_VOICE_NAME", "Kore")
FORM_IMAGE_MODEL_NAME = os.environ.get("KURASU_FORM_IMAGE_MODEL_NAME", "gemini-3.1-flash-image")

PORT = int(os.environ.get("API_BACKEND_PORT", "5000"))
