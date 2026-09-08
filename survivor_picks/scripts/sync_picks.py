"""
Sync picks between the published grid and the models.

The grid stores your picks in its artifact database; the models read
data/input/my_picks.csv. This keeps the two in step so what you click is what
the recommender solves around.

    python scripts/sync_picks.py --from-grid <json>   # grid export -> my_picks.csv
    python scripts/sync_picks.py --show               # what the models currently see

The grid's database is read with the Artifact tool rather than by this script
(it needs your claude.ai session), so `--from-grid` takes the JSON that read
returns - either a path or the raw object:

    {"entries": {"Dustin": {"1": "JAX"}, "Crazy1": {"1": "LAC"}, ...}}
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from survivor_picks.espn import INPUT_DIR, safe_relpath

PICKS_PATH = INPUT_DIR / "my_picks.csv"
ENTRIES = ["Dustin", "Crazy1", "Crazy2", "Crazy3"]
COLUMNS = ["Entry", "Week", "Team"]


def read_picks() -> dict:
    """Current contents of my_picks.csv as {entry: {week: team}}."""
    if not PICKS_PATH.exists():
        return {}
    out: dict = {}
    with PICKS_PATH.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("Entry") and row.get("Week") and row.get("Team"):
                out.setdefault(row["Entry"].strip(), {})[int(row["Week"])] = (
                    row["Team"].strip().upper()
                )
    return out


def write_picks(picks: dict) -> Path:
    """Write {entry: {week: team}} to my_picks.csv, sorted for a readable diff."""
    PICKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PICKS_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for entry in ENTRIES:
            for week in sorted(picks.get(entry, {}), key=int):
                writer.writerow(
                    {"Entry": entry, "Week": week, "Team": picks[entry][week]}
                )
    return PICKS_PATH


def from_grid(payload: dict) -> dict:
    """
    Normalise a grid database document into {entry: {week: team}}.

    Tolerates the older single-entry shape ({"picks": {...}}), which belonged to
    Dustin before the grid knew about entries.
    """
    data = payload.get("data", payload)
    entries = data.get("entries")
    if entries is None and isinstance(data.get("picks"), dict):
        entries = {"Dustin": data["picks"]}
    if not isinstance(entries, dict):
        raise SystemExit("could not find picks in that payload (expected an 'entries' object)")

    out: dict = {}
    for entry, weeks in entries.items():
        if entry not in ENTRIES:
            print(f"   [warn] ignoring unknown entry {entry!r}")
            continue
        for week, team in (weeks or {}).items():
            if team:
                out.setdefault(entry, {})[int(week)] = str(team).strip().upper()
    return out


def show(picks: dict) -> None:
    if not picks:
        print(f"   no picks recorded ({safe_relpath(PICKS_PATH)} is empty or missing)")
        return
    weeks = sorted({w for e in picks.values() for w in e})
    print(f"   {'week':>5} " + "".join(f"{e:>9}" for e in ENTRIES))
    print("   " + "-" * (5 + 9 * len(ENTRIES)))
    for week in weeks:
        print(
            f"   {week:>5} "
            + "".join(f"{picks.get(e, {}).get(week, '-'):>9}" for e in ENTRIES)
        )
    # Two Crazy entries on one team in one week die together - worth flagging.
    for week in weeks:
        crazy = [picks.get(e, {}).get(week) for e in ("Crazy1", "Crazy2", "Crazy3")]
        crazy = [t for t in crazy if t]
        dupes = {t for t in crazy if crazy.count(t) > 1}
        if dupes:
            print(f"   [!] week {week}: Crazy entries share {', '.join(sorted(dupes))}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync grid picks into the models.")
    parser.add_argument("--from-grid", metavar="JSON", help="grid db document, or a path to it")
    parser.add_argument("--show", action="store_true", help="show what the models currently see")
    args = parser.parse_args()

    if args.from_grid:
        raw = args.from_grid
        path = Path(raw)
        text = path.read_text(encoding="utf-8") if path.exists() else raw
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"not valid JSON: {exc}")

        picks = from_grid(payload)
        total = sum(len(v) for v in picks.values())
        written = write_picks(picks)
        print(f"   [OK] wrote {total} pick(s) to {safe_relpath(written)}")
        show(picks)
        return 0

    show(read_picks())
    if not args.show:
        print(f"\n   (pass --from-grid to import from the published board)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
