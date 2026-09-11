# How the table is built

A reviewer starts here. Six decisions explain how the table is made. Each one names the
file and function where it lives, and the check that guards it.

Next read `results/BUILD_REPORT.md`, the same steps with that run's numbers, then use
[the data dictionary](DATA_DICTIONARY.md) for individual fields. `results/manifest.json`
holds all check records. The [decision log](../simd_ingest/decisions.yaml) is authoritative
for current choices and their supersessions; [old plans](plans/README.md) are background only.

## The data flow

```text
13 pinned objects ─► 17 files, hashes verified
        │
        ├─ SmallUser.csv + LargeUser.csv ──► postcode_index   247,773 records, key = postcode + introduction date
        ├─ 6 PHS files ────────────────────► phs_bands        39,972 rows, one per edition and data zone, 1 = most deprived
        └─ 6 shapefile tables ─────────────► govscot_bands    39,972 rows, unweighted bands and population
                                                    │
        postcode_index + phs_bands + govscot_bands ─► postcode_simd   12 joins on the data zone, one edition at a time
                                                    │
                                     written, reopened, re-checked, manifest and build report
```

## The six judgements

**1. What a postcode key is.** `pc_norm` is the postcode uppercased with spaces removed, keeping any
A, B or C suffix NRS added when it split the postcode. `pc_base` removes that suffix, and only
from a small-user record flagged as split. A record is identified by `pc_norm` with its
introduction date, because a postcode can have several lives.
`core/spd.py`, `postcode_keys`. Check: `spd.primary_key_unique`.

**2. When a record is valid.** From its introduction date up to but not including its deletion
date; no deletion date means current. A record whose two dates are equal is kept but is never
valid on any day. `core/spd.py`, `parse_dates` and `active_on`. Checks: `spd.strict_overlaps`,
`spd.touching_pairs`.

**3. Which way the PHS bands run.** PHS publishes 2004 and 2006 with 1 meaning least deprived,
the reverse of every later edition. Those two are turned, `11 - decile` and `6 - quintile`, so
that 1 means most deprived in every column. Ranks and the two 15% flags are never touched.
`core/phs.py`, `canonicalise_phs`. Check: `phs.<edition>.rank1_in_band1`, which requires the
most deprived zone to sit in band 1 after the turn.

**4. Which data zone to join on.** Editions 2004 to 2012 are on 2001 data zones, so they join
through `DataZone2001Code`; 2016 and 2020v2 through `DataZone2011Code`. The directory's 2022
zones are carried but unused. `core/join.py`, `join_edition`. Checks per join:
`rows_unchanged` and `every_record_matched`.

**5. Which geography a within-board band belongs to.** PHS computes within-board bands inside
the board it assigned the data zone to, which is not always the board the directory assigned
the postcode to. The PHS assignment travels with the band as `phs_dz<vintage>_hb`, `_hscp`,
`_ca`. `core/join.py`, the geography columns in `join_edition`.

**6. Published bands are authoritative.** Apart from the explicit early-edition reversal above,
every band is copied from its publisher. No band is reconstructed from rank or population,
and population-weighted bands are not compared with unweighted bands. The population
reconstruction diagnostic was removed on 11 September 2026; the earlier diagnostic-only
policy is historical. PHS and government ranks must agree on the same data zones in every
edition, and the directory's 2020 rank must agree with the attached rank.
`core/crosscheck.py` and `core/join.py`. Checks:
`cross.<edition>.same_zones`, `cross.<edition>.rank_identical`.

## What the saved-file check proves

`core/output.py`, `readback`, reopens the Parquet before replacement. Original and derived
postcode fields must equal the accepted index; null must not replace a supplied value or
source blank. Each attached value is looked up again through the saved data-zone code.
The embedded band convention, schema version, release, source pins and decision hash must
also equal the build contract. The source hashes and schema alone do not prove this.

The CLI and Dagster call the same `core/join.py`, `build_postcode_simd`, for the twelve
joins. Dagster's stages record their checks in its event log; the final stage collects the
records from **that run**, including all 17 source verifications. Missing evidence prevents
publication. Neither the narrative report nor the manifest invents an upstream pass.

For example, the current `AB12 3GQA` record illustrates the direction change without hiding
the source value. These values were checked against the pinned files and saved SPD 2026/2 build:

| Edition | Data-zone key | Published PHS Scotland quintile | Transformation | Saved quintile |
| --- | --- | ---: | --- | ---: |
| 2004 | `S01000336` (2001 vintage) | 2 | `6 - 2` | 4 |
| 2020v2 | `S01006848` (2011 vintage) | 4 | None | 4 |

This example explains the operation; `readback.attached_values` checks every attached value
across the whole table, not just the example postcode.

## Two judgements that live in the lookups, not the table

The table carries every record and every value. What to do with them is decided at lookup
time, in `simd_ingest/lookup.py` and `docs/sql/link_by_era.sql`:

- **Split postcodes** resolve to the A part, as NRS does in its own statistical lookup, unless
  `split="report"` asks for the ambiguity instead.
- **PO boxes** and other large-user postcodes with no linked small-user postcode are excluded,
  as the PHS guidance does, unless `include_po_boxes=True`.

## Where to look when something is wrong

| Symptom | Look at |
| --- | --- |
| A source changed | `source.hash.<file>` in the manifest; the build stops before reading it |
| A join lost or gained rows | `join.<kind>.<edition>.rows_unchanged` |
| A postcode got no value for an edition | `join.<kind>.<edition>.every_record_matched`; its data zone is not in that edition |
| A band looks reversed | `phs.<edition>.rank1_in_band1` |
| A supplied value became null | `readback.index.<column>` or `readback.attached_values` |
| The file describes the wrong convention or sources | `readback.metadata.<field>` |
| A Dagster report lacks upstream evidence | `orchestration/evidence.py`; the final stage refuses publication |
| One record, end to end | `python -m simd_ingest.trace "<postcode>"` |
