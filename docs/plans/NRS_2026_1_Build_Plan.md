# Plan: build both tables from the NRS 2026/1 postcode releases, on a branch

Status: implemented on branch `build/nrs-2026-1`, 30 October 2026, after three reviews.

## Aim

Produce the same two tables we publish today, `postcode_simd_history` and `postcode_simd`, from
the NRS 2026/1 releases instead of 2026/2:

- the Scottish Postcode Directory (SPD) 2026/1, for the history table;
- the Scottish Statistics Postcode Lookup (SSPL) 2026/1, for the main table.

Everything else stays as it is: the SIMD editions, the domains, the Urban Rural Classification
files, the rules and the checks. Only the postcode releases change.

The work lives on its own branch, `build/nrs-2026-1`, and is never merged into `main`. `main`
stays pinned to 2026/2. The branch is the record of how the 2026/1 files were made.

## Why

HEAL-Scot. DataLoch uses the 2026/1 releases, so HIC's tables for the project must be built from
the same releases (Michele Tinti, 30 October 2026).

## What differs between 2026/1 and 2026/2

Checked from the files on 30 October 2026.

| | 2026/1 | 2026/2 |
| --- | --- | --- |
| Royal Mail address file | January 2026 | July 2026 |
| SPD rows, all | 247,261 | 247,773 |
| SPD small users, all and live | 196,390 and 156,976 | 196,769 and 157,282 |
| SPD large users, all and live | 50,871 and 4,817 | 51,004 and 4,767 |
| SPD deleted | 85,468 | 85,724 |
| SSPL rows, all and live (counted) | 229,708 and 161,565 | 230,103 and 161,822 |
| SSPL small and large users (counted) | 187,173 and 42,535 | 187,490 and 42,613 |
| Scottish Parliament fields | `ScottishParliamentaryRegion2021Code`, `ScottishParliamentaryConstituency2021Code` | the same fields with `2026` |
| Urban Rural fields | `UrbanRural6Fold2022Code`, `UrbanRural8Fold2022Code` | the same |
| SIMD rank field | `ScottishIndexOfMultipleDeprivation2020Rank` | the same |

The SPD counts are from its bulletin. NRS publishes no SSPL counts, so those are counted from
the file. The two Parliament fields are the only header change, in `SmallUser.csv`,
`LargeUser.csv` and `SingleRecord.csv`. Every other column keeps its name and order.

Two known differences in content:

- Four split postcodes, AB31 5AS, AB54 7NS, FK14 7JX and KA6 6EY. In 2026/1, NRS swapped their
  A and B suffixes in place, so each part keeps one life from 1996 or 1973, already carrying the
  swapped area. In 2026/2, NRS undid this: each part's old life ends on 18 February 2026, and a
  new life starts with the swapped area. So for a date before 18 February 2026, these 8 parts
  give a different data zone in 2026/1 from the one in 2026/2. The 2026/1 table keeps them as
  NRS published them (checked in both built tables, 30 October 2026).
- The 2026/1 bulletin notes that two 2022 data zone names were misspelt and are now corrected.
  Our tables carry the codes, not the names, so nothing changes.

## Decisions

| Question | Choice | Why |
| --- | --- | --- |
| Rename the 2021 Parliament fields to the 2026 names, so both files have the same columns? | No. Keep the names NRS published. | They are different boundaries. A 2026 name on 2021 codes would be wrong. |
| Same output schema version as `main`? | No. A version name of its own. | The columns differ, so the schema differs. A loaded table must never be mistaken for the 2026/2 one. |
| Merge into `main`? | Never. | `main` builds the current release. This branch builds one fixed older release. |
| Publish the provenance site from the branch? | No. The branch switches off publication in its own copy of the Pages workflow (step 8). | The site describes `main`. The branch carries its own data dictionaries. |

## Steps

### 1. The branch and the sources

The branch already exists. It was created from `main` at `ca5318b` during the plan review, with a
worktree at `local/nrs-2026-1/`. The work happens in that worktree. The SPD 2026/1 files are
already unpacked in `manual_data/SPD/spd_postcodeindex_cut_26_1_csv/`.

