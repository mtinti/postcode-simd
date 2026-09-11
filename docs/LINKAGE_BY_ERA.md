# Linking a cohort to SIMD by era

The PHS deprivation guidance for analysts, version 3.5, gives two ways to handle data that
spans years. The first, "the most appropriate release for each period", re-assigns each event
to the edition recommended for its year, so the deprivation categories are the best available
picture at each point in time. The second uses one edition throughout. This document is the
first approach, in Python and in SQL, and shows that the two give the same answer.

## The rule

For each event:

1. **Edition from the year.** Table 4 of the guidance maps years of health data to an edition.
   1996 to 2003 use SIMD 2004; 2004 to 2006 use 2006; 2007 to 2009 use 2009v2; 2010 to 2013
   use 2012; 2014 to 2016 use 2016; 2017 onwards use 2020v2. Before 1996 there is no SIMD
   edition, and the guidance points to the Carstairs index instead.
2. **Record from the date.** The directory record valid on the event date, by the half-open
   rule `introduced_on <= date < deleted_on`. A postcode as written matches every record whose
   base it is, which includes an old unsplit life and the current split parts. A full NRS key
   with its suffix matches its own part only.
3. **Value from the edition's column.** The measure is the PHS population-weighted
   within-Scotland quintile unless you choose another.
4. **Resolve.** One valid record gives `unique`. Several valid split parts give `a_part`:
   the A part is used, as NRS does when it builds the Scottish Statistics Postcode Lookup,
   because A is the part with more addresses. A known postcode with no valid record on that
   day gives `deleted`. An unknown or missing postcode gives `not_found`. An event before 1996
   gives `no_edition`, with every SIMD column null including the matched key.

   Under the report rule, `split="report"` in Python or the three marked lines deleted in the
   SQL, several parts that agree give `split_consensus` with the shared value and parts that
   disagree give `split_conflict` with a null value. Neither rule averages or votes.

## In Python

```python
import pandas as pd
from simd_ingest import lookup

t = lookup.load("results/postcode_simd.parquet")
cohort = pd.read_csv("my_cohort.csv")        # id, postcode, event_date

out = lookup.attach_by_era(cohort, t, "postcode", "event_date")
out[["id", "postcode", "event_date", "simd_edition", "simd_status", "simd_value", "simd_pc_norm", "simd_label"]]
```

Five columns are added and no row is dropped or duplicated. `simd_label` is per row, since
the edition varies: for example `SIMD 2012, PHS population-weighted, within-Scotland quintile,
1 = most deprived, split postcodes resolved to the A part`. Pass `measure="pw_hb_decile"` or
any other SIMD column suffix to change the measure for every row, and `split="report"` to
refuse split postcodes instead of taking the A part.

## In SQL

`docs/sql/link_by_era.sql` is the same rule as one query. It reads two relations, `events`
with `id`, `postcode` and `event_date`, and `postcode_simd`, and returns one row per event
with `simd_edition`, `simd_status`, `simd_value` and `simd_pc_norm`. It uses nothing beyond
common table expressions, a window function, `CASE` and `COUNT(DISTINCT)`, so it runs
unchanged on DuckDB and SQL Server. The one line that differs is how `postcode_simd` is
exposed.

DuckDB, straight from the Parquet file:

```python
import duckdb, pandas as pd
con = duckdb.connect()
con.execute("CREATE VIEW postcode_simd AS SELECT * FROM 'results/postcode_simd.parquet'")
con.register("events", pd.read_csv("my_cohort.csv"))
out = con.execute(open("docs/sql/link_by_era.sql").read()).df()
```

SQL Server, once the table has been loaded through RDMP or otherwise: create `events` as a
table or temporary table, make sure `postcode_simd` resolves to the loaded table, and run the
file as it is. Both date columns are `DATE`, so the comparisons need no conversion.

To change the measure, edit the six lines of the `CASE` that picks the column. To report
split postcodes instead of taking the A part, delete the three lines marked `-- A part`.

## The two agree

`tests/test_lookup.py` builds a synthetic cohort of 1,940 events from the real directory:
current and deleted postcodes, split parts by full key and by base, unknown and missing
postcodes, written with a space and in mixed case, with dates from 1994 to 2026. It runs
both implementations under both rules and asserts the same status, value, matched key and
edition for every event. No patient data is involved; the postcodes come from the directory
itself.

| Status | Default rule | Report rule |
| --- | ---: | ---: |
| `unique` | 1,194 | 1,194 |
| `deleted` | 396 | 396 |
| `not_found` | 175 | 175 |
| `no_edition` | 119 | 119 |
| `a_part` | 56 | |
| `split_consensus` | | 29 |
| `split_conflict` | | 27 |

The high `deleted` share is a property of the synthetic cohort, which deliberately samples
deleted postcodes and pairs them with random dates. A real cohort, where the postcode was
recorded at the time of the event, should see far fewer, and each one is worth a look: it
means the address on the record was not a live postcode on that date.

## PO boxes are excluded by default

The guidance's Appendix A attaches no deprivation to PO boxes and other large-user postcodes
with no linked small-user postcode, because their location is a sorting office rather than a
home. The directory nonetheless assigns them a data zone, and the table keeps it. Both
implementations therefore exclude those records at lookup time by default, and an event
whose postcode is a PO box comes back `not_found`. In the synthetic cohort 137 events change
status under this rule, almost all from `deleted` or `unique` to `not_found`.

To attach whatever the directory assigns, pass `include_po_boxes=True` in Python, or delete
the one predicate line marked in the SQL. To go the other way and exclude every large-user
record, pass `include_large_users=False`, or add `AND p.spd_user_type = 'small_user'` beside
that predicate.

## Things to keep in mind

- **This is the first of the guidance's two approaches.** Its strength is that each period
  gets the best available categories; its cost is that the data zones inside a quintile change
  between editions, so a trend across an edition boundary mixes a real change with a change
  in the index. For tracking fixed areas over time, use one edition throughout, which is a
  single `attach` call or a fixed `edition` in the SQL.
- **Rates need matching denominators.** The guidance recommends rates over counts by
  deprivation category, and the population year of each edition is in the data dictionary.
  Denominators are not in this table.
- **Within-board bands are for within-board analyses.** The example uses the within-Scotland
  quintile. If you switch to `pw_hb_*`, report against the board in `phs_dz{vintage}_hb`, and
  do not compare boards with each other.
- **Splits are rare and real.** In this cohort 56 of 1,940 events hit a split postcode. Under
  the default they take the A part, which is what every official statistic built from the
  SSPL does. Under the report rule about half agree anyway and the rest conflict, where the
  two parts of one postcode sit in different quintiles. Only more precise address data can
  decide those; the A part is the majority-address convention, not a measurement.
- **Pre-1996 events are not an error.** `no_edition` says the guidance has no SIMD for that
  year. The postcode record may well exist; a plain as-of `lookup` without an edition will
  find it if you need the data zone.
