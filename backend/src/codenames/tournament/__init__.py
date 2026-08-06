"""Model-vs-model tournament: play AI-vs-AI games and record results locally.

Standalone from the web app — it drives the engine and players directly. Run it
with ``python -m codenames.tournament run`` / ``... stats`` (see __main__.py).
"""

from .results import ResultsStore, head_to_head, win_rate_table
from .runner import GameResult, play_game

__all__ = [
    "GameResult",
    "ResultsStore",
    "head_to_head",
    "play_game",
    "win_rate_table",
]
