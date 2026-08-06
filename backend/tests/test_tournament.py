"""Tournament tests: a scripted client drives a full game with no Bedrock calls."""

from codenames.players import LLMResult
from codenames.tournament import ResultsStore, head_to_head, play_game, win_rate_table


class ScriptedClient:
    """Plays a real game deterministically: the spymaster gives a fixed off-board
    clue; the operative always guesses the first word still on the board."""

    def complete(self, model_id, system, user, max_tokens, temperature):
        if "operative" in system:
            prefix = "Words still on the board:"
            line = next(ln for ln in user.splitlines() if ln.startswith(prefix))
            first = line.split(":", 1)[1].strip().split(", ")[0]
            text = f'{{"action": "guess", "word": "{first}", "reasoning": "x"}}'
        else:
            text = '{"clue": "ZZQX", "number": 1, "reasoning": "x", "targets": []}'
        return LLMResult(text, input_tokens=40, output_tokens=15)


def test_play_game_runs_to_completion():
    result = play_game(ScriptedClient(), "haiku", "nova-lite", seed=42)
    assert result.status == "completed"
    assert result.winner in ("red", "blue")
    assert result.winner_model in ("haiku", "nova-lite")
    assert result.loser_model in ("haiku", "nova-lite")
    assert result.winner_model != result.loser_model
    assert result.turns > 0
    assert result.input_tokens > 0
    assert result.ended_by in ("all_cards", "assassin")


def test_results_store_roundtrip(tmp_path):
    store = ResultsStore(tmp_path / "games.jsonl")
    result = play_game(ScriptedClient(), "haiku", "nova-micro", seed=7)
    store.append(result)
    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0]["winner_model"] in ("haiku", "nova-micro")
    assert loaded[0]["game_id"] == result.game_id


def test_win_rate_and_head_to_head():
    results = [
        {"red_model": "a", "blue_model": "b", "winner_model": "a", "loser_model": "b"},
        {"red_model": "b", "blue_model": "a", "winner_model": "a", "loser_model": "b"},
        {"red_model": "a", "blue_model": "b", "winner_model": "b", "loser_model": "a"},
        {"red_model": "a", "blue_model": "b", "winner_model": None},  # excluded
    ]
    table = {row["model"]: row for row in win_rate_table(results)}
    assert table["a"] == {"model": "a", "games": 3, "wins": 2, "win_rate": 0.667}
    assert table["b"] == {"model": "b", "games": 3, "wins": 1, "win_rate": 0.333}

    h2h = head_to_head(results)
    assert h2h["a"]["b"] == {"games": 3, "wins": 2, "win_rate": 0.667}
    assert h2h["b"]["a"] == {"games": 3, "wins": 1, "win_rate": 0.333}
