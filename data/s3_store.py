"""S3-backed persistence for user profiles and meal ratings.

Layout (single bucket, two prefixes):
  profiles/<user_id>.json   single JSON blob per user
  ratings/<user_id>.jsonl   append-only, one JSON per line

user_id is the Matrix MXID, URL-safe encoded.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

PROFILE_DEFAULTS = {
    "diet": "omnivore",
    "allergens": [],
    "avoid_labels": [],
    "preferred_canteens": [],
    "push_optin": False,
}


def _bucket() -> str:
    b = os.environ.get("COPILOT_BUCKET")
    if not b:
        raise RuntimeError("COPILOT_BUCKET env var not set")
    return b


_s3_client = None


def _s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "eu-central-1"))
    return _s3_client


def _encode_user(user_id: str) -> str:
    return quote(user_id, safe="")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_object_json(key: str) -> dict | None:
    try:
        resp = _s3().get_object(Bucket=_bucket(), Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return None
        raise
    return json.loads(resp["Body"].read())


def _put_object_json(key: str, body: Any) -> None:
    _s3().put_object(
        Bucket=_bucket(),
        Key=key,
        Body=json.dumps(body).encode("utf-8"),
        ContentType="application/json",
    )


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _profile_key(user_id: str) -> str:
    return f"profiles/{_encode_user(user_id)}.json"


def _ratings_key(user_id: str) -> str:
    return f"ratings/{_encode_user(user_id)}.jsonl"


# ---------- Profiles ----------

def get_profile(user_id: str) -> dict:
    data = _get_object_json(_profile_key(user_id))
    if data is None:
        now = _now_iso()
        return {
            **PROFILE_DEFAULTS,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
    return data


def save_profile(user_id: str, patch: dict) -> dict:
    existing = _get_object_json(_profile_key(user_id))
    if existing is None:
        existing = {**PROFILE_DEFAULTS, "user_id": user_id, "created_at": _now_iso()}
    merged = _deep_merge(existing, patch)
    merged["user_id"] = user_id
    merged["updated_at"] = _now_iso()
    _put_object_json(_profile_key(user_id), merged)
    return merged


def list_optin_user_ids() -> list[str]:
    bucket = _bucket()
    users: list[str] = []
    paginator = _s3().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="profiles/"):
        for obj in page.get("Contents", []) or []:
            body = _get_object_json(obj["Key"])
            if body and body.get("push_optin"):
                users.append(body.get("user_id", ""))
    return [u for u in users if u]


# ---------- Ratings ----------

def append_rating(user_id: str, meal_name: str, canteen: str, liked: bool, note: str = "") -> dict:
    entry = {
        "ts": _now_iso(),
        "meal": meal_name,
        "canteen": canteen,
        "liked": bool(liked),
        "note": note,
    }
    key = _ratings_key(user_id)
    try:
        resp = _s3().get_object(Bucket=_bucket(), Key=key)
        existing = resp["Body"].read().decode("utf-8")
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            existing = ""
        else:
            raise
    new_body = existing + json.dumps(entry) + "\n"
    _s3().put_object(
        Bucket=_bucket(),
        Key=key,
        Body=new_body.encode("utf-8"),
        ContentType="application/x-ndjson",
    )
    return entry


def get_ratings(user_id: str, limit: int = 20) -> list[dict]:
    try:
        resp = _s3().get_object(Bucket=_bucket(), Key=_ratings_key(user_id))
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return []
        raise
    lines = resp["Body"].read().decode("utf-8").splitlines()
    entries = [json.loads(l) for l in lines if l.strip()]
    entries.reverse()
    return entries[:limit]
