"""
Weekly data fetch for the survivor pool.

Typical use:
    python scripts/fetch.py --fpi --odds --public   # the weekly pull
    python scripts/fetch.py                      # FPI only
    python scripts/fetch.py --all                # season setup (adds schedule + teams)
    python scripts/fetch.py --odds --detail 5-8  # moneylines for a planning window

FPI is the piece that must not be missed: ESPN serves only current ratings, so
an unfetched week is gone for good.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from survivor_picks.espn import EspnError, safe_relpath, season_context
from survivor_picks.fpi import fetch_fpi, save_fpi_snapshot
from survivor_picks.odds import (
    enrich_with_details,
    fetch_season_lines,
    parse_week_arg,
    save_odds,
)
from survivor_picks.public import (
    cross_check,
    fetch_public_picks,
    save_public_picks,
)
from survivor_picks.schedule import fetch_schedule, save_schedule, validate_schedule
from survivor_picks.teams import fetch_teams, save_teams

RULE = "=" * 70


def banner(text: str) -> None:
    print(f"\n{RULE}\n{text}\n{RULE}")


class Context:
    """
    Lazily resolved season/week, shared across tasks in one run.

    Several tasks need to know the current season and week. Resolving it once
    and caching keeps `--all` from making the same calendar lookup three times.
    """

    def __init__(self, season_override: int = None) -> None:
        self._override = season_override
        self._resolved = None

    def _resolve(self) -> dict:
        if self._resolved is None:
            self._resolved = season_context()
        return self._resolved

    @property
    def season(self) -> int:
        return self._override or self._resolve()["season"]

    @property
    def week(self) -> int:
        return self._resolve()["week"]


def run_teams(_args: argparse.Namespace, _ctx: Context) -> None:
    banner("FETCHING TEAM REFERENCE")
    rows = fetch_teams()
    path = save_teams(rows)
    print(f"   parsed {len(rows)} teams")
    print(f"   [OK] wrote {safe_relpath(path)}")


def run_schedule(_args: argparse.Namespace, ctx: Context) -> None:
    banner(f"FETCHING {ctx.season} SCHEDULE")
    games = fetch_schedule(ctx.season)
    print(f"\n   parsed {len(games)} games")

    warnings = validate_schedule(games)
    if warnings:
        print("\n   [warn] schedule validation flagged:")
        for warning in warnings:
            print(f"     - {warning}")
    else:
        print("   [OK] validation passed (272 games, 17 per team, no duplicates)")

    print(f"   [OK] wrote {safe_relpath(save_schedule(games))}")


def run_fpi(args: argparse.Namespace, _ctx: Context) -> None:
    banner("FETCHING FPI RATINGS")
    result = fetch_fpi(season=args.season)

    print(f"   season:       {result['season']}")
    print(f"   espn week:    {result['week']}")
    print(f"   last updated: {result['last_updated']}")
    print(f"   teams parsed: {len(result['teams'])}")

    print("\n   Top 5 by FPI:")
    for row in result["teams"][:5]:
        print(f"     {row['Team']:<24} {row['FPI']:>7.3f}   (rank {row['FPI_Rank']})")

    path = save_fpi_snapshot(result, week=args.week, force=args.force)
    if path:
        print(f"\n   [OK] wrote {safe_relpath(path)}")


def run_odds(args: argparse.Namespace, ctx: Context) -> None:
    weeks = parse_week_arg(args.weeks, ctx.week) if args.weeks else None
    banner(f"FETCHING {ctx.season} ODDS" + (f" (weeks {weeks})" if weeks else " (full season)"))

    rows = fetch_season_lines(ctx.season, weeks)
    print(f"\n   parsed {len(rows)} games")

    # Detail defaults: follow --weeks when the run is already narrowed to
    # specific weeks (asking for a week implies wanting its moneylines), and
    # otherwise just the current week, so the common full-season refresh stays
    # cheap. --no-detail opts out either way.
    if args.no_detail:
        detail_weeks = []
    elif args.detail:
        detail_weeks = parse_week_arg(args.detail, ctx.week)
    elif weeks:
        detail_weeks = weeks
    else:
        detail_weeks = [ctx.week] if ctx.week else []

    targets = [r for r in rows if r["WeekNum"] in detail_weeks]
    if targets:
        print(f"   detail pass on weeks {detail_weeks} ({len(targets)} games)")
        enrich_with_details(targets, workers=args.workers)
    elif detail_weeks:
        print(f"   [info] no fetched games fall in detail weeks {detail_weeks}")
    else:
        print("   [info] skipping detail pass (no moneyline / predictor)")

    history, week_files = save_odds(rows)
    print(f"\n   [OK] appended {len(rows)} rows to {history.name}")
    print(f"   [OK] rebuilt {len(week_files)} per-week file(s) in data/input/odds/")

    priced = sum(1 for r in rows if r["Spread_Home"] is not None)
    with_ml = sum(1 for r in rows if r["Home_ML"] is not None)
    print(f"   this pull: spread {priced}/{len(rows)}, moneyline {with_ml}/{len(rows)}")


def run_public(_args: argparse.Namespace, ctx: Context) -> None:
    banner("FETCHING PUBLIC PICK PERCENTAGES")
    week, rows = fetch_public_picks()
    print(f"   source reports week {week}, {len(rows)} teams")

    ranked = sorted(rows, key=lambda r: -(r["Pick_Pct"] or 0))
    print("\n   Most-picked teams:")
    for row in ranked[:5]:
        print(f"     {row['Team']:<4} {(row['Pick_Pct'] or 0) * 100:>5.1f}% of the field")

    # Compare their win probabilities against our devigged moneylines.
    try:
        our = _our_probs(ctx.season, week)
        for warning in cross_check(rows, our):
            print(f"   [warn] {warning}")
        if our:
            print(f"   cross-checked against {len(our)} of our own priced teams")
    except Exception as exc:  # noqa: BLE001 - a failed check must not lose the scrape
        print(f"   [warn] could not cross-check against our odds: {exc}")

    history, week_file = save_public_picks(week, rows, ctx.season)
    print(f"\n   [OK] appended {len(rows)} rows to {history.name}")
    print(f"   [OK] wrote {safe_relpath(week_file)}")


def _our_probs(season: int, week: int) -> dict:
    """Our devigged win probabilities for a week, keyed by team abbreviation."""
    import csv

    from survivor_picks.espn import INPUT_DIR

    path = INPUT_DIR / "odds" / f"week{week}_odds.csv"
    if not path.exists():
        return {}

    mapping = INPUT_DIR / "abbreviation_mapping.csv"
    if not mapping.exists():
        return {}
    with mapping.open(encoding="utf-8") as handle:
        abbr = {r["team_name"]: r["team_abbreviation"].upper() for r in csv.DictReader(handle)}

    out = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not row["Home_Win_Prob"]:
                continue
            out[abbr.get(row["Home"], row["Home"])] = float(row["Home_Win_Prob"])
            out[abbr.get(row["Away"], row["Away"])] = float(row["Away_Win_Prob"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch NFL survivor pool data from ESPN.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--fpi", action="store_true", help="fetch FPI ratings (default)")
    parser.add_argument("--odds", action="store_true", help="fetch betting lines + ESPN win projections")
    parser.add_argument("--public", action="store_true", help="fetch public pick percentages")
    parser.add_argument("--schedule", action="store_true", help="fetch the season schedule")
    parser.add_argument("--teams", action="store_true", help="fetch the team abbreviation mapping")
    parser.add_argument("--all", action="store_true", help="fetch everything (season setup)")
    parser.add_argument(
        "--weeks",
        help='odds weeks for the cheap pass: "5", "5,7", "5-8", "rest", "all" (default: all)',
    )
    parser.add_argument(
        "--detail",
        help="weeks to also pull moneyline + predictor for (default: current week only)",
    )
    parser.add_argument("--no-detail", action="store_true", help="skip the per-event detail pass")
    parser.add_argument(
        "--workers", type=int, default=8, help="threads for the detail pass (default: 8)"
    )
    parser.add_argument("--season", type=int, help="season year (default: ESPN's current)")
    parser.add_argument("--week", type=int, help="label the FPI snapshot with this week number")
    parser.add_argument("--force", action="store_true", help="overwrite an existing FPI snapshot")
    args = parser.parse_args()

    if args.all:
        tasks = [run_teams, run_schedule, run_fpi, run_odds, run_public]
    else:
        tasks = []
        if args.teams:
            tasks.append(run_teams)
        if args.schedule:
            tasks.append(run_schedule)
        if args.odds:
            tasks.append(run_odds)
        if args.public:
            tasks.append(run_public)
        if args.fpi or not tasks:
            tasks.append(run_fpi)

    context = Context(args.season)

    try:
        for task in tasks:
            task(args, context)
    except ValueError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 2
    except EspnError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n[ABORTED]", file=sys.stderr)
        return 130

    print(f"\n{RULE}\n[DONE]\n{RULE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
