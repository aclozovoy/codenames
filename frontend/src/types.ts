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

export interface MoveRecord {
  seat: string; // e.g. "red spymaster", "blue operative"
  action: "clue" | "guess" | "pass" | "declined";
  word: string | null;
  number: number | null;
  targets: string[];
  outcome: Outcome | "pass" | null;
  reasoning: string;
  input_tokens: number;
  output_tokens: number;
}

export interface Usage {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  usd: number;
  budget_usd: number | null;
}

export type Control = "human" | "ai";
export type SeatKey = "red_spymaster" | "red_operative" | "blue_spymaster" | "blue_operative";
export type Role = "spymaster" | "operative";

export interface GameConfig {
  seats: Record<SeatKey, Control>;
  models: Record<TeamName, string>;
  current_seat: SeatKey | null;
  current_is_ai: boolean;
}

export interface ModelInfo {
  key: string;
  label: string;
  input_usd_per_mtok: number;
  output_usd_per_mtok: number;
}

export interface LogEntry {
  type: "clue" | "guess" | "pass" | "forfeit";
  team: TeamName;
  word: string | null;
  number: number | null;
  card_type: CardType | null;
  outcome: Outcome | null;
}

export interface GameView {
  game_id: string;
  view: ViewName;
  state: GameState;
  moves: MoveRecord[];
  usage: Usage | null;
  config: GameConfig | null;
  log: LogEntry[];
}

export interface GuessResponse extends GameView {
  outcome: Outcome;
}
