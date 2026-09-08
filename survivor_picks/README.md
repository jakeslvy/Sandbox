# survivor_picks

NFL survivor pool data collection. Pulls ESPN FPI, the schedule, betting lines,
and ESPN's own game-level win projections — replacing the manual weekly CSV
downloads that the predecessor project (`../picksim`) required.

**This is the data layer only.** No pick model is implemented yet; that decision
is deliberately still open.

## Setup

Python 3.8+. The fetcher is standard library only — nothing to install.

```bash
pip install -r requirements.txt   # only needed for downstream pandas analysis
```

## Weekly use

```bash
python scripts/fetch.py --fpi --odds
```

Takes a few seconds. Writes an FPI snapshot for the week, refreshes spreads and
totals for the whole season, and pulls moneylines plus ESPN win projections for
the current week.

### Season setup

```bash
python scripts/fetch.py --all
```

Adds the team abbreviation mapping and the full 272-game schedule.

### Other options

```bash
python scripts/fetch.py --odds --detail 5-8   # moneylines for a planning window
python scripts/fetch.py --odds --weeks 5      # just week 5, with its moneylines
python scripts/fetch.py --odds --no-detail    # spreads/totals only (18 requests)
python scripts/fetch.py --week 6              # label the FPI snapshot manually
python scripts/fetch.py --force               # overwrite an existing snapshot
python scripts/fetch.py --season 2025 --fpi   # a past season's final ratings
```

`--weeks` and `--detail` accept `5`, `5,7,9`, `5-8`, `rest`, or `all`.

## What you get

```
data/
├── raw/                              archived FPI payloads only (unrecoverable)
└── input/
    ├── fpi/
    │   ├── week{N}_fpi.csv           ratings snapshot for week N
    │   └── snapshots.csv             provenance log (what was fetched, when)
    ├── odds/
    │   ├── odds_history.csv          append-only observations — source of truth
    │   └── week{N}_odds.csv          derived view, rebuilt from history
    ├── weekly_matchups.csv           full 272-game schedule
    └── abbreviation_mapping.csv      abbreviation → full team name
```

### Signals available

Three independent estimates of who wins, all covering the full season:

| Signal | Column | Coverage | Notes |
|---|---|---|---|
| Market moneyline | `Home_Win_Prob` | 272/272 | vig removed; usually the sharpest |
| ESPN win projection | `ESPN_Home_Win_Prob` | 272/272 | FPI-based, home field included |
| Point spread | `Spread_Home` | 271/272 | home-relative; negative = home favored |
| FPI rating | `week{N}_fpi.csv` | 32 teams | neutral-field points vs average team |

`Open_*` columns hold opening lines, so line movement is available for free.

## Two things worth knowing

**FPI is unrecoverable.** ESPN serves only *current* ratings — there is no
historical week lookup. A week you don't fetch is gone permanently. Snapshots
are never overwritten without `--force`, and every raw response is archived.
`--season 2025` returns that season's *final* ratings, not in-season snapshots.

**Odds are live.** Lines move all week and sharpen toward kickoff, so odds are
stored as append-only observations rather than one file per week. Fetching the
same week repeatedly is expected and builds movement history.

## Data source

Undocumented ESPN endpoints — no API key, no auth, no cost. They can change
without notice, so parsers validate response shape and fail loudly rather than
writing bad data. On failure, check `data/raw/` for the payload.

See `CLAUDE.md` for implementation gotchas.
