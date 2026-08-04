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
    from codenames.players import LLMEngine

    data = _create(client, starting_team="red")
    gid = data["game_id"]

    # Inject a fake engine so the endpoint doesn't call Bedrock. The model is
    # chosen per call from the session config (defaults to haiku); the fake
    # client ignores the model id.
    session = store.get(gid)
    session._engine = LLMEngine(
        _FakeLLM(['{"reasoning": "safe clue", "clue": "ZZZQ", "number": 2, "targets": []}'])
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


# -- game modes (seats + models) ----------------------------------------------


def test_models_endpoint_lists_cheap_models(client):
    models = client.get("/models").json()
    keys = {m["key"] for m in models}
    assert "haiku" in keys
    assert all("input_usd_per_mtok" in m for m in models)


def test_create_defaults_to_all_ai(client):
    cfg = _create(client)["config"]
    assert cfg["seats"] == {
        "red_spymaster": "ai",
        "red_operative": "ai",
        "blue_spymaster": "ai",
        "blue_operative": "ai",
    }
    assert cfg["models"] == {"red": "haiku", "blue": "haiku"}


def test_create_with_seats_and_per_team_models(client):
    resp = client.post(
        "/games?view=spymaster",
        json={
            "starting_team": "red",
            "seats": {"red_spymaster": "human"},
            "models": {"red": "nova-micro", "blue": "haiku"},
        },
    )
    assert resp.status_code == 201
    cfg = resp.json()["config"]
    assert cfg["seats"]["red_spymaster"] == "human"
    assert cfg["seats"]["blue_operative"] == "ai"  # unspecified -> ai
    assert cfg["models"] == {"red": "nova-micro", "blue": "haiku"}
    # Red spymaster is human, so it's the current seat and not AI.
    assert cfg["current_seat"] == "red_spymaster"
    assert cfg["current_is_ai"] is False


def test_create_rejects_unknown_model(client):
    resp = client.post("/games", json={"models": {"red": "gpt-9"}})
    assert resp.status_code == 400


def test_llm_move_on_human_seat_is_409(client):
    data = _create(client, starting_team="red", seats={"red_spymaster": "human"})
    gid = data["game_id"]
    resp = client.post(f"/games/{gid}/llm-move?view=spymaster")
    assert resp.status_code == 409
