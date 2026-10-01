# Plan: population-weighted SIMD domain bands

Drafted 30 September 2026, revised the same day after review (complete-zone tests, the leading
zero-population case, attribution). Status: implemented for release 6.0.0
(decision computed-weighted-domain-bands).

## Aim

Give each SIMD domain rank a population-weighted Scotland quintile and decile, computed by a
midpoint rule validated against PHS's published overall bands, for every edition, in both tables. These would be the first
values in the tables that the build computes rather than copies: PHS publishes weighted bands
for the overall index only, and nobody publishes them for domains.

## Why a decision comes first

Decision `bands-are-looked-up` says every band is copied from a published file and none is
calculated from a rank. Weighted domain bands cannot be copied, so they need an explicit
exception, recorded as its own decision, with every column labelled as computed. The
Government's published unweighted domain bands (5.0.0) stay as they are: this adds a second
basis beside them, never a replacement.

## What is already known

From `Domain_Ntiles_Test_Plan.md` (stage 2) and a re-run on 30 September 2026, using the
population column in each Government shapefile:

| Band | Result against PHS's published overall bands |
| --- | --- |
| Scotland quintile and decile | exact: zero mismatches in all six editions |
| Health board, HSCP, council | nearly exact: none in 2006 and 2009v2; one zone per series in three areas in 2004 and in one council in 2012; 1 to 4 zones per series in Orkney, Shetland and the Western Isles in 2016, and in Shetland in 2020v2 |
| Most and least deprived 15% flags | one zone off in 2009v2 and in 2012 |

The rule, zones ordered by rank:

```
midpoint = cumulative population through the zone - half the zone's population
band     = max(1, min(k, ceil(midpoint * k / total population)))
```

The populations: the 2001 Census for 2004, then NRS small-area estimates for 2004, 2007, 2010,
2014 and 2017, one per edition. A zone's population differs between editions, which is why the
rule reproduces PHS only with the matching edition's column.

Two facts the reproduction cannot settle:

- **Ties.** The overall rank has none, so PHS's handling of ties is untested. Domain ranks have
  5,188 tied groups. The rule here treats a tied group as one block: the cumulative population
  through the whole group, minus half the group's population, so tied zones always share a band.
  That is a project choice; the Government's own unweighted domain bands sometimes split a tie.
- **Zero-population zones.** 1 in 2009v2, 3 in 2012, 2 in 2016, 3 in 2020v2. They carry no
  weight and take the band of their midpoint, as in the reproduction. Without the lower bound, a
  zero-population group ranked first would have midpoint 0 and band 0; `max(1, ...)` puts it in
  band 1. No current edition has that case, but the rule must define it. A total population of
  zero is refused: there is nothing to weight by.

## Step 0: before any code

1. **Ask PHS** whether they compute weighted domain bands, or have a view on doing so by their
   method. A published or endorsed method would change this plan; the feature does not start
   until the question is asked.
2. **Record the decision**, including the exception to `bands-are-looked-up`, the tie rule, and
   whether the population is stored (section 4).

**Decision, 1 October 2026.** Implement as planned, with the recommendations: computed
population-weighted Scotland quintile and decile of every domain rank, an exception to
`bands-are-looked-up` recorded as its own decision; equal ranks grouped together; the six
population columns stored. PHS is to be asked in parallel; the work does not wait for the answer,
and the attribution stays "computed" unless PHS says otherwise.

## Design

### 1. Where they are computed: per data zone, from the source

In the Government reader, per edition, from the shapefile's own rows: every zone of the
edition once, with that edition's population. Never from the output tables, which have one row
per postcode or postcode life, repeat each zone once per postcode, and do not hold every zone
(the main table represents 6,972 of the 6,976 2011 zones): weighting over their rows would count
a zone's population once per postcode and drop missing zones from the total.

### 2. The gate, on every build