| Release | Download | Bytes | SHA256 |
| --- | --- | --- | --- |
| SPD 2026/1 | `https://www.nrscotland.gov.uk/media/qfvgbg3y/spd_postcodeindex_cut_26_1_csv.zip` | 9,752,344 | `415d579a963c3511507bd9ac1f652a7ddd9f5a468647abf23e4cdf1cff960a95` |
| SSPL 2026/1 | `https://www.nrscotland.gov.uk/media/jypjymup/sspl-2026-1.zip` | 8,901,207 | `b8bc805567a167dd23a8891dddf44855a8174ddff3885c7f3caa0defc8d83478` |

The SSPL's `SingleRecord.csv` in `manual_data/SSPL/sspl-2026-1/` is identical to the one in that
zip (SHA256 `f239c2ba…a563`).

### 2. The registry

In `simd_ingest/sources.yaml`, following `docs/UPDATING.md`:

- `spd_release: '2026_1'` and `sspl_release: '2026_1'`;
- replace the `nrs_spd_2026_2` and `nrs_sspl_2026_2` objects with `nrs_spd_2026_1` and
  `nrs_sspl_2026_1`: URL, zip hash, and each member's path and hash;
- `spd_files` and `spd_published_totals` from the 2026/1 bulletin (table above);
- `sspl_file` counted from the file, with `totals_basis: counted`, as for 2026/2;
- no `mirror` for the NRS objects: NRS files are cited, never uploaded.

### 3. The schemas and their descriptions

Rename the two Scottish Parliament fields from `2026` to `2021` in:

- `spd_schema.yaml` (small and large users);
- `sspl_schema.yaml`;
- `output_schema_history.yaml` and `output_schema.yaml`, with a new version name for each, for
  example `postcode_simd_wide_v5_nrs2026_1` and `postcode_simd_sspl_v5_nrs2026_1`;
- `column_descriptions.yaml`: the two descriptions read from the 2026/1 data dictionary, and
  every dictionary reference pointed at the 2026/1 files;
- `description_review.yaml`: the two 2026 keys replaced by the 2021 keys. A test requires the
  same keys in both files. The two new descriptions are reviewed against the 2026/1 dictionary,
  and the new keys cite that review, not the 2 October 2026 review of the 2026 fields. That
  earlier review record is kept unchanged.

Nothing else in the schemas changes.

### 4. The decision entry

Write the entry in `decisions.yaml` now, before the build: why a 2026/1 build exists (HEAL-Scot
and DataLoch), and the decisions above.

The build copies `decisions.yaml` into its run record, writes its hash into the Parquet files
and the manifest, and the audit compares that hash with the file in the checkout. So the
decision entry must be final before the build that is delivered.

### 5. Generated files needed by the build

Regenerate, before the build:

- the SQL import and digest-check scripts (`python -m simd_ingest.sql_check`);
- the example queries (`sql_examples.py`), which select the SPD fields by name.

### 6. Build and check

From here on, the registry, schemas, export contract and decisions are frozen. Any change to one
of them means building and auditing again.

- Build in offline mode into its own results folder, `results_nrs_2026_1/`, through a separate
  configuration file. The production `results/` is not touched.
- Seed that folder with the 2026/2 Parquet files and manifest first, so the build report lists
  what differs between the releases. The comparison runs backwards in time:
  - "added" and "removed" describe the change from 2026/2 to 2026/1;
  - "newly deleted" counts postcodes live in 2026/2 and deleted in 2026/1, not deletions
    between January and July 2026.
- Read `BUILD_REPORT.md`: the published counts against the bulletin, every join and readback
  check, and the agreement between the two tables.
- Run `pytest` and `simd-ingest audit` against the same checkout and configuration. The
  regression fingerprints in `tests/known_snapshot.json` belong to the 2026/2 pins. They do not
  apply to other pins, by design, and must not be edited to make the branch pass.

### 7. Generated files that describe the build

After the build passes, generate the data dictionaries from the 2026/1 manifest, named
explicitly:

```bash
python -m simd_ingest.dictionary results_nrs_2026_1/manifest.json
```

