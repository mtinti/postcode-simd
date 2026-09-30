# Plan: can the SIMD domains be banded defensibly?

Drafted 30 September 2026. Status: **test run and reviewed 30 September 2026; decision
recorded: copy the published domain bands (see the end of the findings).** A feasibility test only: it changes no table, schema or query,
and its outcome is a decision, recorded here, on whether to plan domain quintiles and deciles
at all.

## The rule for this plan: test, report, then stop

The test is run on its own, and nothing else. When it finishes, the findings are reported:
the numbers from every stage, the external search, and a recommendation. **Work stops there.**
No domain band is planned, implemented or added to any table, query, document or release
until the findings have been reviewed and a decision is recorded in this plan. The deciding
table below is guidance for that review, not permission to proceed.

## Why a test first

None of the files we pin carries a domain band: the Scottish Government's shapefiles carry
domain ranks only, PHS no domain data (Domain ranks plan, "What was checked"). As drafted, the
plan assumed no domain band was published anywhere, so any domain band would be HIC's own
derivation, defensible only if the same rule, applied to the overall rank, reproduces the
bands the publishers did release. *Corrected by the test: the Government publishes domain
quintiles, deciles and vigintiles for every edition, 2004 to 2020v2, on statistics.gov.scot;
see the findings.* The overall rank is the one place
where both the rank and its official bands exist, so it is the test bed.

## What is already known

From `Plan_Gap_Closure.md`, sections 2 and 5 (10 September 2026):

| Series | Rule | Verified |
| --- | --- | --- |
| Government unweighted, 2001 zones (2004 to 2012) | half-up cut: `cut(j) = round(j * n / k)`, halves up | quintile, decile, vigintile, all four editions, zero mismatches |
| Government unweighted, 2011 zones (2016, 2020v2) | `ceil(rank * k / n)` | the same three series, zero mismatches |
| PHS population-weighted, Scotland | population midpoint: zones by rank, `min(k, ceil((cum_pop - pop / 2) * k / total_pop))` | 2020v2 only, with NRS 2017 estimates: zero mismatches, both 15% flags exact |
| PHS population-weighted, HB, HSCP, CA | the same within each area | 2020v2: two Shetland zones differ per measure, cause unexplained |

The acceptance script that produced these no longer exists, so the test re-runs them.

What is not known: whether the weighted rule holds for the five earlier editions, which
population PHS used for them, and how the rules behave on domain ranks, which carry halves
and ties that the overall rank never has.

## The test

A standalone script in the scratchpad, reading the pinned Scottish Government DBFs and PHS
CSVs through the existing readers. Nothing is added to the build.

### Stage 1: unweighted overall bands (re-verify)

For every edition, apply the vintage's rule to the overall rank and compare with the
Government's published quintile, decile and vigintile. **Pass: zero mismatches in all 18
series.** A failure here stops the test: the rules are not what we believe.

### Stage 2: weighted overall bands (extend)

For every edition, apply the population-midpoint rule at Scotland level to the overall rank,
using the population column each Government file carries (`totpop2001` for 2004, then SAPE
2004, 2007, 2010, 2014 and 2017), and compare with PHS's country quintile, decile and both 15%
flags. **Pass per edition: zero mismatches.** An edition that fails gets no weighted domain
bands; record the mismatch count and try the neighbouring years' estimates only if one is
pinned, never by searching for a population that happens to fit. Sub-geography bands are out
of scope: the Shetland exceptions show they are not exactly reproducible even for 2020v2.

### Stage 3: the rules on domain ranks (diagnose)

The overall rank is a clean permutation, 1 to n. Domain ranks are not: 7,796 values end in .5
and 1,072 tied groups do not carry the average of their positions (2020v2 income: twelve zones
at 6969 where positions run 6965 to 6976). For every edition and published domain:

1. **Ties are kept together.** Every rule is applied to the rank value, not to a position, so
   zones with the same rank always get the same band. No tie-break by zone code: it would be
   arbitrary and would split identical zones.
2. **The half-up cut with halves.** A rank ending in .5 never equals an integer cut, so the
   2001 rule needs no extra definition; state and test that.
3. **The weighted rule with ties.** A tied group is one block: its cumulative population is
   taken through the whole group, minus half the group's population, so the group shares one
   band.