Before any domain band is written, the same function must reproduce PHS's published overall
Scotland quintile and decile exactly, from the overall rank and the same population, for every
edition. Any mismatch stops the build. The derivation is thereby checked against PHS on every
build, not once. Sub-geography bands are not part of the gate and not produced (section 6).

Further checks: every band whole and within 1 to 5 or 1 to 10; bands never falling as the rank
rises; tied zones always in the same band; the population share of each band recorded as an
observation, expected within a few hundredths of a percentage point of a fifth or tenth.

### 3. Columns

Per edition and published domain: `simd{edition}_{domain}_domain_pw_scotland_quintile` and
`_decile`, type `int8`, not nullable, source `computed`. 41 pairs by 2 bands: 82 columns per
table, appended after every existing column, so the 354 history and 311 main columns keep their
positions and fingerprints. No 2004 crime columns. Each note says: Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government. Reproducing
PHS's overall bands validates the rule; it does not make PHS the author of these bands or
endorse the tie rule, so the bands are described as computed until PHS says otherwise (step 0).

### 4. The population, optional

`simd{edition}_population`, six columns, type `int32`: the zone's population in that edition's
shapefile. Stored only if the decision says so, for transparency. Its note must say it is the
data zone's population repeated on every postcode in the zone, and must never be summed or used
to weight across rows. Recommendation: store it; without it an analyst cannot see the weight
behind a band.

### 5. Readback, trace, SQL and Python

- Readback and trace recompute the bands from the pinned sources through the same function,
  independently of the build's tables, and compare exactly.
- SQL: seven `computed_pw_{domain}_domain_quintile` and seven `_decile` measures, chosen by
  edition, null where an edition did not publish the domain; the core grows by 14. The prefix
  says they were computed by this pipeline, not published, beside `phs_` and `gov_` for the
  published measures. The walkthrough carries the decile only, beside the published unweighted decile, so
  the two bases are never confused.
- Python: `income_domain_pw_scotland_decile` and so on, labelled "Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government". The 2020v2 housing source status applies as it
  does to the published bands: these are cut from the shapefile rank, which the status describes.

### 6. Scope

Scotland quintile and decile only. Not produced: health board, HSCP or council bands, which PHS's
own bands show are not exactly reproducible; 15% flags, off by a zone in two editions; weighted
vigintiles, which PHS does not publish for the overall index either; any comparison across
editions.

### 7. Documents

The data dictionaries; `LINKAGE_BY_ERA.md` and `EXAMPLES.md` state the three domain bases side
by side (published unweighted bands, computed weighted bands, and the ranks), and that the
weighted ones are derived; a decision entry; the plan index.

## Tests

- **The gate.** A synthetic edition whose published PHS bands the rule does not reproduce stops
  the build; the real editions pass.
- **The rule by hand.** A few zones with known populations and a tie: the tie shares a band, the
  cut points fall where the arithmetic says, a zero-population zone takes its midpoint's band, a
  zero-population group ranked first takes band 1, and a zero total population is refused.
- **Order independence.** Shuffling the source rows changes no band.
- **Real values, on the source.** The population share of each band, computed on the complete
  source-zone reference (every zone of the edition once, with its population), never on a
  postcode table; an example zone per edition checked by hand against its rank and population.
- **The postcode rows cannot move a band.** Agreement between the main and history tables is not
  proof: both could share one wrongly computed lookup. The test instead adds and removes postcode
  rows, duplicates some and drops every postcode of some zones, and checks that no band changes.
  The trap is real: even one row per zone from the main table leaves out the four 2011 zones it
  lacks, three with no population and S01011598 with 801 residents in the 2017 estimates, and
  that alone changes five 2020v2 income-decile assignments (checked 30 September 2026).
- **Readback and trace** catch a changed band; the SQL core and Python labels as above;
  fingerprints of the existing 354 and 311 columns unchanged; SQL Server round trip.

## Release

6.0.0: both schemas, the CSV digests, the SQL output and the loader's expectations change.

## Effort

About a day, most of it tests and documents; the computation itself is one function already
written for the feasibility test.
