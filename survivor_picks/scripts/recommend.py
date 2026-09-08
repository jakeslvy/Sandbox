"""
This week's recommended pick for every entry.

    python scripts/recommend.py              # current week, all four entries
    python scripts/recommend.py --week 3     # a specific week
    python scripts/recommend.py --path       # show each entry's full planned path

Reads picks already made from data/input/my_picks.csv (Entry,Week,Team) so the
solve respects teams you have already burned.

Each entry is a different game. Dustin's has no elimination and is scored on
streak plus total wins; Crazy is true survivor. They will disagree - that is
correct, not a bug.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from survivor_picks.espn import season_context
from survivor_picks.model import (
    ModelError,
    best_week18_team,
    evaluate,
    leverage_values,
    load_board,
    load_my_picks,
    load_observed_shares,
    solve_crazy,
    solve_dustin,
)

RULE = "=" * 74

ENTRIES = ["Dustin", "Crazy1", "Crazy2"]      # Crazy3 is picked by hand


def build_paths(board, my_picks, week):
    """Solve each entry's own objective, respecting what it has already used."""
    paths, notes = {}, {}

    used = set(my_picks.get("Dustin", {}).values())
    locked = {w: t for w, t in my_picks.get("Dustin", {}).items()}
    paths["Dustin"] = solve_dustin(board, used=used, locked=locked)
    notes["Dustin"] = "streak + total wins, no elimination"

    for entry in ("Crazy1", "Crazy2"):
        used = set(my_picks.get(entry, {}).values())
        locked = {w: t for w, t in my_picks.get(entry, {}).items()}
        reserve = best_week18_team(board, used)

        week_values = None
        if entry == "Crazy2":
            shares = load_observed_shares(week)
            if shares:
                week_values = {week: leverage_values(board, week, shares)}
                top = max(shares, key=shares.get)
                notes[entry] = (
                    f"survival + leverage on observed picks "
                    f"(field is {shares[top] * 100:.0f}% on {top})"
                )
            else:
                notes[entry] = (
                    f"survival only - NO observed pick data for week {week}; "
                    "run: python scripts/fetch.py --public"
                )
        else:
            notes.setdefault(entry, "survival to wk17, reserving " + reserve)

        paths[entry] = solve_crazy(board, used=used, locked=locked, week_values=week_values)
    return paths, notes


def manual_options(board, my_picks, week, avoid, count=5):
    """
    Crazy3 is picked by hand, so show the best available teams rather than one
    answer. Flags anything the other entries already hold, since doubling up
    means those entries die together.
    """
    used = set(my_picks.get("Crazy3", {}).values())
    j = board.week_index(week)
    ranked = sorted(
        (
            (board.P[i, j], board.teams[i])
            for i in range(len(board.teams))
            if board.P[i, j] > 0 and board.teams[i] not in used
        ),
        reverse=True,
    )
    return [(t, p, t in avoid) for p, t in ranked[:count]]


def main() -> int:
    parser = argparse.ArgumentParser(description="Recommended picks per entry.")
    parser.add_argument("--week", type=int, help="week to recommend for (default: current)")
    parser.add_argument("--path", action="store_true", help="show each entry's full planned path")
    args = parser.parse_args()

    try:
        board = load_board()
        week = args.week or season_context()["week"]
        if week not in board.weeks:
            raise ModelError(f"week {week} is not on the board")

        my_picks = load_my_picks()
        paths, notes = build_paths(board, my_picks, week)
    except ModelError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(RULE)
    print(f"WEEK {week} RECOMMENDATIONS   (lines captured {board.captured or 'unknown'})")
    print(RULE)

    print(f"\n{'entry':<9} {'pick':>5} {'win%':>7}  {'opponent':<12} basis")
    print("-" * 74)
    for entry in ENTRIES:
        path = paths[entry]
        if week not in path:
            print(f"{entry:<9} {'--':>5} {'':>7}  {'':<12} already picked / week not solved")
            continue
        team = path[week]
        prob = board.prob(team, week)
        print(f"{entry:<9} {team:>5} {prob * 100:>6.1f}%  "
              f"{board.matchup(team, week):<12} {notes[entry]}")

    crazy_picks = [paths[e][week] for e in ("Crazy1", "Crazy2") if week in paths[e]]
    if len(set(crazy_picks)) < len(crazy_picks):
        dupes = {t for t in crazy_picks if crazy_picks.count(t) > 1}
        print(
            f"\n   [!] Crazy entries share {', '.join(sorted(dupes))} this week - "
            "they would be eliminated together."
        )

    taken = {paths[e][week] for e in ENTRIES if week in paths[e]}
    print("\nCrazy3 (your pick) - best available:")
    for team, prob, clash in manual_options(board, my_picks, week, taken):
        flag = "   <- Crazy1/2 already here" if clash else ""
        print(f"   {team:>5} {prob * 100:>6.1f}%  {board.matchup(team, week):<12}{flag}")

    print(f"\n{'entry':<9} {'survive':>9} {'E[streak]':>10} {'E[wins]':>9} {'weakest week':>14}")
    print("-" * 74)
    for entry in ENTRIES:
        m = evaluate(board, paths[entry])
        weak = f"{m['weakest_prob'] * 100:.0f}% wk{m['weakest_week']}" if m["weakest_prob"] else "-"
        print(
            f"{entry:<9} {m['survival'] * 100:>8.2f}% {m['expected_streak']:>10.2f} "
            f"{m['expected_wins']:>9.2f} {weak:>14}"
        )

    if args.path:
        for entry in ENTRIES:
            path = paths[entry]
            print(f"\n{entry} full path:")
            line = "   "
            for w in sorted(path):
                line += f"wk{w}:{path[w]}({board.prob(path[w], w) * 100:.0f})  "
                if len(line) > 66:
                    print(line)
                    line = "   "
            if line.strip():
                print(line)

    print(
        "\nDustin's has no elimination (streak + total wins); Crazy is survivor. "
        "\nDisagreement between them is expected. Leverage applies only to weeks "
        "\nwith observed pick data - it cannot be modelled for future weeks."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
