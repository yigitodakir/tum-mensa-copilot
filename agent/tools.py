"""LangChain @tool wrappers around data/* modules.

All tools fail soft: on exception they return {"error": "..."} instead of
raising so the agent can surface the problem in natural language.
"""
from __future__ import annotations

from typing import List, Union

from langchain_core.tools import tool

from data import eat_api, s3_store


def _soft(fn):
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001 — intentional: tools fail soft
            return {"error": f"{type(e).__name__}: {e}"}
    return wrapped


@tool
def fetch_menu(canteen_id: str, date: str) -> Union[List[dict], dict]:
    """Return today's dishes from a TUM canteen.

    Args:
        canteen_id: one of 'mensa-garching', 'mensa-arcisstr', 'mensa-lothstr'
                    (or any ID from the eat-api canteens enum).
        date: ISO date 'YYYY-MM-DD'. Must be today or later this week.

    Returns: list of {name, dish_type, price_student, labels}.
    `price_student` is a pre-formatted display string like '1.00€ + 0.90€/100g'
    (some canteens sell by weight). Quote it verbatim; do not reformat.
    """
    return _soft(eat_api.fetch_menu)(canteen_id, date)


@tool
def list_canteens() -> Union[List[dict], dict]:
    """Return supported canteens with {id, name, campus}."""
    return _soft(eat_api.list_canteens)()


@tool
def get_user_profile(user_id: str) -> dict:
    """Return the stored dietary profile for a Matrix user.

    Shape: {
      diet: 'omnivore'|'vegetarian'|'vegan'|'pescatarian',
      allergens: [str],
      avoid_labels: [str],
      preferred_canteens: [str],
      push_optin: bool
    }
    Returns defaults if the user is new.
    """
    return _soft(s3_store.get_profile)(user_id)


@tool
def save_user_profile(user_id: str, patch: dict) -> dict:
    """Deep-merge `patch` into the user's profile and persist. Returns the new profile."""
    return _soft(s3_store.save_profile)(user_id, patch)


@tool
def log_meal_rating(
    user_id: str,
    meal_name: str,
    liked: bool,
    note: str = "",
) -> dict:
    """Record whether the user liked or disliked a meal.
    liked=True means enjoyed, liked=False means avoid in future.
    Do not ask which canteen — if the user mentioned one, put it in `note` instead."""
    return _soft(s3_store.append_rating)(user_id, meal_name, "", liked, note)


@tool
def get_meal_history(user_id: str, limit: int = 20) -> Union[List[dict], dict]:
    """Most recent ratings, newest first."""
    return _soft(s3_store.get_ratings)(user_id, limit)


ALL_TOOLS = [
    fetch_menu,
    list_canteens,
    get_user_profile,
    save_user_profile,
    log_meal_rating,
    get_meal_history,
]
