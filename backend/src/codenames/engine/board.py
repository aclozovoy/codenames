"""Board generation: pick 25 words and assign card colours."""

from __future__ import annotations

import random

from .types import Card, CardType, Team
from .words import load_words

BOARD_SIZE = 25

# Card colour distribution. The team that goes first gets one extra card (9 vs 8),
# which is why they also have to move first. 9 + 8 + 7 + 1 = 25.
STARTING_TEAM_CARDS = 9
SECOND_TEAM_CARDS = 8
NEUTRAL_CARDS = 7
ASSASSIN_CARDS = 1


def build_board(
    starting_team: Team,
    words: list[str] | None = None,
    rng: random.Random | None = None,
) -> list[Card]:
    """Build a shuffled 25-card board.

    Args:
        starting_team: the team that moves first (gets 9 cards).
        words: pool to sample from; defaults to the bundled list.
        rng: inject a seeded ``random.Random`` for deterministic tests.
    """
    rng = rng or random.Random()
    pool = list(words) if words is not None else list(load_words())
    if len(pool) < BOARD_SIZE:
        raise ValueError(f"need at least {BOARD_SIZE} words, got {len(pool)}")

    chosen = rng.sample(pool, BOARD_SIZE)

    second_team = starting_team.opponent
    types = (
        [starting_team.card_type] * STARTING_TEAM_CARDS
        + [second_team.card_type] * SECOND_TEAM_CARDS
        + [CardType.NEUTRAL] * NEUTRAL_CARDS
        + [CardType.ASSASSIN] * ASSASSIN_CARDS
    )
    rng.shuffle(types)

    return [Card(word=word, type=card_type) for word, card_type in zip(chosen, types, strict=True)]
