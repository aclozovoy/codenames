import { useCallback, useEffect, useState } from "react";
import "./App.css";
import * as api from "./api";
import type {
  CardState,
  Control,
  GameConfig,
  GameState,
  GameView,
  ModelInfo,
  MoveRecord,
  Role,
  SeatKey,
  TeamName,
  Usage,
  ViewName,
} from "./types";

type Mode = "ai" | "single" | "two";

function buildSeats(mode: Mode, team: TeamName, role: Role): Partial<Record<SeatKey, Control>> {
  if (mode === "ai") return {};
  if (mode === "single") return { [`${team}_${role}` as SeatKey]: "human" };
  return { [`red_${role}` as SeatKey]: "human", [`blue_${role}` as SeatKey]: "human" };
}

function viewFor(mode: Mode, role: Role): ViewName {
  return mode === "ai" ? "spymaster" : role;
}

export default function App() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [view, setView] = useState<ViewName>("spymaster");
  const [gameId, setGameId] = useState<string | null>(null);
  const [state, setState] = useState<GameState | null>(null);
  const [moves, setMoves] = useState<MoveRecord[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [config, setConfig] = useState<GameConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listModels().then(setModels).catch(() => setModels([]));
  }, []);

  const applyView = useCallback((v: GameView) => {
    setGameId(v.game_id);
    setState(v.state);
    setMoves(v.moves ?? []);
    setUsage(v.usage ?? null);
    setConfig(v.config ?? null);
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

  useEffect(() => {
    if (!gameId) return;
    const ws = api.openGameSocket(gameId, view);
    ws.onmessage = (ev) => {
      const payload = JSON.parse(ev.data) as GameView;
      setState(payload.state);
      setMoves(payload.moves ?? []);
      setUsage(payload.usage ?? null);
      setConfig(payload.config ?? null);
    };
    return () => ws.close();
  }, [gameId, view]);

  const startGame = (opts: api.CreateOptions, chosenView: ViewName) => {
    setView(chosenView);
    run(() => api.createGame(chosenView, opts));
  };

  const backToSetup = () => {
    setGameId(null);
    setState(null);
    setConfig(null);
    setMoves([]);
    setUsage(null);
  };

  // Seat-aware derived flags.
  const seats = config?.seats;
  const currentSeat = config?.current_seat ?? null;
  const currentControl: Control | undefined =
    seats && currentSeat ? seats[currentSeat] : undefined;
  const winner = state?.winner ?? null;
  const humanTurn = !!state && !winner && currentControl === "human";
  const aiTurn = !!state && !winner && !!config?.current_is_ai;
  const hasHuman = seats ? Object.values(seats).includes("human") : false;
  // A human operative must not see the spymaster's reasoning — it names the
  // target words. Hide it while such a game is in progress; reveal it at the end.
  const hasHumanOperative =
    !!seats && (seats.red_operative === "human" || seats.blue_operative === "human");
  const hideReasoning = hasHumanOperative && !winner;

  return (
    <div className="app">
      <header className="topbar">
        <h1>Vibecodenames</h1>
        <div className="controls">
          {state && (
            <button onClick={backToSetup} disabled={busy}>
              New Game
            </button>
          )}
          {state && !hasHuman && <ViewToggle view={view} onChange={setView} />}
        </div>
      </header>

      {error && <div className="error">⚠ {error}</div>}

      {!state ? (
        <Setup models={models} busy={busy} onStart={startGame} />
      ) : (
        <div className="layout">
          <main>
            <StatusBar state={state} />

            {aiTurn && (
              <div className="ai-bar">
                <button
                  className="ai-move"
                  disabled={busy}
                  onClick={() => run(() => api.llmMove(gameId!, view))}
                >
                  {busy ? "🤖 thinking…" : `🤖 AI move — ${currentSeat?.replace("_", " ")}`}
                </button>
                <span className="ai-hint">
                  {state.phase === "await_clue"
                    ? "the AI spymaster will give a clue"
                    : "the AI operative will make one guess"}
                </span>
              </div>
            )}

            {state.phase === "await_clue" && humanTurn && (
              <ClueForm
                team={state.current_team}
                busy={busy}
                onSubmit={(w, n) => run(() => api.giveClue(gameId!, view, w, n))}
              />
            )}
            <Board
              state={state}
              view={view}
              canGuess={humanTurn && state.phase === "await_guess"}
              busy={busy}
              onGuess={(word) => run(() => api.makeGuess(gameId!, view, word))}
            />
            {humanTurn && state.phase === "await_guess" && state.guesses_made >= 1 && (
              <button
                className="pass"
                disabled={busy}
                onClick={() => run(() => api.passTurn(gameId!, view))}
              >
                Pass turn (end guessing)
              </button>
            )}
          </main>

          <aside className="sidebar">
            <ConfigSummary config={config} models={models} />
            <UsageBar usage={usage} />
            {hideReasoning ? <ReasoningHidden /> : <Thoughts moves={moves} />}
          </aside>
        </div>
      )}
    </div>
  );
}

// -- setup screen --------------------------------------------------------------

function Setup({
  models,
  busy,
  onStart,
}: {
  models: ModelInfo[];
  busy: boolean;
  onStart: (opts: api.CreateOptions, view: ViewName) => void;
}) {
  const [mode, setMode] = useState<Mode>("ai");
  const [team, setTeam] = useState<TeamName>("red");
  const [role, setRole] = useState<Role>("spymaster");
  const [redModel, setRedModel] = useState("haiku");
  const [blueModel, setBlueModel] = useState("haiku");

  const start = () => {
    onStart(
      {
        seats: buildSeats(mode, team, role),
        models: { red: redModel, blue: blueModel },
      },
      viewFor(mode, role),
    );
  };

  return (
    <div className="setup">
      <h2>New game</h2>

      <label className="setup-label">Mode</label>
      <div className="chips">
        {(
          [
            ["ai", "AI only"],
            ["single", "Single player"],
            ["two", "Two player (shared screen)"],
          ] as [Mode, string][]
        ).map(([m, label]) => (
          <button key={m} className={mode === m ? "chip active" : "chip"} onClick={() => setMode(m)}>
            {label}
          </button>
        ))}
      </div>

      {mode === "single" && (
        <>
          <label className="setup-label">Your team</label>
          <div className="chips">
            {(["red", "blue"] as TeamName[]).map((t) => (
              <button
                key={t}
                className={team === t ? `chip active team-${t}` : "chip"}
                onClick={() => setTeam(t)}
              >
                {t}
              </button>
            ))}
          </div>
        </>
      )}

      {mode !== "ai" && (
        <>
          <label className="setup-label">
            {mode === "two" ? "Both humans play as" : "Your role"}
          </label>
          <div className="chips">
            {(["spymaster", "operative"] as Role[]).map((r) => (
              <button
                key={r}
                className={role === r ? "chip active" : "chip"}
                onClick={() => setRole(r)}
              >
                {mode === "two" ? `both ${r}s` : r}
              </button>
            ))}
          </div>
        </>
      )}

      <label className="setup-label">AI models</label>
      <div className="model-picks">
        <ModelSelect label="🔴 Red AI" value={redModel} models={models} onChange={setRedModel} />
        <ModelSelect label="🔵 Blue AI" value={blueModel} models={models} onChange={setBlueModel} />
      </div>

      <button className="start" onClick={start} disabled={busy}>
        {busy ? "Starting…" : "Start game"}
      </button>
      <p className="setup-note">{describe(mode, team, role)}</p>
    </div>
  );
}

function describe(mode: Mode, team: TeamName, role: Role): string {
  if (mode === "ai") return "Both teams are AI. Step through with the AI move button and watch the reasoning.";
  if (mode === "single")
    return `You play the ${team} ${role}; AI fills the other three seats. You'll see the ${viewFor(mode, role)} view.`;
  return `Two humans: red ${role} and blue ${role} (shared ${role} view). AI plays the ${role === "spymaster" ? "operatives" : "spymasters"}.`;
}

function ModelSelect({
  label,
  value,
  models,
  onChange,
}: {
  label: string;
  value: string;
  models: ModelInfo[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="model-select">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        {models.map((m) => (
          <option key={m.key} value={m.key}>
            {m.label} (${m.input_usd_per_mtok}/${m.output_usd_per_mtok} per 1M)
          </option>
        ))}
      </select>
    </label>
  );
}

// -- game components -----------------------------------------------------------

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
      <span className="tag">{team} spymaster (you)</span>
      <input placeholder="clue word" value={word} onChange={(e) => setWord(e.target.value)} />
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
  canGuess,
  busy,
  onGuess,
}: {
  state: GameState;
  view: ViewName;
  canGuess: boolean;
  busy: boolean;
  onGuess: (word: string) => void;
}) {
  const clickable = canGuess && !state.winner && !busy;
  return (
    <div className="board">
      {state.cards.map((card) => (
        <CardTile
          key={card.word}
          card={card}
          spymaster={view === "spymaster"}
          clickable={clickable && !card.revealed}
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

function ConfigSummary({ config, models }: { config: GameConfig | null; models: ModelInfo[] }) {
  if (!config) return null;
  const label = (key: string) => models.find((m) => m.key === key)?.label ?? key;
  const seatLine = (seat: SeatKey) =>
    config.seats[seat] === "human" ? "you" : `AI (${label(config.models[seat.startsWith("red") ? "red" : "blue"])})`;
  return (
    <div className="config">
      <div className="config-row">
        <span className="dot red" /> spymaster: {seatLine("red_spymaster")} · operative:{" "}
        {seatLine("red_operative")}
      </div>
      <div className="config-row">
        <span className="dot blue" /> spymaster: {seatLine("blue_spymaster")} · operative:{" "}
        {seatLine("blue_operative")}
      </div>
    </div>
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

function ReasoningHidden() {
  return (
    <div className="thoughts">
      <h2>Model reasoning</h2>
      <p className="hint">
        🙈 Hidden while you're guessing — the spymaster's reasoning names the target
        words. It'll appear here once the game ends.
      </p>
    </div>
  );
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
