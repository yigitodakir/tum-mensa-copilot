"""Hit the agent end-to-end with 5 canned prompts against live Bedrock + Eat API.

Usage:
    python scripts/smoke_test.py

Requires the same env as bot/matrix_bot.py (AWS creds + COPILOT_BUCKET).
Exits non-zero if any prompt fails.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from agent.graph import ask  # noqa: E402 — load_dotenv must run first

PROMPTS = [
    "What's for lunch today at Garching?",
    "I'm vegan, any options?",
    "Save my allergen: lactose.",
    "I had the Chili today, 4/5.",
    "How close is Arcisstr mensa to MI HS1?",
]

DEMO_USER = "@smoketest:tum.de"


def main() -> int:
    failures = 0
    for i, prompt in enumerate(PROMPTS, 1):
        print(f"\n── [{i}/{len(PROMPTS)}] {prompt}")
        try:
            reply = ask(DEMO_USER, prompt)
        except Exception:
            failures += 1
            print("ERROR:")
            traceback.print_exc()
            continue
        print(reply)
        if len(reply) <= 20:
            failures += 1
            print(f"FAIL: reply too short ({len(reply)} chars)")
    print(f"\n── {len(PROMPTS) - failures}/{len(PROMPTS)} prompts OK")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
