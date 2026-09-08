# survivor_picks - working notes

NFL survivor pool data fetching. Successor to `../picksim`, which required
manually downloading a FPI CSV every week.

## Current state

**Fetch layer plus the published grid. No automated pick model yet.**

`POOLS.md` is the authority on Jake's pools, entry names (`Dustin`, `Crazy1`,
`Crazy2`, `Crazy3`), the Crazy tie breaker rules, and every strategy conclusion
reached so far - read it before discussing picks or building pick logic. Two
things from it that are easy to get wrong:

- **The two pools are different games.** Crazy is true survivor: optimise
  P(survive to ~wk17-18), not expected weeks survived. Dustin's has **no
  elimination** - you pick all 18 weeks and it is scored on longest streak
  (half the pot) plus total wins (half), so survivor logic does not transfer.
- The three Crazy entries must be **decorrelated**, not three copies of one
  optimal path. That is worth 1.7x and outranks every other refinement.
- Crazy's tie breaker needs **six** unused teams in week 18; reserve exactly
  one of the best, not six.

Public pick percentages / game theory are deliberately deferred. Ask before
assuming an approach.

The picksim questions that prompted this are now settled and recorded in
`POOLS.md`: win probability comes from devigged moneylines (home field already
priced in), and the solver is an exact assignment via
`scipy.optimize.linear_sum_assignment` on log-probabilities. Field/leverage
remains open and is the deferred game-theory work.

## Weekly workflow

**Jake does not run these commands himself.** When he says "update football",
"refresh for week N", or anything similar, run the whole pipeline for him and
republish the board, then report the recommendation in chat. Do not hand him
the commands to run.

The full weekly sequence:

1. `python scripts/fetch.py --fpi --odds --public`
2. `python scripts/build_grid_data.py`
3. Republish `grid.html` with the Artifact tool (same URL - it updates in place)
4. Tell him what each entry's model recommends and why

If he has locked picks on the board since the last run, import them first so the
solves exclude burned teams: read the artifact db (`read_db`, collection `picks`,
doc `2026`) and pass the JSON to `scripts/sync_picks.py --from-grid`.

```bash
python scripts/fetch.py --fpi --odds --public   # pull the week's data
python scripts/build_grid_data.py               # rebuild the board
python scripts/recommend.py                     # this week's pick per entry
```

`recommend.py` reads `data/input/my_picks.csv` (Entry,Week,Team) so solves
exclude teams already burned. Picks made on the published grid live in its
artifact database - read it with the Artifact tool (`read_db`, collection
`picks`, doc `2026`) and import with:

```bash
python scripts/sync_picks.py --from-grid '<the json that came back>'
python scripts/sync_picks.py --show             # what the models currently see
```

The models are in `src/survivor_picks/model.py`, one named function per
objective. `leverage_values()` raises rather than falling back to a model when a
week has no observed pick data - do not add a fallback, that is the point.

## The published grid

`grid.html` is the interactive board (published as an Artifact; URL in
`data/output/artifact_url.txt`). It renders `data/output/grid_data.json`, which
`scripts/build_grid_data.py` regenerates from the fetched odds.

It holds all four entries behind a selector, stored in the `db` capability as
`{entries: {Dustin: {week: team}, Crazy1: ..., ...}}`. Switching to a Crazy entry
outlines any team another Crazy entry already holds that week, since doubling up
means those entries are eliminated together. The stats panel adapts: Dustin's
shows expected wins (it has no elimination), the Crazy entries show path
survival.

Regenerate and republish after a fetch, or the board shows stale lines.

## Running it

```bash
python scripts/fetch.py              # FPI only - the weekly routine
python scripts/fetch.py --all        # FPI + schedule + teams (season setup)
python scripts/fetch.py --schedule   # refresh after a flex/relocation change
python scripts/fetch.py --week 6     # override the snapshot's week label
python scripts/fetch.py --force      # overwrite an existing snapshot
python scripts/fetch.py --season 2025 --fpi

python scripts/fetch.py --fpi --odds        # the full weekly pull
python scripts/fetch.py --odds --detail 5-8 # moneylines for a planning window
python scripts/fetch.py --odds --no-detail  # spreads/totals only, 18 requests
```

Stdlib only - no install needed to fetch. `pandas` is for downstream analysis.

If Jake asks to "run the fetch" / "pull this week's data", it's
`python scripts/fetch.py --fpi --odds`. Check `data/input/fpi/snapshots.csv` afterward to
confirm ESPN's `lastUpdated` actually moved since the previous snapshot.

## Odds vs FPI - they behave differently

