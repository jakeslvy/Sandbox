"""
Fetch ESPN Football Power Index ratings.

ESPN serves only the *current* FPI - there is no historical week lookup - so each
fetch is a point-in-time snapshot that must be captured while it is live. Files
are written as weekN_fpi.csv and never silently overwritten.

The website rounds FPI to one decimal (5.9); this API returns full precision
(5.854), which is what we store.
"""

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from .espn import (
    INPUT_DIR,
    NFL_TEAMS,
    POWERINDEX_URL,
    EspnError,
    dig,
    fetch_json,
    require,
    utc_stamp,
)

FPI_DIR = INPUT_DIR / "fpi"
MANIFEST = FPI_DIR / "snapshots.csv"

# First two columns match the legacy picksim format so existing readers that
# expect Team/FPI keep working; everything after is additive.
COLUMNS = [
    "Team",
    "FPI",
    "Abbrev",
    "FPI_Rank",
    "EPA_Off",
    "EPA_Def",
    "EPA_ST",
    "SOS_Rank",
    "Rem_SOS_Rank",
    "Game_Control_Rank",
    "Wins",
    "Losses",
    "Ties",
    "Proj_Wins",
    "Proj_Losses",
    "Playoff_Pct",
]

# ESPN stat key -> our column name, for the "fpi" category.
FPI_FIELDS = {
    "fpi": "FPI",
    "fpirank": "FPI_Rank",
    "epaoffense": "EPA_Off",
    "epadefense": "EPA_Def",
    "epaspecialteams": "EPA_ST",
    "avgsosrank": "SOS_Rank",
    "sosremainingrank": "Rem_SOS_Rank",
    "gamecontrolrank": "Game_Control_Rank",
    "numwins": "Wins",
    "numlosses": "Losses",
    "numties": "Ties",
}

# ...and for the "projections" category.
PROJECTION_FIELDS = {
    "projectedw": "Proj_Wins",
    "projectedl": "Proj_Losses",
    "probmakeplayoffs": "Playoff_Pct",
}


def fetch_fpi(season: Optional[int] = None) -> Dict[str, Any]:
    """
    Pull current FPI ratings for all 32 teams.

    Args:
        season: Season year. Defaults to whatever ESPN considers current.
                Past seasons return that season's *final* ratings.

    Returns:
        Dict with keys: teams (list of row dicts), season, week, last_updated.
    """
    params: Dict[str, Any] = {"region": "us", "lang": "en", "limit": 50}
    if season is not None:
        params["season"] = season

    payload = fetch_json(POWERINDEX_URL, params, archive_as="powerindex")

    categories = payload.get("categories")
    require(isinstance(categories, list) and categories, "'categories' missing or empty")

    # Category label lists tell us what each positional value means. They are
    # positional, so we must not assume a fixed order.
    label_map: Dict[str, List[str]] = {}
    for category in categories:
        name = category.get("name")
        names = category.get("names")
        if name and isinstance(names, list):
            label_map[name] = names

    require("fpi" in label_map, "no 'fpi' category in response")
    require(
        "fpi" in label_map["fpi"],
        "'fpi' category does not contain an 'fpi' stat",
    )

    teams_payload = payload.get("teams")
    require(isinstance(teams_payload, list) and teams_payload, "'teams' missing or empty")

    rows: List[Dict[str, Any]] = []
    for entry in teams_payload:
        team = entry.get("team") or {}
        display_name = team.get("displayName")
        if not display_name:
            continue

        row: Dict[str, Any] = {column: None for column in COLUMNS}
        row["Team"] = display_name
        row["Abbrev"] = team.get("abbreviation")

        for category in entry.get("categories") or []:
            category_name = category.get("name")
            values = category.get("values")
            labels = label_map.get(category_name)
            if not labels or not isinstance(values, list):
                continue

            stats = dict(zip(labels, values))
            mapping = FPI_FIELDS if category_name == "fpi" else PROJECTION_FIELDS
            for espn_key, column in mapping.items():
                if espn_key in stats:
                    row[column] = stats[espn_key]

        if row["FPI"] is None:
            raise EspnError(f"No FPI value returned for {display_name}")

        rows.append(row)

    require(
        len(rows) == NFL_TEAMS,
        f"expected {NFL_TEAMS} teams, parsed {len(rows)}",
    )

    rows.sort(key=lambda r: r["FPI"], reverse=True)

    # ESPN returns values with float artifacts (84.89999999999999); round to
    # meaningful precision so diffs between weekly snapshots stay readable.
    for row in rows:
        for column, value in row.items():
            if isinstance(value, float):
                row[column] = round(value, 3)

    return {
        "teams": rows,
        "season": dig(payload, "requestedSeason", "year"),
        "week": dig(payload, "currentSeason", "type", "week", "number"),
        "last_updated": payload.get("lastUpdated"),
    }


def save_fpi_snapshot(
    result: Dict[str, Any],
    week: Optional[int] = None,
    *,
    force: bool = False,
) -> Optional[Path]:
    """
    Write a snapshot to data/input/fpi/weekN_fpi.csv and log it in the manifest.

    The week number labels the week the ratings are *current for* - i.e. ratings
    fetched during week 5 reflect results through week 4 and are saved as
    week5_fpi.csv.

    Args:
        result: Output of fetch_fpi().
        week: Override the week number. Defaults to ESPN's reported current week.
        force: Overwrite an existing file for that week.

    Returns:
        Path written, or None if the file existed and force was False.
    """
    week_number = week if week is not None else result.get("week")
    if week_number is None:
        raise EspnError("Could not determine week number; pass --week explicitly")

    FPI_DIR.mkdir(parents=True, exist_ok=True)
    path = FPI_DIR / f"week{week_number}_fpi.csv"

    if path.exists() and not force:
        print(f"   [skip] {path.name} already exists (use --force to overwrite)")
        return None

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(result["teams"])

    _log_snapshot(path, result, week_number)
    return path


def _log_snapshot(path: Path, result: Dict[str, Any], week_number: int) -> None:
    """
    Append to snapshots.csv so every file's provenance stays auditable.

    ESPN's lastUpdated matters: fetching twice in one week can yield identical
    ratings, and this is how we tell a real refresh from a duplicate.
    """
    fields = ["file", "season", "week", "espn_last_updated", "fetched_at_utc"]
    exists = MANIFEST.exists()

    with MANIFEST.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "file": path.name,
                "season": result.get("season"),
                "week": week_number,
                "espn_last_updated": result.get("last_updated"),
                "fetched_at_utc": utc_stamp(),
            }
        )
