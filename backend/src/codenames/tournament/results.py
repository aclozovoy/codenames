"""Local (JSONL) result storage and win-rate aggregation."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from .runner import GameResult


class ResultsStore:
    """Append-only JSONL store — one game result per line."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, result: GameResult) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(result)) + "\n")

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


def _decided(results: list[dict]) -> list[dict]:
    """Games with a real winner (exclude errors/unfinished)."""
    return [r for r in results if r.get("winner_model")]


def win_rate_table(results: list[dict]) -> list[dict]:
    """Per-model games/wins/win-rate, sorted by win rate desc."""
    games: dict[str, int] = defaultdict(int)
    wins: dict[str, int] = defaultdict(int)
    for r in _decided(results):
        games[r["red_model"]] += 1
        games[r["blue_model"]] += 1
        wins[r["winner_model"]] += 1
    rows = [
        {
            "model": m,
            "games": games[m],
            "wins": wins[m],
            "win_rate": round(wins[m] / games[m], 3) if games[m] else 0.0,
        }
        for m in games
    ]
    return sorted(rows, key=lambda x: (-x["win_rate"], -x["games"], x["model"]))


def head_to_head(results: list[dict]) -> dict[str, dict[str, dict]]:
    """Nested {model: {opponent: {games, wins, win_rate}}} for each matchup."""

    def new_cell() -> dict:
        return {"games": 0, "wins": 0}

    table: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(new_cell))
    for r in _decided(results):
        a, b = r["red_model"], r["blue_model"]
        table[a][b]["games"] += 1
        table[b][a]["games"] += 1
        table[r["winner_model"]][r["loser_model"]]["wins"] += 1
    for opps in table.values():
        for cell in opps.values():
            cell["win_rate"] = round(cell["wins"] / cell["games"], 3) if cell["games"] else 0.0
    return {m: dict(opps) for m, opps in table.items()}
