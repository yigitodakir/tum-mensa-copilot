# TUM-Mensa-Copilot
CLI-based AI chatbot that helps TUM students decide what and where to eat on campus. Built against the TUM-Dev Eat API, and AWS Bedrock (Claude Sonnet 4.6).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in AWS creds + bucket name
aws s3 mb s3://campus-copilot-food
python chat.py            # interactive REPL
```

## Layout

- `agent/` — LangGraph + tool wrappers
- `data/` — Eat API, Navigatum, S3, TUMonline clients
- `prompts/` — agent persona
- `tests/` — unit tests with recorded fixtures
- `chat.py` (interactive REPL)

