// Types mirroring the backend Pydantic schemas (codenames/api/schemas.py).
// Kept in sync by hand for now; can be auto-generated from the OpenAPI schema later.

export type TeamName = "red" | "blue";
export type ViewName = "operative" | "spymaster";
export type Phase = "await_clue" | "await_guess" | "game_over";
export type CardType = "red" | "blue" | "neutral" | "assassin";
export type Outcome = "correct" | "wrong_team" | "neutral" | "assassin";

export interface CardState {
  word: string;
  revealed: boolean;
  type: CardType | null; // null when hidden (operative view, unrevealed)
}

export interface ClueState {
  word: string;
  number: number;
}

export interface GameState {
  phase: Phase;
  starting_team: TeamName;
  current_team: TeamName;
  current_clue: ClueState | null;
  guesses_made: number;
  guesses_allowed: number | null;
  winner: TeamName | null;
  red_remaining: number;
  blue_remaining: number;
  cards: CardState[];
}

export interface GameView {
  game_id: string;
  view: ViewName;
  state: GameState;
}

export interface GuessResponse extends GameView {
  outcome: Outcome;
}
