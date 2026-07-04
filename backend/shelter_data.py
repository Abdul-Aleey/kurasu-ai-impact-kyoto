import io
import logging

import numpy as np
import pandas as pd
from google.cloud import storage

log = logging.getLogger("kurasu.shelter_data")

BUCKET_NAME = "kurasu-ai-shelter"
EMERGENCY_SITES_FILE = "emergency_evacuation_sites.csv"
EVACUATION_CENTERS_FILE = "designated_evacuation_center_data.csv"

# Standard Japan GSI (国土地理院) open-data headers for 指定緊急避難場所 /
# 指定避難所 datasets, with generic fallbacks in case this bucket's export
# varies slightly -- can't be verified without live access to the bucket.
LAT_COLUMN_CANDIDATES = ["緯度", "lat", "latitude"]
LNG_COLUMN_CANDIDATES = ["経度", "lng", "lon", "longitude"]
NAME_COLUMN_CANDIDATES = ["施設・場所名", "施設名", "名称", "name"]

# Disaster-type columns on the emergency-sites file. Each flags whether that
# specific site is designated safe for that specific disaster -- a site good
# for fire evacuation is not necessarily safe ground for a tsunami, so
# filtering by this (when we can) is a real safety improvement, not just a
# nice-to-have.
DISASTER_TYPE_COLUMNS = {
  "flood": "洪水",
  "landslide": "崖崩れ、土石流及び地滑り",
  "storm_surge": "高潮",
  "earthquake": "地震",
  "tsunami": "津波",
  "fire": "大規模な火事",
  "internal_flooding": "内水氾濫",
  "volcanic": "火山現象",
}
_CRISIS_TYPE_KEYWORDS = {
  "flood": ["flood"],
  "landslide": ["landslide", "mudslide", "slide"],
  "storm_surge": ["storm surge", "surge"],
  "earthquake": ["earthquake", "quake", "shaking"],
  "tsunami": ["tsunami"],
  "fire": ["fire"],
  "internal_flooding": ["urban flooding", "drainage"],
  "volcanic": ["volcano", "volcanic", "eruption"],
}

_EARTH_RADIUS_KM = 6371.0

_emergency_sites_df: pd.DataFrame | None = None
_evacuation_centers_df: pd.DataFrame | None = None


def _download_csv_as_dataframe(bucket_name: str, blob_name: str) -> pd.DataFrame:
  client = storage.Client()
  blob = client.bucket(bucket_name).blob(blob_name)
  raw_bytes = blob.download_as_bytes()

  last_error: Exception | None = None
  for encoding in ("utf-8", "shift_jis"):
    try:
      return pd.read_csv(io.BytesIO(raw_bytes), encoding=encoding)
    except UnicodeDecodeError as e:
      last_error = e
      continue
  raise ValueError(f"Could not decode {blob_name} with utf-8 or shift_jis") from last_error


def _find_column(df: pd.DataFrame, candidates: list[str], purpose: str) -> str:
  for name in candidates:
    if name in df.columns:
      return name
  raise ValueError(f"Could not find a {purpose} column. Actual columns: {list(df.columns)}")


def load_shelter_data() -> None:
  """Downloads both shelter CSVs from GCS into RAM once, at process startup,
  so nearest-shelter lookups never hit the network per-request. Any failure
  (missing bucket, no IAM access, unexpected encoding/columns) is logged and
  leaves the data as unavailable rather than crashing the app -- the
  disaster agent falls back to a web-search-based degraded mode."""
  global _emergency_sites_df, _evacuation_centers_df
  try:
    _emergency_sites_df = _download_csv_as_dataframe(BUCKET_NAME, EMERGENCY_SITES_FILE)
    _evacuation_centers_df = _download_csv_as_dataframe(BUCKET_NAME, EVACUATION_CENTERS_FILE)
    log.info(
      "Loaded shelter data: %d emergency sites, %d evacuation centers",
      len(_emergency_sites_df), len(_evacuation_centers_df),
    )
  except Exception:
    log.exception("Failed to load shelter data from GCS -- disaster agent will run in degraded mode")
    _emergency_sites_df = None
    _evacuation_centers_df = None


