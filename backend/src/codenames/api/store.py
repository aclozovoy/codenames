"""In-memory game session store + WebSocket broadcast.

Single-process, non-persistent — fine for development and for LLM-vs-LLM runs.
Swap this for a real backing store later without touching the engine or routes.
"""

from __future__ import annotations

import asyncio
import random
import secrets

from fastapi import WebSocket

from ..engine import Game, Team


def _team(name: str) -> Team:
    return Team.RED if name == "red" else Team.BLUE


class GameSession:
    """One game plus its connected WebSocket spectators."""

    def __init__(self, game_id: str, game: Game) -> None:
        self.game_id = game_id
        self.game = game
        # Serialises mutations so concurrent actors (e.g. two LLMs) can't race.
        self.lock = asyncio.Lock()
        # Each connection remembers which view it wants.
        self._connections: dict[WebSocket, str] = {}

    def view_payload(self, view: str) -> dict:
        state = self.game.spymaster_state() if view == "spymaster" else self.game.operative_state()
        return {"game_id": self.game_id, "view": view, "state": state}

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
