import logging

import httpx

log = logging.getLogger("kurasu.waste_location")

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_TIMEOUT_SECONDS = 5.0
# Nominatim's usage policy requires a real, identifying User-Agent -- a
# generic/default one gets silently rate-limited or blocked.
_USER_AGENT = "KurasuAI-WasteGuide/1.0 (https://github.com/Abdul-Aleey/kurasu-ai-impact-kyoto)"


async def reverse_geocode_area(lat: float, lng: float) -> str | None:
  """Turns GPS coordinates into a human-readable Japanese administrative
  area name (e.g. "Shibuya, Tokyo" or "Naka Ward, Yokohama, Kanagawa
  Prefecture"), suitable for looking up municipality-specific waste-sorting
  rules. Uses OpenStreetMap's free Nominatim reverse-geocoding service (no
  API key needed) rather than asking an LLM to guess a ward/city from raw
  coordinates, which it cannot reliably do. Returns None on any failure
  (network error, unparseable response, non-Japan location) so the caller
  can fall back to asking the user directly -- never guesses or fabricates
  a place name.

  Japan's administrative naming is genuinely inconsistent in OSM's data:
  Tokyo's 23 special wards appear as a top-level "city" with no separate
  prefecture-level field at all, while a regular city (e.g. Osaka,
  Yokohama) has its ward under "suburb"/"city_district" and its prefecture
  under "province"/"state". Every field is tried in priority order rather
  than assumed to always be present in the same place.
  """
  try:
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
      response = await client.get(
        _NOMINATIM_URL,
        params={
          "lat": lat, "lon": lng, "format": "jsonv2",
          "accept-language": "en", "zoom": 14,
        },
        headers={"User-Agent": _USER_AGENT},
      )
      response.raise_for_status()
      data = response.json()
  except (httpx.HTTPError, ValueError):
    log.warning("Reverse geocoding failed for (%s, %s)", lat, lng, exc_info=True)
    return None

  address = data.get("address", {})
  if not address or address.get("country_code") != "jp":
    return None

  parts: list[str] = []

  # Deliberately excludes "quarter"/"neighbourhood" -- those are informal,
  # sub-ward-level names (and sometimes untranslated Japanese even with
  # accept-language=en) that don't change which municipality's waste rules
  # apply, so including them just adds confusing extra detail.
  for key in ("suburb", "city_district"):
    if address.get(key):
      parts.append(address[key])
      break

  for key in ("city", "town", "village", "municipality"):
    value = address.get(key)
    if value and value not in parts:
      parts.append(value)
      break

  for key in ("province", "state"):
    if address.get(key):
      parts.append(address[key])
      break
  else:
    # Tokyo's 23 special wards don't carry a separate prefecture-level
    # field in OSM's data -- "Tokyo" only ever shows up inside display_name
    # for these, never broken out as its own address component.
    display_name = data.get("display_name", "")
    if "Tokyo" in display_name and "Tokyo" not in parts:
      parts.append("Tokyo")

  return ", ".join(parts) if parts else None
