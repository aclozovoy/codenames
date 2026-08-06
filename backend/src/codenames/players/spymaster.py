"""LLM spymaster: turns a board into a clue, with visible reasoning."""

from __future__ import annotations

from dataclasses import dataclass

from ..engine import Game, Team
from .engine import LLMEngine, ModelConfig
from .parsing import extract_json
from .prompts import build_spymaster_prompt


@dataclass
class ClueDecision:
    word: str
    number: int
    reasoning: str
    targets: list[str]
    input_tokens: int
    output_tokens: int


class LLMSpymaster:
    def __init__(self, engine: LLMEngine, model: ModelConfig, attempts: int = 2) -> None:
        self.engine = engine
        self.model = model
        self.attempts = attempts

    def give_clue(self, game: Game, team: Team) -> ClueDecision:
        system, user = build_spymaster_prompt(game, team)
        # A clue may not be a word still on the board (the engine rejects it too).
        on_board = {
            c["word"].upper() for c in game.spymaster_state()["cards"] if not c["revealed"]
        }
        # Cheap models occasionally emit malformed JSON or an on-board clue — retry.
        last_error: ValueError | None = None
        for _ in range(self.attempts):
            result = self.engine.run(system, user, self.model)
            try:
                return self._parse(result, on_board)
            except ValueError as exc:
                last_error = exc
        raise last_error  # type: ignore[misc]

    def _parse(self, result, on_board: set[str]) -> ClueDecision:
        data = extract_json(result.text)

        word = str(data.get("clue", "")).strip()
        if not word or any(ch.isspace() for ch in word):
            raise ValueError(f"spymaster returned an invalid clue word: {data!r}")
        if word.upper() in on_board:
            raise ValueError(f"spymaster clue {word!r} is a word on the board")
        try:
            number = int(data["number"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"spymaster returned an invalid number: {data!r}") from exc

        return ClueDecision(
            word=word.upper(),
            number=max(0, number),
            reasoning=str(data.get("reasoning", "")).strip(),
            targets=[str(t).upper() for t in data.get("targets", []) if isinstance(t, str)],
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
