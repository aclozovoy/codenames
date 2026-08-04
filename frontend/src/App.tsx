import { useCallback, useEffect, useState } from "react";
import "./App.css";
import * as api from "./api";
import type { CardState, GameState, GameView, MoveRecord, Usage, ViewName } from "./types";

export default function App() {
  const [view, setView] = useState<ViewName>("spymaster");
  const [gameId, setGameId] = useState<string | null>(null);
  const [state, setState] = useState<GameState | null>(null);
  const [moves, setMoves] = useState<MoveRecord[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const applyView = useCallback((v: GameView) => {
    setGameId(v.game_id);
    setState(v.state);
    setMoves(v.moves ?? []);
    setUsage(v.usage ?? null);
  }, []);

  const run = useCallback(
    async (fn: () => Promise<GameView>) => {
      setError(null);
      setBusy(true);
      try {
        applyView(await fn());
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
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
      setMoves(payload.moves ?? []);
      setUsage(payload.usage ?? null);
    };
    return () => ws.close();
  }, [gameId, view]);

  const newGame = () => run(() => api.createGame(view));

  const aiSeat =
    state && state.phase === "await_clue"
      ? `${state.current_team} spymaster`
      : state
        ? `${state.current_team} operative`
        : "";

  return (
    <div className="app">
      <header className="topbar">
        <h1>Codenames</h1>
        <div className="controls">
          <button onClick={newGame} disabled={busy}>
            New Game
          </button>
          <ViewToggle view={view} onChange={setView} />
        </div>
      </header>

      {error && <div className="error">⚠ {error}</div>}

      {!state ? (
        <p className="hint">
          Click <strong>New Game</strong> to start.
        </p>
      ) : (
        <div className="layout">
          <main>
            <StatusBar state={state} />

            {!state.winner && (
              <div className="ai-bar">
                <button
                  className="ai-move"
                  disabled={busy}
                  onClick={() => run(() => api.llmMove(gameId!, view))}
                >
                  {busy ? "🤖 thinking…" : `🤖 AI move — ${aiSeat}`}
                </button>
                <span className="ai-hint">
                  {state.phase === "await_clue"
                    ? "the spymaster will give a clue"
                    : "the operative will make one guess"}
                </span>
              </div>
            )}

            {state.phase === "await_clue" && !state.winner && (
              <ClueForm
                team={state.current_team}
                busy={busy}
                onSubmit={(w, n) => run(() => api.giveClue(gameId!, view, w, n))}
              />
            )}
            <Board
              state={state}
              view={view}
              busy={busy}
              onGuess={(word) => run(() => api.makeGuess(gameId!, view, word))}
            />
            {state.phase === "await_guess" && state.guesses_made >= 1 && !state.winner && (
              <button className="pass" disabled={busy} onClick={() => run(() => api.passTurn(gameId!, view))}>
                Pass turn (end guessing)
              </button>
            )}
          </main>

          <aside className="sidebar">
            <UsageBar usage={usage} />
            <Thoughts moves={moves} />
          </aside>
        </div>
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
  busy,
}: {
  onSubmit: (word: string, n: number) => void;
  team: string;
  busy: boolean;
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
        placeholder="clue word (or use AI move)"
        value={word}
        onChange={(e) => setWord(e.target.value)}
      />
      <input
        type="number"
        min={0}
        max={9}
        value={number}
        onChange={(e) => setNumber(Number(e.target.value))}
      />
      <button type="submit" disabled={busy}>
        Give clue
      </button>
    </form>
  );
}

function Board({
  state,
  view,
  busy,
  onGuess,
}: {
  state: GameState;
  view: ViewName;
  busy: boolean;
  onGuess: (word: string) => void;
}) {
  const canGuess = state.phase === "await_guess" && !state.winner && !busy;
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
    classes.push("hint", `hint-${card.type}`);
  }
  if (clickable) classes.push("clickable");
  return (
    <button className={classes.join(" ")} disabled={!clickable} onClick={onClick}>
      {card.word}
    </button>
  );
}

function UsageBar({ usage }: { usage: Usage | null }) {
  if (!usage || usage.calls === 0) return null;
  const budget = usage.budget_usd ? ` / $${usage.budget_usd.toFixed(2)} budget` : "";
  return (
    <div className="usage">
      💸 ${usage.usd.toFixed(4)}
      {budget} · {usage.calls} calls · {usage.input_tokens + usage.output_tokens} tokens
    </div>
  );
}

function moveTitle(m: MoveRecord): string {
  if (m.action === "clue") return `clue “${m.word}” ${m.number}`;
  if (m.action === "guess") return `guessed ${m.word} → ${m.outcome}`;
  if (m.action === "pass") return "passed";
  return "wanted to pass (must guess first)";
}

function Thoughts({ moves }: { moves: MoveRecord[] }) {
  return (
    <div className="thoughts">
      <h2>Model reasoning</h2>
      {moves.length === 0 ? (
        <p className="hint">Trigger an AI move to see what the model is thinking.</p>
      ) : (
        <ol className="thought-log">
          {moves
            .map((m, i) => ({ m, i }))
            .reverse()
            .map(({ m, i }) => {
              const team = m.seat.startsWith("red") ? "red" : "blue";
              return (
                <li key={i} className={`thought seat-${team}`}>
                  <div className="thought-head">
                    <span className="thought-seat">{m.seat}</span>
                    <span className={`thought-outcome outcome-${m.outcome ?? m.action}`}>
                      {moveTitle(m)}
                    </span>
                  </div>
                  {m.reasoning && <p className="thought-body">{m.reasoning}</p>}
                </li>
              );
            })}
        </ol>
      )}
    </div>
  );
}
