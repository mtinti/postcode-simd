# Two SQL postcode-to-SIMD lookups

Both examples use the latest postcode geography, resolve ordinary split postcodes to A,
and use the linked small-user record for a large user. Only the SIMD edition choice differs.
The imported table is unchanged: it still holds every directory life and each record's own
source geography and attached SIMD.

| Question | Query | Edition choice |
| --- | --- | --- |
| One edition for the whole cohort | [link_latest.sql](sql/link_latest.sql) | Explicit choice; defaults to 2020v2, the newest configured edition |
| Appropriate edition for each event year | [link_by_era.sql](sql/link_by_era.sql) | PHS guidance v3.5, Table 4 |

"Latest" does not mean reconstructing the patient's address at the event date. A reused
postcode uses its latest geography even for an old event. The date in the second query
selects an **index edition**, not an older postcode life.

## Run the examples

First expose the validated imported table as `postcode_simd`, then run
[create_latest_postcode_lookup.sql](sql/create_latest_postcode_lookup.sql). This creates
`simd_postcode_latest`, a view with one row per ordinary postcode. The postcode selection
rules live there once, rather than being copied into both queries.

For DuckDB, from the repository root:

```python
from pathlib import Path
import duckdb
import pandas as pd

sql = Path("docs/sql")
events = pd.read_csv("my_cohort.csv", dtype={"postcode": "string"})
# Required only for link_by_era.sql. Reject invalid text; do not silently coerce it.
events["event_date"] = pd.to_datetime(events["event_date"], errors="raise")

with duckdb.connect() as con:
    con.execute("CREATE VIEW postcode_simd AS SELECT * FROM 'results/postcode_simd.parquet'")
    con.execute((sql / "create_latest_postcode_lookup.sql").read_text())
    con.register("events", events)
    latest = con.execute((sql / "link_latest.sql").read_text()).df()
    by_era = con.execute((sql / "link_by_era.sql").read_text()).df()
```

The fixed-edition query only needs `events(id, postcode)`. The era query additionally needs
`event_date` typed as a date or timestamp, not unvalidated text; establish the study's time
zone before deriving event years. Both retain repeated/null IDs and identical input rows.
They return the explicitly listed columns, not every cohort column. SQL row order is not
guaranteed; include your own event identifier and `ORDER BY` if order matters.

For SQL Server, import `postcode_simd` with its natural key `(pc_norm, introduced_on)`,
date-typed introduction dates and a bit/boolean `is_current`. Provide the `events` relation,
and execute the shared `CREATE VIEW` in its own batch before either query. The files use
common T-SQL/DuckDB constructs, but automated execution is currently tested only on DuckDB.
The separate-batch requirement is documented by
[Microsoft](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-view-transact-sql?view=sql-server-ver17).

A view reflects changes to its underlying table; it does not need rebuilding for each
cohort. If importing a new snapshot drops/recreates the table, recreate the view afterwards.
For an existing view definition, use your database's normal reviewed view-update procedure.

## What comes from PHS, and what we chose

References are the downloaded
[PHS deprivation guidance v3.5](../manual_data/2023-12-phs-deprivation-guidance-v35.pdf)
and PHS's [postcode-file documentation](https://publichealthscotland.scot/resources-and-tools/health-intelligence-and-data-management/geography-population-and-deprivation-support/geography/postcode-file/).
Page numbers below are printed page numbers, not PDF viewer numbers.

1. **Postcode version and splits.** The PHS postcode page describes latest versions,
   including some deleted records, and using only the A part of split postcodes. The view
   first takes the newest introduction for each complete NRS key, across both user types.
   It then prefers live records, whole/A records, and newest introduction, in that order.
   That ordering is our explicit implementation policy. A newer B part never displaces a
   live A part. If only B/C is live, no older deleted whole/A record is substituted.
   No B/C fallback or averaging is used for an ordinary postcode.
2. **Large users.** Appendix A, pp. 28–30, explains that usable geography is required and
   large users may be linked to small users. As agreed for this project, the SQL follows
   `LinkedSmallUserPostcode` and takes the latest small-user life of that exact named key.
   A specific link to B remains B: the A convention applies to ordinary postcode inputs,
   not to rewriting a supplied link. Missing links and `NO LINKP`/`NO LINK` give no SIMD;
   neither the large user's own data zone nor an older life is a fallback. If the linked
   key's newest record is now a large user, it is not accepted as a small-user target.
3. **Edition.** Sections 3.2.1.1 and 3.2.1.2 describe respectively using an appropriate
   edition per period and using one edition throughout. Neither approach is universally
   preferable: choose for the study. In `link_latest.sql`, change the two lines marked
   `EDIT EDITION` together to select another edition.
4. **Measure and direction.** Sections 3.1.1–3.1.2 distinguish PHS population-weighted
   categories and band direction. Both queries use PHS population-weighted within-Scotland
   quintiles, with 1 most deprived. The CLI already standardises the reversed 2004/2006
   bands and joins each edition through its correct data-zone vintage. SQL copies those
   values; it does not reverse them again or substitute Government unweighted bands.

