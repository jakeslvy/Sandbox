"""
Fetch betting lines and ESPN's game-level win projections.

Unlike FPI, odds are *live* - a line pulled Tuesday and the same line pulled
Sunday morning are different numbers, and the later one is sharper. So odds are
stored as append-only observations keyed by fetch time rather than as one file
per week. Nothing is ever overwritten; re-fetching a week adds rows and gives
line movement for free.

Two fetch paths, because the data is split across two endpoints:

  cheap  - the scoreboard carries spread and over/under inline, so the whole
           season costs 18 requests (~7s).
  detail - moneyline and the predictor are per-event only, so a week costs
           ~32 requests (~1.3s threaded) and the full season ~544 (~23s).

Moneyline is the one worth paying for: it converts to a win probability, which
is what survivor actually needs, and it is the only field with 100% coverage
(one game currently has an over/under and moneylines but no posted spread).
"""

import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .espn import (
    CORE_EVENT_URL,
    INPUT_DIR,
    REGULAR_SEASON_WEEKS,
    fetch_json,
    fetch_scoreboard,
    parse_competitors,
    require,
    utc_stamp,
)

ODDS_DIR = INPUT_DIR / "odds"
HISTORY_PATH = ODDS_DIR / "odds_history.csv"

DEFAULT_WORKERS = 8

COLUMNS = [
    "Season",
    "WeekNum",
    "Week",
    "Game_ID",
    "Away",
    "Home",
    "Kickoff_UTC",
    "NeutralSite",
    "Provider",
    # Current market
    "Spread_Home",          # home-relative: negative = home favored
    "Spread_Detail",        # ESPN's display string, e.g. "GB -7.5"
    "Over_Under",
    "Away_ML",
    "Home_ML",
    # Derived, vig removed
    "Away_Win_Prob",
    "Home_Win_Prob",
    # Opening market, for line movement
    "Open_Spread_Home",
    "Open_Away_ML",
    "Open_Home_ML",
    # ESPN's own FPI-based model, for comparison
    "ESPN_Home_Win_Prob",
    "ESPN_Matchup_Quality",
    "Fetched_At_UTC",
]

# Fields the cheap scoreboard pass cannot populate. Used to decide whether a
# newer observation should be allowed to blank out an older one - see
# _rebuild_week_views.
DETAIL_COLUMNS = [
    "Away_ML",
    "Home_ML",
    "Away_Win_Prob",
    "Home_Win_Prob",
    "Open_Spread_Home",
    "Open_Away_ML",
    "Open_Home_ML",
    "ESPN_Home_Win_Prob",
    "ESPN_Matchup_Quality",
]


def american_to_prob(moneyline: Optional[float]) -> Optional[float]:
    """Convert American moneyline odds to raw implied probability (vig included)."""
    if moneyline is None:
        return None
    moneyline = float(moneyline)
    if moneyline < 0:
        return (-moneyline) / ((-moneyline) + 100.0)
    return 100.0 / (moneyline + 100.0)


def devig(
    away_ml: Optional[float],
    home_ml: Optional[float],
) -> Tuple[Optional[float], Optional[float]]:
    """
    Convert a moneyline pair to fair win probabilities.

    Raw implied probabilities sum to more than 1 - the excess is the book's
    margin. Normalizing by the total removes it proportionally, which is the
    standard approximation and plenty accurate for two-way markets.
    """
    away_raw = american_to_prob(away_ml)
    home_raw = american_to_prob(home_ml)
    if away_raw is None or home_raw is None:
        return None, None
    total = away_raw + home_raw
    if total <= 0:
        return None, None
    return away_raw / total, home_raw / total


