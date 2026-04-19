<div align="center">

# TUM Food Copilot

**An AI chat agent that helps TUM students decide what and where to eat on campus.**

Grounded in live Mensa menus, your dietary profile, and your past preferences.

<p>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <img alt="LLM" src="https://img.shields.io/badge/Claude-Sonnet%204.6-8A2BE2">
  <img alt="Runtime" src="https://img.shields.io/badge/AWS-Bedrock%20%7C%20S3-FF9900">
  <img alt="Framework" src="https://img.shields.io/badge/LangGraph-agent-1E8E3E">
</p>

</div>

---

## Overview

**TUM Food Copilot** is a conversational assistant for TUM students. Ask it and it replies with a ranked, grounded recommendation — pulled from the live [TUM-Dev Eat API](https://tum-dev.github.io/eat-api/docs/), filtered against your stored dietary profile, and informed by meals you've rated in the past.

The current entrypoint is a polished terminal REPL powered by [`rich`](https://github.com/Textualize/rich).

## Architecture

```text
                         User (terminal)
                              │
                              ▼
                      ┌───────────────┐
                      │   chat.py     │  rich REPL
                      └───────┬───────┘
                              │  ask(user_id, text)
                              ▼
                      ┌───────────────┐
                      │  LangGraph    │  agent/graph.py
                      │  state machine│  Claude Sonnet 4.6
                      └───────┬───────┘
                              │  tool calls
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌─────────────┐     ┌─────────────┐     ┌────────────┐
   │  Eat API    │     │  Navigatum  │     │     S3     │
   │  (menus)    │     │  (walking)  │     │ (profile + │
   │             │     │             │     │  ratings)  │
   └─────────────┘     └─────────────┘     └────────────┘
```

The agent runs a bounded tool loop: Claude decides which tools to call, `ToolNode` executes them, results flow back into the model, and the loop terminates when the model returns a final answer.

## Tech stack

| Layer         | Choice                                                     |
| ------------- | ---------------------------------------------------------- |
| LLM           | AWS Bedrock · `anthropic.claude-sonnet-4-6`                |
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph)     |
| Terminal UI   | [rich](https://github.com/Textualize/rich)                 |
| Storage       | S3 (JSON + JSONL blobs, keyed by user id)                  |
| Menus         | [TUM-Dev Eat API](https://tum-dev.github.io/eat-api/docs/) |
| Distances     | [Navigatum](https://nav.tum.de/api)                        |

## Quick start

Requires Python 3.10+, an AWS account with Bedrock access, and an S3 bucket.

```bash
git clone https://github.com/yigitodakir/tum-mensa-copilot.git
cd tum-food-copilot

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env         # fill in AWS creds + bucket
aws s3 mb s3://campus-copilot-food

python chat.py               # launch the chatbot
```

Use `/exit`, `/quit`, Ctrl-D, or Ctrl-C to leave. Set `COPILOT_DEBUG=1` to see full tracebacks on errors.

## Configuration

All configuration is environment-based. See [.env.example](.env.example).

| Variable                | Required | Default                          | Purpose                                |
| ----------------------- | :------: | -------------------------------- | -------------------------------------- |
| `AWS_ACCESS_KEY_ID`     |    ✓     | —                                | AWS credentials for Bedrock + S3.      |
| `AWS_SECRET_ACCESS_KEY` |    ✓     | —                                | —                                      |
| `AWS_REGION`            |    ✓     | `eu-north-1`                     | Region for the S3 bucket.              |
| `BEDROCK_REGION`        |          | `eu-central-1`                   | Region serving the Claude model.       |
| `BEDROCK_MODEL_ID`      |          | `eu.anthropic.claude-sonnet-4-6` | Override to swap models.               |
| `COPILOT_BUCKET`        |    ✓     | —                                | S3 bucket for profiles + ratings.      |
| `EAT_API_CACHE_DIR`     |          | `/tmp/eat-cache`                 | Disk cache for Eat API responses.      |
| `COPILOT_DEBUG`         |          | unset                            | `1` → show full tracebacks in REPL.    |

## Project layout

```
tum-food-copilot/
├── chat.py                 # entrypoint: rich-powered REPL
├── agent/
│   ├── graph.py            # LangGraph state machine (Bedrock + tool loop)
│   └── tools.py            # @tool wrappers (fail-soft)
├── data/
│   ├── eat_api.py          # menus + 1h disk cache
│   ├── navigatum.py        # campus coordinates + haversine
│   └── s3_store.py         # profiles + ratings persistence
├── prompts/
│   └── system.md           # agent persona + tool-use policy
├── requirements.txt
└── .env.example
```

## How it works

1. `chat.py` reads a line from the terminal and calls `agent.graph.ask(user_id, text)`.
2. The LangGraph state machine prepends the system prompt (from [prompts/system.md](prompts/system.md)) and invokes Claude Sonnet 4.6 on Bedrock.
3. If Claude emits tool calls, `ToolNode` runs them against `agent/tools.py` — which delegates to the `data/` layer (Eat API, Navigatum, S3).
4. Tool results flow back into the model; the loop continues until Claude returns a final answer.
5. Persistence side effects (new profile fields, meal ratings) land in S3 and show up on the *next* turn thanks to `MemorySaver` keyed by `user_id`.

