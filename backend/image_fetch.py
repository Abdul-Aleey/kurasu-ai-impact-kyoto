import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_MAX_BYTES = 8 * 1024 * 1024
_TIMEOUT_SECONDS = 6.0


def find_urls(text: str | None) -> list[str]:
  return _URL_RE.findall(text or "")


def _is_safe_host(hostname: str) -> bool:
  """Rejects private/loopback/link-local targets (e.g. cloud metadata
  endpoints) before the server makes an outbound request to a user-supplied
  URL, as basic SSRF protection."""
  try:
    addr_info = socket.getaddrinfo(hostname, None)
  except socket.gaierror:
    return False
  for info in addr_info:
    ip = ipaddress.ip_address(info[4][0])
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
      return False
  return True


async def try_fetch_image(url: str) -> tuple[bytes, str] | None:
  """Fetches `url` and returns (bytes, mime_type) only if it resolves to a
  safe public host and the response is actually an image within a size cap.
  Lets a user paste a link to a photo (e.g. of a notice slip) as plain text
  instead of uploading it, while guarding against SSRF and oversized bodies.
  """
  parsed = urlparse(url)
  if parsed.scheme not in ("http", "https") or not parsed.hostname:
    return None
  if not _is_safe_host(parsed.hostname):
    return None

  try:
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, follow_redirects=True) as client:
      response = await client.get(url)
      content_type = response.headers.get("content-type", "").split(";")[0].strip()
      if not content_type.startswith("image/"):
        return None
      if len(response.content) > _MAX_BYTES:
        return None
      return response.content, content_type
  except httpx.HTTPError:
    return None
