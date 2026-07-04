import io
import re
import wave

from google.genai import types

import settings
from agents.common import GlobalGemini
from text_utils import strip_japanese_for_speech, strip_markdown_for_speech

_PCM_RATE_RE = re.compile(r"rate=(\d+)")


def _wrap_pcm_as_wav(pcm_bytes: bytes, mime_type: str) -> bytes:
  """Gemini TTS returns raw 16-bit PCM (mime like 'audio/L16;rate=24000').
  Browsers can't play raw PCM via <audio>, so wrap it in a minimal WAV
  container. Any other mime type is assumed already-playable and passed
  through untouched by the caller.
  """
  rate_match = _PCM_RATE_RE.search(mime_type)
  sample_rate = int(rate_match.group(1)) if rate_match else 24000

  buffer = io.BytesIO()
  with wave.open(buffer, "wb") as wav_file:
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)  # 16-bit
    wav_file.setframerate(sample_rate)
    wav_file.writeframes(pcm_bytes)
  return buffer.getvalue()


def synthesize(text: str) -> tuple[bytes, str]:
  """Synthesizes `text` to speech using Gemini's native TTS model, via the
  same google-genai Client (and same Vertex/API-key auth branch) already
  used for chat -- one unified auth story, no separate TTS service/IAM role.
  Returns (audio_bytes, content_type).
  """
  spoken_text = strip_japanese_for_speech(strip_markdown_for_speech(text))
  client = GlobalGemini(model=settings.TTS_MODEL_NAME).api_client

  # Gemini's native TTS has no numeric speech-rate parameter -- pace and
  # delivery style are controlled by describing them in the prompt itself.
  # Prepending this instruction (not spoken aloud, interpreted as a style
  # cue) is the documented way to get a brisker, more natural pace instead
  # of the default reading, which trends slow for long responses.
  styled_text = f"Say the following clearly at a natural, brisk pace, not slow:\n{spoken_text}"

  response = client.models.generate_content(
    model=settings.TTS_MODEL_NAME,
    contents=styled_text,
    config=types.GenerateContentConfig(
      response_modalities=["AUDIO"],
      speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
          prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=settings.TTS_VOICE_NAME)
        )
      ),
    ),
  )

  part = response.candidates[0].content.parts[0]
  audio_bytes = part.inline_data.data
  mime_type = part.inline_data.mime_type or ""

  if mime_type.startswith("audio/L16") or "pcm" in mime_type:
    return _wrap_pcm_as_wav(audio_bytes, mime_type), "audio/wav"
  return audio_bytes, mime_type or "audio/wav"
