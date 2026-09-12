# Postcode-SIMD reference table

A CLI pipeline that rebuilds one postcode-to-SIMD table from hash-pinned public files.
Routine maintenance is a postcode-directory refresh. Adding a SIMD edition is a separate,
less frequent change to the source registry and output schema.

The current source configuration is SPD 2026/2 and six SIMD editions (2004–2020v2):
247,773 directory records × 162 columns. Current and deleted records, both user types,
remain in the table. Each new directory release replaces the snapshot completely.

## Start here

For a human review, read [How it is built](docs/HOW_IT_IS_BUILT.md), then the build's
`results/BUILD_REPORT.md`. The report shows the actual checks, changes since the previous
snapshot, and an example postcode. [Updating the sources](docs/UPDATING.md) is the maintenance
runbook. The [data dictionary](docs/DATA_DICTIONARY.md) describes the columns.

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
python -m simd_ingest.trace "AB12 3GQA"    # follow one record back to its source rows
python -m pytest tests -q
```

Offline mode never accesses the network. Audit never downloads or repairs files, regardless
of source mode. Download mode rechecks cached hashes; it does not discover or accept “latest”
automatically.

## What a build leaves

- `results/postcode_simd.parquet`: the current complete snapshot, keyed by
  `(pc_norm, introduced_on)`. Release is metadata/an attribute, not part of the key.
- `results/BUILD_REPORT.md`: the human review entry point.
- `results/manifest.json`: all checks, observations, input pins and output fingerprints.
- `results/runs/<run-id>/`: retained configuration/source/schema/decision snapshots,
  runtime and code hashes, and that run's report. Failed builds retain their error and checks too.

The build writes a candidate, reopens it and checks saved values and metadata before replacing
the current table. Validation failure leaves the previous publication untouched. Run one
writer per results directory; files are replaced atomically individually, not as a multi-file
transaction. After an interrupted publication, run `audit`; if it fails, rebuild from pinned
sources. Keep `results/runs`, source archives and the corresponding code in your backups.
Old table copies are not retained.

There is no scheduler, server, intermediate-table cache or orchestration database.
The old orchestration plans remain [historical records](docs/plans/README.md).

## Use the table

To inspect live directory records, use `WHERE is_current`. An ordinary postcode can still
have several split records: do not assume `pc_base` is unique in the imported table.

```sql
SELECT pc_norm, pc_base, simd2020v2_pw_scotland_quintile
FROM 'results/postcode_simd.parquet'
WHERE is_current AND pc_base = 'G718BQ';
```

`pc_norm` removes ASCII spaces and keeps the NRS split suffix; `pc_base` removes a validated
suffix only from a flagged small-user record. Original postcode text is preserved.
PHS population-weighted fields (`pw`) and Government unweighted fields (`uw`) are distinct.

For cohort linkage, start with [Two SQL lookups](docs/LINKAGE_BY_ERA.md): run the
[shared setup](docs/sql/create_latest_postcode_lookup.sql), then choose
[one SIMD edition](docs/sql/link_latest.sql) or [edition by event year](docs/sql/link_by_era.sql).
Both use latest postcode geography, the A part for ordinary split postcodes, and linked
small-user geography for large users, with explicit statuses and both record keys.

The [Python helpers](docs/EXAMPLES.md) remain a separate current/as-of record lookup with
own-record geography and an optional split consensus/conflict policy; they are not equivalent
to the new SQL. Exclusions remain consumer choices, not deletions from the imported table.
Adding a source edition does not automatically change the analyst's edition-by-year policy.

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
`core/spd.py`, `phs.py`, `govscot.py`, `join.py` and `output.py` contain the data rules.
`sources.yaml` declares sources and editions, `spd_schema.yaml` declares directory headers,
`output_schema.yaml` declares the saved table, and `decisions.yaml` records policy.
Tests include synthetic postcode refreshes, a new SIMD edition/vintage, corrupted inputs
and saved files; downloaded-data tests also pin the current logical output fingerprint.
