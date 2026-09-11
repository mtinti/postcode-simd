# Postcode-SIMD reference table

One Parquet file that attaches all six editions of the Scottish Index of Multiple Deprivation to
every record of the Scottish Postcode Directory, built from hash-pinned public sources by a
pipeline that records what it read, what it checked and why it made each choice.

It is for analysts who link health or social care records to area deprivation and want the
whole history in one place: every postcode the directory has ever held, with its dates, and for
each one the PHS population-weighted bands and the Scottish Government unweighted bands of every
SIMD edition from 2004 to 2020v2. The lookups that come with it follow the PHS deprivation
guidance for analysts, including the rule for choosing an edition by the year of the data and
the handling of split postcodes.

Status: v1.1.0, built from Scottish Postcode Directory 2026/2. The repository holds the means
to reproduce the table and the record of how it was built. It holds no source data and no
output; a clone that runs the build gets the same file, hash for hash.

| | |
| --- | --- |
| Output | `results/postcode_simd.parquet`, 247,773 rows by 162 columns, plus `results/manifest.json` |
| Sources | 13 objects from PHS, National Records of Scotland and maps.gov.scot, see `simd_ingest/sources.yaml` |
| Decisions | `simd_ingest/decisions.yaml`, an upstream of every table |
| Dictionary | `docs/DATA_DICTIONARY.md`, generated from the frozen schema |
| Orchestration | Dagster, with the CLI as an equivalent path through the same functions |

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the package, the `simd-ingest` command and the test dependencies. Python 3.12
and the versions pinned in `pyproject.toml` and `requirements.txt` are what v1.1.0 was verified
with. Nothing needs a GIS library; the shapefile attribute tables are read with `dbfread`.

## Build

Two modes, set in `config/workflow.yaml`. Both finish in the same verified state.

```bash
# offline: every pinned file already under manual_data/, no network access
python -m simd_ingest.cli build

# download: fetch the 13 pinned objects into data/cache, place the 17 files under data/sources
python -m simd_ingest.cli build --source-mode download
```

A build verifies every source hash, builds the three reference tables and the index, runs about
450 checks, writes the table to a temporary file, reopens it, verifies it against the source
lookups, renames it into place, then writes the manifest. A blocking failure stops before anything
is written. The offline build takes about fifteen seconds.

```bash
python -m simd_ingest.cli audit     # re-verify the existing table against freshly verified sources
python -m simd_ingest.cli fetch     # download and verify only
```

## Run it in Dagster

```bash
export DAGSTER_HOME=$PWD/.dagster
dagster dev -m simd_ingest.orchestration.definitions
```

Open the URL it prints, select the `build_postcode_simd` job and materialise all. The graph has
eighteen source assets, one per pinned file plus the decision log, and four table assets:
`phs_bands`, `govscot_bands`, `postcode_index` and `postcode_simd`. Every check the CLI runs is
attached to the asset it guards. Blocking checks fail the asset and nothing downstream runs. The
population reconstruction is a warning and never blocks.

The instance directory `.dagster` is the provenance record: every run, every materialisation with
its metadata and data version, every check result. Back it up with `results/`. Intermediate tables
go to `data/work`, which is disposable.

To see why the data is the way it is, open the `source/decisions` asset, or read
`simd_ingest/decisions.yaml` directly. Each table's materialisation records the hash of the
decision log it was built under, and the manifest records it as `decisions_sha256`.

## Run it in Docker

The same pipeline as an image, with nothing baked in: sources, cache, results and the
instance are mounted from the project directory. Inside Docker the default mode is download,
so this works from a clean machine with no data. `docs/DOCKER.md` is the full walkthrough,
including the air-gapped variant.

```bash
docker compose build                    # the image
docker compose run --rm build           # fetch the pinned sources into ./data, build ./results
docker compose run --rm test            # the test suite, against what the build fetched
docker compose up dagster               # the UI on http://localhost:3000, instance in ./.dagster
```

The base image is pinned by digest in the `Dockerfile`. A download-mode build inside the
container from an empty cache produces a Parquet file byte-identical to the native macOS
build under the same inputs, so the image is a valid clean-machine reproduction.

## Query it

The table is wide and mostly historical. Most questions start by filtering to current records.

