from codenames.engine import BOARD_SIZE
from codenames.engine.words import load_words


def test_word_list_is_large_enough():
    words = load_words()
    assert len(words) >= BOARD_SIZE


def test_words_are_upper_and_unique():
    words = load_words()
    assert all(w == w.upper() for w in words)
    assert len(set(words)) == len(words)


def test_no_comments_or_blanks_leak_in():
    words = load_words()
    assert all(w and not w.startswith("#") for w in words)