def fetch_season_lines(
    season: int,
    weeks: Optional[Sequence[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Pull spreads and totals for every game via the scoreboard (the cheap path).

    Args:
        season: Season year.
        weeks: Week numbers to fetch. Defaults to the full regular season.

    Returns:
        One partially-populated observation row per game.
    """
    target_weeks = list(weeks) if weeks else list(range(1, REGULAR_SEASON_WEEKS + 1))
    rows: List[Dict[str, Any]] = []

    for week in target_weeks:
        events = fetch_scoreboard(season, week)
        priced = 0
        for event in events:
            row = _parse_scoreboard_event(event, season, week)
            if row:
                rows.append(row)
                if row["Spread_Home"] is not None:
                    priced += 1

        print(f"   week {week:>2}: {len(events)} games, {priced} with a posted spread")

    return rows


def _parse_scoreboard_event(
    event: Dict[str, Any],
    season: int,
    week: int,
) -> Optional[Dict[str, Any]]:
    """Build an observation row from one scoreboard event."""
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    competition = competitions[0]

    sides = parse_competitors(competition)
    if not sides:
        return None

    # A game can be listed with no line posted yet; that is not an error.
    odds_list = competition.get("odds") or []
    odds = odds_list[0] if odds_list else {}

    row: Dict[str, Any] = {column: None for column in COLUMNS}
    row.update(
        {
            "Season": season,
            "WeekNum": week,
            "Week": f"Week {week}",
            "Game_ID": event.get("id"),
            "Away": sides["away"],
            "Home": sides["home"],
            "Kickoff_UTC": event.get("date"),
            "NeutralSite": bool(competition.get("neutralSite")),
            "Provider": (odds.get("provider") or {}).get("name"),
            # ESPN's 'spread' is home-relative: negative means the home team is
            # favored. Verified 2026-09-08 against the display strings.
            "Spread_Home": odds.get("spread"),
            "Spread_Detail": odds.get("details"),
            "Over_Under": odds.get("overUnder"),
        }
    )
    return row


def enrich_with_details(
    rows: List[Dict[str, Any]],
    workers: int = DEFAULT_WORKERS,
) -> List[Dict[str, Any]]:
    """
    Add moneylines, opening lines, and ESPN's win projection to each row.

    This is the expensive path (two requests per game), so it is applied only to
    the rows handed in - normally just the week being picked. Rows are updated
    in place and also returned.

    A per-game failure is logged and left blank rather than aborting the run; a
    partial week of odds is still useful. A total failure is reported loudly,
    since that usually means an endpoint moved rather than one odd game.
    """
    if not rows:
        return rows

    print(f"   fetching moneyline + predictor for {len(rows)} games ({workers} workers)...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_enrich_row, rows))

    filled = sum(1 for row in rows if row["Home_ML"] is not None)
    projected = sum(1 for row in rows if row["ESPN_Home_Win_Prob"] is not None)
    print(f"   moneyline on {filled}/{len(rows)}, predictor on {projected}/{len(rows)}")

    if filled == 0 and projected == 0:
        print(
            "   [warn] the detail pass returned nothing for any game - the "
            "per-event endpoints may have moved. Spreads and totals are unaffected."
        )
    return rows


def _enrich_row(row: Dict[str, Any]) -> None:
    """Fetch the two per-event endpoints for a single game."""
    event_id = row.get("Game_ID")
    if not event_id:
        return
    base = CORE_EVENT_URL.format(eid=event_id)
    label = f"{row.get('Away')} @ {row.get('Home')}"

    try:
        payload = fetch_json(f"{base}/odds", retries=2)
        item = (payload.get("items") or [{}])[0]
        away = item.get("awayTeamOdds") or {}
        home = item.get("homeTeamOdds") or {}

        row["Away_ML"] = away.get("moneyLine")
        row["Home_ML"] = home.get("moneyLine")
        row["Away_Win_Prob"], row["Home_Win_Prob"] = devig(row["Away_ML"], row["Home_ML"])

        row["Open_Away_ML"] = _open_value(away, "moneyLine")
        row["Open_Home_ML"] = _open_value(home, "moneyLine")
        row["Open_Spread_Home"] = _open_value(home, "pointSpread")

        # The core endpoint prices some games the scoreboard leaves blank.
        if row["Spread_Home"] is None and item.get("spread") is not None:
            row["Spread_Home"] = item.get("spread")
            row["Spread_Detail"] = item.get("details")
    except Exception as exc:  # noqa: BLE001 - one bad game must not kill the run
        print(f"   [warn] odds failed for {label}: {exc}")

    try:
        payload = fetch_json(f"{base}/predictor", retries=2)
        stats = {
            stat.get("name"): stat.get("value")
            for stat in (payload.get("homeTeam") or {}).get("statistics") or []
        }
        # gameProjection on homeTeam is the home side's win percentage (0-100).
        row["ESPN_Home_Win_Prob"] = stats.get("gameProjection")
        row["ESPN_Matchup_Quality"] = stats.get("matchupQuality")
    except Exception as exc:  # noqa: BLE001
        print(f"   [warn] predictor failed for {label}: {exc}")


def _parse_signed_number(raw: Any) -> Optional[float]:
    """
    Coerce ESPN's signed-number strings to float.

    Covers both American odds ("-192", "+295") and point spreads ("-3.5"), which
    share the same string encoding.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace("+", "")
    if text.upper() in ("EVEN", "EV", "PK", "PICK", ""):
        return 0.0 if text.upper() in ("PK", "PICK") else 100.0
    try:
        return float(text)
    except ValueError:
        return None


def _open_value(side: Dict[str, Any], field: str) -> Optional[float]:
    """
    Pull an opening price from a team's nested 'open' block.

    That block encodes the same price several ways - 'value'/'decimal' are
    decimal odds (1.52) while 'american' is the American price ("-192"). Always
    take the American form: the current moneyLine is American, and mixing the
    two silently breaks open-vs-current line movement comparisons.
    """
    node = (side.get("open") or {}).get(field)
    if isinstance(node, dict):
        return _parse_signed_number(node.get("american") or node.get("alternateDisplayValue"))
    return _parse_signed_number(node)


def save_odds(rows: List[Dict[str, Any]]) -> Tuple[Path, List[Path]]:
    """
    Append observations to the history log, then rebuild the per-week views.

    History is the source of truth and is never rewritten - that is what makes
    line movement recoverable.

    Returns:
        (history path, list of per-week paths written)
    """
    require(bool(rows), "no odds rows to save")
    ODDS_DIR.mkdir(parents=True, exist_ok=True)

    stamp = utc_stamp()
    for row in rows:
        row["Fetched_At_UTC"] = stamp

    exists = HISTORY_PATH.exists()
    with HISTORY_PATH.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)

    return HISTORY_PATH, _rebuild_week_views(sorted({row["WeekNum"] for row in rows}))


def _rebuild_week_views(weeks: Iterable[int]) -> List[Path]:
    """
    Regenerate week{N}_odds.csv from the full history.

    Each field takes its most recent non-empty value, so a cheap spreads-only
    refresh no longer blanks out moneylines fetched by an earlier detail pass.
    Rebuilding from history rather than from the current run also self-heals any
    week whose view was clobbered before this behaviour existed.
    """
    if not HISTORY_PATH.exists():
        return []

    with HISTORY_PATH.open(newline="", encoding="utf-8") as handle:
        history = list(csv.DictReader(handle))

    wanted = {str(week) for week in weeks}
    latest: Dict[str, Dict[str, str]] = {}
    for row in history:
        if row.get("WeekNum") not in wanted:
            continue
        game_id = row.get("Game_ID")
        if not game_id:
            continue
        merged = latest.setdefault(game_id, {column: "" for column in COLUMNS})
        for column in COLUMNS:
            value = row.get(column, "")
            if value not in ("", None):
                merged[column] = value

    written: List[Path] = []
    for week in sorted(wanted, key=int):
        week_rows = [r for r in latest.values() if r.get("WeekNum") == week]
        if not week_rows:
            continue
        week_rows.sort(key=lambda r: (r.get("Kickoff_UTC") or "", r.get("Home") or ""))
        path = ODDS_DIR / f"week{week}_odds.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(week_rows)
        written.append(path)

    return written


def parse_week_arg(value: str, current_week: Optional[int] = None) -> List[int]:
    """
    Interpret a --weeks argument: "5", "5,7,9", "5-8", "all", or "rest".

    "rest" means the current week through week 18, which is the span a survivor
    plan actually has to cover.
    """
    value = (value or "").strip().lower()
    if value == "all":
        return list(range(1, REGULAR_SEASON_WEEKS + 1))
    if value == "rest":
        start = current_week or 1
        return list(range(start, REGULAR_SEASON_WEEKS + 1))

    weeks: List[int] = []
    try:
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_str, end_str = part.split("-", 1)
                weeks.extend(range(int(start_str), int(end_str) + 1))
            else:
                weeks.append(int(part))
    except ValueError as exc:
        raise ValueError(
            f'could not parse weeks {value!r} - expected "5", "5,7", "5-8", "rest" or "all"'
        ) from exc

    invalid = [w for w in weeks if not 1 <= w <= REGULAR_SEASON_WEEKS]
    if invalid:
        raise ValueError(f"week numbers out of range 1-{REGULAR_SEASON_WEEKS}: {invalid}")
    return sorted(set(weeks))
