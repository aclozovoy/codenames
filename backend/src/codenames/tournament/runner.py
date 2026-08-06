"""Play a full AI-vs-AI game and produce a recordable result."""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from ..engine import Game, GuessOutcome, Phase, Team
from ..players import MODELS, BudgetExceeded, LLMEngine, LLMOperative, LLMSpymaster
from ..players.engine import LLMClient

# Per-game safety caps so a flailing game can't run forever or overspend.
DEFAULT_GAME_BUDGET_USD = 0.20
MAX_TURNS = 60


@dataclass
class GameResult:
    game_id: str
    played_at: str
    red_model: str
    blue_model: str
    starting_team: str
    winner: str | None  # "red" | "blue" | None (unfinished/error)
    winner_model: str | None
    loser_model: str | None
    status: str  # "completed" | "max_turns" | "budget" | "error"
    ended_by: str | None  # "all_cards" | "assassin" | None
    turns: int
    clues: int
    guesses: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_s: float
    seed: int | None
    error: str | None = None


def play_game(
    client: LLMClient,
    red_model: str,
    blue_model: str,
    *,
    seed: int | None = None,
    budget_usd: float = DEFAULT_GAME_BUDGET_USD,
    attempts: int = 4,
) -> GameResult:
    """Play one AI-vs-AI game to completion and return its result.

    ``red_model`` / ``blue_model`` are keys in ``players.MODELS``. Each seat uses
    its team's model; one shared engine tracks total tokens/cost with a budget cap.
    """
    red = MODELS[red_model]
    blue = MODELS[blue_model]
    engine = LLMEngine(client=client, budget_usd=budget_usd)
    game = Game.new(rng=random.Random(seed))
    starting_team = game.starting_team.value

    started = time.monotonic()
    turns = clues = guesses = 0
    assassin_hit = False
    status = "completed"
    error: str | None = None

    try:
        while game.phase is not Phase.GAME_OVER:
            if turns >= MAX_TURNS:
                status = "max_turns"
                break
            team = game.current_team
            model = red if team is Team.RED else blue

            if game.phase is Phase.AWAIT_CLUE:
                turns += 1
                decision = LLMSpymaster(engine, model, attempts=attempts).give_clue(game, team)
                game.give_clue(decision.word, decision.number)
                clues += 1
            else:  # AWAIT_GUESS
                decision = LLMOperative(engine, model, attempts=attempts).next_move(game, team)
                if decision.action == "guess":
                    outcome = game.guess(decision.word)
                    guesses += 1
                    if outcome is GuessOutcome.ASSASSIN:
                        assassin_hit = True
                # pass / give_up: end the turn (forfeit if no guess made yet, so a
                # bot that keeps passing can't loop forever).
                elif game.guesses_made >= 1:
                    game.pass_turn()
                else:
                    game.forfeit_turn()
    except BudgetExceeded as exc:
        status = "budget"
        error = str(exc)
    except Exception as exc:  # a model that never yields a valid clue, etc.
        status = "error"
        error = f"{type(exc).__name__}: {exc}"

    winner = game.winner.value if game.winner else None
    winner_model = None
    loser_model = None
    if winner:
        winner_model = red_model if winner == "red" else blue_model
        loser_model = blue_model if winner == "red" else red_model
    ended_by = "assassin" if assassin_hit else ("all_cards" if winner else None)

    now = datetime.now(UTC).isoformat(timespec="seconds")
    return GameResult(
        game_id=uuid.uuid4().hex[:12],
        played_at=now,
        red_model=red_model,
        blue_model=blue_model,
        starting_team=starting_team,
        winner=winner,
        winner_model=winner_model,
        loser_model=loser_model,
        status=status,
        ended_by=ended_by,
        turns=turns,
        clues=clues,
        guesses=guesses,
        input_tokens=engine.total_input_tokens,
        output_tokens=engine.total_output_tokens,
        cost_usd=round(engine.total_usd, 6),
        duration_s=round(time.monotonic() - started, 2),
        seed=seed,
        error=error,
    )


def as_dict(result: GameResult) -> dict:
    return asdict(result)
