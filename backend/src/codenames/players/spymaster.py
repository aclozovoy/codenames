"""LLM spymaster: turns a board into a clue, with visible reasoning."""

from __future__ import annotations

from dataclasses import dataclass

from ..engine import Game, Team
from .engine import LLMEngine
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
    def __init__(self, engine: LLMEngine) -> None:
        self.engine = engine

    def give_clue(self, game: Game, team: Team) -> ClueDecision:
        system, user = build_spymaster_prompt(game, team)
        result = self.engine.run(system, user)
        data = extract_json(result.text)

        word = str(data.get("clue", "")).strip()
        if not word or any(ch.isspace() for ch in word):
            raise ValueError(f"spymaster returned an invalid clue word: {data!r}")
        try:
            number = int(data["number"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"spymaster returned an invalid number: {data!r}") from exc
        number = max(0, number)

        return ClueDecision(
            word=word.upper(),
            number=number,
            reasoning=str(data.get("reasoning", "")).strip(),
            targets=[str(t).upper() for t in data.get("targets", []) if isinstance(t, str)],
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
