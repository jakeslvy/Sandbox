"""
Fetch public survivor pick percentages.

This is the field's actual behaviour, and it is the one input no odds model can
derive. The public is not a pure odds-chaser: measured against a win-probability
model fitted to real data, pick shares deviate by ~2x in both directions (brand
names over-picked, unglamorous favourites under-picked). That residual is the
entire leverage edge.

**Only the current week exists.** No source publishes future pick percentages as
observations, because the public has not picked yet - anything labelled "week 12
pick %" is a projection off week-12 odds, which adds essentially nothing over
just using the odds. So this must be fetched weekly, in-week, and accumulated.
A week not fetched is a week of field behaviour lost.

Source: survivorgrid.com - server-rendered HTML, no API, robots.txt permits all.
Small site with no stability guarantee, so the parser validates hard and fails
loudly rather than feeding bad leverage numbers into pick decisions.
"""

import csv
import html
import re
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .espn import INPUT_DIR, EspnError, NFL_TEAMS, require, utc_stamp

SURVIVORGRID_URL = "https://www.survivorgrid.com/"

PUBLIC_DIR = INPUT_DIR / "public"
HISTORY_PATH = PUBLIC_DIR / "picks_history.csv"

COLUMNS = [
    "Season",
    "WeekNum",
    "Week",
    "Team",
    "Pick_Pct",        # share of the public taking this team, 0-1
    "Source_Win_Pct",  # the source's own win probability, for cross-checking
    "Source_EV",
    "Fetched_At_UTC",
]

# The source's team codes differ from ESPN's in a few places.
TEAM_FIXES = {"JAC": "JAX", "WAS": "WSH", "LA": "LAR", "SD": "LAC", "OAK": "LV"}


def _text(fragment: str) -> str:
    """Strip tags and collapse whitespace in one table cell."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _cells(row_html: str) -> List[str]:
    return [_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.S | re.I)]


def _pct(value: str) -> Optional[float]:
    if not value.endswith("%"):
        return None
    try:
        return float(value.rstrip("%")) / 100
    except ValueError:
        return None


def fetch_public_picks(timeout: int = 30) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Scrape the current week's public pick percentages.

    Returns:
        (week_number, rows) - one row per team.

    Raises:
        EspnError: if the page shape changed or the data fails validation.
    """
    request = urllib.request.Request(SURVIVORGRID_URL)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            page = response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        raise EspnError(f"could not fetch {SURVIVORGRID_URL}: {exc}") from exc

    # The page states its own week, e.g. "2026 Season - Week 1 Grid".
    heading = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S | re.I)
    week_match = re.search(r"Week\s*(\d{1,2})", _text(heading.group(1)) if heading else "")
    require(bool(week_match), "could not read the week number from the page heading")
    week = int(week_match.group(1))

    rows_html = re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I)
    require(len(rows_html) > 1, "no table rows found")

    rows: List[Dict[str, Any]] = []
    for row_html in rows_html[1:]:
        cells = _cells(row_html)
        if len(cells) < 4:
            continue
        ev, win, pick, team = cells[0], cells[1], cells[2], cells[3]
        if not re.fullmatch(r"[A-Z]{2,3}", team):
            continue
        rows.append(
            {
                "Team": TEAM_FIXES.get(team, team),
                "Pick_Pct": _pct(pick),
                "Source_Win_Pct": _pct(win),
                "Source_EV": float(ev) if re.fullmatch(r"[\d.]+", ev) else None,
            }
        )

    _validate(rows)
    return week, rows


def _validate(rows: List[Dict[str, Any]]) -> None:
    """
    Fail loudly on anything that would quietly corrupt a leverage calculation.

    A silently truncated scrape is worse than no scrape: it would understate the
    field's concentration and make chalk look contrarian.
    """
    require(
        len(rows) == NFL_TEAMS,
        f"expected {NFL_TEAMS} teams, parsed {len(rows)}",
    )

    missing = [r["Team"] for r in rows if r["Pick_Pct"] is None]
    # A team on bye legitimately has no pick share; more than a handful is a parse failure.
    require(len(missing) <= 6, f"{len(missing)} teams have no pick % ({missing[:8]})")

    total = sum(r["Pick_Pct"] or 0 for r in rows)
    require(
        0.90 <= total <= 1.10,
        f"pick percentages sum to {total * 100:.1f}%, expected ~100%",
    )


def cross_check(rows: List[Dict[str, Any]], our_probs: Dict[str, float]) -> List[str]:
    """
    Compare the source's win probabilities against our devigged moneylines.

    Both describe the same games, so a large divergence means one of the two went
    stale - worth surfacing before the numbers reach a pick decision.
    """
    warnings: List[str] = []
    gaps = []
    for row in rows:
        theirs = row["Source_Win_Pct"]
        ours = our_probs.get(row["Team"])
        if theirs is None or ours is None:
            continue
        gaps.append((abs(theirs - ours), row["Team"], theirs, ours))

    if not gaps:
        warnings.append("no overlapping teams to cross-check")
        return warnings

    gaps.sort(reverse=True)
    worst = gaps[0]
    if worst[0] > 0.10:
        warnings.append(
            f"{worst[1]}: source says {worst[2] * 100:.0f}% win, we say {worst[3] * 100:.0f}% "
            f"- one of the two may be stale"
        )
    return warnings


def save_public_picks(week: int, rows: List[Dict[str, Any]], season: int) -> Tuple[Path, Path]:
    """
    Append to history and refresh the per-week view.

    Pick percentages move through the week as the public commits, so like odds
    these are append-only observations rather than a single snapshot.
    """
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()

    records = [
        {
            "Season": season,
            "WeekNum": week,
            "Week": f"Week {week}",
            "Team": r["Team"],
            "Pick_Pct": r["Pick_Pct"],
            "Source_Win_Pct": r["Source_Win_Pct"],
            "Source_EV": r["Source_EV"],
            "Fetched_At_UTC": stamp,
        }
        for r in rows
    ]

    exists = HISTORY_PATH.exists()
    with HISTORY_PATH.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerows(records)

    week_path = PUBLIC_DIR / f"week{week}_public.csv"
    with week_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(sorted(records, key=lambda r: -(r["Pick_Pct"] or 0)))

    return HISTORY_PATH, week_path
