"""Core value types for the Codenames engine.

Kept deliberately small and dependency-free (stdlib only) so the game logic is
trivial to unit-test and reuse. The API layer converts these to/from JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Team(Enum):
    """The two competing teams."""

    RED = "red"
    BLUE = "blue"

    @property
    def opponent(self) -> Team:
        return Team.BLUE if self is Team.RED else Team.RED

    @property
    def card_type(self) -> CardType:
        """The card colour that belongs to this team."""
        return CardType.RED if self is Team.RED else CardType.BLUE


class CardType(Enum):
    """What a card is 'worth'. RED/BLUE belong to teams; NEUTRAL is a bystander;
    ASSASSIN loses the game for whoever reveals it."""

    RED = "red"
    BLUE = "blue"
    NEUTRAL = "neutral"
    ASSASSIN = "assassin"


class Role(Enum):
    """A seat at the table. The spymaster gives clues; operatives guess."""

    SPYMASTER = "spymaster"
    OPERATIVE = "operative"


class Phase(Enum):
    """Whose action the game is waiting on."""

    AWAIT_CLUE = "await_clue"  # current team's spymaster must give a clue
    AWAIT_GUESS = "await_guess"  # current team's operatives may guess
    GAME_OVER = "game_over"


class GuessOutcome(Enum):
    """Result of revealing one card."""

    CORRECT = "correct"  # revealed the guessing team's own card
    WRONG_TEAM = "wrong_team"  # revealed the opposing team's card
    NEUTRAL = "neutral"  # revealed a bystander
    ASSASSIN = "assassin"  # revealed the assassin -> immediate loss


@dataclass
class Card:
    """One of the 25 cards on the board."""

    word: str
    type: CardType
    revealed: bool = False


@dataclass(frozen=True)
class Clue:
    """A spymaster's clue: a single word plus a count of related cards."""

    word: str
    number: int


class InvalidMove(Exception):
    """Raised when an action violates the game rules or current phase."""