def _haversine_km(lat1: float, lng1: float, lat2: np.ndarray, lng2: np.ndarray) -> np.ndarray:
  lat1_r, lng1_r, lat2_r, lng2_r = map(np.radians, [lat1, lng1, lat2, lng2])
  dlat = lat2_r - lat1_r
  dlng = lng2_r - lng1_r
  a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlng / 2) ** 2
  return _EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))


def _nearest_from(df: pd.DataFrame, user_lat: float, user_lng: float, top_n: int) -> list[dict]:
  lat_col = _find_column(df, LAT_COLUMN_CANDIDATES, "latitude")
  lng_col = _find_column(df, LNG_COLUMN_CANDIDATES, "longitude")
  name_col = _find_column(df, NAME_COLUMN_CANDIDATES, "name")

  lats = pd.to_numeric(df[lat_col], errors="coerce").values
  lngs = pd.to_numeric(df[lng_col], errors="coerce").values
  distances = _haversine_km(user_lat, user_lng, lats, lngs)

  valid = ~np.isnan(distances)
  valid_indices = np.where(valid)[0]
  if len(df) > 0 and len(valid_indices) == 0:
    # Columns were found by name, but every value in them failed to parse
    # as a coordinate -- silently returning an empty list here would look
    # identical to "no shelters exist," which is a much more confusing
    # failure mode to debug than a clear log line pointing at the real cause.
    log.warning(
      "All %d rows in %s/%s failed to parse as numeric coordinates -- check for a header/format mismatch",
      len(df), lat_col, lng_col,
    )
  nearest = valid_indices[np.argsort(distances[valid_indices])[:top_n]]

  return [
    {
      "name": str(df.iloc[i][name_col]),
      "lat": float(df.iloc[i][lat_col]),
      "lng": float(df.iloc[i][lng_col]),
      "distance_km": round(float(distances[i]), 2),
    }
    for i in nearest
  ]


def _filter_by_crisis_type(df: pd.DataFrame, crisis_type: str) -> pd.DataFrame:
  """Best-effort: narrows emergency sites to ones flagged safe for the
  user's specific disaster type. Falls back to the unfiltered dataframe if
  the crisis type isn't recognized, the column isn't found, or filtering
  would leave nothing -- an imperfect but present result beats none, and
  the specialist agent is told this filtering is best-effort either way."""
  if not crisis_type:
    return df
  crisis_lower = crisis_type.lower()
  matched_key = next(
    (key for key, keywords in _CRISIS_TYPE_KEYWORDS.items() if any(k in crisis_lower for k in keywords)),
    None,
  )
  if not matched_key:
    return df

  column = DISASTER_TYPE_COLUMNS.get(matched_key)
  if not column or column not in df.columns:
    return df

  filtered = df[df[column].notna() & (df[column].astype(str).str.strip() != "")]
  return filtered if len(filtered) > 0 else df


def find_nearest_shelters(user_lat: float, user_lng: float, crisis_type: str = "", top_n: int = 3) -> dict:
  """Returns the nearest emergency sites AND evacuation centers, ready to be
  injected as verified context for the disaster agent. `data_available` is
  False if the CSVs never loaded (e.g. no GCS access), in which case both
  lists are empty and the caller should fall back to a web search instead."""
  if _emergency_sites_df is None or _evacuation_centers_df is None:
    return {"data_available": False, "emergency_sites": [], "evacuation_centers": []}

  try:
    filtered_sites = _filter_by_crisis_type(_emergency_sites_df, crisis_type)
    # Designated evacuation centers (indoor/longer-term) don't carry
    # per-disaster-type flag columns in the standard GSI schema the way
    # emergency sites do, so this filter is expected to no-op here in the
    # typical case -- it's applied anyway as a harmless defensive measure,
    # since _filter_by_crisis_type() already falls back to unfiltered if
    # the matching column isn't present, and can only help if this
    # specific bucket's export happens to carry it.
    filtered_centers = _filter_by_crisis_type(_evacuation_centers_df, crisis_type)
    return {
      "data_available": True,
      "emergency_sites": _nearest_from(filtered_sites, user_lat, user_lng, top_n),
      "evacuation_centers": _nearest_from(filtered_centers, user_lat, user_lng, top_n),
    }
  except Exception:
    log.exception("Shelter lookup failed despite loaded data")
    return {"data_available": False, "emergency_sites": [], "evacuation_centers": []}
