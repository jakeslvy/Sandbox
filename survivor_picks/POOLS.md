# Pools, entries, and strategy

Jake's two 2026-season pools, their rules, and what the analysis concluded for
each. Only **Crazy** is a true survivor pool; **Dustin's** has no elimination and
is scored on longest streak plus total wins, so most survivor intuitions do not
transfer between them. Strategy numbers here come from lines captured 2026-09-08 and
will drift as the season moves; the *conclusions* are more durable than the
figures.

## Entries

Four entries in total, across two pools:

| Entry | Pool | Field | Notes |
|---|---|---|---|
| `Dustin` | Dustin's Pool | ~50 entries | Single entry |
| `Crazy1` | Crazy | ~8,000 entries | One of three |
| `Crazy2` | Crazy | ~8,000 entries | One of three |
| `Crazy3` | Crazy | ~8,000 entries | One of three |

Use these exact names when recording or displaying picks.

## Dustin's Pool (~50 entries)

**This is not a survivor pool.** There is no elimination - you keep picking all
18 weeks regardless of losses. The pot splits into two independent prizes:

> Like last year, there will be two pots this season. The first half of the pot
> goes to the person who has the longest winning streak from the beginning. The
> second half of the pot goes to the person with the most total wins throughout
> the season.

That makes it two games with different objectives:

| Pot | Objective | What to maximise |
|---|---|---|
| **Streak** (half) | Longest run of wins starting week 1 | E[streak] - front-load your best teams |
| **Total wins** (half) | Most wins across all 18 weeks | Sum of win probabilities - order irrelevant |

**Total wins has no reach discounting.** Because you are never eliminated, week
15 counts exactly as much as week 1. This is the opposite of survivor logic and
the one place in this project where hoarding/ordering genuinely does not matter -
only the *set* of 18 team-week assignments does.

### The two pots barely conflict

| Plan | E[total wins] | E[streak] |
|---|---|---|
| Max total wins | **14.06** | 3.59 |
| Max streak | 13.92 | **3.88** |
| Blend (25% streak weight) | 14.05 | 3.75 |
| Blend (50% streak weight) | 13.99 | 3.85 |

A blend around 25-50% streak weight captures ~99.5% of the maximum wins and
~97-99% of the maximum streak. **Play the blend; don't choose between the pots.**
The two optimal plans share 9 of 18 picks anyway.

### Practical approach

Front-load slightly (which serves the streak pot) while taking the highest-
probability assignment overall (which serves the wins pot). Re-solve weekly.
Public pick percentages are explicitly **not** a factor here - Jake is playing
this one straight on probability.

### Team reuse

**Each team may be picked only once**, confirmed with Jake. This is what couples
the 18 weeks together and makes the assignment solve meaningful - without it both
pots would collapse to "take the highest-probability team every week" and need no
optimiser at all. All figures above assume the one-use rule.

## Crazy (~8,000 entries, 3 entries)

Field empties at a median of week 17 (IQR 14-19); 60% of the time nobody
survives all 18 weeks, and when someone does it is often many people - mean ~37
survivors. **Jake's read from prior years: it usually reaches the tie breaker,
and frequently still splits after it.** Plan on the tie breaker mattering, not
on winning outright in week 18.

### Tie breaker rules (verbatim)

> The tie breaker will be picking five additional teams to win in week 18 (you
> can only pick teams that you have not picked already). The tie breaker will
> only be used if there is more than one entry left after the regular week 18
> picks are calculated. The winner will be the entry that has the regular week
> 18 pick correct and has the most tie breaker games correct (if there is still
> a tie, the entries with the most tie breaker picks correct will split the
> pot). NOTE: If all week 18 entries lose, the tie breaker will be used to
> determine the winner.

### What the tie breaker changes

**You need six unused teams available in week 18, not one** - the regular pick
plus five tie breaker teams, none of them used earlier in the season. Week 18
has no byes, so all 32 teams play; after 17 weekly picks you will have 15 unused,
so the constraint is never infeasible. What matters is their *quality*.

A losing week-18 pick is not automatically fatal: if every remaining entry loses
their week-18 pick, the tie breaker still decides it. That softens the penalty
for a week-18 miss relative to any other week.

