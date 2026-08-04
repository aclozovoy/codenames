"""The Codenames game state machine.

Turn cycle (the 4-role model):
    AWAIT_CLUE  -> spymaster calls give_clue(word, number)
    AWAIT_GUESS -> operatives call guess(word) up to (number + 1) times,
                   or stop early with pass_turn()
    ...turn ends on a wrong/neutral guess, on using up the guesses, or on a pass.
    GAME_OVER   -> a team revealed all its cards, or someone hit the assassin.

The engine holds full state (including hidden card colours). Use
``operative_state()`` when exposing the board to a guesser or its LLM so unrevealed
colours stay secret; ``spymaster_state()`` reveals everything.
"""

from __future__ import annotations

import random

from .board import build_board
from .types import (
    Card,
    CardType,
    Clue,
    GuessOutcome,
    InvalidMove,
    Phase,
    Team,
)


class Game:
    def __init__(self, board: list[Card], starting_team: Team) -> None:
        if len(board) != 25:
            raise ValueError(f"board must have 25 cards, got {len(board)}")
        self.board = board
        self.starting_team = starting_team
        self.current_team = starting_team
        self.phase = Phase.AWAIT_CLUE
        self.current_clue: Clue | None = None
        self.guesses_made = 0
        # None means "unlimited" (a clue number of 0); otherwise number + 1.
        self.guesses_allowed: int | None = None
        self.winner: Team | None = None
        # Lightweight move log — handy for UI replay and LLM prompt context.
        self.history: list[dict] = []

    # -- construction -----------------------------------------------------------

    @classmethod
    def new(
        cls,
        starting_team: Team | None = None,
        words: list[str] | None = None,
        rng: random.Random | None = None,
    ) -> Game:
        """Create a fresh game with a randomly generated board."""
        rng = rng or random.Random()
        if starting_team is None:
            starting_team = rng.choice([Team.RED, Team.BLUE])
        board = build_board(starting_team, words=words, rng=rng)
        return cls(board, starting_team)

    # -- queries ----------------------------------------------------------------

    def cards_remaining(self, team: Team) -> int:
        """How many of ``team``'s cards are still hidden."""
        wanted = team.card_type
        return sum(1 for c in self.board if c.type is wanted and not c.revealed)

    def _find_card(self, word: str) -> Card | None:
        target = word.strip().upper()
        for card in self.board:
            if card.word.upper() == target:
                return card
        return None

    # -- actions ----------------------------------------------------------------

    def give_clue(self, word: str, number: int) -> Clue:
        """Current team's spymaster gives a clue.

        A clue is one word plus a number N; the operatives then get up to N + 1
        guesses (N = 0 means unlimited). The clue word may not be a whitespace-
        containing phrase and may not match any unrevealed board word.
        """
        if self.phase is not Phase.AWAIT_CLUE:
            raise InvalidMove(f"cannot give a clue during phase {self.phase.value}")

        clue_word = word.strip()
        if not clue_word:
            raise InvalidMove("clue word must not be empty")
        if any(ch.isspace() for ch in clue_word):
            raise InvalidMove("clue must be a single word")
        if number < 0:
            raise InvalidMove("clue number must be >= 0")
        if self._is_word_on_unrevealed_board(clue_word):
            raise InvalidMove("clue must not match a word still on the board")

        clue = Clue(word=clue_word, number=number)
        self.current_clue = clue
        self.guesses_made = 0
        self.guesses_allowed = number + 1 if number >= 1 else None
        self.phase = Phase.AWAIT_GUESS
        self.history.append(
            {"type": "clue", "team": self.current_team.value, "word": clue_word, "number": number}
        )
        return clue

    def guess(self, word: str) -> GuessOutcome:
        """Current team's operatives reveal one card by word."""
        if self.phase is not Phase.AWAIT_GUESS:
            raise InvalidMove(f"cannot guess during phase {self.phase.value}")

        card = self._find_card(word)
        if card is None:
            raise InvalidMove(f"no card with word {word!r}")
        if card.revealed:
            raise InvalidMove(f"card {card.word!r} is already revealed")

        card.revealed = True
        guessing_team = self.current_team
        outcome = self._classify(card, guessing_team)
        self.history.append(
            {
                "type": "guess",
                "team": guessing_team.value,
                "word": card.word,
                "card_type": card.type.value,
                "outcome": outcome.value,
            }
        )

        if outcome is GuessOutcome.ASSASSIN:
            self._finish(guessing_team.opponent)
        elif outcome is GuessOutcome.CORRECT:
            self.guesses_made += 1
            if self.cards_remaining(guessing_team) == 0:
                self._finish(guessing_team)
            elif self.guesses_allowed is not None and self.guesses_made >= self.guesses_allowed:
                self._end_turn()
            # otherwise: stay in AWAIT_GUESS, they may keep guessing
        elif outcome is GuessOutcome.WRONG_TEAM:
            other = guessing_team.opponent
            if self.cards_remaining(other) == 0:
                self._finish(other)
            else:
                self._end_turn()
        else:  # NEUTRAL
            self._end_turn()

        return outcome

    def pass_turn(self) -> None:
        """Voluntarily stop guessing and hand over to the other team.

        Only legal after making at least one guess this turn (a team must always
        make at least one guess for a clue)."""
        if self.phase is not Phase.AWAIT_GUESS:
            raise InvalidMove(f"cannot pass during phase {self.phase.value}")
        if self.guesses_made < 1:
            raise InvalidMove("must make at least one guess before passing")
        self.history.append({"type": "pass", "team": self.current_team.value})
        self._end_turn()

    def forfeit_turn(self) -> None:
        """End the current team's turn without requiring a guess.

        Unlike pass_turn, this does not require a prior guess. It exists for an
        automated operative that cannot produce a valid guess and gives up."""
        if self.phase is not Phase.AWAIT_GUESS:
            raise InvalidMove(f"cannot forfeit during phase {self.phase.value}")
        self.history.append({"type": "forfeit", "team": self.current_team.value})
        self._end_turn()

    # -- internal helpers -------------------------------------------------------

    def _classify(self, card: Card, guessing_team: Team) -> GuessOutcome:
        if card.type is CardType.ASSASSIN:
            return GuessOutcome.ASSASSIN
        if card.type is CardType.NEUTRAL:
            return GuessOutcome.NEUTRAL
        if card.type is guessing_team.card_type:
            return GuessOutcome.CORRECT
        return GuessOutcome.WRONG_TEAM

    def _is_word_on_unrevealed_board(self, word: str) -> bool:
        target = word.upper()
        return any(c.word.upper() == target and not c.revealed for c in self.board)

    def _end_turn(self) -> None:
        self.current_team = self.current_team.opponent
        self.phase = Phase.AWAIT_CLUE
        self.current_clue = None
        self.guesses_made = 0
        self.guesses_allowed = None

    def _finish(self, winner: Team) -> None:
        self.winner = winner
        self.phase = Phase.GAME_OVER
        self.current_clue = None
        self.history.append({"type": "game_over", "winner": winner.value})

    # -- serialisation ----------------------------------------------------------

    def _base_state(self) -> dict:
        return {
            "phase": self.phase.value,
            "starting_team": self.starting_team.value,
            "current_team": self.current_team.value,
            "current_clue": (
                None
                if self.current_clue is None
                else {"word": self.current_clue.word, "number": self.current_clue.number}
            ),
            "guesses_made": self.guesses_made,
            "guesses_allowed": self.guesses_allowed,
            "winner": self.winner.value if self.winner else None,
            "red_remaining": self.cards_remaining(Team.RED),
            "blue_remaining": self.cards_remaining(Team.BLUE),
        }

    def spymaster_state(self) -> dict:
        """Full state including every card's colour — for spymasters only."""
        state = self._base_state()
        state["cards"] = [
            {"word": c.word, "revealed": c.revealed, "type": c.type.value} for c in self.board
        ]
        return state

    def operative_state(self) -> dict:
        """State with unrevealed card colours hidden — safe for operatives."""
        state = self._base_state()
        state["cards"] = [
            {
                "word": c.word,
                "revealed": c.revealed,
                "type": c.type.value if c.revealed else None,
            }
            for c in self.board
        ]
        return state
