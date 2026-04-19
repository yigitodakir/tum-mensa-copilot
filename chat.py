"""TUM Food Copilot — interactive CLI chatbot.

Usage:
    python chat.py

Type '/exit' or press Ctrl-D to quit. Set COPILOT_DEBUG=1 for full tracebacks.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console  # noqa: E402
from rich.markdown import Markdown  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.text import Text  # noqa: E402

from agent.graph import ask  # noqa: E402 — load_dotenv must run first

USER_ID = "cli-user"
APP_NAME = "TUM Food Copilot"
EXIT_WORDS = {"exit", "quit", "/exit", "/quit", ":q"}

console = Console()


def _banner() -> Panel:
    title = Text(APP_NAME, style="bold bright_cyan")
    subtitle = Text("Your TUM canteen companion  ·  type /exit to quit", style="dim")
    body = Text.assemble(title, "\n", subtitle)
    return Panel(
        body,
        border_style="bright_blue",
        padding=(1, 2),
    )


def _reply_panel(reply: str) -> Panel:
    return Panel(
        Markdown(reply),
        title=f"[bold green]{APP_NAME}[/]",
        title_align="left",
        border_style="green",
        padding=(1, 2),
    )


def _error_panel(exc: BaseException) -> Panel:
    msg = f"[bold]{type(exc).__name__}[/]: {exc}"
    if os.environ.get("COPILOT_DEBUG") == "1":
        msg += "\n\n" + traceback.format_exc()
    return Panel(
        msg,
        title="[bold red]error[/]",
        title_align="left",
        border_style="red",
        padding=(1, 2),
    )


def main() -> int:
    console.print(_banner())
    while True:
        try:
            text = console.input("[bold cyan]you[/] › ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye 👋[/]")
            return 0
        if not text:
            continue
        if text.lower() in EXIT_WORDS:
            console.print("[dim]Goodbye 👋[/]")
            return 0
        try:
            with console.status("[dim]thinking…[/]", spinner="dots"):
                reply = ask(USER_ID, text)
        except Exception as e:  # noqa: BLE001 — surface errors, keep REPL alive
            console.print(_error_panel(e))
            continue
        console.print(_reply_panel(reply))


if __name__ == "__main__":
    sys.exit(main())
