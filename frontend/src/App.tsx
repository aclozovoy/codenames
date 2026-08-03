import { useCallback, useEffect, useState } from "react";
import "./App.css";
import * as api from "./api";
import type { CardState, GameState, GameView, ViewName } from "./types";

export default function App() {
  const [view, setView] = useState<ViewName>("spymaster");
  const [gameId, setGameId] = useState<string | null>(null);
  const [state, setState] = useState<GameState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const applyView = useCallback((v: GameView) => {
    setGameId(v.game_id);
    setState(v.state);
  }, []);

  const run = useCallback(
    async (fn: () => Promise<GameView>) => {
      setError(null);
      try {
        applyView(await fn());
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [applyView],
  );

  // Live updates: (re)open a WebSocket whenever the game or view changes.
  useEffect(() => {
    if (!gameId) return;
    const ws = api.openGameSocket(gameId, view);
    ws.onmessage = (ev) => {
      const payload = JSON.parse(ev.data) as GameView;
      setState(payload.state);
    };
    return () => ws.close();
  }, [gameId, view]);

  const newGame = () => run(() => api.createGame(view));

  return (
    <div className="app">
      <header className="topbar">
        <h1>Codenames</h1>
        <div className="controls">
          <button onClick={newGame}>New Game</button>
          <ViewToggle view={view} onChange={setView} />
        </div>
      </header>

      {error && <div className="error">⚠ {error}</div>}

      {!state ? (
        <p className="hint">
          Click <strong>New Game</strong> to start.
        </p>
      ) : (
        <>
          <StatusBar state={state} />
          {state.phase === "await_clue" && !state.winner && (
            <ClueForm
              team={state.current_team}
              onSubmit={(w, n) => run(() => api.giveClue(gameId!, view, w, n))}
            />
          )}
          <Board
            state={state}
            view={view}
            onGuess={(word) => run(() => api.makeGuess(gameId!, view, word))}
          />
          {state.phase === "await_guess" && state.guesses_made >= 1 && !state.winner && (
            <button className="pass" onClick={() => run(() => api.passTurn(gameId!, view))}>
              Pass turn (end guessing)
            </button>
          )}
        </>
      )}
    </div>
  );
}

function ViewToggle({ view, onChange }: { view: ViewName; onChange: (v: ViewName) => void }) {
  return (
    <div className="view-toggle">
      {(["spymaster", "operative"] as ViewName[]).map((v) => (
        <button key={v} className={view === v ? "active" : ""} onClick={() => onChange(v)}>
          {v}
        </button>
      ))}
    </div>
  );
}

function StatusBar({ state }: { state: GameState }) {
  if (state.winner) {
    return (
      <div className={`status winner-${state.winner}`}>🏆 {state.winner.toUpperCase()} wins!</div>
    );
  }
  const clue = state.current_clue;
  const remaining =
    state.guesses_allowed === null ? "∞" : Math.max(0, state.guesses_allowed - state.guesses_made);
  return (
    <div className={`status turn-${state.current_team}`}>
      <span className="tag">{state.current_team.toUpperCase()}'s turn</span>
      <span>
        {state.phase === "await_clue"
          ? "waiting for clue"
          : clue
            ? `clue: “${clue.word}” ${clue.number} · guesses left: ${remaining}`
            : "guessing"}
      </span>
      <span className="score">
        🔴 {state.red_remaining} &nbsp; 🔵 {state.blue_remaining}
      </span>
    </div>
  );
}

function ClueForm({
  onSubmit,
  team,
}: {
  onSubmit: (word: string, n: number) => void;
  team: string;
}) {
  const [word, setWord] = useState("");
  const [number, setNumber] = useState(1);
  return (
    <form
      className="clue-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (word.trim()) onSubmit(word.trim(), number);
        setWord("");
      }}
    >
      <span className="tag">{team} spymaster</span>
      <input
        placeholder="clue word"
        value={word}
        onChange={(e) => setWord(e.target.value)}
        autoFocus
      />
      <input
        type="number"
        min={0}
        max={9}
        value={number}
        onChange={(e) => setNumber(Number(e.target.value))}
      />
      <button type="submit">Give clue</button>
    </form>
  );
}

function Board({
  state,
  view,
  onGuess,
}: {
  state: GameState;
  view: ViewName;
  onGuess: (word: string) => void;
}) {
  const canGuess = state.phase === "await_guess" && !state.winner;
  return (
    <div className="board">
      {state.cards.map((card) => (
        <CardTile
          key={card.word}
          card={card}
          spymaster={view === "spymaster"}
          clickable={canGuess && !card.revealed}
          onClick={() => onGuess(card.word)}
        />
      ))}
    </div>
  );
}

function CardTile({
  card,
  spymaster,
  clickable,
  onClick,
}: {
  card: CardState;
  spymaster: boolean;
  clickable: boolean;
  onClick: () => void;
}) {
  const classes = ["card"];
  if (card.revealed) {
    classes.push("revealed", `type-${card.type}`);
  } else if (spymaster && card.type) {
    classes.push("hint", `hint-${card.type}`); // spymaster sees hidden colours as a tint
  }
  if (clickable) classes.push("clickable");
  return (
    <button className={classes.join(" ")} disabled={!clickable} onClick={onClick}>
      {card.word}
    </button>
  );
}