```python
import pandas as pd
t = pd.read_parquet("results/postcode_simd.parquet")

# Current SIMD 2020v2 quintile for a postcode as a person writes it.
key = "G71 8BQ".upper().replace(" ", "")
rows = t[t.is_current & (t.pc_base == key)]
# len(rows) == 0: not found.  == 1: unique.  > 1: a split postcode; report it, never pick A.
rows[["pc_norm", "DataZone2011Code", "simd2020v2_pw_scotland_quintile"]]

# The record valid for a full postcode on a given day, half-open interval. The two date
# columns arrive as Python dates; convert them once to compare with a Timestamp.
for c in ("introduced_on", "deleted_on"):
    t[c] = pd.to_datetime(t[c])
day = pd.Timestamp("2015-06-01")
asof = t[(t.pc_norm == "AB101BF") & (t.introduced_on <= day) & (t.deleted_on.isna() | (t.deleted_on > day))]
```

The same in DuckDB:

```sql
SELECT pc_norm, simd2020v2_pw_scotland_quintile
FROM 'results/postcode_simd.parquet'
WHERE is_current AND pc_base = 'G718BQ';

SELECT *
FROM 'results/postcode_simd.parquet'
WHERE pc_norm = 'AB101BF'
  AND introduced_on <= DATE '2015-06-01'
  AND (deleted_on IS NULL OR deleted_on > DATE '2015-06-01');
```

For the lookups the PHS guidance describes, most recent or at a date, with split postcodes
and cohort files handled, use `simd_ingest.lookup`. `docs/EXAMPLES.md` walks through four
worked cases with real output. For linking a cohort by era, each event taking the edition
the guidance recommends for its year, see `docs/LINKAGE_BY_ERA.md`, which gives the same
rule in Python and in one SQL query that runs on DuckDB and SQL Server.

Two rules from the PHS deprivation guidance are built into the column names. Columns named
`simd{ed}_pw_*` are PHS population-weighted; `simd{ed}_uw_*` are Scottish Government unweighted.
Never mix the two in one analysis, and say which you used. Within-board bands such as
`simd{ed}_pw_hb_decile` are computed within the board in `phs_dz{vintage}_hb`; use that code, not
the directory's `HealthBoardArea2019Code`, when reporting them.

## Test

```bash
python -m pytest tests -q
```

Unit tests on the core rules and the lookup statuses run without any data. With the pinned
sources and a build present, the integration tests also run: a modified-cell readback failure,
the Dagster job reproducing the CLI's fingerprint with repeated data versions, a corrupted source
blocking downstream, an edited decision log changing its version, and the Python and SQL era
linkage agreeing on a synthetic cohort. Without data those tests report themselves as skipped.

## Layout

```text
config/workflow.yaml           source mode, roots, cache, work and results directories
simd_ingest/sources.yaml       pinned objects, files, hashes, URLs, licences, column maps
simd_ingest/decisions.yaml     the decision log
simd_ingest/output_schema.yaml the frozen 162-column contract
simd_ingest/core/              plain Python: fetch, phs, govscot, crosscheck, spd, join, output, checks
simd_ingest/orchestration/     the Dagster code location
simd_ingest/cli.py             fetch, build, audit; installed as the `simd-ingest` command
simd_ingest/lookup.py          the guidance-following lookups
simd_ingest/dictionary.py      regenerates docs/DATA_DICTIONARY.md
docs/                          dictionary, examples, era linkage, Docker walkthrough, SQL, plans
tests/                         the test suites
```

Install the package with `pip install -e ".[dev]"` to get the `simd-ingest` command and the
test dependencies.

## Licences and attribution

The code and documentation are MIT licensed. The data the pipeline downloads is not part of
this repository and stays under its publishers' terms:

- Public Health Scotland, SIMD population-weighted lookups, Open Government Licence v3.0.
- Scottish Government, SIMD ranks and unweighted bands via SpatialData.gov.scot, Open
  Government Licence v3.0. Contains Scottish Government data.
- National Records of Scotland, Scottish Postcode Directory. Confirm NRS terms before
  redistributing the index or any table derived from it, which includes the output of this
  pipeline.

## Citing

If you use the table or the pipeline, cite the repository with its version tag and the
`logical_fingerprint` from the manifest of the build you used, so the exact data can be
identified.
