"""
Build the dataset the interactive grid renders.

Reads the fetched per-week odds and emits data/output/grid_data.json, then
injects it into grid.html so the page ships with its data embedded.

Run after every fetch, or the published board shows stale lines:

    python scripts/fetch.py --odds --weeks all
    python scripts/build_grid_data.py
"""

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from survivor_picks.espn import INPUT_DIR, PROJECT_ROOT, REGULAR_SEASON_WEEKS, safe_relpath

OUTPUT = PROJECT_ROOT / "data" / "output" / "grid_data.json"
PAGE = PROJECT_ROOT / "grid.html"
PLACEHOLDER = "/*__DATA__*/"


def load_abbreviations() -> dict:
    path = INPUT_DIR / "abbreviation_mapping.csv"
    if not path.exists():
        raise SystemExit(f"missing {safe_relpath(path)} - run: python scripts/fetch.py --teams")
    with path.open(encoding="utf-8") as handle:
        return {r["team_name"]: r["team_abbreviation"].upper() for r in csv.DictReader(handle)}


def build() -> dict:
    abbr = load_abbreviations()
    teams, games, weeks_seen = set(), {}, set()
    missing = 0
    captured = ""

    for week in range(1, REGULAR_SEASON_WEEKS + 1):
        path = INPUT_DIR / "odds" / f"week{week}_odds.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                home, away = row["Home"], row["Away"]
                teams.update([home, away])
                weeks_seen.add(week)
                captured = max(captured, row.get("Fetched_At_UTC") or "")

                if not row["Home_Win_Prob"]:
                    # Cheap pass only - no moneyline yet for this game.
                    missing += 1
                    continue

                home_p = float(row["Home_Win_Prob"])
                away_p = float(row["Away_Win_Prob"])
                espn = float(row["ESPN_Home_Win_Prob"]) / 100 if row["ESPN_Home_Win_Prob"] else None
                spread = float(row["Spread_Home"]) if row["Spread_Home"] else None

                for team, opp, prob, is_home in (
                    (home, away, home_p, True),
                    (away, home, away_p, False),
                ):
                    games.setdefault(abbr[team], {})[str(week)] = {
                        "p": round(prob, 4),
                        "opp": abbr[opp],
                        "h": is_home,
                        "sp": spread if is_home else (None if spread is None else -spread),
                        "e": None if espn is None else round(espn if is_home else 1 - espn, 4),
                    }

    if not games:
        raise SystemExit("no priced games found - run: python scripts/fetch.py --odds --weeks all")

    cells = sum(len(v) for v in games.values())
    print(f"   teams {len(teams)} · weeks {len(weeks_seen)} · team-week cells {cells}")
    if missing:
        print(f"   [warn] {missing} games have no moneyline yet - run the detail pass:")
        print(f"          python scripts/fetch.py --odds --weeks all")

    return {
        "season": 2026,
        "weeks": sorted(weeks_seen),
        "teams": [{"n": t, "a": abbr[t]} for t in sorted(teams)],
        "games": games,
        "captured": captured[:10],
    }


def inject(data: dict) -> None:
    """Embed the dataset in grid.html, replacing whatever it currently carries."""
    if not PAGE.exists():
        print(f"   [warn] {safe_relpath(PAGE)} not found - JSON written, page not updated")
        return

    html = PAGE.read_text(encoding="utf-8")
    payload = json.dumps(data, separators=(",", ":"))

    if PLACEHOLDER in html:
        html = html.replace(PLACEHOLDER + "{}", payload)
    else:
        # Already injected once; swap the previous payload out.
        start = html.index("const DATA = ") + len("const DATA = ")
        end = html.index(";\n", start)
        html = html[:start] + payload + html[end:]

    PAGE.write_text(html, encoding="utf-8")
    print(f"   [OK] embedded into {safe_relpath(PAGE)}")


def add_recommendations(data: dict) -> dict:
    """
    Solve each entry's model and embed the recommended path in the board.

    This is what puts the recommendation in front of you on the page itself,
    rather than only in the output of scripts/recommend.py. Crazy3 is omitted
    deliberately - it is picked by hand.
    """
    OUTPUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")

    try:
        from survivor_picks.model import (
            load_board,
            load_my_picks,
            leverage_values,
            load_observed_shares,
            solve_crazy,
            solve_dustin,
        )
    except ImportError as exc:
        print(f"   [warn] no recommendations embedded ({exc}); pip install -r requirements.txt")
        return data

    board = load_board()
    mine = load_my_picks()
    recommend = {}

    for entry, solver in (
        ("Dustin", solve_dustin),
        ("Crazy1", solve_crazy),
        ("Crazy2", solve_crazy),
    ):
        used = set(mine.get(entry, {}).values())
        locked = dict(mine.get(entry, {}))
        try:
            if entry == "Crazy2":
                week_values = {}
                for week in board.weeks:
                    shares = load_observed_shares(week)
                    if shares:
                        week_values[week] = leverage_values(board, week, shares)
                path = solve_crazy(board, used=used, locked=locked, week_values=week_values or None)
            elif entry == "Crazy1":
                path = solve_crazy(board, used=used, locked=locked)
            else:
                path = solve_dustin(board, used=used, locked=locked)
            recommend[entry] = {str(w): t for w, t in path.items()}
        except Exception as exc:  # noqa: BLE001 - a failed solve must not block the board
            print(f"   [warn] could not solve {entry}: {exc}")

    data["recommend"] = recommend
    weeks_done = ", ".join(
        f"{e}:{recommend[e].get(str(board.weeks[0]), '?')}" for e in recommend
    )
    print(f"   [OK] embedded recommendations ({weeks_done} in week {board.weeks[0]})")
    return data


def main() -> int:
    print("=" * 70)
    print("BUILDING GRID DATA")
    print("=" * 70)
    data = build()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    data = add_recommendations(data)
    OUTPUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"   [OK] wrote {safe_relpath(OUTPUT)} ({OUTPUT.stat().st_size / 1024:.0f} KB)")

    inject(data)
    print("\nRepublish grid.html to push this to the live board.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
