# Postcode-SIMD reference tables

A CLI pipeline that rebuilds two postcode-to-SIMD tables from hash-pinned public files.
Routine maintenance is a refresh of one of the two NRS postcode products. Adding a SIMD
edition is a separate, less frequent change to the source registry and output schemas.

| Table | Postcode source | One row per | Key | Answers |
| --- | --- | --- | --- | --- |
| `postcode_simd.parquet`, the **main table** | Scottish Statistics Postcode Lookup (SSPL) 2026/1 | whole postcode, latest life, both user types: 229,708 rows × 146 columns | `pc_norm` | what is this postcode's SIMD now |
| `postcode_simd_history.parquet`, the **history table** | Scottish Postcode Directory (SPD) 2026/2 | postcode life, both user types: 247,773 rows × 162 columns | `pc_norm`, `introduced_on` | what was this postcode's SIMD on a date |

Six SIMD editions (2004–2020v2) are attached to both. The two NRS products allocate data
zones differently: the SSPL takes the zone containing the centroid of the postcode's 2022
output area, the SPD the zone containing the postcode itself. On SSPL 2026/1 against SPD
2026/2 the 2011 data zone differs for 6,189 postcodes current in both, which changes the
2020v2 Scotland quintile of 3,844 of them. Every build reports these counts. PHS builds
its own lookups from the SPD, so use the history table where agreement with PHS practice
matters. Each new release replaces its table completely.

## Start here

For a human review, read [How it is built](docs/HOW_IT_IS_BUILT.md), then the build's
`results/BUILD_REPORT.md`. The report shows the actual checks, changes since the previous
snapshot, and an example postcode. [Updating the sources](docs/UPDATING.md) is the maintenance
runbook. The data dictionaries describe the columns of the [main](docs/DATA_DICTIONARY.md) and
[history](docs/DATA_DICTIONARY_HISTORY.md) tables.

## Install and build

Python 3.12 or newer; runtime versions are pinned in `pyproject.toml`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Verify files already supplied under manual_data/, then rebuild.
simd-ingest build

# Or download the explicitly pinned release, then rebuild.
simd-ingest build --source-mode download
```

`python -m simd_ingest.cli` is equivalent to `simd-ingest`. Settings live in
`config/workflow.yaml`; use `--config <path>` for a separate review output directory.

```bash
simd-ingest fetch --source-mode download  # download/verify only
simd-ingest audit --source-mode download  # read-only audit of data/sources and results
python -m simd_ingest.trace "AB12 3GQ"     # follow one main-table record back to its source rows
python -m simd_ingest.trace "AB12 3GQA" --table history
python -m pytest tests -q
```

Offline mode never accesses the network. Audit never downloads or repairs files, regardless
of source mode. Download mode rechecks cached hashes; it does not discover or accept “latest”
automatically.

## What a build leaves

- `results/postcode_simd.parquet`: the main table, keyed by `pc_norm`.
- `results/postcode_simd_history.parquet`: the history table, keyed by `(pc_norm, introduced_on)`.
  Release is metadata/an attribute of each table, not part of its key.
- `results/BUILD_REPORT.md`: the human review entry point, including the agreement between the two tables.
- `results/manifest.json`: all checks, observations, input pins and both tables' fingerprints.
- `results/runs/<run-id>/`: retained configuration/source/schema/decision snapshots,
  runtime and code hashes, and that run's report. Failed builds retain their error and checks too.

The build writes both candidates, reopens them and checks saved values and metadata before
replacing the current tables. Validation failure leaves the previous publication untouched. Run
one writer per results directory; files are replaced atomically individually, not as a multi-file
transaction. After an interrupted publication, run `audit`; if it fails, rebuild from pinned
sources. Keep `results/runs`, source archives and the corresponding code in your backups.
Old table copies are not retained.

There is no scheduler, server, intermediate-table cache or orchestration database.
The old orchestration plans remain [historical records](docs/plans/README.md).

## Use the tables

The main table has one row per whole postcode, so a present-day question is one lookup:

```sql
SELECT pc_norm, is_current, simd2020v2_pw_scotland_quintile
FROM 'results/postcode_simd.parquet'
WHERE pc_norm = 'G718BQ';
```

The history table keeps every life and the NRS split parts. A question about a date, or
about which split part applies, goes there:

```sql
SELECT pc_norm, pc_base, introduced_on, deleted_on, simd2020v2_pw_scotland_quintile
FROM 'results/postcode_simd_history.parquet'
WHERE pc_base = 'G718BQ' AND introduced_on <= DATE '2015-06-01'
  AND (deleted_on IS NULL OR deleted_on > DATE '2015-06-01');
```

`pc_norm` removes ASCII spaces; in the history table it keeps the NRS split suffix and
`pc_base` removes a validated suffix from a flagged small-user record. Original postcode text
is preserved. PHS population-weighted fields (`pw`) and Government unweighted fields (`uw`)
are distinct.

For cohort linkage, start with [Two SQL lookups](docs/LINKAGE_BY_ERA.md): run the
[shared setup](docs/sql/create_latest_postcode_lookup.sql) on the history table, then choose
[one SIMD edition](docs/sql/link_latest.sql) or [edition by event year](docs/sql/link_by_era.sql).
Both use latest postcode geography, the A part for ordinary split postcodes, and linked
small-user geography for large users, with explicit statuses and both record keys.

The [Python helpers](docs/EXAMPLES.md) read either table: current lookups against the main
table, current or as-of lookups against the history table, with own-record geography and an
optional split consensus/conflict policy. A dated question against the main table is refused.
Exclusions remain consumer choices, not deletions from the tables. Adding a source edition
does not automatically change the analyst's edition-by-year policy.

## Optional Docker runner

```bash
docker compose build
docker compose run --rm build
docker compose run --rm test
```

This packages the same CLI, with sources and results mounted from the host.
See [Docker](docs/DOCKER.md) for offline and audit commands.

## Code to read

`cli.py` handles arguments; `pipeline.py` contains the single build sequence.
`core/sspl.py` and `core/spd.py` read the two postcode products, `phs.py`, `govscot.py`,
`join.py` and `output.py` contain the shared data rules, and `core/agreement.py` compares the
two tables. `sources.yaml` declares sources and editions, `sspl_schema.yaml` and
`spd_schema.yaml` declare the postcode file headers, `output_schema.yaml` and
`output_schema_history.yaml` declare the saved tables, and `decisions.yaml` records policy.
Tests include synthetic postcode refreshes of both products, a new SIMD edition/vintage,
corrupted inputs and saved files; downloaded-data tests also pin both tables' rows-only
fingerprints.