4. **Measure the cost of 1 to 3.** Per edition, domain and series: the band sizes (zones and,
   for weighted, population share) against the overall rank's, the number of tied groups that
   straddle a cut, and the largest resulting deviation. Report, for example, "2020v2 income
   decile 10 holds 693 zones, not 697 or 698, because a tie of 12 straddles the cut".
5. **Determinism.** The result depends only on the published ranks and populations: the same
   inputs give the same bands, and reordering the rows changes nothing.

Stage 3 has no pass mark of its own; it produces the numbers the decision needs.

### An external check, if one exists

Look for any published domain band: the Scottish Government's SIMD map, the SIMD 2020
technical notes, and the 2016 and 2020 data zone lookups. If one is found, pin it and compare,
which would be stronger evidence than stages 1 and 2. If none is found, record where we
looked.

## Reporting the findings

When the test finishes, before anything else:

1. Write the findings into a new section of this plan: every stage's numbers, the tables of
   band sizes and straddling ties, the external search and where it looked, and a
   recommendation from the table below.
2. Report the same findings in the conversation, and stop.
3. Only once the findings are reviewed is a decision recorded here, and only then may a
   separate implementation plan be written.

## Findings, 30 September 2026

The test ran as planned: a scratchpad script reading the pinned sources through the pipeline's
own readers, plus the external search. Nothing in the repository changed. Work has stopped
here for review.

### Stage 1: unweighted overall bands, re-verified

**Pass.** The vintage rules reproduce the Government's published overall quintile, decile and
vigintile exactly: zero mismatches in all 18 series (six editions, three bands; 6,505 zones for
2001 geography, 6,976 for 2011).

### Stage 2: weighted overall bands, extended to every edition

**Pass for all six editions.** The population-midpoint rule, using the population column in
each Government shapefile, reproduces PHS's Scotland quintile and decile exactly for every
edition, not only 2020v2:

| Edition | Population | Total | Zones with zero population | Quintile / decile mismatches | 15% flag mismatches |
| --- | --- | --- | --- | --- | --- |
| 2004 | `totpop2001` | 5,062,011 | 0 | 0 / 0 | 0 |
| 2006 | `sape2004` | 5,078,400 | 0 | 0 / 0 | 0 |
| 2009v2 | `sape2007` | 5,144,200 | 1 | 0 / 0 | 1 most, 1 least |
| 2012 | `sape2010` | 5,222,100 | 3 | 0 / 0 | 1 most |
| 2016 | `sape2014` | 5,347,600 | 2 | 0 / 0 | 0 |
| 2020v2 | `sape2017` | 5,424,800 | 3 | 0 / 0 | 0 |

The 15% flags are not exact for 2009v2 and 2012, whichever inequality is used. Flags are not
proposed for domains, so this does not affect the decision; it is recorded as unexplained.

### Stage 3: the rules on domain ranks

41 edition-domain pairs, 82 series (quintile and decile). The domain ranks carry 7,796 half
values and 5,188 tied groups, of which 1,072 do not carry the average of their positions.
These are not scattered: 2009v2 income and employment and 2012 income give every tied group
its **lowest** position (competition ranking), 1,071 groups; the only other exception is one
2020v2 income group, twelve zones at 6969 where positions run 6965 to 6976. Every other
domain averages its ties.

- **Ties across a cut are rare.** 12 of the 82 series have a tied group straddling a cut, at
  most 2 groups and 2 zones per series.
- **Band sizes stay equal.** Unweighted, every domain band is within one zone of the overall
  rank's band of the same edition: deciles 649 to 652 zones for 2001 geography, 697 to 699 for
  2011. Weighted, every band holds its fifth or tenth of the population to within 0.036
  percentage points (2012 access decile), against 0.020 for the overall rank.
- **Deterministic.** Reordering the rows changes no band in any of the 41 pairs.

### The external check: published domain bands exist for every edition

*Revised 30 September after review. The first version of this section said only 2020 had
published domain bands; the search had missed two datasets.*

The Scottish Government publishes, on statistics.gov.scot, the rank, quintile, decile and
vigintile of the overall SIMD and of every domain, for every data zone, in three datasets:

| Dataset | Editions | Zones | Rows |
| --- | --- | --- | --- |
| `scottish-index-of-multiple-deprivation-historical-i` | 2004, 2006, 2009, 2012 (no 2004 crime) | 6,505 (2001) | 806,620 |
| `scottish-index-of-multiple-deprivation-historical-ii` | 2016 | 6,976 (2011) | 223,232 |
| `scottish-index-of-multiple-deprivation` | 2020 (the revised 2020v2) | 6,976 (2011) | 223,232 |

Each downloads as one CSV from `https://statistics.gov.scot/downloads/cube-table?uri=` plus the
dataset URI. None carries population-weighted or sub-geography bands, indicators or scores.

**Their ranks against ours.**

- **2004 to 2012.** Identical except that every half rank is rounded **up** to a whole number,
  in every differing zone (for example 592 in 2004 income, 1,162 in 2004 employment). The same
  ranking, stored as integers.
- **2016.** Identical in every domain.
- **2020.** Identical except housing, 628 zones differing by 0.5 to 4.5. Our housing equals the
  ranks workbook, so two Government files agree against this one.

**Their bands against the candidate rules.** Of 819,897 published domain zone-bands (41
edition-domain pairs, three bands each), the vintage rule applied to our ranks as they stand
disagrees with 19, and rounding half ranks down first with 21. No rule based on the rank alone
reproduces all of them, for two reasons:

1. **The publisher splits some ties.** In 2006 employment (1 quintile, 2 deciles, 2
   vigintiles), 2006 income (1 decile, 1 vigintile) and 2009 employment (1 decile, 2
   vigintiles), zones with the same rank are in different published bands: for example
   S01001951 and S01006050, both 1952 in 2009 employment, are deciles 3 and 4. Keeping ties
   together cannot reproduce these.
2. **The publisher treats the same tie two ways.** S01008149 and S01012978 have housing rank
   2790.5 in both 2016 and 2020v2, across the cut between decile 4 (to 2790) and 5 (from 2791).
   The 2016 publication puts them in decile 5 (quintile 3); the 2020 publication puts them in
   decile 4 (quintile 2). The earlier finding that rounding down reproduces all 24 published
   2020 series is true, but it is a 2020 convention, not a rule for 2011 zones: it gets 2016
   wrong for the same pair.

2020v2 housing against our ranks has two separate causes, to be kept apart:

- **Rank-source disagreement.** Of the 628 zones whose housing rank differs between the CSV and
  our shapefile, only two change band under the published 2020 convention: S01008634 (2093 in
  ours, 2092.5 in the CSV; 1 decile and 1 vigintile) and S01006994 (5930 and 5929.5; 1
  vigintile). No quintile changes. The other 626 fall in the same band either way.
- **Tie convention.** S01008149 and S01012978, whose ranks agree (2790.5 in both sources), move
  one band in each series if a half rank is used as it stands instead of rounded down. That is
  the 2016-versus-2020 tie question above, not a rank disagreement.

Earlier counts of 2 quintiles, 3 deciles and 4 vigintiles added the two causes together.

The earlier table in the one-rule section stands for the overall bands, which are clean
permutations; for domains the table above supersedes it.

### Recommendation, for review

**Copy the published bands; do not derive them.** They exist for every edition and domain, so
domain bands can be carried like everything else in the tables: copied as published, from a
pinned source, never recalculated. A derived rule would disagree with the publisher in 19 to 21
zone-bands whatever tie convention is chosen, and would need its own defence.

#### Where each value comes from

The shapefiles stay the source of every rank; the statistics.gov.scot CSVs are added for one
thing only, the domain bands, which no other source publishes.

| Value | Source | Why |
| --- | --- | --- |
| Overall rank and bands | Shapefile, as now | Identical in both sources; nothing to gain |
| Domain ranks | Shapefile, as now (4.0.0) | Half ranks exactly as published; the 2004 to 2012 CSV rounds them up. For 2020 housing the shapefile agrees with the ranks workbook, the CSV does not. No change to the 4.0.0 columns |
| Domain quintile, decile, vigintile | statistics.gov.scot CSV | The only published source |
| Population, percentile, indicators | Shapefile | Not in the CSVs |

Switching the rank source to the CSVs was considered and rejected: it would lose the half
ranks for 2004 to 2012, take the 2020 housing ranking that two other Government files disagree
with, change the 4.0.0 domain columns in a second breaking release, and drop the populations
that reproduce the PHS weighted bands.

