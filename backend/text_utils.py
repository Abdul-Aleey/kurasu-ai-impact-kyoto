import json
import re


def parse_json_loose(raw: str) -> dict:
  """Parses a JSON object out of `raw`, tolerating markdown code fences.

  The orchestrator uses ADK's `output_schema` (Gemini structured output),
  which should already guarantee raw JSON with no fences -- this is a
  defensive fallback for the rare case a model still wraps its answer in
  ```json ... ``` or includes stray text around the object.
  """
  text = raw.strip()
  fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
  if fence_match:
    text = fence_match.group(1).strip()
  try:
    return json.loads(text)
  except json.JSONDecodeError:
    pass

  brace_match = re.search(r"\{.*\}", text, re.DOTALL)
  if brace_match:
    return json.loads(brace_match.group(0))
  raise ValueError(f"Could not parse JSON from model output: {raw!r}")


def extract_marked_json(text: str, marker: str) -> tuple[str, dict | None]:
  """Some specialists emit a plain-text reply for most turns, but append a
  literal marker string followed by a JSON payload on the turn where
  they've finished a multi-turn task (e.g. a completed form). Splits those
  apart: returns (visible_text_with_marker_removed, parsed_json_or_None).
  If the marker is present but the JSON after it fails to parse, the
  marker is still stripped but None is returned -- a malformed payload
  shouldn't leak the raw marker/JSON into what the user sees."""
  if marker not in text:
    return text, None
  visible, _, json_part = text.partition(marker)
  visible = visible.strip()
  try:
    return visible, parse_json_loose(json_part)
  except ValueError:
    return visible, None


_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_HEADER = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_MD_BOLD_ITALIC = re.compile(r"(\*\*\*|\*\*|\*|__|_)")
_MD_CODE = re.compile(r"`([^`]*)`")


def strip_markdown_for_speech(text: str) -> str:
  """Removes markdown symbols before TTS so e.g. `**bold**` and
  `### Header` aren't read literally."""
  text = _MD_LINK.sub(r"\1", text)
  text = _MD_HEADER.sub("", text)
  text = _MD_CODE.sub(r"\1", text)
  text = _MD_BOLD_ITALIC.sub("", text)
  return text.strip()


# Hiragana, katakana, kanji (plus the rarer CJK extension-A block), Japanese
# punctuation/full-width space, and halfwidth katakana -- covers Japanese
# names/addresses that sometimes appear verbatim in a reply (e.g. an
# original-language name kept alongside its English translation).
_JAPANESE_CHARS = re.compile(
  r"[　-〿぀-ゟ゠-ヿ㐀-䶿一-鿿ｦ-ﾟ]+"
)


def strip_japanese_for_speech(text: str) -> str:
  """The TTS voice should skip Japanese words entirely rather than attempt
  to pronounce them -- removes them and cleans up whatever punctuation
  they leave behind (e.g. an empty "()" where a Japanese name used to sit
  next to its English translation)."""
  text = _JAPANESE_CHARS.sub(" ", text)
  text = re.sub(r"\(\s*\)", "", text)
  text = re.sub(r"\s+([.,!?:;])", r"\1", text)
  text = re.sub(r"\s+", " ", text)
  return text.strip()
