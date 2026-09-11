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

Status: v1.2.0, built from Scottish Postcode Directory 2026/2. The repository holds the means
to reproduce the table and the record of how it was built. It holds no source data and no
output; a clone that runs the build gets the same file, hash for hash.

| | |
| --- | --- |
| Output | `results/postcode_simd.parquet`, 247,773 rows by 162 columns, plus `results/manifest.json` |
| Sources | 13 objects from PHS, National Records of Scotland and maps.gov.scot, see `simd_ingest/sources.yaml` |
| Decisions | `simd_ingest/decisions.yaml`, an upstream of every table |
| Dictionary | `docs/DATA_DICTIONARY.md`, generated from the frozen schema |
| Orchestration | Dagster, with the CLI as an equivalent path through the same functions |

## For a reviewer: start here

Read [How it is built](docs/HOW_IT_IS_BUILT.md) first: the data flow, the decisions and
the functions to inspect. Then read `results/BUILD_REPORT.md` from the build being reviewed:
the same steps with actual check results and a worked postcode. Use the
[data dictionary](docs/DATA_DICTIONARY.md) for field definitions and `results/manifest.json`
for the complete machine-readable evidence.

The [decision log](simd_ingest/decisions.yaml) records current policy and explicit supersessions.
Documents in [docs/plans](docs/plans/README.md) are historical design records, not a second
set of instructions for today's build. Analyst lookup choices are documented separately in
[Examples](docs/EXAMPLES.md) and [Linkage by era](docs/LINKAGE_BY_ERA.md).

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

This installs the package, the `simd-ingest` command and the test dependencies. Python 3.12
and the versions pinned in `pyproject.toml` and `requirements.txt` are what v1.2.0 was verified
with. Nothing needs a GIS library; the shapefile attribute tables are read with `dbfread`.

## Build

Two modes, set in `config/workflow.yaml`. Both finish in the same verified state.

```bash
# offline: every pinned file already under manual_data/, no network access
python -m simd_ingest.cli build

# download: fetch the 13 pinned objects into data/cache, place the 17 files under data/sources
python -m simd_ingest.cli build --source-mode download
```

A build verifies every source hash, prepares the index and the twelve edition tables, joins them
one edition at a time, writes the table to a temporary file, reopens it, verifies it against
the source lookups and provenance contract, renames it into place, then writes the manifest
and build report. A failed validation prevents replacement of the published table. The exact
check count is recorded by the run, not fixed in this README. The offline build takes about
fifteen seconds on the development machine.

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
five conceptual parts: the sources and four tables (22 assets in total: 17 pinned files,
the decision log and four tables). `postcode_index` is both directory files with keys and
dates derived. `phs_bands` is the
six PHS editions with the 2004 and 2006 bands turned so that 1 means most deprived. `govscot_bands`
is the six government editions from the shapefile tables. `postcode_simd` joins them, one edition
at a time in a fixed order, then writes the file, reads it back and writes the manifest. Every
blocking check is attached to the asset it guards. The supported job runs every source and
check before publishing; final-only materialisation without this run's upstream evidence is refused.

**For a reviewer, the graph is not the place to start.** Every build writes
`results/BUILD_REPORT.md`, a page that says what happened to the data in order with that run's
numbers: the sources verified, the index assembled, each PHS edition and whether it was turned,
each government edition and whether its ranks match, the twelve joins with rows before and
after, the output and its readback, and one postcode followed through. It is
written by the CLI and by the Dagster job alike. `docs/HOW_IT_IS_BUILT.md` is the static
companion: the six judgements in the pipeline, where each lives in the code, and which check
guards it.

The CLI accumulates check records directly. Dagster stores those same records in its check
events; the final asset collects them from the current run before writing the report and
manifest. Missing records are never labelled as passed. Both paths call the same join sequence
and saved-file validator, and a regression test compares their complete check records.

The instance directory `.dagster` is the provenance record: every run, every materialisation with
its metadata and data version, every check result. Back it up with `results/`. The three intermediate
tables go to `data/work` as Parquet, about 16 MB, and are disposable.

To see why the data is the way it is, open the `source/decisions` asset, or read
`simd_ingest/decisions.yaml` directly. Every table depends on that versioned asset, and the
output metadata and manifest record its hash as `decisions_sha256`.

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
# len(rows) == 0: not found.  == 1: unique.  > 1: a split postcode; lookup.py takes the A part as NRS does.
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
resolved to the A part as NRS does and cohort files handled, use `simd_ingest.lookup`. `docs/EXAMPLES.md` walks through four
worked cases with real output. For linking a cohort by era, each event taking the edition
the guidance recommends for its year, see `docs/LINKAGE_BY_ERA.md`, which gives the same
rule in Python and in one SQL query that runs on DuckDB and SQL Server.

To inspect the join for one record rather than trust it, `python -m simd_ingest.trace "AB12 3GQA"`
rebuilds the two reference tables from the pinned sources and prints, edition by edition, the
data zone the record was joined through, the PHS and government source rows, and whether every
attached value equals its source. The three prepared Dagster tables are also on disk under
`data/work/` as Parquet, one per asset, for ad hoc inspection with pandas.

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
the Dagster job reproducing the CLI's file hash and complete check evidence with repeated data versions, a corrupted source
blocking downstream, an edited decision log changing its version, and the Python and SQL era
linkage agreeing on a synthetic cohort. Without data those tests report themselves as skipped.
Small saved-file fixtures test null versus supplied text, metadata-value corruption and failed
publication without needing downloaded data. Missing or failed upstream evidence is tested too.

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
