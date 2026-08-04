"""Prompt construction for the LLM players.

The spymaster prompt uses the full (colour-revealing) view; the operative prompt
uses the hidden view so the model only knows what a real operative would.
"""

from __future__ import annotations

from ..engine import Game, Team


def build_spymaster_prompt(game: Game, team: Team) -> tuple[str, str]:
    state = game.spymaster_state()
    yours, theirs, neutral, assassin = [], [], [], []
    for card in state["cards"]:
        if card["revealed"]:
            continue
        bucket = {
            team.value: yours,
            team.opponent.value: theirs,
            "neutral": neutral,
            "assassin": assassin,
        }[card["type"]]
        bucket.append(card["word"])

    system = (
        f"You are the {team.value} team's spymaster in the word game Codenames. "
        "Give a single-word clue that connects as many of YOUR team's words as possible "
        "while avoiding the opponent's words, the neutral bystanders, and above all the assassin "
        "(guessing the assassin loses the game instantly). The clue must be a single English word, "
        "must not appear on the board, and must not be a proper noun taken from the board. "
        "Respond ONLY with a JSON object and nothing else."
    )
    user = (
        f"YOUR words ({team.value}): {', '.join(yours)}\n"
        f"OPPONENT words ({team.opponent.value}): {', '.join(theirs)}\n"
        f"NEUTRAL bystanders: {', '.join(neutral)}\n"
        f"ASSASSIN (never point here): {', '.join(assassin)}\n\n"
        'Respond with JSON: {"reasoning": "...", "clue": "WORD", "number": N, '
        '"targets": ["WORD", ...]}\n'
        "- reasoning: a concise explanation of your thinking, at most 3 sentences\n"
        "- clue: a single word not on the board\n"
        "- number: how many of YOUR words the clue points to (a positive integer)\n"
        "- targets: the list of your words you intend the clue to point to\n"
        "Keep it short so the JSON is complete. Output only the JSON object."
    )
    return system, user


def build_operative_prompt(game: Game, team: Team) -> tuple[str, str]:
    state = game.operative_state()
    clue = state["current_clue"]
    if clue is None:
        raise ValueError("operative prompt requires an active clue")
    remaining = (
        "unlimited"
        if state["guesses_allowed"] is None
        else max(0, state["guesses_allowed"] - state["guesses_made"])
    )
    unrevealed = [c["word"] for c in state["cards"] if not c["revealed"]]
    revealed = [f"{c['word']} ({c['type']})" for c in state["cards"] if c["revealed"]]

    system = (
        f"You are an operative on the {team.value} team in the word game Codenames. "
        "Your spymaster gave a one-word clue and a number. Pick the single word on the board "
        "you are most confident belongs to your team. You may instead stop guessing to be safe. "
        "Avoid the opponent's words, neutral bystanders, and especially the assassin. "
        "Respond ONLY with a JSON object and nothing else."
    )
    user = (
        f'Clue: "{clue["word"]}" for {clue["number"]}\n'
        f"Guesses remaining this turn: {remaining}\n"
        f"Words still on the board: {', '.join(unrevealed)}\n"
        f"Already revealed: {', '.join(revealed) if revealed else 'none'}\n\n"
        'Respond with JSON: {"reasoning": "...", "action": "guess", "word": "WORD"} to guess, '
        'or {"reasoning": "...", "action": "pass"} to stop guessing this turn.\n'
        "- word must be exactly one of the words still on the board.\n"
        "- reasoning: concise, at most 3 sentences. Output only the JSON object."
    )
    return system, user
