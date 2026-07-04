import numpy as np
import cv2


def decode_qr_code(image_bytes: bytes) -> str | None:
  """Deterministically decodes a QR code from raw image bytes, if present.

  Reading a QR code is a precise pixel-grid decoding problem, not something
  a vision-language model reliably does just by "looking" at the image --
  this gives the delivery scheduler agent ground-truth decoded content
  (usually the courier's redelivery URL) instead of relying on the model to
  guess at it from the photo.
  """
  if not image_bytes:
    return None

  try:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
      return None

    detector = cv2.QRCodeDetector()
    data, _points, _straight_qrcode = detector.detectAndDecode(image)
    return data or None
  except cv2.error:
    return None
