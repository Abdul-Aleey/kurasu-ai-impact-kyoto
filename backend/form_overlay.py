import io
import logging
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

logging.getLogger("fontTools").setLevel(logging.WARNING)

_FONT_PATH = Path(__file__).parent / "assets" / "fonts" / "NotoSansJP-Regular.ttf"

# A clearly contrasting color plus a solid background box behind each
# answer -- the underlying form is a real, potentially busy scanned photo,
# so the overlay needs to stay legible regardless of whatever's printed
# underneath it, not just be colored text floating on top.
_ANSWER_COLOR = (176, 32, 32)
_BOX_PADDING = 4

_FILL_LABEL = {
  "write": "{answer}",
  "circle": "( {answer} )",
  "check": "[✓] {answer}",
  "shade": "■ {answer}",
}


def _font_size_for(image_height: int) -> int:
  # Scales with resolution so the answer text stays a sensible size
  # relative to the photo, whether it's a phone snapshot or a high-res scan.
  return max(16, min(48, int(image_height * 0.022)))


def render_overlaid_page_image(page: dict, page_image_bytes: bytes, language: Literal["en", "ja"]) -> bytes:
  """Deterministic fallback for one page: overlays translated answers
  directly onto a copy of the user's own uploaded photo, at AI-estimated
  positions (`x_pct`/`y_pct` per field), rather than regenerating the
  image with AI -- used when `form_image_gen` can't produce a result for
  this specific page/language (safety filter, no image part returned,
  API error, etc.), so a generation hiccup never means the user gets
  nothing for that page. Position accuracy is a best-effort visual
  estimate, not guaranteed pixel-perfect. Returns PNG bytes."""
  answer_key = "answer_ja" if language == "ja" else "answer_en"

  img = Image.open(io.BytesIO(page_image_bytes)).convert("RGB")
  draw = ImageDraw.Draw(img)
  width, height = img.size
  font = ImageFont.truetype(str(_FONT_PATH), size=_font_size_for(height))

  for field in page["fields"]:
    answer = str(field.get(answer_key) or "-")
    label_template = _FILL_LABEL.get(field.get("fill_type", "write"), _FILL_LABEL["write"])
    text = label_template.format(answer=answer)

    x = int((float(field.get("x_pct", 0) or 0) / 100) * width)
    y = int((float(field.get("y_pct", 0) or 0) / 100) * height)
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))

    bbox = draw.textbbox((x, y), text, font=font)
    box = (
      bbox[0] - _BOX_PADDING, bbox[1] - _BOX_PADDING,
      bbox[2] + _BOX_PADDING, bbox[3] + _BOX_PADDING,
    )
    draw.rectangle(box, fill=(255, 255, 255), outline=_ANSWER_COLOR, width=2)
    draw.text((x, y), text, fill=_ANSWER_COLOR, font=font)

  buffer = io.BytesIO()
  img.save(buffer, format="PNG")
  return buffer.getvalue()
