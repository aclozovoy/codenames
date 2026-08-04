"""FastAPI application: REST endpoints + a WebSocket for live state updates.

Run locally with:
    uvicorn codenames.api.app:app --reload

Note on views: without auth yet, the board view is chosen by a ``view`` query
parameter (default ``operative``, which hides unrevealed colours). Real per-seat
access control comes with player/auth support later.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from ..engine import InvalidMove, Phase
from ..players import BudgetExceeded, LLMOperative, LLMSpymaster
from .schemas import (
    ClueRequest,
    CreateGameRequest,
    GameSummary,
    GameView,
    GuessRequest,
    GuessResponse,
)
from .store import GameSession, GameStore

app = FastAPI(title="Codenames", version="0.1.0")

# Permissive CORS for local frontend dev (Vite on :5173, etc.). Tighten for prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = GameStore()


# -- error mapping --------------------------------------------------------------


@app.exception_handler(InvalidMove)
async def _invalid_move_handler(request: Request, exc: InvalidMove) -> JSONResponse:
    # Illegal given the current game state -> 409 Conflict.
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(BudgetExceeded)
async def _budget_handler(request: Request, exc: BudgetExceeded) -> JSONResponse:
    # 402 Payment Required — the game's LLM spend cap was reached.
    return JSONResponse(status_code=402, content={"detail": str(exc)})


# -- dependencies ---------------------------------------------------------------


def get_session(game_id: str) -> GameSession:
    session = store.get(game_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"no game {game_id!r}")
    return session


# Reusable typed dependencies (modern FastAPI style — avoids calls in defaults).
SessionDep = Annotated[GameSession, Depends(get_session)]
ViewQuery = Annotated[str, Query()]


# -- routes ---------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/games", response_model=list[GameSummary])
async def list_games() -> list[GameSummary]:
    return [
        GameSummary(
            game_id=s.game_id,
            phase=s.game.phase.value,
            current_team=s.game.current_team.value,
            winner=s.game.winner.value if s.game.winner else None,
        )
        for s in store.all()
    ]


@app.post("/games", response_model=GameView, status_code=201)
async def create_game(
    body: CreateGameRequest,
    view: ViewQuery = "operative",
) -> GameView:
    session = store.create(starting_team=body.starting_team, seed=body.seed)
    return GameView(**session.view_payload(view))


@app.get("/games/{game_id}", response_model=GameView)
async def get_game(
    session: SessionDep,
    view: ViewQuery = "operative",
) -> GameView:
    return GameView(**session.view_payload(view))


@app.post("/games/{game_id}/clue", response_model=GameView)
async def give_clue(
    body: ClueRequest,
    session: SessionDep,
    view: ViewQuery = "operative",
) -> GameView:
    async with session.lock:
        session.game.give_clue(body.word, body.number)
        await session.broadcast()
    return GameView(**session.view_payload(view))


@app.post("/games/{game_id}/guess", response_model=GuessResponse)
async def make_guess(
    body: GuessRequest,
    session: SessionDep,
    view: ViewQuery = "operative",
) -> GuessResponse:
    async with session.lock:
        outcome = session.game.guess(body.word)
        await session.broadcast()
    payload = session.view_payload(view)
    return GuessResponse(outcome=outcome.value, **payload)


@app.post("/games/{game_id}/pass", response_model=GameView)
async def pass_turn(
    session: SessionDep,
    view: ViewQuery = "operative",
) -> GameView:
    async with session.lock:
        session.game.pass_turn()
        await session.broadcast()
    return GameView(**session.view_payload(view))


@app.post("/games/{game_id}/llm-move", response_model=GameView)
async def llm_move(
    session: SessionDep,
    view: ViewQuery = "operative",
) -> GameView:
    """Advance the game by one LLM action for whoever is currently on the move.

    AWAIT_CLUE -> the current team's spymaster produces a clue.
    AWAIT_GUESS -> the current team's operative makes one guess (or passes).
    Each move is recorded with the model's reasoning in the session's move log.
    """
    game = session.game
    if game.phase is Phase.GAME_OVER:
        raise InvalidMove("game is over")

    async with session.lock:
        engine = session.ensure_engine()
        team = game.current_team

        if game.phase is Phase.AWAIT_CLUE:
            decision = await run_in_threadpool(LLMSpymaster(engine).give_clue, game, team)
            game.give_clue(decision.word, decision.number)
            session.moves.append(
                {
                    "seat": f"{team.value} spymaster",
                    "action": "clue",
                    "word": decision.word,
                    "number": decision.number,
                    "targets": decision.targets,
                    "outcome": None,
                    "reasoning": decision.reasoning,
                    "input_tokens": decision.input_tokens,
                    "output_tokens": decision.output_tokens,
                }
            )
        else:  # AWAIT_GUESS
            decision = await run_in_threadpool(LLMOperative(engine).next_move, game, team)
            move = {
                "seat": f"{team.value} operative",
                "word": decision.word,
                "number": None,
                "targets": [],
                "reasoning": decision.reasoning,
                "input_tokens": decision.input_tokens,
                "output_tokens": decision.output_tokens,
            }
            if decision.action == "pass":
                if game.guesses_made >= 1:
                    game.pass_turn()
                    move.update(action="pass", outcome="pass")
                else:
                    # A team must guess at least once; record the declined pass
                    # without changing state so the user can trigger another move.
                    move.update(action="declined", outcome=None)
            else:
                outcome = game.guess(decision.word)
                move.update(action="guess", outcome=outcome.value)
            session.moves.append(move)

        await session.broadcast()

    return GameView(**session.view_payload(view))


@app.websocket("/games/{game_id}/ws")
async def game_ws(websocket: WebSocket, game_id: str, view: str = Query("operative")) -> None:
    session = store.get(game_id)
    if session is None:
        await websocket.close(code=4404)
        return
    await session.connect(websocket, view)
    try:
        # We don't expect inbound messages; hold the socket open for broadcasts.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        session.disconnect(websocket)
