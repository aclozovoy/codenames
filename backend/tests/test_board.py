import random

from codenames.engine import BOARD_SIZE, CardType, Team, build_board
from codenames.engine.board import (
    ASSASSIN_CARDS,
    NEUTRAL_CARDS,
    SECOND_TEAM_CARDS,
    STARTING_TEAM_CARDS,
)


def _counts(board):
    counts = dict.fromkeys(CardType, 0)
    for card in board:
        counts[card.type] += 1
    return counts


def test_board_has_25_cards():
    board = build_board(Team.RED, rng=random.Random(1))
    assert len(board) == BOARD_SIZE


def test_distribution_starting_team_gets_nine():
    board = build_board(Team.RED, rng=random.Random(1))
    counts = _counts(board)
    assert counts[CardType.RED] == STARTING_TEAM_CARDS  # RED started
    assert counts[CardType.BLUE] == SECOND_TEAM_CARDS
    assert counts[CardType.NEUTRAL] == NEUTRAL_CARDS
    assert counts[CardType.ASSASSIN] == ASSASSIN_CARDS


def test_distribution_flips_with_starting_team():
    board = build_board(Team.BLUE, rng=random.Random(1))
    counts = _counts(board)
    assert counts[CardType.BLUE] == STARTING_TEAM_CARDS  # BLUE started
    assert counts[CardType.RED] == SECOND_TEAM_CARDS


def test_seed_is_deterministic():
    a = build_board(Team.RED, rng=random.Random(42))
    b = build_board(Team.RED, rng=random.Random(42))
    assert [(c.word, c.type) for c in a] == [(c.word, c.type) for c in b]


def test_words_are_unique_on_board():
    board = build_board(Team.RED, rng=random.Random(7))
    words = [c.word for c in board]
    assert len(set(words)) == len(words)


def test_all_cards_start_hidden():
    board = build_board(Team.RED, rng=random.Random(7))
    assert all(not c.revealed for c in board)