**Reserve exactly one team, not six.** Holding back the single best week-18 team
is worth it; hoarding a full slate is not, because you have to survive to week 18
before any of it counts:

| Top wk-18 teams reserved | P(alive after wk17) | Expected TB hits (of 5) | Combined |
|---|---|---|---|
| 0 | 1.55% | 2.55 | 0.0283 |
| **1** | **1.39%** | **2.74** | **0.0312** |
| 2 | 1.10% | 3.01 | 0.0269 |
| 6 | 0.66% | 3.80 | 0.0206 |

Reserving all six costs 57% of your survival probability to buy 1.25 expected
tie breaker hits - a bad trade. Reserving one is the peak.

### Three entries: decorrelate them

The single biggest lever in this pool. Three copies of the same optimal path are
worth barely more than one entry, because they die on the same Sunday. Three
paths that never share a team in the same week are close to independent:

| | P(at least one alive at wk17) |
|---|---|
| 3 clones | 1.55% |
| 3 decorrelated | **2.59%** |

**1.7x**, which dwarfs every other optimisation available. The cost is that
Crazy2 and Crazy3 have worse individual odds (0.70% and 0.36% vs 1.55%); pay it.

This is decorrelation against variance only, with no knowledge of the field.
Public pick data would improve it further by letting the entries diverge from
the crowd specifically rather than merely from each other - see "Not yet built".

## Strategy conclusions (Crazy unless noted)

**Optimise P(survive to your target week), not expected weeks survived.** A
single entry lasts ~3.9 weeks on average, but the *winner* is decided at week
13-17, so the branches that matter are the ones where you are still alive.
Optimising for average duration optimises for a comfortable death. Match the
horizon to where the pool actually empties, and use the full grid rather than a
short planning window.

**Maximin vs max-product is a false choice.** Run as true optimisations they
select 15 of the same 18 teams (1.11% vs 1.14% full-season survival). Not worth
deliberating.

**Re-solve every week.** Distant lines are unreliable - a week-15 price today
carries little information about week 15. Use the full grid for the constraint
structure (what using a team now costs you later), but treat the back half as
provisional and re-run once new lines land.

**Hoarding good teams pays less than it feels like it should.** The alternative
to your best team is your *second*-best, not your thirtieth - a median gap of
2.6 points. And most strong teams are strong in several weeks (SF is 84% in
week 2, 83% in week 3), so "saving" one rarely preserves anything unique.

## Leverage: only observed pick data counts

`scripts/fetch.py --public` scrapes the current week's public pick percentages
(survivorgrid). **Only the current week exists** - no source publishes future
pick percentages as observations, because the public has not picked yet.

**Do not model pick shares as a function of win probability and treat the result
as leverage.** It was tried; it is not a measurement. Modelled shares are a
deterministic function of the same win probabilities the straight model already
optimises, so "leverage" computed from them only re-expresses the objective. It
is also unstable - varying the fitted slope swings the number of picks that
differ from the straight model between 0 and 8, with no data behind the swing:

| fitted slope | picks differing from straight model |
|---|---|
| 6-10 | 0 |
| 12-15 | 3 |
| 20 | 8 |

The consequence: **Crazy2 cannot be a pre-computed season path.** Leverage is a
week-by-week decision taken with that week's observed percentages. Use the season
solve as a skeleton for constraint-checking (what using a team now costs later),
then override each week once the real numbers publish. Crazy1 and Crazy2 will
diverge organically over the season; there is no way to forecast when.

Verified on real week-1 data: leverage did **not** change the week-1 pick (still
JAX). That is one genuine observation, consistent with leverage being unable to
do work while ~5,700 of 8,000 entries survive the week. Weeks 2-17 are
*unevaluated*, not shown to be unaffected.

A week not fetched is a week of field behaviour lost permanently - unlike odds,
it cannot be re-derived later.

## Not yet built

**Public pick percentages / game theory.** Deliberately deferred. Given a 1.7x
gain from blind decorrelation alone, differentiating against the actual field
is expected to be worth more than any remaining pick-optimisation gain. Ask
before assuming an approach here.
