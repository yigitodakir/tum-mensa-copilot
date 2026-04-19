# Campus Mensa Co-Pilot — Implementation Spec

> **Goal of this doc:** Hand this file to a fresh developer (or a fresh Claude Code session in an empty repo) and they should be able to build a working hackathon MVP end-to-end. All design decisions, APIs, file layouts, and tool contracts are fixed below.

---

## 1. Overview

**Campus Mensa Co-Pilot** is an AI chat agent that lives inside TUM's Matrix server and helps students decide what and where to eat on campus. The user DMs the bot ("I have 45min between lectures, I'm vegan, what's my best option?") and the agent responds with a ranked recommendation grounded in today's real menu data, the user's stored dietary profile, their past ratings, and the walking distance from their next lecture hall.

### Primary user flow
1. Student sends DM to the Matrix bot.
2. Bot forwards message → LangGraph agent (Claude Sonnet 4.6 on AWS Bedrock).
3. Agent calls tools: `fetch_menu`, `get_user_profile`, `get_canteen_distance`, etc.
4. Agent replies in the Matrix channel with a grounded recommendation, citing the canteen, price, and labels.

### Success criteria for the hackathon demo
- Live demo: ask "what's for lunch today?" in Matrix → get a real, grounded reply in < 10s.
- Dietary filtering actually works (pork user → never recommend pork).
- Memory actually works (rate a meal 2/5 → agent avoids re-recommending it).
- Daily 9am push works once against a test user.

---

## 2. Feature Tiers

Build strictly in this order. Tier 1 is the demo; Tier 2/3 are the "wow" layer.

### Tier 1 — MVP (must ship)
- Daily menu fetch across the three biggest canteens: `mensa-garching`, `mensa-arcisstr`, `mensa-lothstr`.
- Dietary profile stored in S3 (diet, allergens, preferred canteens, weekly budget).
- Natural-language Q&A over today's menu via Claude Sonnet 4.6.
- Daily 9am push: "Here are today's best picks for you at Mensa X."
- Matrix DM as the only UI.

### Tier 2 — Should-have
- Navigatum-powered distance: "closest canteen to MI HS1 that serves vegan today."
- Meal ratings (`/rate Spaghetti Bolognese 4`) persisted to S3 + recalled for future recs.
- Weekly budget tracker: `/spent 4.20 Spaghetti garching` → agent warns when >80% of weekly budget.

### Tier 3 — Stretch
- Weekly meal plan ("plan my week under 25€, high protein").
- Macro/nutrition reasoning from meal labels.
- TUMonline-calendar-aware routing: agent pulls next lecture → picks closest canteen with a dish matching the user's profile.
- Group coordination in a Matrix room: "who's going to Garching at 12:30?" → agent tallies replies.

---

## 3. Architecture

```
                    Matrix DM / Room
                          │
                          ▼
                ┌─────────────────────┐
                │ matrix-nio bot loop │   bot/matrix_bot.py
                └──────────┬──────────┘
                           │ user_id + text
                           ▼
                ┌─────────────────────┐
                │   LangGraph agent   │   agent/graph.py
                │  (Claude Sonnet 4.6 │
                │      on Bedrock)    │
                └──────────┬──────────┘
                           │ tool calls
        ┌──────────────────┼───────────────────┬──────────────────┐
        ▼                  ▼                   ▼                  ▼
  ┌──────────┐      ┌─────────────┐      ┌──────────┐      ┌───────────┐
  │ Eat API  │      │  Navigatum  │      │    S3    │      │ TUMonline │
  │ (tum-dev)│      │ (nav.tum.de)│      │  bucket  │      │  NAT API  │
  └──────────┘      └─────────────┘      └──────────┘      └───────────┘

  EventBridge cron (0 9 ? * MON-FRI *) ──► scheduler/daily_push.py
```

---

