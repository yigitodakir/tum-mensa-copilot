"""TUM Mensa Co-Pilot — interactive CLI chatbot.

Usage:
    python chat.py

Type 'exit' or press Ctrl-D to quit.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from agent.graph import ask  # noqa: E402 — load_dotenv must run first

USER_ID = "cli-user"


def main() -> int:
    print("Campus Mensa Co-Pilot. Type 'exit' to quit.\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            return 0
        try:
            reply = ask(USER_ID, text)
        except Exception as e:  # noqa: BLE001 — surface errors, don't crash the REPL
            print(f"[error] {type(e).__name__}: {e}")
            traceback.print_exc()
            print()
            continue
        print(f"bot> {reply}\n")


if __name__ == "__main__":
    sys.exit(main())
