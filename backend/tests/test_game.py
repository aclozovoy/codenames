"""Tests for the Game state machine, using hand-built boards with known colours.

Board layout helper produces predictable words:
    RED cards   -> "R0".."R8"   (9, RED starts)
    BLUE cards  -> "B0".."B7"   (8)
    NEUTRAL     -> "N0".."N6"   (7)
    ASSASSIN    -> "A0"         (1)
"""

import pytest

from codenames.engine import (
    Card,
    CardType,
    Game,
    GuessOutcome,
    InvalidMove,
    Phase,
    Team,
)


def make_board() -> list[Card]:
    cards: list[Card] = []
    cards += [Card(f"R{i}", CardType.RED) for i in range(9)]
    cards += [Card(f"B{i}", CardType.BLUE) for i in range(8)]
    cards += [Card(f"N{i}", CardType.NEUTRAL) for i in range(7)]
    cards += [Card("A0", CardType.ASSASSIN)]
    return cards


def new_game() -> Game:
    return Game(make_board(), starting_team=Team.RED)


# -- initial state --------------------------------------------------------------


def test_initial_state():
    g = new_game()
    assert g.phase is Phase.AWAIT_CLUE
    assert g.current_team is Team.RED
    assert g.winner is None
    assert g.cards_remaining(Team.RED) == 9
    assert g.cards_remaining(Team.BLUE) == 8


def test_constructor_rejects_wrong_board_size():
    with pytest.raises(ValueError):
        Game([Card("X", CardType.NEUTRAL)], starting_team=Team.RED)


# -- giving clues ---------------------------------------------------------------


def test_give_clue_transitions_and_sets_allowance():
    g = new_game()
    g.give_clue("ANIMAL", 2)
    assert g.phase is Phase.AWAIT_GUESS
    assert g.current_clue.word == "ANIMAL"
    assert g.guesses_allowed == 3  # number + 1


def test_clue_number_zero_means_unlimited():
    g = new_game()
    g.give_clue("VAGUE", 0)
    assert g.guesses_allowed is None


def test_cannot_give_clue_when_awaiting_guess():
    g = new_game()
    g.give_clue("ANIMAL", 2)
    with pytest.raises(InvalidMove):
        g.give_clue("AGAIN", 1)


def test_clue_rejects_multiword_empty_and_negative():
    g = new_game()
    with pytest.raises(InvalidMove):
        g.give_clue("TWO WORDS", 1)
    with pytest.raises(InvalidMove):
        g.give_clue("   ", 1)
    with pytest.raises(InvalidMove):
        g.give_clue("OK", -1)


def test_clue_cannot_match_word_on_board():
    g = new_game()
    with pytest.raises(InvalidMove):
        g.give_clue("r0", 1)  # matches board word "R0" case-insensitively


# -- guessing -------------------------------------------------------------------


def test_correct_guess_lets_team_continue():
    g = new_game()
    g.give_clue("REDS", 2)  # allowance 3
    assert g.guess("R0") is GuessOutcome.CORRECT
    assert g.phase is Phase.AWAIT_GUESS  # still their turn
    assert g.current_team is Team.RED


def test_using_up_allowance_ends_turn():
    g = new_game()
    g.give_clue("REDS", 1)  # allowance 2
    g.guess("R0")
    g.guess("R1")  # second correct guess uses the allowance
    assert g.phase is Phase.AWAIT_CLUE
    assert g.current_team is Team.BLUE


def test_neutral_guess_ends_turn():
    g = new_game()
    g.give_clue("REDS", 2)
    assert g.guess("N0") is GuessOutcome.NEUTRAL
    assert g.current_team is Team.BLUE
    assert g.phase is Phase.AWAIT_CLUE


def test_wrong_team_guess_ends_turn():
    g = new_game()
    g.give_clue("REDS", 2)
    assert g.guess("B0") is GuessOutcome.WRONG_TEAM
    assert g.current_team is Team.BLUE
    assert g.cards_remaining(Team.BLUE) == 7  # revealing helped BLUE


def test_assassin_loses_immediately():
    g = new_game()
    g.give_clue("REDS", 2)
    assert g.guess("A0") is GuessOutcome.ASSASSIN
    assert g.phase is Phase.GAME_OVER
    assert g.winner is Team.BLUE


def test_revealing_all_own_cards_wins():
    g = new_game()
    g.give_clue("ALL", 0)  # unlimited guesses
    for i in range(9):
        g.guess(f"R{i}")
    assert g.phase is Phase.GAME_OVER
    assert g.winner is Team.RED


def test_wrong_team_guess_can_hand_opponent_the_win():
    g = new_game()
    # Reveal 7 of BLUE's 8 cards directly so only B7 remains.
    for c in g.board:
        if c.type is CardType.BLUE and c.word != "B7":
            c.revealed = True
    assert g.cards_remaining(Team.BLUE) == 1
    g.give_clue("REDS", 2)
    assert g.guess("B7") is GuessOutcome.WRONG_TEAM  # RED reveals BLUE's last card
    assert g.phase is Phase.GAME_OVER
    assert g.winner is Team.BLUE


# -- passing --------------------------------------------------------------------


def test_pass_requires_a_guess_first():
    g = new_game()
    g.give_clue("REDS", 2)
    with pytest.raises(InvalidMove):
        g.pass_turn()


def test_pass_after_a_guess_ends_turn():
    g = new_game()
    g.give_clue("REDS", 2)
    g.guess("R0")
    g.pass_turn()
    assert g.current_team is Team.BLUE
    assert g.phase is Phase.AWAIT_CLUE


# -- guard rails ----------------------------------------------------------------


def test_cannot_guess_before_a_clue():
    g = new_game()
    with pytest.raises(InvalidMove):
        g.guess("R0")


def test_guessing_unknown_word_raises():
    g = new_game()
    g.give_clue("REDS", 2)
    with pytest.raises(InvalidMove):
        g.guess("NOPE")


def test_cannot_guess_revealed_card():
    g = new_game()
    g.give_clue("REDS", 2)
    g.guess("R0")
    with pytest.raises(InvalidMove):
        g.guess("R0")


def test_no_moves_after_game_over():
    g = new_game()
    g.give_clue("REDS", 2)
    g.guess("A0")  # assassin -> game over
    with pytest.raises(InvalidMove):
        g.guess("R0")
    with pytest.raises(InvalidMove):
        g.give_clue("X", 1)


# -- views ----------------------------------------------------------------------


def test_operative_view_hides_unrevealed_colours():
    g = new_game()
    g.give_clue("REDS", 2)
    g.guess("R0")
    state = g.operative_state()
    by_word = {c["word"]: c for c in state["cards"]}
    assert by_word["R0"]["type"] == "red"  # revealed -> visible
    assert by_word["R1"]["type"] is None  # hidden
    assert by_word["A0"]["type"] is None


def test_spymaster_view_reveals_all_colours():
    g = new_game()
    state = g.spymaster_state()
    by_word = {c["word"]: c for c in state["cards"]}
    assert by_word["A0"]["type"] == "assassin"
    assert by_word["R5"]["type"] == "red"
