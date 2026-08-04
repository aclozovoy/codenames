// Thin typed client over the FastAPI backend. Uses same-origin relative URLs,
// which Vite proxies to http://localhost:8000 in dev (see vite.config.ts).

import type {
  Control,
  GameView,
  GuessResponse,
  ModelInfo,
  SeatKey,
  TeamName,
  ViewName,
} from "./types";

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      // non-JSON error body — keep the status text
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export interface CreateOptions {
  starting_team?: TeamName;
  seed?: number;
  seats?: Partial<Record<SeatKey, Control>>;
  models?: Partial<Record<TeamName, string>>;
}

export async function createGame(view: ViewName, opts: CreateOptions = {}): Promise<GameView> {
  const resp = await fetch(`/games?view=${view}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
  return handle<GameView>(resp);
}

export async function listModels(): Promise<ModelInfo[]> {
  return handle<ModelInfo[]>(await fetch("/models"));
}

export async function getGame(gameId: string, view: ViewName): Promise<GameView> {
  return handle<GameView>(await fetch(`/games/${gameId}?view=${view}`));
}

export async function giveClue(
  gameId: string,
  view: ViewName,
  word: string,
  number: number,
): Promise<GameView> {
  const resp = await fetch(`/games/${gameId}/clue?view=${view}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word, number }),
  });
  return handle<GameView>(resp);
}

export async function makeGuess(
  gameId: string,
  view: ViewName,
  word: string,
): Promise<GuessResponse> {
  const resp = await fetch(`/games/${gameId}/guess?view=${view}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ word }),
  });
  return handle<GuessResponse>(resp);
}

export async function passTurn(gameId: string, view: ViewName): Promise<GameView> {
  return handle<GameView>(await fetch(`/games/${gameId}/pass?view=${view}`, { method: "POST" }));
}

/** Advance the game by one LLM action (spymaster clue or one operative guess). */
export async function llmMove(gameId: string, view: ViewName): Promise<GameView> {
  return handle<GameView>(await fetch(`/games/${gameId}/llm-move?view=${view}`, { method: "POST" }));
}

/** Open a live WebSocket for a game/view. Caller handles messages + cleanup. */
export function openGameSocket(gameId: string, view: ViewName): WebSocket {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return new WebSocket(`${proto}://${window.location.host}/games/${gameId}/ws?view=${view}`);
}
