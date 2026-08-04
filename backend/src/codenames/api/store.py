"""In-memory game session store + WebSocket broadcast.

Single-process, non-persistent — fine for development and for LLM-vs-LLM runs.
Swap this for a real backing store later without touching the engine or routes.
"""

from __future__ import annotations

import asyncio
import os
import random
import secrets

from fastapi import WebSocket

from ..engine import Game, Team
from ..players import DEFAULT_MODEL, MODELS, LLMEngine

# Per-game hard cap on LLM spend (USD). The engine refuses calls past this.
DEFAULT_GAME_BUDGET_USD = 0.50

_bedrock_client = None  # created lazily so importing this module needs no AWS


def _shared_bedrock_client():
    """One boto3 Bedrock client shared across games (creating it is cheap; the
    network call happens per request)."""
    global _bedrock_client
    if _bedrock_client is None:
        from ..players.bedrock import BedrockClient

        _bedrock_client = BedrockClient(region=os.environ.get("AWS_REGION", "us-west-2"))
    return _bedrock_client


def _team(name: str) -> Team:
    return Team.RED if name == "red" else Team.BLUE


class GameSession:
    """One game plus its connected spectators and LLM state."""

    def __init__(self, game_id: str, game: Game) -> None:
        self.game_id = game_id
        self.game = game
        # Serialises mutations so concurrent actors (e.g. two LLMs) can't race.
        self.lock = asyncio.Lock()
        # Each connection remembers which view it wants.
        self._connections: dict[WebSocket, str] = {}
        # Reasoning log — every LLM move with its thinking (the playback record).
        self.moves: list[dict] = []
        self._engine: LLMEngine | None = None

    def ensure_engine(self) -> LLMEngine:
        """Create this game's cost-tracked LLM engine on first use."""
        if self._engine is None:
            self._engine = LLMEngine(
                client=_shared_bedrock_client(),
                model=MODELS[DEFAULT_MODEL],
                budget_usd=DEFAULT_GAME_BUDGET_USD,
            )
        return self._engine

    def view_payload(self, view: str) -> dict:
        state = self.game.spymaster_state() if view == "spymaster" else self.game.operative_state()
        return {
            "game_id": self.game_id,
            "view": view,
            "state": state,
            "moves": self.moves,
            "usage": self._engine.usage if self._engine else None,
        }

    async def connect(self, websocket: WebSocket, view: str) -> None:
        await websocket.accept()
        self._connections[websocket] = view
        await websocket.send_json(self.view_payload(view))

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(websocket, None)

    async def broadcast(self) -> None:
        """Push the latest state to every connected spectator, per their view."""
        dead: list[WebSocket] = []
        for websocket, view in list(self._connections.items()):
            try:
                await websocket.send_json(self.view_payload(view))
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket)


class GameStore:
    def __init__(self) -> None:
        self._sessions: dict[str, GameSession] = {}

    def create(self, starting_team: str | None = None, seed: int | None = None) -> GameSession:
        rng = random.Random(seed)
        team = _team(starting_team) if starting_team else None
        game = Game.new(starting_team=team, rng=rng)
        game_id = secrets.token_urlsafe(8)
        session = GameSession(game_id, game)
        self._sessions[game_id] = session
        return session

    def get(self, game_id: str) -> GameSession | None:
        return self._sessions.get(game_id)

    def all(self) -> list[GameSession]:
        return list(self._sessions.values())
