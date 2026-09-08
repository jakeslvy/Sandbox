"""
The three pick models, as explicit named objectives.

Each pool is a different game and wants a different thing. They are separated
here deliberately - conflating a single-week calculation with a season-long
solve produces confident, wrong answers, which is exactly the failure this
module exists to prevent.

    dustin  - Dustin's Pool. No elimination; you pick all 18 weeks. Scored on
              longest streak from week 1 (half the pot) plus total wins (half).
              Maximises a blend of E[streak] and expected total wins.

    crazy   - Crazy, a true survivor pool. Maximises P(survive to the target
              week), holding back the best week-18 team for the tie breaker.

    leverage - NOT a separate path. A per-week adjustment applied on top of
              `crazy`, using OBSERVED public pick percentages for that week.
              It cannot be pre-computed for future weeks; see POOLS.md.

All solves are exact assignment problems (Hungarian / linear_sum_assignment)
over log-probabilities, so the no-reuse rule is structural rather than a filter
applied afterwards.
"""

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import numpy as np
from scipy.optimize import linear_sum_assignment

from .espn import INPUT_DIR, PROJECT_ROOT, REGULAR_SEASON_WEEKS

BOARD_PATH = PROJECT_ROOT / "data" / "output" / "grid_data.json"

# Any cell that must never be chosen: a bye, a used team, a reserved team.
FORBIDDEN = -1e6


class ModelError(RuntimeError):
    """Raised when a model is asked for something it cannot honestly answer."""


@dataclass
class Board:
    """Win probabilities for every team in every week."""

    teams: List[str]
    weeks: List[int]
    P: np.ndarray                      # teams x weeks; 0.0 means no game (bye)
    opponents: Dict[str, Dict[int, str]] = field(default_factory=dict)
    captured: str = ""

    def matchup(self, team: str, week: int) -> str:
        """e.g. "vs CLE" or "@ DEN"; empty when the team is on bye."""
        return self.opponents.get(team, {}).get(week, "")

    def team_index(self, team: str) -> int:
        try:
            return self.teams.index(team)
        except ValueError as exc:
            raise ModelError(f"unknown team {team!r}") from exc

    def week_index(self, week: int) -> int:
        try:
            return self.weeks.index(week)
        except ValueError as exc:
            raise ModelError(f"week {week} not on the board") from exc

    def prob(self, team: str, week: int) -> float:
        return float(self.P[self.team_index(team), self.week_index(week)])

    def logs(self) -> np.ndarray:
        return np.where(self.P > 0, np.log(np.maximum(self.P, 1e-9)), FORBIDDEN)