FPI is a weekly snapshot: grab it once, it's done, a missed week is gone forever.
Odds are **live** - a line pulled Tuesday and the same line pulled Sunday morning
are different numbers and the later one is sharper. So they're stored
differently:

- `data/input/odds/odds_history.csv` is **append-only** and is the source of
  truth. Re-fetching a week adds rows rather than replacing them, which is what
  makes line movement recoverable. Never rewrite it.
- `data/input/odds/week{N}_odds.csv` is a derived view, rebuilt from history on
  every save. Each field takes its most recent non-empty value, so a cheap
  spreads-only pass cannot blank out moneylines an earlier detail pass fetched.
  Safe to delete; the next run regenerates it.

Two fetch paths, because ESPN splits the data:

- **cheap** - spread + over/under come inline with the scoreboard, so the whole
  season is 18 requests (~7s). This is the default for all 18 weeks.
- **detail** - moneyline and ESPN's win projection are per-event only, ~2
  requests per game (~32 per week, ~1.3s threaded; ~544 for a full season,
  ~23s). It defaults to the weeks named by `--weeks`, or to the current week
  when `--weeks` is absent, so the routine full-season refresh stays cheap while
  a targeted `--odds --weeks 5` still gets real moneylines. `--detail` sets it
  explicitly, `--no-detail` skips it.

Prefer **moneyline** over spread as the win-probability source: `devig()`
converts a moneyline pair to fair probabilities, coverage is 272/272, and one
game currently has moneylines and a total but no posted spread.

Verified coverage as of 2026-09-08, full census of all 272 games: moneyline
272/272, ESPN predictor 272/272, over/under 272/272, spread 271/272 (MIN @ TB
in week 3 is the gap).

## Things that will bite you

**ESPN serves only *current* FPI.** There is no historical week lookup. A week
that isn't fetched is unrecoverable. This is why snapshots are never overwritten
without `--force` and why every raw response is archived to `data/raw/` before
parsing. If a week was missed, say so plainly - don't backfill it from a later
snapshot and don't imply the gap is fixable.

**Never set a browser User-Agent.** `site.api.espn.com` 403s browser-like UA
strings ("Mozilla/5.0 ...") from non-browser clients, and also rejects arbitrary
custom tokens ("survivor-picks/1.0"). urllib's default `Python-urllib/3.x` works
on all three endpoints. Verified 2026-09-08. This is the first thing someone
would "fix" and it will break everything - see the comment in `espn.py`.

**The endpoints are undocumented and unsupported.** Parsers read ESPN's category
label lists positionally rather than hardcoding column order, and validate shape
before writing, raising `EspnError` rather than writing bad data.

**Only FPI payloads are archived to `data/raw/`.** Archiving everything cost
~40MB per afternoon of pure duplication - the schedule is re-fetchable and the
parsed odds observations already live in `odds_history.csv`. Don't add
`archive_as=` to scoreboard or per-event calls; FPI is archived because it is
the one thing that cannot be re-fetched.

**`--season 2025` returns end-of-season ratings, not in-season snapshots.** Fine
for reference, insufficient to reconstruct what FPI said in week 6 of that
season. The only real in-season record is `../picksim/data/input/fpi/`
(weeks 0-13 of 2025) - treat those as irreplaceable.

## Output contract

First columns of each CSV match the legacy picksim format on purpose, so older
code keeps working; everything after is additive. Don't reorder them.

- `weekN_fpi.csv` - `Team,FPI` first. Full precision (`5.854`; espn.com shows `5.9`).
- `weekly_matchups.csv` - `Week,TeamA,TeamB` first, where TeamA=away, TeamB=home.
  Explicit `Away`/`Home`/`NeutralSite` columns follow; prefer those.
- `abbreviation_mapping.csv` - `team_abbreviation,team_name` first, abbrev lowercased
  to match pool exports.
- `odds_history.csv` / `week{N}_odds.csv` - `Spread_Home` is **home-relative**
  (negative = home favored), verified against ESPN's display strings. All
  moneyline columns are American format; ESPN's nested `open` block also carries
  decimal odds under `value`/`decimal`, which must NOT be used - mixing formats
  across the open/current columns silently breaks line-movement comparisons.
  `ESPN_Home_Win_Prob` is a 0-100 percentage; `Home_Win_Prob` is a 0-1
  proportion with vig removed. Don't compare them without scaling.

The week number labels the week ratings are **current for**: fetched during
week 5 = results through week 4 = `week5_fpi.csv`.

Schedule validation asserts 272 games, 17 per team, no team twice in a week.
