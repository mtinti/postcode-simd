# How the table is built

One page for a reviewer. Six things carry judgement; everything else is copying values across
on a key. Each one names the file and function where it lives, and the check that guards it.

Every build also writes `results/BUILD_REPORT.md`, the same steps with that run's numbers.

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

**6. Nothing is calculated, and the sources are trusted.** Every band is copied from a published
file. The only cross-source check is that PHS and the Scottish Government describe the same data
zones with the same ranks in every edition, which is what makes joining them on the data zone
meaningful. No band is recomputed from a formula or from population, and no band is compared
between the two publishers; each is trusted for its own values. `core/crosscheck.py`. Checks:
`cross.<edition>.same_zones`, `cross.<edition>.rank_identical`.

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
| One record, end to end | `python -m simd_ingest.trace "<postcode>"` |
