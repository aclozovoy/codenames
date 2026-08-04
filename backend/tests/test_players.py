"""Tests for the LLM players, using a fake client (no Bedrock calls)."""

import pytest

from codenames.engine import Card, CardType, Game, Team
from codenames.players import (
    BudgetExceeded,
    LLMEngine,
    LLMOperative,
    LLMResult,
    LLMSpymaster,
    ModelConfig,
)
from codenames.players.parsing import extract_json

MODEL = ModelConfig(model_id="fake", input_usd_per_mtok=1.0, output_usd_per_mtok=5.0, label="Fake")


class FakeClient:
    """Returns queued canned completions; records the prompts it was given."""

    def __init__(self, responses, input_tokens=1000, output_tokens=500):
        self.responses = list(responses)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.prompts = []

    def complete(self, model_id, system, user, max_tokens, temperature):
        self.prompts.append((system, user))
        # Pop through the queue but repeat the last item, so retry attempts (which
        # re-call on a parse failure) keep seeing the same canned response.
        text = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return LLMResult(text, self.input_tokens, self.output_tokens)


def make_board():
    cards = [Card(f"R{i}", CardType.RED) for i in range(9)]
    cards += [Card(f"B{i}", CardType.BLUE) for i in range(8)]
    cards += [Card(f"N{i}", CardType.NEUTRAL) for i in range(7)]
    cards += [Card("A0", CardType.ASSASSIN)]
    return cards


def engine_with(responses, budget=None):
    return LLMEngine(FakeClient(responses), budget_usd=budget)


# -- JSON extraction -----------------------------------------------------------


def test_extract_json_from_surrounding_prose():
    text = 'Sure! Here is my clue:\n{"clue": "ANIMAL", "number": 2}\nGood luck.'
    assert extract_json(text) == {"clue": "ANIMAL", "number": 2}


def test_extract_json_raises_when_absent():
    with pytest.raises(ValueError):
        extract_json("no json here")


# -- spymaster -----------------------------------------------------------------


def test_spymaster_parses_clue_and_reasoning():
    game = Game(make_board(), starting_team=Team.RED)
    eng = engine_with(
        [
            '{"reasoning": "R0 and R1 are both X", "clue": "letter", "number": 2, '
            '"targets": ["R0", "R1"]}'
        ]
    )
    decision = LLMSpymaster(eng, MODEL).give_clue(game, Team.RED)
    assert decision.word == "LETTER"
    assert decision.number == 2
    assert decision.reasoning.startswith("R0 and R1")
    assert decision.targets == ["R0", "R1"]
    assert decision.input_tokens == 1000


def test_spymaster_rejects_multiword_clue():
    game = Game(make_board(), starting_team=Team.RED)
    eng = engine_with(['{"clue": "two words", "number": 1}'])
    with pytest.raises(ValueError):
        LLMSpymaster(eng, MODEL).give_clue(game, Team.RED)


def test_spymaster_prompt_hides_nothing_from_spymaster():
    game = Game(make_board(), starting_team=Team.RED)
    client = FakeClient(['{"clue": "x", "number": 1}'])
    LLMSpymaster(LLMEngine(client), MODEL).give_clue(game, Team.RED)
    _, user = client.prompts[0]
    assert "A0" in user  # the assassin is shown to the spymaster


# -- operative -----------------------------------------------------------------


def _game_awaiting_guess():
    game = Game(make_board(), starting_team=Team.RED)
    game.give_clue("SPY", 2)
    return game


def test_operative_parses_guess():
    game = _game_awaiting_guess()
    eng = engine_with(['{"reasoning": "R0 fits", "action": "guess", "word": "R0"}'])
    decision = LLMOperative(eng, MODEL).next_move(game, Team.RED)
    assert decision.action == "guess"
    assert decision.word == "R0"
    assert decision.reasoning == "R0 fits"


def test_operative_can_pass():
    game = _game_awaiting_guess()
    eng = engine_with(['{"reasoning": "too risky", "action": "pass"}'])
    decision = LLMOperative(eng, MODEL).next_move(game, Team.RED)
    assert decision.action == "pass"
    assert decision.word is None


def test_operative_gives_up_after_repeated_invalid_guesses():
    # An invalid word on every attempt -> the operative gives up (counts as a pass).
    game = _game_awaiting_guess()
    eng = engine_with(['{"action": "guess", "word": "NOPE"}'])
    decision = LLMOperative(eng, MODEL, attempts=2).next_move(game, Team.RED)
    assert decision.action == "give_up"
    assert decision.word is None
    assert eng.usage["calls"] == 2  # it retried before giving up


def test_operative_prompt_hides_colours():
    game = _game_awaiting_guess()
    client = FakeClient(['{"action": "guess", "word": "R0"}'])
    LLMOperative(LLMEngine(client), MODEL).next_move(game, Team.RED)
    _, user = client.prompts[0]
    # Operative sees the words but not their colours or the assassin label.
    assert "R0" in user
    assert "assassin" not in user.lower()


# -- cost tracking + budget guard ----------------------------------------------


def test_engine_tracks_cost():
    eng = engine_with(['{"clue": "x", "number": 1}'])
    game = Game(make_board(), starting_team=Team.RED)
    LLMSpymaster(eng, MODEL).give_clue(game, Team.RED)
    # 1000 in * $1/M + 500 out * $5/M = 0.001 + 0.0025 = 0.0035
    assert eng.usage["calls"] == 1
    assert eng.usage["usd"] == pytest.approx(0.0035)


def test_budget_guard_blocks_when_reached():
    # Budget below the cost of a single call -> first call ok, second blocked.
    eng = engine_with(['{"clue": "x", "number": 1}', '{"clue": "y", "number": 1}'], budget=0.004)
    game = Game(make_board(), starting_team=Team.RED)
    sm = LLMSpymaster(eng, MODEL)
    sm.give_clue(game, Team.RED)  # spends 0.0035, now >= budget 0.004? no, 0.0035 < 0.004
    # Second call: 0.0035 < 0.004 so it still runs, pushing to 0.007
    sm.give_clue(game, Team.RED)
    # Third would be blocked (0.007 >= 0.004)
    with pytest.raises(BudgetExceeded):
        sm.give_clue(game, Team.RED)
