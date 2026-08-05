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
Control = Literal["human", "ai"]
SeatKey = Literal["red_spymaster", "red_operative", "blue_spymaster", "blue_operative"]

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


class MoveRecord(BaseModel):
    """One LLM move plus the model's reasoning — the playback/thoughts log."""

    seat: str  # e.g. "red spymaster", "blue operative"
    action: str  # "clue" | "guess" | "pass" | "declined"
    word: str | None = None
    number: int | None = None
    targets: list[str] = []
    outcome: str | None = None  # guess outcome, when applicable
    reasoning: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class LogEntry(BaseModel):
    """One entry in the public running log of clues and guesses."""

    type: Literal["clue", "guess", "pass", "forfeit"]
    team: TeamName
    word: str | None = None
    number: int | None = None
    card_type: Literal["red", "blue", "neutral", "assassin"] | None = None
    outcome: str | None = None


class Usage(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    usd: float
    budget_usd: float | None = None


class GameConfig(BaseModel):
    """Who controls each seat, which model each team's AI uses, and whose move it is."""

    seats: dict[SeatKey, Control]
    models: dict[TeamName, str]
    current_seat: SeatKey | None = None
    current_is_ai: bool = False


class ModelInfo(BaseModel):
    """A selectable AI model for the New Game picker."""

    key: str
    label: str
    input_usd_per_mtok: float
    output_usd_per_mtok: float


class GameView(BaseModel):
    """A game's state as seen through one view (operative or spymaster)."""

    game_id: str
    view: ViewName
    state: GameState
    moves: list[MoveRecord] = []
    usage: Usage | None = None
    config: GameConfig | None = None
    log: list[LogEntry] = []


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
    # Seat controls; omit for all-AI. Any seats left out default to "ai".
    seats: dict[SeatKey, Control] | None = None
    # AI model key per team (from GET /models). Defaults to "haiku".
    models: dict[TeamName, str] | None = None


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
    moves: list[MoveRecord] = []
    usage: Usage | None = None
    config: GameConfig | None = None
    log: list[LogEntry] = []
