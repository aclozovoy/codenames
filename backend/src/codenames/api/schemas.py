"""Pydantic request/response models.

These define the HTTP contract and drive the auto-generated OpenAPI schema, which
we can later turn into TypeScript types for the frontend. They mirror the plain
dicts produced by the engine's ``*_state()`` methods.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TeamName = Literal["red", "blue"]
ViewName = Literal["operative", "spymaster"]

# -- board / state --------------------------------------------------------------


class CardState(BaseModel):
    word: str
    revealed: bool
    # None when the colour is hidden (operative view, unrevealed card).
    type: Literal["red", "blue", "neutral", "assassin"] | None = None


class ClueState(BaseModel):
    word: str
    number: int


class GameState(BaseModel):
    phase: Literal["await_clue", "await_guess", "game_over"]
    starting_team: TeamName
    current_team: TeamName
    current_clue: ClueState | None = None
    guesses_made: int
    guesses_allowed: int | None = None
    winner: TeamName | None = None
    red_remaining: int
    blue_remaining: int
    cards: list[CardState]


class GameView(BaseModel):
    """A game's state as seen through one view (operative or spymaster)."""

    game_id: str
    view: ViewName
    state: GameState


class GameSummary(BaseModel):
    """Lightweight listing entry (no board)."""

    game_id: str
    phase: str
    current_team: TeamName
    winner: TeamName | None = None


# -- requests -------------------------------------------------------------------


class CreateGameRequest(BaseModel):
    starting_team: TeamName | None = None  # None -> random
    seed: int | None = None  # set for a reproducible board


class ClueRequest(BaseModel):
    word: str
    number: int = Field(ge=0, description="0 means unlimited guesses")


class GuessRequest(BaseModel):
    word: str


# -- responses ------------------------------------------------------------------


class GuessResponse(BaseModel):
    game_id: str
    outcome: Literal["correct", "wrong_team", "neutral", "assassin"]
    view: ViewName
    state: GameState