Limits of the interpretation: Appendix A does not settle every case where a large user's
own and linked geography disagree. The linked route is a documented project choice, not
proof of exact equivalence to PHS's published postcode lookup. The view also keeps the last
known version for every ordinary postcode in our snapshot, including wholly deleted ones;
PHS's exact deleted-record retention criteria have not been reproduced. Equal-priority
representatives are flagged and receive no SIMD. A retained deleted link target is visible
through `simd_source_is_current`, rather than silently treated as live.

The joins normalise the supplied postcode by uppercasing and removing ASCII spaces;
the original input stays in the output. Input must be an ordinary postcode, not a full
NRS key with an A/B/C suffix. Normalisation does not repair invalid postcodes. The imported
`pc_base` is already derived from validated directory records, not guessed from patient text.

## Edition by event year

The six rows in `link_by_era.sql` transcribe Table 4 (p. 17):

| Years of health data | SIMD edition |
| --- | --- |
| 1996–2003 | 2004 |
| 2004–2006 | 2006 |
| 2007–2009 | 2009v2 |
| 2010–2013 | 2012 |
| 2014–2016 | 2016 |
| 2017 onwards | 2020v2 |

Before 1996 the query returns `no_edition`; it does not invent a SIMD or calculate Carstairs.
A missing date returns `missing_date`. Edition and value are null in both cases, but postcode
provenance can still be present. These date statuses take precedence over postcode problems.

A postcode refresh changes the underlying snapshot, not this year mapping. To add a new
SIMD edition, first extend and validate ingestion, then expose its column in the shared view.
Change the fixed-edition default only by a deliberate analyst decision. Change the era rows
and edition-selection `CASE` only after reviewing the new recommendation; installing a new
edition must not silently reclassify old events.

## Read the result

`simd_edition` and `simd_measure` identify the requested index, weighting, scope and direction.
`simd_status` records the linkage route or why no value was assigned:

| Status | Meaning |
| --- | --- |
| `matched` | The ordinary small-user record supplied its own SIMD |
| `a_part` | The A part supplied SIMD for an ordinary split postcode |
| `linked_small_user` | The large user's named small-user link supplied SIMD |
| `missing_postcode` / `not_found` | Blank/null input / no matching ordinary postcode |
| `unlinked_large_user` | Link absent, blank or a no-link sentinel |
| `linked_small_user_not_found` | Named link is absent or its latest record is not small-user |
| `split_a_missing` | No eligible whole/A representative; B/C is not substituted |
| `ambiguous_postcode` | Equally preferred representatives; no arbitrary value chosen |
| `missing_simd` | Geography resolved, but the selected edition's value is null |
| `missing_date` / `no_edition` | Era query only: no date / no SIMD recommendation for the year |

All failure statuses have null `simd_value`. Matched and source natural keys are separate:
`(matched_pc_norm, matched_introduced_on)` identifies the postcode representative;
`(simd_source_pc_norm, simd_source_introduced_on)` identifies the record supplying SIMD.
For an ambiguous postcode the matched key is only one diagnostic candidate, not an accepted
match. Current flags and `spd_release` make deleted records and snapshot provenance visible.
The shared view also exposes both source data-zone vintages for a manual trace.

For SPD 2026/2, `AB11 6GN` illustrates why this matters: its own attached 2020v2 quintile is
2, but the linked `AB11 6BE` supplies 3. The SQL returns 3 and both keys. All 3,249 current
large-user records with real links resolve through a small user in this snapshot; 96 get a
different 2020v2 quintile from their own-record value. One retained deleted large user,
`EH3 9RW`, names `EH3 9PE`, whose latest life is now large-user. Its result is
`linked_small_user_not_found`, with no fallback or further link chasing. These are downloaded-data
regression examples, not expectations for every future postcode release.

For rates, use appropriate population denominators with matching definitions; this lookup
does not supply denominators or turn a quintile into an individual deprivation measurement.

## Verification and the existing Python helper

[tests/test_sql.py](../tests/test_sql.py) executes the SQL against small, hand-specified
cases and the downloaded snapshot. It covers Table 4 boundaries, postcode reuse, split A/B
disagreement, missing A, user-type changes, linked versus own SIMD, link failures, deleted
records and repeated events. It checks one lookup row per base across the real snapshot.
These are checks of the documented policy, not comparison with a PHS postcode-level oracle.

The existing [Python examples](EXAMPLES.md) remain a separate historical/record-level API.
`lookup.py` uses current-only or event-date-valid records and the selected record's own
attached geography, including for large users. It also accepts explicit NRS suffixes and
offers a split consensus/conflict mode. It has **not** been changed to implement the new
SQL policy, and Python/SQL output parity is no longer claimed.
