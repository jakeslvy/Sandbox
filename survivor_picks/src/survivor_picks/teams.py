"""
Fetch the NFL team reference table.

Produces the abbreviation -> full name mapping that pool exports need, since
most pools record picks as lowercase abbreviations (kc, phi, lar) while FPI and
schedule data use full display names.
"""

import csv
from pathlib import Path
from typing import Any, Dict, List

from .espn import INPUT_DIR, NFL_TEAMS, TEAMS_URL, fetch_json, require

MAPPING_PATH = INPUT_DIR / "abbreviation_mapping.csv"

COLUMNS = ["team_abbreviation", "team_name", "espn_id", "location", "nickname"]


def fetch_teams() -> List[Dict[str, Any]]:
    """Pull all 32 teams with their abbreviations and display names."""
    payload = fetch_json(TEAMS_URL, {"limit": 50})

    entries = (
        payload.get("sports", [{}])[0]
        .get("leagues", [{}])[0]
        .get("teams")
    )
    require(isinstance(entries, list) and entries, "could not locate teams list")

    rows: List[Dict[str, Any]] = []
    for entry in entries:
        team = entry.get("team") or {}
        abbreviation = team.get("abbreviation")
        display_name = team.get("displayName")
        if not abbreviation or not display_name:
            continue
        rows.append(
            {
                # Pool exports are lowercase; keep the mapping key in that form.
                "team_abbreviation": abbreviation.lower(),
                "team_name": display_name,
                "espn_id": team.get("id"),
                "location": team.get("location"),
                "nickname": team.get("name"),
            }
        )

    require(len(rows) == NFL_TEAMS, f"expected {NFL_TEAMS} teams, parsed {len(rows)}")
    rows.sort(key=lambda r: r["team_name"])
    return rows


def save_teams(rows: List[Dict[str, Any]], path: Path = MAPPING_PATH) -> Path:
    """Write the abbreviation mapping to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path
