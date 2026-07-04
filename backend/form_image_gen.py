from typing import Literal

from google.genai import types

import settings
from agents.common import GlobalGemini

_FILL_INSTRUCTION = {
  "write": 'Write "{answer}" in the blank space for "{label}", in clear block lettering.',
  "circle": (
    'This field has bare printed option text with no checkbox next to it (Japanese convention: '
    '〇で囲む). Draw a clear hand-drawn circle/oval around ONLY the printed option "{answer}" for '
    '"{label}" -- around that option\'s text only, not a box, not a tick.'
  ),
  "check": (
    'This field has a small printed checkbox (☐/□) next to each option. Put a clear checkmark (✓) '
    'INSIDE that small printed box next to the option "{answer}" for "{label}". Mark ONLY the small '
    'box itself -- do NOT draw a circle or oval around the option\'s text, and do not mark any '
    'other option\'s box.'
  ),
  "shade": 'Fill in (shade solid, like a dark pen mark) the bubble or box for the printed option "{answer}" for "{label}".',
}


def _build_prompt(page: dict, language: Literal["en", "ja"]) -> str:
  language_instruction = (
    "Translate every printed label, heading, and instruction on this form into clear English, "
    "while keeping the exact same layout, structure, sections, and visual design."
    if language == "en" else
    "Keep every printed label, heading, and instruction on this form exactly as it already is, "
    "in the original Japanese -- do not translate or alter the original text."
  )
  answer_key = "answer_ja" if language == "ja" else "answer_en"

  lines = [
    "This is a photo of a real Japanese form that needs to be filled in. Redraw it as a clean, "
    "straight, high-quality, print-ready version: correct any tilt, skew, shadows, or glare from "
    "the photo, but preserve the original layout, structure, section order, and colors as "
    "closely as possible -- this should look like the same form, not a redesigned one.",
    language_instruction,
    "Follow real Japanese form-filling conventions, not generic marks: a bare printed option with "
    "no box next to it gets circled (〇で囲む); a printed checkbox (☐/□) next to an option gets a "
    "checkmark placed INSIDE that small box, never a circle around the option's text -- these two "
    "are visually different marks and must not be confused with each other, even when they're "
    "selecting from a similar-looking list of options.",
    "Now fill in the form exactly as follows, matching each instruction to the right field on "
    "the form:",
  ]
  for field in page["fields"]:
    template = _FILL_INSTRUCTION.get(field.get("fill_type", "write"), _FILL_INSTRUCTION["write"])
    lines.append("- " + template.format(answer=field.get(answer_key) or "-", label=field["label_en"]))
  lines.append(
    "Render all added text and marks clearly and legibly, in a color that stands out against the "
    "form's own printed text (e.g. blue or black ink look). Do not add, remove, or alter any "
    "field, label, or section that isn't explicitly listed above."
  )
  return "\n".join(lines)


def render_form_page_image(
    page: dict, page_image_bytes: bytes, page_image_mime_type: str, language: Literal["en", "ja"],
) -> tuple[bytes, str]:
  """Uses Gemini's native image-editing model to redraw one uploaded form
  photo -- deskewed and cleaned up, same layout/colors -- with that page's
  answers filled in per each field's fill_type (written text, a circled
  option, a checked box, or a shaded bubble). Returns (image_bytes,
  mime_type). Raises if the model returns no image part (e.g. a safety
  filter, or an ambiguous prompt), so the caller can fall back to the
  deterministic overlay renderer instead of returning nothing."""
  client = GlobalGemini(model=settings.FORM_IMAGE_MODEL_NAME).api_client
  prompt = _build_prompt(page, language)

  response = client.models.generate_content(
    model=settings.FORM_IMAGE_MODEL_NAME,
    contents=[
      types.Part.from_bytes(data=page_image_bytes, mime_type=page_image_mime_type),
      types.Part(text=prompt),
    ],
    config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
  )

  for part in response.candidates[0].content.parts:
    if part.inline_data and part.inline_data.data:
      return part.inline_data.data, part.inline_data.mime_type or "image/png"

  raise ValueError("Image model returned no image part")