def load_board(path: Path = BOARD_PATH) -> Board:
    """Load the board built by scripts/build_grid_data.py."""
    if not path.exists():
        raise ModelError(
            f"no board at {path} - run: python scripts/build_grid_data.py"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    teams = [t["a"] for t in data["teams"]]
    weeks = data["weeks"]

    P = np.zeros((len(teams), len(weeks)))
    opponents: Dict[str, Dict[int, str]] = {}
    for i, team in enumerate(teams):
        for j, week in enumerate(weeks):
            game = data["games"].get(team, {}).get(str(week))
            if game:
                P[i, j] = game["p"]
                opponents.setdefault(team, {})[week] = (
                    f"{'vs' if game.get('h') else '@'} {game['opp']}"
                )

    if not P.any():
        raise ModelError("board has no priced games")
    return Board(
        teams=teams, weeks=weeks, P=P,
        opponents=opponents, captured=data.get("captured", ""),
    )


# --------------------------------------------------------------------------
# solving
# --------------------------------------------------------------------------

def _mask(
    board: Board,
    values: np.ndarray,
    used: Optional[Iterable[str]] = None,
    reserved: Optional[Iterable[str]] = None,
    locked: Optional[Dict[int, str]] = None,
) -> np.ndarray:
    """Apply the constraints that are not part of the objective."""
    v = values.copy()
    for team in list(used or []) + list(reserved or []):
        v[board.team_index(team), :] = FORBIDDEN
    if locked:
        for week, team in locked.items():
            j = board.week_index(week)
            col = np.full(board.P.shape[0], FORBIDDEN)
            i = board.team_index(team)
            col[i] = values[i, j] if values[i, j] > FORBIDDEN else 0.0
            v[:, j] = col
    return v


def _assign(board: Board, values: np.ndarray, weeks: Sequence[int]) -> Dict[int, str]:
    """
    Exact team-to-week assignment maximising the summed value.

    Each team is used at most once and each week gets exactly one team - the
    no-reuse rule is the structure of the problem, not a post-filter.
    """
    cols = [board.week_index(w) for w in weeks]
    sub = values[:, cols]
    rows, chosen = linear_sum_assignment(-sub)
    out = {}
    for r, c in zip(rows, chosen):
        if sub[r, c] <= FORBIDDEN / 2:
            continue
        out[weeks[c]] = board.teams[r]
    if len(out) < len(weeks):
        missing = [w for w in weeks if w not in out]
        raise ModelError(f"no feasible pick for week(s) {missing} - too many teams excluded")
    return out


# --------------------------------------------------------------------------
# objective 1: Dustin's Pool
# --------------------------------------------------------------------------

def solve_dustin(
    board: Board,
    used: Optional[Iterable[str]] = None,
    locked: Optional[Dict[int, str]] = None,
    streak_weight: float = 0.35,
    iterations: int = 60,
) -> Dict[int, str]:
    """
    Dustin's Pool: blend longest-streak and total-wins.

    No elimination, so total wins carries no reach discount - week 15 counts as
    much as week 1. The streak half does discount, so its term is weighted by
    P(reaching that week), recomputed until the path stops improving.

    streak_weight 0.25-0.50 captures ~99% of both pots; 0.35 sits in the middle.
    """
    logs = board.logs()
    weeks = list(board.weeks)
    path = _assign(board, _mask(board, logs, used, None, locked), weeks)

    for _ in range(iterations):
        reach, running = [], 1.0
        for week in weeks:
            reach.append(running)
            running *= board.prob(path[week], week)

        blended = np.where(
            board.P > 0,
            streak_weight * logs * np.array(reach)[None, :]
            + (1 - streak_weight) * board.P * 0.35,
            FORBIDDEN,
        )
        nxt = _assign(board, _mask(board, blended, used, None, locked), weeks)
        if nxt == path:
            break
        path = nxt
    return path


# --------------------------------------------------------------------------
# objective 2: Crazy
# --------------------------------------------------------------------------

def best_week18_team(board: Board, used: Optional[Iterable[str]] = None) -> str:
    """The strongest week-18 team, held back for the tie breaker's regular pick."""
    j = board.week_index(REGULAR_SEASON_WEEKS)
    burned = set(used or [])
    ranked = sorted(
        (i for i in range(len(board.teams)) if board.P[i, j] > 0 and board.teams[i] not in burned),
        key=lambda i: -board.P[i, j],
    )
    if not ranked:
        raise ModelError("no team available for week 18")
    return board.teams[ranked[0]]


def solve_crazy(
    board: Board,
    used: Optional[Iterable[str]] = None,
    locked: Optional[Dict[int, str]] = None,
    target_week: int = 17,
    reserve_week18: bool = True,
    week_values: Optional[Dict[int, np.ndarray]] = None,
) -> Dict[int, str]:
    """
    Crazy: maximise P(survive weeks 1..target_week).

    Reserves the best week-18 team so the tie breaker's *regular* pick is strong.
    Reserving exactly one is the optimum - holding more costs more survival than
    the extra tie breaker hits are worth (see POOLS.md).

    week_values optionally replaces a week's column with leverage-adjusted values
    (see leverage_values). Only ever supply that for a week with OBSERVED public
    pick data.
    """
    logs = board.logs()
    if week_values:
        for week, column in week_values.items():
            logs[:, board.week_index(week)] = column

    reserved = [best_week18_team(board, used)] if reserve_week18 else []
    weeks = [w for w in board.weeks if w <= target_week]
    return _assign(board, _mask(board, logs, used, reserved, locked), weeks)


# --------------------------------------------------------------------------
# objective 3: leverage (a per-week adjustment, not a path)
# --------------------------------------------------------------------------

def leverage_values(board: Board, week: int, shares: Dict[str, float]) -> np.ndarray:
    """
    Leverage-adjusted log-values for ONE week, from observed pick percentages.

    equity = P(your team wins) / P(the field survives alongside you)

    Everyone who picked your team survives exactly when you do, diluting your
    share of the pot; everyone else survives at their own rate. Fading the crowd
    pays in proportion to how concentrated it is, not as a blanket rule.

    `shares` must be OBSERVED percentages for this week. Modelled shares derived
    from win probability are not a measurement - they re-express the objective
    the solve already has, and produce unstable results. See POOLS.md.
    """
    if not shares:
        raise ModelError(
            f"no observed pick percentages for week {week} - "
            "leverage cannot be modelled from win probability"
        )

    j = board.week_index(week)
    total = sum(shares.values())
    if total <= 0:
        raise ModelError(f"pick percentages for week {week} sum to zero")

    s = np.array([shares.get(t, 0.0) / total for t in board.teams])
    field = float((s * board.P[:, j]).sum())

    out = np.full(len(board.teams), FORBIDDEN)
    for i in range(len(board.teams)):
        p = board.P[i, j]
        if p <= 0:
            continue
        # everyone on your team survives with you; everyone else at their own rate
        alive = s[i] + (field - s[i] * p)
        if alive > 0:
            out[i] = np.log(p / alive)
    return out


def load_observed_shares(week: int) -> Dict[str, float]:
    """Read scraped public pick percentages for a week. Empty if not fetched."""
    path = INPUT_DIR / "public" / f"week{week}_public.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return {
            r["Team"]: float(r["Pick_Pct"])
            for r in csv.DictReader(handle)
            if r.get("Pick_Pct")
        }


# --------------------------------------------------------------------------
# evaluation
# --------------------------------------------------------------------------

def evaluate(board: Board, path: Dict[int, str]) -> Dict[str, Any]:
    """Score a path on every metric the two pools care about."""
    weeks = sorted(path)
    probs = [board.prob(path[w], w) for w in weeks]

    survival, expected_streak, running = 1.0, 0.0, 1.0
    for p in probs:
        running *= p
        expected_streak += running
    survival = running

    weakest = min(range(len(probs)), key=lambda k: probs[k]) if probs else None
    return {
        "weeks": weeks,
        "survival": survival,
        "expected_streak": expected_streak,
        "expected_wins": sum(probs),
        "weakest_week": weeks[weakest] if weakest is not None else None,
        "weakest_prob": probs[weakest] if weakest is not None else None,
        "min_prob": min(probs) if probs else None,
    }


def load_my_picks(path: Path = INPUT_DIR / "my_picks.csv") -> Dict[str, Dict[int, str]]:
    """
    Picks already made, as {entry: {week: team}}.

    CSV columns: Entry,Week,Team - entries are Dustin, Crazy1, Crazy2, Crazy3.
    """
    if not path.exists():
        return {}
    out: Dict[str, Dict[int, str]] = {}
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            entry, week, team = row.get("Entry"), row.get("Week"), row.get("Team")
            if entry and week and team:
                out.setdefault(entry.strip(), {})[int(week)] = team.strip().upper()
    return out