## 4. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| LLM | AWS Bedrock `anthropic.claude-sonnet-4-6-*` | Strong tool-use, already provisioned by the hackathon. |
| Orchestration | LangGraph | Explicit state machine, easier to debug than ReAct loops. |
| Chat | `simplematrixbotlib` (sync) → `matrix-nio` (if async needed) | Fastest path to a working Matrix bot in Python. |
| Storage | S3, JSON blobs keyed by Matrix user ID | No DB to provision. Hackathon-grade. |
| Scheduler | AWS EventBridge cron → ECS task or Lambda | One cron, one target. |
| Runtime (dev) | AWS SageMaker Notebook | Already provisioned. |
| Runtime (prod) | Long-running ECS Fargate task | Matrix bot needs a persistent connection; Lambda would churn. |

---

## 5. External APIs

All endpoints below are the **exact** strings to use. Sourced from `tum_systems.md`. No auth needed for Tier 1/2.

### 5.1 TUM-Dev Eat API (primary menu source)
- **Docs:** https://tum-dev.github.io/eat-api/docs/
- **GitHub:** https://github.com/TUM-Dev/eat-api
- **Weekly URL:** `https://tum-dev.github.io/eat-api/<canteen-id>/<year>/<iso-week>.json`
- **Example:** `https://tum-dev.github.io/eat-api/mensa-garching/2026/16.json`
- **Canteen IDs used in MVP:** `mensa-garching`, `mensa-arcisstr`, `mensa-lothstr` (list of all IDs: https://tum-dev.github.io/eat-api/enums/canteens.json).
- **Auth:** none.
- **Rate limiting:** cache responses for ≥ 1 hour on disk/S3. This is a static site hosted on GitHub Pages — don't hammer it.
- **Response shape** (`days[].dishes[]`):
  ```json
  {
    "name": "Spaghetti Bolognese",
    "prices": { "students": { "base_price": 3.5 } },
    "labels": ["BEEF","GLUTEN"],
    "dish_type": "Pasta"
  }
  ```
  Full label enum: https://tum-dev.github.io/eat-api/enums/labels.json

### 5.2 OpenMensa v2 (fallback)
- **Docs:** https://openmensa.org/api/v2/
- Use only if Eat API is down. Different ID scheme.

### 5.3 Navigatum (distances)
- **Docs:** https://nav.tum.de/api
- **Location lookup:** `GET https://nav.tum.de/api/locations/{id}` (e.g. `mi_hs1`, `mensa-garching`).
- Use the returned `coordinates` (`lat`, `lon`) to compute haversine distance + approx walking time (83 m/min).
- **Auth:** none.

### 5.4 TUMonline NAT API (Tier 3 only — calendar-aware routing)
- **Docs / Swagger:** https://api.srv.nat.tum.de/docs
- Use the public endpoints only. For write ops (don't need them), use `demo.campus.tum.de`, **never** live TUMonline.

### 5.5 Matrix
- **Setup guide:** https://wiki.ito.cit.tum.de/bin/view/CIT/ITO/Docs/Services/Matrix/Einrichtung/
- **Get a long-lived access token** (copy-paste from `tum_systems.md`):
  ```bash
  curl --header "Content-Type: application/json" \
       --request POST \
       --data '{"password": "YOUR_PASSWORD", "type": "m.login.password", "identifier": {"type": "m.id.user", "user": "YOUR_USERNAME"}}' \
       https://matrix.org/_matrix/client/v3/login
  ```
  Do **NOT** reuse the token from Element — it's short-lived.
- Libraries: `simplematrixbotlib` (sync) or `matrix-nio` (async).

---

## 6. Repository Layout

Target fresh repo name: `campus-copilot`. Final tree:

```
campus-copilot/
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── bot/
│   ├── __init__.py
│   └── matrix_bot.py          # entrypoint — run this to start the bot
├── agent/
│   ├── __init__.py
│   ├── graph.py               # LangGraph StateGraph + invocation helper
│   └── tools.py               # @tool-decorated wrappers around data/*
├── data/
│   ├── __init__.py
│   ├── eat_api.py             # fetch_menu, list_canteens (+ 1h disk cache)
│   ├── navigatum.py           # get_canteen_distance
│   ├── tumonline.py           # get_next_lecture (Tier 3)
│   └── s3_store.py            # profile / ratings / spend persistence
├── scheduler/
│   └── daily_push.py          # EventBridge target
├── prompts/
│   └── system.md              # agent persona
├── tests/
│   ├── fixtures/
│   │   └── garching_week16.json
│   └── test_tools.py
└── scripts/
    └── smoke_test.py          # runs 5 canned prompts through the agent
```

---

## 7. Tool Contracts (LangChain `@tool` signatures)

These are the exact Python signatures the agent sees. Keep docstrings concrete — they're part of the prompt.

```python
# agent/tools.py
from langchain_core.tools import tool

@tool
def fetch_menu(canteen_id: str, date: str) -> list[dict]:
    """Return today's dishes from a TUM canteen.

    Args:
        canteen_id: one of 'mensa-garching', 'mensa-arcisstr', 'mensa-lothstr'
                    (or any ID from the eat-api canteens enum).
        date: ISO date 'YYYY-MM-DD'. Must be today or later this week.

    Returns: list of {name, dish_type, price_student_eur, labels}.
    """

@tool
def list_canteens() -> list[dict]:
    """Return supported canteens with {id, name, campus}."""

@tool
def get_user_profile(user_id: str) -> dict:
    """Return the stored dietary profile for a Matrix user.

    Shape: {
      diet: 'omnivore'|'vegetarian'|'vegan'|'pescatarian',
      allergens: [str],       # e.g. ['gluten','lactose']
      avoid_labels: [str],    # eat-api labels to avoid, e.g. ['PORK','BEEF']
      preferred_canteens: [str],
      budget_weekly_eur: float,
      push_optin: bool
    }
    Returns defaults if the user is new.
    """

@tool
def save_user_profile(user_id: str, patch: dict) -> dict:
    """Deep-merge `patch` into the user's profile and persist. Returns the new profile."""

@tool
def log_meal_rating(user_id: str, meal_name: str, canteen: str, score: int, note: str = "") -> dict:
    """Append a 1-5 rating. Agent should call this when the user says e.g. 'I hated the bolognese'."""

@tool
def get_meal_history(user_id: str, limit: int = 20) -> list[dict]:
    """Most recent ratings, newest first."""

@tool
def get_canteen_distance(origin_id: str, canteen_id: str) -> dict:
    """Walking distance via Navigatum.

    Args:
        origin_id: a Navigatum location id, e.g. 'mi_hs1', 'lmu_hauptgebaeude'.
        canteen_id: same as fetch_menu.

    Returns: {meters: int, walk_minutes: int}
    """

@tool
def get_weekly_spend(user_id: str) -> dict:
    """Returns {spent_eur, budget_eur, remaining_eur, pct_used, week_iso}."""

@tool
def log_purchase(user_id: str, amount_eur: float, meal_name: str, canteen: str) -> dict:
    """Record a purchase against this week's budget."""
```

All tools must **fail soft**: on any exception return `{"error": "<human-readable>"}` instead of raising. The agent prompt tells Claude to surface errors as natural language.

---

## 8. S3 Schema

Single bucket, three prefixes:

```
s3://campus-copilot-<env>/
  profiles/<user_id>.json                       # single file per user
  ratings/<user_id>.jsonl                       # append-only, one JSON per line
  spend/<user_id>/<iso-week>.json               # one file per user per week
```

`user_id` is the Matrix MXID, URL-safe encoded (`@alice:tum.de` → `%40alice%3Atum.de`).

### profiles/<user_id>.json
```json
{
  "user_id": "@alice:tum.de",
  "diet": "vegetarian",
  "allergens": ["lactose"],
  "avoid_labels": ["PORK","BEEF","FISH"],
  "preferred_canteens": ["mensa-garching","mensa-arcisstr"],
  "budget_weekly_eur": 25.0,
  "push_optin": true,
  "created_at": "2026-04-18T08:00:00Z",
  "updated_at": "2026-04-18T08:00:00Z"
}
```

### ratings/<user_id>.jsonl (one line per rating)
```json
{"ts":"2026-04-18T12:42:00Z","meal":"Spaghetti Bolognese","canteen":"mensa-garching","score":2,"note":"too salty"}
```

### spend/<user_id>/<iso-week>.json
```json
{
  "week": "2026-W16",
  "budget_eur": 25.0,
  "purchases": [
    {"ts":"2026-04-15T12:40:00Z","amount_eur":4.20,"meal":"Chili sin Carne","canteen":"mensa-garching"}
  ],
  "spent_eur": 4.20
}
```

---

## 9. LangGraph Agent

Minimal working skeleton — paste, fill in, run. `agent/graph.py`:

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_aws import ChatBedrock
from langchain_core.messages import SystemMessage
from pathlib import Path

from agent.tools import (
    fetch_menu, list_canteens,
    get_user_profile, save_user_profile,
    log_meal_rating, get_meal_history,
    get_canteen_distance,
    get_weekly_spend, log_purchase,
)

TOOLS = [
    fetch_menu, list_canteens,
    get_user_profile, save_user_profile,
    log_meal_rating, get_meal_history,
    get_canteen_distance,
    get_weekly_spend, log_purchase,
]

SYSTEM_PROMPT = Path("prompts/system.md").read_text()

llm = ChatBedrock(
    model_id="anthropic.claude-sonnet-4-6-20250101-v1:0",  # pin to what's deployed
    model_kwargs={"temperature": 0.2, "max_tokens": 1024},
).bind_tools(TOOLS)


class State(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: str


def call_model(state: State):
    msgs = [SystemMessage(content=SYSTEM_PROMPT.format(user_id=state["user_id"]))] + state["messages"]
    return {"messages": [llm.invoke(msgs)]}


def route(state: State):
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


def run_tools(state: State):
    from langgraph.prebuilt import ToolNode
    return ToolNode(TOOLS).invoke(state)


graph = StateGraph(State)
graph.add_node("model", call_model)
graph.add_node("tools", run_tools)
graph.set_entry_point("model")
graph.add_conditional_edges("model", route, {"tools": "tools", END: END})
graph.add_edge("tools", "model")
app = graph.compile()


def ask(user_id: str, text: str) -> str:
    result = app.invoke({"user_id": user_id, "messages": [("user", text)]})
    return result["messages"][-1].content
```

### prompts/system.md (starter)
```
You are Campus Mensa Co-Pilot, a helpful assistant for TUM students.

The current Matrix user is: {user_id}

Rules:
- ALWAYS call get_user_profile(user_id) before recommending food. Respect diet, allergens, avoid_labels.
- ALWAYS ground menu claims in fetch_menu. Never invent dishes, prices, or labels.
- When the user mentions a location ("after my MI HS1 lecture"), use get_canteen_distance.
- When the user reports eating something, call log_purchase and log_meal_rating if they mention a score.
- Prefer canteens in preferred_canteens when options are equivalent.
- Be concise. Max 5 bullet points per reply. Always include price and canteen.
- If a tool returns {"error": ...}, apologize briefly and ask the user for a workaround.
```

---

## 10. Matrix Bot Loop

`bot/matrix_bot.py` using `simplematrixbotlib`:

```python
import os
import asyncio
import simplematrixbotlib as botlib
from agent.graph import ask

creds = botlib.Creds(
    homeserver=os.environ["MATRIX_HOMESERVER"],
    username=os.environ["MATRIX_USER"],
    access_token=os.environ["MATRIX_TOKEN"],
)
bot = botlib.Bot(creds)
PREFIX = ""  # respond to all DMs; tighten later

@bot.listener.on_message_event
async def on_msg(room, message):
    if message.sender == creds.username:
        return
    reply = await asyncio.to_thread(ask, message.sender, message.body)
    await bot.api.send_text_message(room.room_id, reply)

bot.run()
```

Env vars required: `MATRIX_HOMESERVER`, `MATRIX_USER`, `MATRIX_TOKEN`, plus AWS creds for Bedrock/S3.

---

## 11. Daily Push Scheduler

`scheduler/daily_push.py`:

```python
import os, boto3, json, asyncio
import simplematrixbotlib as botlib
from agent.graph import ask

s3 = boto3.client("s3")
BUCKET = os.environ["COPILOT_BUCKET"]

def list_optin_users() -> list[str]:
    users = []
    for obj in s3.list_objects_v2(Bucket=BUCKET, Prefix="profiles/").get("Contents", []):
        body = json.loads(s3.get_object(Bucket=BUCKET, Key=obj["Key"])["Body"].read())
        if body.get("push_optin"):
            users.append(body["user_id"])
    return users

async def main():
    creds = botlib.Creds(
        homeserver=os.environ["MATRIX_HOMESERVER"],
        username=os.environ["MATRIX_USER"],
        access_token=os.environ["MATRIX_TOKEN"],
    )
    bot = botlib.Bot(creds); await bot.api.login()
    for user_id in list_optin_users():
        reply = ask(user_id, "Give me today's best pick based on my profile, in 3 bullets.")
        room = await bot.api.get_or_create_dm(user_id)
        await bot.api.send_text_message(room, f"☀️ Good morning!\n\n{reply}")

if __name__ == "__main__":
    asyncio.run(main())
```

### EventBridge rule
```
Schedule: cron(0 7 ? * MON-FRI *)    # 07:00 UTC = 09:00 CEST
Target:   ECS task running scheduler/daily_push.py (or Lambda if package is small)
```

---

## 12. Environment & Setup

### `.env.example`
```
# Matrix
MATRIX_HOMESERVER=https://matrix.tum.de
MATRIX_USER=@copilot-bot:tum.de
MATRIX_TOKEN=syt_xxx

# AWS
AWS_REGION=eu-central-1
COPILOT_BUCKET=campus-copilot-dev
BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-6-20250101-v1:0

# Optional: cache dir for Eat API responses
EAT_API_CACHE_DIR=/tmp/eat-cache
```

### `requirements.txt`
```
boto3
python-dotenv
requests
pydantic
langchain
langchain-aws
langchain-core
langgraph
simplematrixbotlib
matrix-nio
```

### IAM (least-privilege for the bot)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:eu-central-1::foundation-model/anthropic.claude-sonnet-4-6-*" },
    { "Effect": "Allow", "Action": ["s3:GetObject","s3:PutObject","s3:ListBucket"],
      "Resource": ["arn:aws:s3:::campus-copilot-*","arn:aws:s3:::campus-copilot-*/*"] }
  ]
}
```

### Run it locally in 10 minutes
1. `git init campus-copilot && cd campus-copilot`
2. Create the file tree from §6 (empty files are fine to start).
3. `python -m venv .venv && source .venv/bin/activate`
4. `pip install -r requirements.txt`
5. `cp .env.example .env` — fill in `MATRIX_TOKEN` (see §5.5), AWS creds, and bucket name.
6. `aws s3 mb s3://campus-copilot-dev`
7. Implement modules in order: `data/eat_api.py` → `data/s3_store.py` → `agent/tools.py` → `agent/graph.py` → `bot/matrix_bot.py`.
8. `python scripts/smoke_test.py` to verify the agent answers.
9. `python -m bot.matrix_bot` — DM the bot from your Matrix account.

---

## 13. Testing & Verification

### Unit tests (`tests/test_tools.py`)
- Record one Eat API JSON response to `tests/fixtures/garching_week16.json`.
- `test_fetch_menu_filters_by_date` — parses the fixture, asserts dish count for 2026-04-15.
- `test_profile_defaults` — new user gets `diet=omnivore`, empty allergens.
- `test_rating_append` — two `log_meal_rating` calls → `get_meal_history` returns both, newest first.
- `test_distance_haversine` — seeded lat/lon pair → known meter distance (±5%).

CI must not hit live APIs. Use `responses` or `pytest-httpx` to stub HTTP.

### `scripts/smoke_test.py` (manual)
Runs the agent through 5 canned prompts end-to-end against live Bedrock + live Eat API:
```
1. "What's for lunch today at Garching?"
2. "I'm vegan, any options?"
3. "Save my allergen: lactose."
4. "I had the Chili today, 4/5."
5. "How close is Arcisstr mensa to MI HS1?"
```
For each: print the reply, assert `len(reply) > 20` and no stack traces.

### Demo checklist (hackathon)
- [ ] Pre-seed a demo user profile in S3 (vegetarian, budget 25€, allergen: nuts).
- [ ] Pre-record one rating so memory is visible.
- [ ] Have `scripts/smoke_test.py` green output on a second terminal.
- [ ] Screen capture: Matrix client + terminal showing tool calls, ~2 min.
- [ ] Backup: if Bedrock is rate-limited mid-demo, switch `BEDROCK_MODEL_ID` to Nova Pro.

---

## 14. Out of Scope / Risks

- **Moodle:** no public API, requires SSO via Playwright. Explicitly excluded from MVP.
- **Live TUMonline writes:** never hit production TUMonline; use `demo.campus.tum.de` if you ever need writes.
- **Eat API rate limits:** it's GitHub Pages — cache for ≥ 1 hour on disk. Don't fetch per message.
- **Bedrock quotas:** hackathon account may be rate-limited. Keep temperature low, max_tokens modest, and have Nova Pro ready as a fallback `model_id`.
- **PII:** Matrix user IDs are the only identifiers stored. Never log message contents to S3.
- **Token secrets:** `.env` is gitignored; never commit `MATRIX_TOKEN`.

---

## 15. Stretch Backlog (post-hackathon)

- Allergen vision: user uploads a plate photo → Claude vision extracts ingredients → cross-check profile allergens.
- Reservation / pre-order integration if/when Studierendenwerk exposes one.
- Slack bridge (same agent core, different bot layer).
- Calendar auto-reminders: 30 min before next lecture, suggest the nearest canteen.
- Group coordination rooms: "/going garching 12:30" → agent maintains a live headcount.
- Per-dorm leaderboards for "most vegan week."

---

## Appendix A — Canteen ID cheat sheet

| ID | Name | Campus |
|---|---|---|
| `mensa-garching` | Mensa Garching | Garching (FMI/Physics/Chem) |
| `mensa-arcisstr` | Mensa Arcisstr. | Main campus |
| `mensa-lothstr` | Mensa Lothstr. | HM / north |
| `stubistro-goethestr` | StuBistro Goethestr. | Main |
| `stucafe-garching` | StuCafé Garching | Garching |

Full authoritative list: https://tum-dev.github.io/eat-api/enums/canteens.json

## Appendix B — Label cheat sheet (filter these for diets)

- Vegetarian excludes: `BEEF`, `PORK`, `POULTRY`, `FISH`, `GAME`, `LAMB`, `VEAL`.
- Vegan additionally excludes: `MILK`, `LACTOSE`, `EGG`, `HONEY`, `CHEESE`.
- Pescatarian excludes everything meat-ish except `FISH`.

Full label enum: https://tum-dev.github.io/eat-api/enums/labels.json

## Appendix C — Source docs (don't re-discover these)

- Eat API: https://tum-dev.github.io/eat-api/docs/
- OpenMensa: https://openmensa.org/api/v2/
- Navigatum: https://nav.tum.de/api
- TUMonline NAT: https://api.srv.nat.tum.de/docs
- Matrix TUM setup: https://wiki.ito.cit.tum.de/bin/view/CIT/ITO/Docs/Services/Matrix/Einrichtung/
- TUM-Dev community: https://www.tum.dev/
