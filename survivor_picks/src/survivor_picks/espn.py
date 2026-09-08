"""
ESPN API client and shared project constants.

These endpoints back espn.com but are undocumented and unsupported, so every
parser validates the shape it expects and fails loudly with a clear message
rather than silently writing garbage into the pick model.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# site.web.api serves the FPI/analytics surface; site.api serves scores/schedule.
POWERINDEX_URL = "https://site.web.api.espn.com/apis/fitt/v3/sports/football/nfl/powerindex"
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
CORE_EVENT_URL = (
    "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
    "/events/{eid}/competitions/{eid}"
)

# Do NOT set a custom User-Agent. site.api.espn.com sits behind a filter that
# 403s browser-like UA strings ("Mozilla/5.0 ...") coming from non-browser
# clients, and also rejects arbitrary custom tokens ("survivor-picks/1.0").
# urllib's default "Python-urllib/3.x" is accepted by all endpoints.
# Verified 2026-09-08: Mozilla UA -> 403, custom token -> 403, default -> 200.

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
RAW_DIR = DATA_DIR / "raw"

REGULAR_SEASON = 2          # ESPN's seasontype for the regular season
REGULAR_SEASON_WEEKS = 18
NFL_TEAMS = 32
GAMES_PER_TEAM = 17
# 32 teams x 17 games, each game counted by both sides.
SEASON_GAMES = NFL_TEAMS * GAMES_PER_TEAM // 2


class EspnError(RuntimeError):
    """Raised when ESPN is unreachable or returns a shape we don't recognize."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp() -> str:
    """Timestamp for CSV columns, e.g. 2026-09-08T13:55:38Z."""
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_relpath(path: Path) -> str:
    """
    Render a path relative to the working directory when possible.

    Path.relative_to raises if the path isn't under cwd (a different drive on
    Windows, or running the script from elsewhere), so fall back to the absolute
    path rather than crashing a successful fetch on a cosmetic detail.
    """
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def fetch_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    archive_as: Optional[str] = None,
    retries: int = 3,
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    GET a JSON endpoint with retries and exponential backoff.

    Args:
        url: Base endpoint URL.
        params: Query string parameters.
        archive_as: If set, save the raw response under data/raw/ before
                    parsing. Reserve this for payloads that cannot be re-fetched
                    later - see archive_raw().
        retries: Number of attempts before giving up.
        timeout: Per-request timeout in seconds.

    Returns:
        The decoded JSON body.

    Raises:
        EspnError: On repeated network failure or non-JSON responses.
    """
    query = urllib.parse.urlencode(params or {})
    full_url = f"{url}?{query}" if query else url
    request = urllib.request.Request(full_url)

    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
            payload = json.loads(body)
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                backoff = 2 ** (attempt - 1)
                print(f"   [retry {attempt}/{retries}] {exc} - waiting {backoff}s")
                time.sleep(backoff)
        except json.JSONDecodeError as exc:
            # A non-JSON body usually means a block page or an endpoint that
            # moved; retrying won't help.
            raise EspnError(f"Non-JSON response from {full_url}: {exc}") from exc
    else:
        raise EspnError(f"Failed to fetch {full_url} after {retries} attempts: {last_error}")

    if archive_as:
        archive_raw(payload, archive_as)

    return payload


def archive_raw(payload: Dict[str, Any], name: str) -> Path:
    """
    Save a raw response that could not be reconstructed if we lost it.

    Only FPI qualifies: ESPN serves current ratings only, so an unarchived
    response is gone for good. Schedule and odds payloads are deliberately NOT
    archived - the schedule is re-fetchable and the parsed odds observations are
    already preserved in odds_history.csv, so archiving them added ~40MB per
    afternoon of pure duplication.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{name}_{utc_now().strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def require(condition: bool, message: str) -> None:
    """Assert an expectation about ESPN's response shape."""
    if not condition:
        raise EspnError(
            f"Unexpected ESPN response shape: {message}. "
            "The undocumented API may have changed."
        )


def dig(payload: Any, *keys: Any, default: Any = None) -> Any:
    """Walk a nested dict/list path, returning `default` if any step is missing."""
    node: Any = payload
    for key in keys:
        if isinstance(node, dict):
            if key not in node:
                return default
            node = node[key]
        elif isinstance(node, list):
            if not isinstance(key, int) or key >= len(node):
                return default
            node = node[key]
        else:
            return default
    return node


def season_context() -> Dict[str, Optional[int]]:
    """
    Look up the season and week ESPN currently considers active.

    Uses limit=1 so callers that only need the calendar don't pull and archive a
    full 32-team FPI payload.

    Returns:
        {"season": year, "week": week_number} - either may be None off-season.
    """
    payload = fetch_json(POWERINDEX_URL, {"region": "us", "lang": "en", "limit": 1})
    return {
        "season": dig(payload, "requestedSeason", "year"),
        "week": dig(payload, "currentSeason", "type", "week", "number"),
    }


def fetch_scoreboard(season: int, week: int) -> List[Dict[str, Any]]:
    """
    Fetch one week of the regular season scoreboard and return its events.

    Shared by the schedule and odds fetchers, which both read this endpoint -
    the schedule wants the matchups, odds wants the inline lines that ride along
    with them.
    """
    payload = fetch_json(
        SCOREBOARD_URL,
        {"dates": season, "seasontype": REGULAR_SEASON, "week": week},
    )
    events = payload.get("events")
    require(isinstance(events, list), f"week {week}: 'events' is not a list")
    return events


def parse_competitors(competition: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """
    Pull home and away display names from a competition block.

    Returns None when either side is missing, which callers treat as a game to
    skip rather than an error.
    """
    sides: Dict[str, str] = {}
    for competitor in competition.get("competitors") or []:
        name = dig(competitor, "team", "displayName")
        if competitor.get("homeAway") in ("home", "away") and name:
            sides[competitor["homeAway"]] = name
    if "home" not in sides or "away" not in sides:
        return None
    return sides
