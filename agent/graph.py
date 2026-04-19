"""LangGraph state machine: Claude Sonnet 4.6 on Bedrock + tool loop."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from agent.tools import ALL_TOOLS

SYSTEM_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "system.md"


class State(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str


_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatBedrockConverse(
            model=os.environ.get(
                "BEDROCK_MODEL_ID",
                "anthropic.claude-sonnet-4-6",
            ),
            region_name=os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_REGION", "eu-central-1"),
            temperature=0.2,
            max_tokens=1024,
        ).bind_tools(ALL_TOOLS)
    return _llm


def _system_prompt(user_id: str) -> str:
    template = SYSTEM_PROMPT_PATH.read_text()
    return template.replace("{user_id}", user_id).replace("{today}", date.today().isoformat())


def call_model(state: State) -> dict:
    msgs = [SystemMessage(content=_system_prompt(state["user_id"]))] + state["messages"]
    return {"messages": [_get_llm().invoke(msgs)]}


def route(state: State) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


def run_tools(state: State) -> dict:
    return ToolNode(ALL_TOOLS).invoke(state)


def _build_app():
    graph = StateGraph(State)
    graph.add_node("model", call_model)
    graph.add_node("tools", run_tools)
    graph.set_entry_point("model")
    graph.add_conditional_edges("model", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "model")
    return graph.compile(checkpointer=MemorySaver())


_app = None


def _app_instance():
    global _app
    if _app is None:
        _app = _build_app()
    return _app


def ask(user_id: str, text: str) -> str:
    """Run a single user message through the agent and return the assistant reply text."""
    result = _app_instance().invoke(
        {"user_id": user_id, "messages": [("user", text)]},
        config={"configurable": {"thread_id": user_id}},
    )
    last = result["messages"][-1]
    content = last.content
    if isinstance(content, list):
        parts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
        return "\n".join(p for p in parts if p)
    return str(content)
