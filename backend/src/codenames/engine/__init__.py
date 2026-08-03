"""Pure game logic — no FastAPI, no boto3. Framework-agnostic and unit-tested."""

from .board import BOARD_SIZE, build_board
from .game import Game
from .types import (
    Card,
    CardType,
    Clue,
    GuessOutcome,
    InvalidMove,
    Phase,
    Role,
    Team,
)
from .words import load_words

__all__ = [
    "BOARD_SIZE",
    "Card",
    "CardType",
    "Clue",
    "Game",
    "GuessOutcome",
    "InvalidMove",
    "Phase",
    "Role",
    "Team",
    "build_board",
    "load_words",
]
