"""Loads the bundled Codenames word list."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=1)
def load_words() -> tuple[str, ...]:
    """Return the bundled word list, upper-cased and de-duplicated.

    Cached so the file is read once per process. Returns a tuple so the cached
    value can't be mutated by callers.
    """
    raw = files("codenames").joinpath("data/wordlist.txt").read_text(encoding="utf-8")
    seen: set[str] = set()
    words: list[str] = []
    for line in raw.splitlines():
        word = line.strip().upper()
        if not word or word.startswith("#") or word in seen:
            continue
        seen.add(word)
        words.append(word)
    return tuple(words)
