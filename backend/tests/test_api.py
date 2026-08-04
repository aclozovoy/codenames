"""API tests via FastAPI's TestClient (in-process, no server needed).

Uses a fixed seed so the board is reproducible, then reads the spymaster view to
learn each card's colour before driving guesses.
"""

import pytest
from fastapi.testclient import TestClient

from codenames.api.app import app

SEED = 2026


@pytest.fixture
def client():
    return TestClient(app)


def _create(client, **body):
    body.setdefault("seed", SEED)
    resp = client.post("/games", json=body)
    assert resp.status_code == 201
    return resp.json()


def _cards_by_color(client, game_id):
    """Return {color: [words...]} from the spymaster view."""
    state = client.get(f"/games/{game_id}", params={"view": "spymaster"}).json()["state"]
    out: dict[str, list[str]] = {}
    for card in state["cards"]:
        out.setdefault(card["type"], []).append(card["word"])
    return out


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_game_defaults_to_operative_view(client):
    data = _create(client)
    assert data["view"] == "operative"
    # Operative view hides every unrevealed colour at the start.
    assert all(c["type"] is None for c in data["state"]["cards"])
    assert data["state"]["phase"] == "await_clue"


def test_spymaster_view_shows_colors(client):
    data = _create(client)
    gid = data["game_id"]
    colors = _cards_by_color(client, gid)
    assert len(colors["red"]) + len(colors["blue"]) == 17  # 9 + 8
    assert len(colors["neutral"]) == 7
    assert len(colors["assassin"]) == 1


def test_missing_game_is_404(client):
    assert client.get("/games/nope").status_code == 404


def test_full_turn_flow(client):
    data = _create(client, starting_team="red")
    gid = data["game_id"]
    colors = _cards_by_color(client, gid)

    # Spymaster gives a clue.
    r = client.post(f"/games/{gid}/clue", json={"word": "SPY", "number": 2})
    assert r.status_code == 200
    assert r.json()["state"]["guesses_allowed"] == 3

    # A correct guess keeps the turn.
    r = client.post(f"/games/{gid}/guess", json={"word": colors["red"][0]})
    assert r.json()["outcome"] == "correct"
    assert r.json()["state"]["current_team"] == "red"

    # Passing hands over to blue.
    r = client.post(f"/games/{gid}/pass")
    assert r.json()["state"]["current_team"] == "blue"
    assert r.json()["state"]["phase"] == "await_clue"


def test_assassin_ends_game(client):
    data = _create(client, starting_team="red")
    gid = data["game_id"]
    colors = _cards_by_color(client, gid)

    client.post(f"/games/{gid}/clue", json={"word": "SPY", "number": 3})
    r = client.post(f"/games/{gid}/guess", json={"word": colors["assassin"][0]})
    assert r.json()["outcome"] == "assassin"
    assert r.json()["state"]["phase"] == "game_over"
    assert r.json()["state"]["winner"] == "blue"


def test_illegal_move_returns_409(client):
    data = _create(client, starting_team="red")
    gid = data["game_id"]
    # Guessing before any clue is illegal for the current state.
    r = client.post(f"/games/{gid}/guess", json={"word": "APPLE"})
    assert r.status_code == 409


def test_clue_validation_rejects_negative_number(client):
    data = _create(client)
    gid = data["game_id"]
    r = client.post(f"/games/{gid}/clue", json={"word": "SPY", "number": -1})
    assert r.status_code == 422  # pydantic request validation


def test_list_games_includes_created(client):
    gid = _create(client)["game_id"]
    ids = [g["game_id"] for g in client.get("/games").json()]
    assert gid in ids


def test_websocket_receives_initial_and_updates(client):
    data = _create(client, starting_team="red")
    gid = data["game_id"]

    with client.websocket_connect(f"/games/{gid}/ws?view=spymaster") as ws:
        initial = ws.receive_json()
        assert initial["game_id"] == gid
        assert initial["view"] == "spymaster"

        # A REST mutation should push a fresh state over the socket.
        client.post(f"/games/{gid}/clue", json={"word": "SPY", "number": 1})
        update = ws.receive_json()
        assert update["state"]["current_clue"] == {"word": "SPY", "number": 1}


# -- LLM move endpoint (with a fake client, no Bedrock) ------------------------


class _FakeLLM:
    """Stand-in for BedrockClient — returns queued canned completions."""

    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, model_id, system, user, max_tokens, temperature):
        from codenames.players import LLMResult

        return LLMResult(self.responses.pop(0), input_tokens=100, output_tokens=50)


def test_llm_move_records_reasoning(client):
    from codenames.api.app import store
    from codenames.players import LLMEngine, ModelConfig

    data = _create(client, starting_team="red")
    gid = data["game_id"]

    # Inject a fake engine so the endpoint doesn't call Bedrock.
    session = store.get(gid)
    session._engine = LLMEngine(
        _FakeLLM(['{"reasoning": "safe clue", "clue": "ZZZQ", "number": 2, "targets": []}']),
        ModelConfig("fake", input_usd_per_mtok=1.0, output_usd_per_mtok=5.0),
    )

    resp = client.post(f"/games/{gid}/llm-move?view=spymaster")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"]["phase"] == "await_guess"
    assert body["state"]["current_clue"] == {"word": "ZZZQ", "number": 2}
    last = body["moves"][-1]
    assert last["seat"] == "red spymaster"
    assert last["action"] == "clue"
    assert last["reasoning"] == "safe clue"
    assert body["usage"]["calls"] == 1
