"""Extract a JSON object from a model's text output.

Cheap models sometimes wrap JSON in prose or code fences; we grab the outermost
braces and parse that.
"""

from __future__ import annotations

import json


def extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in model output: {text!r}")
    snippet = text[start : end + 1]
    try:
        parsed = json.loads(snippet)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in model output: {snippet!r}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"expected a JSON object, got {type(parsed).__name__}: {snippet!r}")
    return parsed
