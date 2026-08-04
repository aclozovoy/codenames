# Codenames

A web implementation of the board game **Codenames** where you can play with or
against LLMs — or watch two models play each other — with every AI clue and guess
shown alongside the model's reasoning. Model calls run on **AWS Bedrock** using
cheap models (Claude Haiku, Amazon Nova, Llama).

## Features

- **Full game engine** — 25-card boards, the real 9/8/7/1 distribution, the
  faithful clue → guess → turn cycle, and all win/loss paths (all cards, assassin,
  opponent completion).
- **Game modes** as seat assignments over the 4 seats (red/blue × spymaster/operative),
  each controlled by a human or an AI:
  - **AI only** — both teams are AI; step through and watch.
  - **Single player** — pick a team + role; AI fills the other three seats.
  - **Two player (shared screen)** — two humans on the same role (opposite teams),
    so one shared view; AI plays the other role.
- **Per-team model selection** — choose a different cheap model for each team's AI,
  so you can pit models against each other.
- **Visible reasoning** — every AI move records the model's thinking; the UI shows a
  running "Model reasoning" log (your playback of the game).
- **Step-through control** — an "AI move" button advances the current AI seat one
  action at a time (one clue, or one guess).
- **Cost controls** — a live token/USD usage meter, a per-game hard spend cap
  enforced in-app, and an AWS Budget for account-level alerts.

## Architecture

```
backend/                    Python 3.11 · FastAPI
  src/codenames/
    engine/                 Pure game logic — no FastAPI, no boto3 (fully unit-tested)
    players/                LLM players on Bedrock; the only place that imports boto3
    api/                    FastAPI app: REST + WebSocket, in-memory session store
  tests/                    pytest (58 tests)
frontend/                   Vite · React · TypeScript
  src/                      Board UI, New Game setup, reasoning log, live WebSocket
```

The engine is deliberately framework-agnostic; the API and the LLM players build on
top of it. The frontend talks to the backend over REST + a WebSocket that broadcasts
state (and the reasoning log) on every move.

## Prerequisites

- **Python 3.11+** and **Node 18+**
- **AWS credentials** configured (`aws configure`) with **Bedrock access** in
  `us-west-2`. First-time Anthropic-model use requires submitting the one-time
  "use case details" form in the Bedrock console.

## Running locally

**Backend** (from `backend/`):

```bash
python3.11 -m venv ../.venv
../.venv/bin/pip install uv
../.venv/bin/uv pip install -e ".[dev]"
../.venv/bin/uvicorn codenames.api.app:app --reload --port 8000
```

**Frontend** (from `frontend/`):

```bash
npm install
npm run dev
```

Then open the Vite URL (http://localhost:5173). The frontend proxies API and
WebSocket calls to the backend on :8000.

## AI models

Cheap Bedrock models offered in the New Game picker (prices are approximate USD per
1M tokens, in/out):

| Model | Cost (in / out) | Notes |
|---|---|---|
| Claude Haiku 4.5 | $1.00 / $5.00 | strongest play of the cheap set |
| Amazon Nova Lite | $0.06 / $0.24 | very cheap |
| Amazon Nova Micro | $0.035 / $0.14 | cheapest; ~30× under Haiku |
| Llama 3.1 8B | $0.22 / $0.22 | open-model variety |

## Cost controls

Two layers:

1. **App-level hard stop** — each game shares one `LLMEngine` with a USD budget
   (default $0.50). It tracks token spend and refuses the next call once the cap is
   reached (HTTP 402).
2. **AWS Budget** — an account-level monthly budget with email alerts at
   50/80/100%.

## Development

From `backend/`:

```bash
pytest                # run the test suite
ruff check .          # lint
ruff format .         # format
```

From `frontend/`:

```bash
npx tsc -b --noEmit   # type-check
npm run build         # production build
```

## Status

Playable end to end: engine, REST + WebSocket API, LLM players with reasoning, the
three game modes, per-team model selection, and cost controls are all implemented.
The session store is in-memory (games reset when the backend restarts) and there is
no auth yet — the board view is chosen per request rather than gated per player.