Without the path, the generator reads `results/manifest.json`, the 2026/2 build. Check that both
`docs/DATA_DICTIONARY.md` and `docs/DATA_DICTIONARY_HISTORY.md` name release `2026_1` and carry
the new manifest's counts and fingerprints.

The dictionaries are not inputs to the build, so generating them does not require a rebuild.

### 8. Record and deliver

- A short section at the top of the branch README: which releases it builds, and that `main`
  builds the current one.
- **Switch off Pages publication on the branch, before the first push.** The Pages workflow runs
  on every push, and publishes a preview for any branch or tag other than `main`. A tag's
  preview is never removed, because the clean-up runs only when a branch is deleted. In the
  branch's copy of `.github/workflows/pages.yml`, the publish step gets the condition
  `github.ref == 'refs/heads/main'`. A tag points at a commit of the branch, so the same
  condition covers the branch push and the tag push. The provenance tests and the site build
  still run. The workflow on `main` is not changed.
- Commit, then tag that commit, for example `v6.1.0-nrs2026.1`, so the exact code that made the
  files can be cited. The commit holds the frozen inputs of step 6.
- Push the branch and its tag to GitHub. Check in the Actions log that the publish step was
  skipped for both, and that `gh-pages` gained no `preview/` folder for them.
- Upload the build's delivery set to OneDrive, in `onedrive:postcode-simd/nrs-2026-1/`, with
  `rclone copy` in the foreground:
  - `postcode_simd_history.csv.gz` and `postcode_simd.csv.gz`;
  - `postcode_simd_history.parquet` and `postcode_simd.parquet`;
  - `manifest.json` and `BUILD_REPORT.md`;
  - `CSV_README.txt`, the one named in the 2026/1 manifest's `attribution` entry. It carries
    the source acknowledgements and the release names, and the audit reads it.

  Then compare each file's size with `rclone lsl`, and copy again on a mismatch.

## Checks and tests

**Data zone coverage.** Three separate checks, because the two postcode products do not cover
the same zones:

1. **The SIMD sources are complete.** Every edition's source tables hold every zone of that
   edition: 6,505 zones of 2001, 6,976 of 2011. The build already checks this.
2. **Every postcode finds its SIMD.** Every postcode whose record names a data zone finds SIMD
   values in every edition that uses that vintage. The build's join gate already checks this.
3. **What each table covers, reported.** The number of distinct zones of each vintage in each
   table, counted and printed in the build report:

   | Table | 2001 zones | 2011 zones |
   | --- | --- | --- |
   | History, from SPD 2026/1 | 6,505 (all) | 6,976 (all) |
   | Main, from SSPL 2026/1 | 6,498 | 6,972 |

   The history table must cover every zone, and the build fails if it does not. The main
   table's gaps are a fact of the SSPL: 7 zones of 2001 and 4 of 2011 have no postcode in it.
   They are reported, never filled.

**Other checks.**

- The full suite passes on the branch, apart from the 2026/2 fingerprints, which do not apply.
- The counts match the bulletin, and the tables read back unchanged.
- The two Parliament columns hold 2021 codes. Every code is one of the 2021 Scottish Parliament
  regions or constituencies. A spot check of a few postcodes against the 2026/1 file.

**SQL Server.** The import script drops and recreates `postcode_simd`, `postcode_simd_history`
and their staging tables in whatever database it is connected to. So the test uses a new,
disposable database, `postcode_simd_nrs2026_1_test`, on the local SQL Server:

- connect to it by name, and check `DB_NAME()` before importing;
- import the 2026/1 CSVs, then run the digest check with the 2026/1 manifest's row counts and
  digest totals;
- never run it in a database that holds the 2026/2 tables;
- drop the test database by name afterwards.

## Order of work

1. Review of this plan.
2. In the worktree: the registry (step 2), the schemas and descriptions (step 3), the decision
   entry (step 4).
3. The SQL scripts and example queries (step 5).
4. Build, read the report, run the tests and the audit (step 6).
5. The dictionaries (step 7), then the SQL Server test.
6. README section, Pages publication switched off, commit, tag, push, OneDrive upload (step 8).
