"""TUM-Dev Eat API client with 1-hour on-disk cache.

Eat API is a static GitHub Pages site; responses are stable for the week.
Cache to disk to stay well under any rate limits.

Docs: https://tum-dev.github.io/eat-api/docs/
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

EAT_API_BASE = "https://tum-dev.github.io/eat-api"
CANTEENS_ENUM_URL = f"{EAT_API_BASE}/enums/canteens.json"
CACHE_TTL_SECONDS = 60 * 60  # 1 hour
DEFAULT_CACHE_DIR = "/tmp/eat-cache"

_DEFAULT_CANTEENS = [
    {"id": "mensa-garching", "name": "Mensa Garching", "campus": "Garching"},
    {"id": "mensa-arcisstr", "name": "Mensa Arcisstr.", "campus": "Main"},
    {"id": "mensa-lothstr", "name": "Mensa Lothstr.", "campus": "Lothstr."},
]


def _cache_dir() -> Path:
    d = Path(os.environ.get("EAT_API_CACHE_DIR", DEFAULT_CACHE_DIR))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_path(key: str) -> Path:
    safe = key.replace("/", "_").replace(":", "_")
    return _cache_dir() / f"{safe}.json"


def _read_cache(key: str) -> Any | None:
    p = _cache_path(key)
    if not p.exists():
        return None
    if time.time() - p.stat().st_mtime > CACHE_TTL_SECONDS:
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(key: str, data: Any) -> None:
    try:
        _cache_path(key).write_text(json.dumps(data))
    except OSError:
        pass


def _http_get_json(url: str, cache_key: str) -> Any:
    cached = _read_cache(cache_key)
    if cached is not None:
        return cached
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    _write_cache(cache_key, data)
    return data


def _parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _week_url(canteen_id: str, d: date) -> tuple[str, str]:
    iso_year, iso_week, _ = d.isocalendar()
    url = f"{EAT_API_BASE}/{canteen_id}/{iso_year}/{iso_week:02d}.json"
    key = f"{canteen_id}_{iso_year}_{iso_week:02d}"
    return url, key


def _format_student_price(dish: dict) -> str | None:
    """Format the student price as e.g. '3.50€', '0.90€/100g', or '0.50€ + 0.90€/100g'.

    Eat API shape: {"base_price": float, "price_per_unit": float, "unit": str}.
    Returns None when no non-zero price component is available.
    """
    prices = dish.get("prices") or {}
    student = prices.get("students") or prices.get("student") or {}
    if not isinstance(student, dict):
        return None
    base = student.get("base_price")
    per_unit = student.get("price_per_unit")
    unit = student.get("unit")
    parts: list[str] = []
    if isinstance(base, (int, float)) and base > 0:
        parts.append(f"{float(base):.2f}€")
    if isinstance(per_unit, (int, float)) and per_unit > 0 and isinstance(unit, str) and unit:
        parts.append(f"{float(per_unit):.2f}€/{unit}")
    return " + ".join(parts) if parts else None


def fetch_week(canteen_id: str, d: date) -> dict:
    """Raw weekly payload for the ISO week containing `d`."""
    url, key = _week_url(canteen_id, d)
    return _http_get_json(url, key)


def fetch_menu(canteen_id: str, date_str: str) -> list[dict]:
    """Return dishes for a single day across the three main canteens.

    Returns a list of {name, dish_type, price_student, labels}.
    `price_student` is a pre-formatted display string like '1.00€ + 0.90€/100g'
    (or None when no price is available). Raises on HTTP error; callers in
    tools.py convert to soft errors.
    """
    d = _parse_date(date_str)
    week = fetch_week(canteen_id, d)
    iso_target = d.isoformat()
    for day in week.get("days", []):
        if day.get("date") == iso_target:
            out = []
            for dish in day.get("dishes", []):
                out.append({
                    "name": dish.get("name", ""),
                    "dish_type": dish.get("dish_type", ""),
                    "price_student": _format_student_price(dish),
                    "labels": list(dish.get("labels") or []),
                })
            return out
    return []


def list_canteens() -> list[dict]:
    """Return the supported canteens. Falls back to the MVP 3 if enum fetch fails."""
    try:
        raw = _http_get_json(CANTEENS_ENUM_URL, "canteens_enum")
    except requests.RequestException:
        return list(_DEFAULT_CANTEENS)
    out = []
    for c in raw if isinstance(raw, list) else []:
        cid = c.get("canteen_id") or c.get("id")
        if not cid:
            continue
        out.append({
            "id": cid,
            "name": c.get("name", cid),
            "campus": c.get("location", {}).get("address", "") if isinstance(c.get("location"), dict) else "",
        })
    return out or list(_DEFAULT_CANTEENS)
