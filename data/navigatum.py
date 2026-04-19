"""Navigatum client for campus building coordinates + walking distance.

Docs: https://nav.tum.de/api
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any
import json

import requests

NAV_API_BASE = "https://nav.tum.de/api"
WALK_METERS_PER_MIN = 83.0
CACHE_DIR = Path(os.environ.get("EAT_API_CACHE_DIR", "/tmp/eat-cache")) / "nav"


def _cache_path(location_id: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = location_id.replace("/", "_").replace(":", "_")
    return CACHE_DIR / f"{safe}.json"


def _lookup_location(location_id: str) -> dict[str, Any]:
    cached = _cache_path(location_id)
    if cached.exists():
        try:
            return json.loads(cached.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    url = f"{NAV_API_BASE}/locations/{location_id}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    try:
        cached.write_text(json.dumps(data))
    except OSError:
        pass
    return data


def _extract_coords(payload: dict[str, Any]) -> tuple[float, float] | None:
    coords = payload.get("coords") or payload.get("coordinates") or {}
    if isinstance(coords, dict):
        lat = coords.get("lat")
        lon = coords.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return float(lat), float(lon)
    return None


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two (lat, lon) points."""
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def get_canteen_distance(origin_id: str, canteen_id: str) -> dict:
    """Compute walking distance + minutes between two Navigatum location IDs."""
    origin = _lookup_location(origin_id)
    dest = _lookup_location(canteen_id)
    o = _extract_coords(origin)
    d = _extract_coords(dest)
    if not o or not d:
        raise ValueError(f"Missing coordinates for {origin_id!r} or {canteen_id!r}")
    meters = haversine_meters(o[0], o[1], d[0], d[1])
    walk = max(1, round(meters / WALK_METERS_PER_MIN))
    return {"meters": int(round(meters)), "walk_minutes": int(walk)}
