"""Tournament CLI.

Examples:
    # Round-robin: every pair of the cheap models, 5 games each
    python -m codenames.tournament run --games 5

    # Just two models
    python -m codenames.tournament run --matchup nova-micro nova-lite --games 10

    # Analyse whatever has been recorded so far
    python -m codenames.tournament stats
"""

from __future__ import annotations

import argparse
import itertools
import os
import random

from ..players import MODELS
from .results import ResultsStore, head_to_head, win_rate_table
from .runner import play_game

DEFAULT_RESULTS = os.environ.get("CODENAMES_RESULTS", "results/games.jsonl")


def _print_stats(store: ResultsStore) -> None:
    from collections import Counter

    results = store.load()
    decided = [r for r in results if r.get("winner_model")]
    print(f"\n{len(results)} games recorded ({len(decided)} decided) in {store.path}")

    status = Counter(r.get("status", "?") for r in results)
    if status:
        print("  status: " + ", ".join(f"{k}={v}" for k, v in sorted(status.items())))
    ended = Counter(r.get("ended_by") for r in decided if r.get("ended_by"))
    if ended:
        print("  decided by: " + ", ".join(f"{k}={v}" for k, v in sorted(ended.items())))

    table = win_rate_table(results)
    if not table:
        print("No decided games yet.")
        return
    print("\nOverall win rates:")
    print(f"  {'model':<14}{'games':>6}{'wins':>6}{'win rate':>10}")
    for row in table:
        print(f"  {row['model']:<14}{row['games']:>6}{row['wins']:>6}{row['win_rate']:>10.1%}")

    print("\nHead-to-head (row model's win rate vs column):")
    h2h = head_to_head(results)
    models = sorted(h2h)
    print("  " + " " * 14 + "".join(f"{m[:10]:>12}" for m in models))
    for a in models:
        cells = []
        for b in models:
            if a == b:
                cells.append(f"{'—':>12}")
            elif b in h2h[a]:
                c = h2h[a][b]
                cells.append(f"{c['wins']}/{c['games']} {c['win_rate']:.0%}".rjust(12))
            else:
                cells.append(f"{'·':>12}")
        print(f"  {a:<14}" + "".join(cells))


def _run(args: argparse.Namespace) -> None:
    from ..players.bedrock import BedrockClient

    model_keys = [m.strip() for m in args.models.split(",")] if args.models else list(MODELS)
    for key in model_keys:
        if key not in MODELS:
            raise SystemExit(f"unknown model {key!r}; choices: {', '.join(MODELS)}")

    if args.matchup:
        pairings = [tuple(args.matchup)]
    else:
        pairings = list(itertools.combinations(model_keys, 2))
    if not pairings:
        raise SystemExit("need at least two models for a round-robin")

    client = BedrockClient(region=args.region)
    store = ResultsStore(args.results)
    rng = random.Random(args.seed)

    total = len(pairings) * args.games
    print(f"Playing {total} games ({len(pairings)} pairing(s) x {args.games}) -> {store.path}\n")

    played = 0
    spent = 0.0
    for m1, m2 in pairings:
        for i in range(args.games):
            # Alternate which model is red so the first-move edge is shared.
            red, blue = (m1, m2) if i % 2 == 0 else (m2, m1)
            seed = rng.randrange(1_000_000_000)
            result = play_game(client, red, blue, seed=seed)
            store.append(result)
            played += 1
            spent += result.cost_usd
            win = result.winner_model or f"({result.status})"
            print(
                f"[{played}/{total}] {red}(R) vs {blue}(B) seed={seed} -> "
                f"{win} {result.ended_by or ''} "
                f"[{result.turns}t, ${result.cost_usd:.4f}]"
            )
    print(f"\nDone. Spent ~${spent:.4f} on {played} games.")
    _print_stats(store)


def _stats(args: argparse.Namespace) -> None:
    _print_stats(ResultsStore(args.results))


def main() -> None:
    parser = argparse.ArgumentParser(prog="codenames.tournament")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="play AI-vs-AI games and record results")
    run.add_argument("--models", help="comma-separated model keys (default: all)")
    run.add_argument("--matchup", nargs=2, metavar=("RED", "BLUE"), help="a single pairing")
    run.add_argument("--games", type=int, default=3, help="games per pairing (default 3)")
    run.add_argument("--results", default=DEFAULT_RESULTS, help="JSONL output path")
    run.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    run.add_argument("--seed", type=int, default=None, help="seed for the game-seed sequence")
    run.set_defaults(func=_run)

    stats = sub.add_parser("stats", help="print win-rate tables from recorded results")
    stats.add_argument("--results", default=DEFAULT_RESULTS, help="JSONL input path")
    stats.set_defaults(func=_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
