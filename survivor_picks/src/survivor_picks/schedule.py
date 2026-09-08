"""
Fetch the full NFL regular season schedule.

Unlike FPI, the schedule is stable - one fetch per season covers all 18 weeks,
with a refresh only needed if a game is flexed or relocated.

TeamA/TeamB match the legacy picksim column order (TeamA = away, TeamB = home).
Explicit Away/Home/Neutral columns follow so nothing downstream has to rely on
that convention being remembered correctly.
"""

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from .espn import (
    GAMES_PER_TEAM,
    INPUT_DIR,
    NFL_TEAMS,
    REGULAR_SEASON_WEEKS,
    SEASON_GAMES,
    fetch_scoreboard,
    parse_competitors,
    require,
)

SCHEDULE_PATH = INPUT_DIR / "weekly_matchups.csv"

COLUMNS = [
    "Week",
    "TeamA",
    "TeamB",
    "WeekNum",
    "Away",
    "Home",
    "NeutralSite",
    "Kickoff_UTC",
    "Season",
]


def fetch_schedule(season: int, weeks: int = REGULAR_SEASON_WEEKS) -> List[Dict[str, Any]]:
    """
    Pull every regular season game, one request per week.

    Args:
        season: Season year (e.g. 2026).
        weeks: Number of regular season weeks.

    Returns:
        List of game row dicts, ordered by week.
    """
    games: List[Dict[str, Any]] = []

    for week in range(1, weeks + 1):
        events = fetch_scoreboard(season, week)
        if not events:
            print(f"   [warn] week {week}: no games returned")
            continue

        for event in events:
            game = _parse_event(event, season, week)
            if game:
                games.append(game)

        print(f"   week {week:>2}: {len(events)} games")

    require(bool(games), "no games parsed for the entire season")
    return games


def _parse_event(event: Dict[str, Any], season: int, week: int) -> Optional[Dict[str, Any]]:
    """Extract one game's teams and venue info, or None if the shape is unusable."""
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    competition = competitions[0]

    sides = parse_competitors(competition)
    if not sides:
        print(f"   [warn] week {week}: could not resolve home/away for event {event.get('id')}")
        return None

    return {
        "Week": f"Week {week}",
        "TeamA": sides["away"],
        "TeamB": sides["home"],
        "WeekNum": week,
        "Away": sides["away"],
        "Home": sides["home"],
        "NeutralSite": bool(competition.get("neutralSite")),
        "Kickoff_UTC": event.get("date"),
        "Season": season,
    }


def save_schedule(games: List[Dict[str, Any]], path: Path = SCHEDULE_PATH) -> Path:
    """Write the schedule to CSV, replacing any previous version."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(games)
    return path


def validate_schedule(games: List[Dict[str, Any]]) -> List[str]:
    """
    Sanity-check the schedule against known NFL structure.

    Returns a list of human-readable warnings; empty means everything checks out.
    A modern 18-week season is 272 games with each team playing 17 and taking one
    bye, so anything else is worth surfacing before it reaches the pick model.
    """
    warnings: List[str] = []

    if len(games) != SEASON_GAMES:
        warnings.append(f"expected {SEASON_GAMES} games, got {len(games)}")

    appearances: Dict[str, int] = {}
    per_week: Dict[int, Dict[str, int]] = {}
    for game in games:
        week_counts = per_week.setdefault(game["WeekNum"], {})
        for side in ("Away", "Home"):
            team = game[side]
            appearances[team] = appearances.get(team, 0) + 1
            week_counts[team] = week_counts.get(team, 0) + 1

    if len(appearances) != NFL_TEAMS:
        warnings.append(f"expected {NFL_TEAMS} distinct teams, got {len(appearances)}")

    for team, count in sorted(appearances.items()):
        if count != GAMES_PER_TEAM:
            warnings.append(f"{team} plays {count} games (expected {GAMES_PER_TEAM})")

    for week, counts in sorted(per_week.items()):
        for team, count in counts.items():
            if count > 1:
                warnings.append(f"week {week}: {team} appears {count} times")

    return warnings