#### The gate that ties the bands to our ranks

A band belongs to the ranking it was cut from, so every build compares each CSV rank with the
shapefile rank of the same edition, domain and zone before any band is used:

- **Equal**, or
- **a known difference, pinned exactly:** in 2004 to 2012 a half rank in the shapefile and the
  same rank rounded up in the CSV (checked per zone, not by count); in 2020v2 the 628 housing
  zones, listed by code with both ranks.

Anything else stops the build: a different ranking has appeared and its bands cannot be trusted
to describe ours. The same gate checks that every zone is present once per edition and domain,
that bands are whole numbers in range, that bands never decrease as the published rank rises
(split ties allowed), and that 2004 has no crime bands.

#### Sources

The three CSVs are pinned in `sources.yaml` like every other source: URL, SHA256 and size, read
offline from `manual_data`. Before relying on them:

- **Confirm the download addresses are stable.** statistics.gov.scot may be moving platform
  (the review calls it the Data about Scotland portal), and the 2020 dataset says it will not be
  updated. A pinned hash protects the content, not the address; the files must be kept in
  `manual_data` so the build never depends on the site.
- **Record the licence**, expected to be the Open Government Licence as for the other
  Government sources.

#### Open decision: 2020v2 housing

Its published bands were cut from a housing ranking that differs from ours in 628 zones. Under
the 2020 convention that difference changes a band for two zones only, 1 decile and 2
vigintiles, and no quintile (see the findings). Options:

1. Copy them anyway and document that they belong to the CSV's housing ranking.
2. Copy them with an explicit source-disagreement status on the 628 zones.
3. Withhold 2020v2 housing bands until the Government says which ranking is authoritative.

**Recommended, supported by review: option 2.** It keeps both publications' values as
published and does not have HIC decide which Government file is wrong:

- Housing ranks stay from the shapefile, which agrees with the ranks workbook.
- The 2020v2 housing bands are copied from the CSV like every other domain band.
- The 628 zones are listed in a pinned audit file with both ranks; the gate tests against that
  exact list, so any further disagreement fails the build.
- The status means **the two Government sources disagree on this zone's housing rank**, never
  "this band is wrong": for 626 of the 628 the band is the same either way. It must not be set
  for the tie-convention pair, whose ranks agree.

Ask the Government's SIMD team which 2020 housing ranking is authoritative, without blocking
the feature on the answer.

#### Scope

Unweighted Scotland quintile, decile and vigintile, as published: 3 bands for each of the 41
edition-domain pairs, 123 columns per table if carried in both. Weighted domain bands would
still be HIC's extension of the PHS method (stage 2 passes everywhere), a separate decision. No
sub-geography domain bands, and no comparison across editions is implied.

**Decision, 30 September 2026: recorded after review.** Copy the Scottish Government's
published domain quintiles, deciles and vigintiles, unweighted and for Scotland, for every
edition, from the three statistics.gov.scot CSVs; keep every rank from the shapefiles; gate
each CSV rank against the shapefile rank with the known differences pinned exactly. For 2020v2
housing, option 2: copy the bands with an explicit source-disagreement status on the 628 zones,
and ask the Government which ranking is authoritative without blocking on the answer. No
derived domain bands and no weighted domain bands. Implementation: `Domain_Bands_Plan.md`.

## Deciding, after review

*Drafted before the test found published domain bands for every edition; the recommendation
above supersedes this table, which assumed derivation.*

| Outcome | Recommendation |
| --- | --- |
| Stage 1 passes, stage 3 deviations small (a few zones per band) | Plan unweighted Scotland domain quintiles and deciles, labelled derived by HIC with the rule named, and a decision entry |
| Stage 2 passes for an edition as well | Weighted Scotland domain bands may be planned for that edition, labelled the same way |
| Stage 1 fails, or stage 3 shows large or erratic deviations | No domain bands; record why and keep the ranks only |

Whatever the result: no sub-geography domain bands, no vigintiles (a twentieth is too small
for the ties to settle), and no comparison across editions is implied, since domains and
indicators changed between them.

## Effort

About an hour for stages 1 to 3 and a short write-up of the numbers into this plan; the
external search separately. Implementation, if a reviewed decision chooses it, would be a new
plan and a release of its own: new columns, schema bump, SQL measures, Python labels and
tests. None of that is part of this plan.
