"""LLM operative: picks the next guess (or passes), with visible reasoning."""

from __future__ import annotations

from dataclasses import dataclass

from ..engine import Game, Team
from .engine import LLMEngine
from .parsing import extract_json
from .prompts import build_operative_prompt


@dataclass
class GuessDecision:
    action: str  # "guess" or "pass"
    word: str | None  # the board word to guess; None when passing
    reasoning: str
    input_tokens: int
    output_tokens: int


class LLMOperative:
    def __init__(self, engine: LLMEngine) -> None:
        self.engine = engine

    def next_move(self, game: Game, team: Team) -> GuessDecision:
        system, user = build_operative_prompt(game, team)
        result = self.engine.run(system, user)
        data = extract_json(result.text)

        action = str(data.get("action", "")).strip().lower()
        reasoning = str(data.get("reasoning", "")).strip()

        if action == "pass":
            return GuessDecision("pass", None, reasoning, result.input_tokens, result.output_tokens)

        word = data.get("word")
        if not isinstance(word, str) or not word.strip():
            raise ValueError(f"operative returned no valid word to guess: {data!r}")

        target = word.strip().upper()
        cards = game.operative_state()["cards"]
        available = {c["word"].upper() for c in cards if not c["revealed"]}
        if target not in available:
            raise ValueError(f"operative guessed {word!r}, which is not an available board word")

        return GuessDecision("guess", target, reasoning, result.input_tokens, result.output_tokens)
