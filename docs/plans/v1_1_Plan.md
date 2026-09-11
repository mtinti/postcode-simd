# v1.1: CSV output, a lookup that follows the PHS guidance, and a Docker package

Proposed 11 September 2026. Three steps, each reviewed before the next. The v1.0 table and
its 162-column contract do not change; everything here is added beside it.

## Step 1. CSV beside the Parquet

For RDMP, whose delimited-file attacher is the way in, and for anyone without a Parquet reader.

**Build**

- `results/postcode_simd.csv`, written from the same in-memory table as the Parquet, in the
  same row order, by the same build. UTF-8, LF line endings, one header row, RFC 4180 quoting,
  dates as `YYYY-MM-DD`, booleans as `1` and `0`, integers unpadded.
- Null and blank both become an empty field. CSV cannot tell them apart; `spd_user_type`
  can, because a column is null exactly when it does not exist for that user type. The
  dictionary says so.
- A readback check for the CSV: reopen it as text, compare row count, primary key and every
  value against the Parquet rendered by the same rules. Blocking, like the Parquet readback.
- The manifest records the CSV as a second output with its own SHA256. The Dagster
  materialisation metadata carries both paths.
- `simd_ingest/ddl.py` generates `docs/postcode_simd.sqlserver.sql`: a CREATE TABLE for the
  RDMP catalogue with types mapped from the schema, string lengths taken from the longest
  value in this release plus headroom, `pc_norm` as `VARCHAR(8)`, and a collation left as
  a named placeholder. Labelled as generated and not yet executed against a server.

**Done when**

- The build writes both files. The CSV readback passes. Loading the CSV with pandas as
  text and applying the documented rendering rules reproduces the Parquet exactly.
- The DDL parses under a SQL Server grammar check, or failing that is reviewed by eye and
  labelled unexecuted.

**You review**

- The rendering rules, especially `1`/`0` for booleans and empty for both null and blank.
- Whether the DDL is what an RDMP catalogue would want, since you know the catalogue.

## Step 2. A lookup that follows the guidance

The PHS deprivation guidance's method is: choose the edition for the years of your data,
choose the category, choose the level, and match by postcode. This step turns that into
one small module and a worked document, so an analyst does not reinvent the join.

**Build**

- `simd_ingest/lookup.py` with three functions and no Dagster dependency:
  - `recommended_edition(year)`: the guidance's table 4, years of health data to edition.
    Labelled as the PHS recommendation. Never called implicitly; the analyst passes the
    edition, and this helper is how they choose it.
  - `lookup(table, postcode, on=None, edition, measure)`: one postcode, either a full NRS
    key or an ordinary postcode. With `on` a date, selects records valid on that day by the
    half-open rule; without, selects current records. Returns a status and the candidates.
  - `attach(events, table, postcode_col, date_col, edition, measure)`: the same for a whole
    frame of events, vectorised, one result row per event, never dropping or duplicating an
    event row.
- Statuses, from the policy already agreed in the plan: `not_found`, `unique`,
  `split_consensus` when several valid records agree on the requested measure,
  `split_conflict` when they disagree, giving a null value, and `deleted` when the postcode
  exists but no record is valid on that day. Never choose A, average or vote.
- Every result carries the label the guidance's checklist demands, built from the column
  name: index, edition, weighting, level, and which end is most deprived.
- `docs/EXAMPLES.md`: the four questions an analyst actually asks, each with the code and
  its real output from the v1.0 file:
  1. Most recent SIMD quintile for a postcode as written.
  2. SIMD at the date of an event, edition chosen by the guidance.
  3. A split postcode, showing consensus and conflict.
  4. A cohort file with postcodes and dates, attached in one call, with the status counts.
- Tests with fixtures for each status, a reused postcode with two introductions, a
  same-day record, and a cohort where one event has no postcode.

**Done when**

- The four examples run as written and their printed output matches the document.
- `attach` on a fixture cohort returns exactly one row per input row, with the expected
  statuses. On the 226 ambiguous current postcodes, `lookup` returns consensus for the 23
  whose parts share a data zone and conflict for the others.

**You review**

- The status names and the consensus rule. This is the policy analysts will live with.
- Whether `recommended_edition` should exist at all, or whether the table belongs only in
  the document.

## Step 3. Package and test in Docker

**Build**

- `Dockerfile` on a pinned `python:3.12-slim` digest, installing `requirements.txt` and the
  package. No source data and no results baked in. Entry point is the CLI; the same image
  runs the Dagster web server.
- `compose.yaml` with three services: `build` runs the CLI, `test` runs the suite,
  `dagster` serves the UI. Volumes for `manual_data`, `data`, `results` and `.dagster`,
  so the instance and outputs live on the host.
- The runbook gains a Docker section that mirrors the native one command for command.

**Done when**

- `docker compose run test` passes every test, with `manual_data` mounted.
- `docker compose run build --source-mode download` from an empty cache produces the same
  rows-only fingerprint as the native build. Whether the file SHA256 also matches across
  macOS and Linux is recorded either way; the fingerprint is the guarantee.
- `docker compose up dagster` serves the graph and a run from it succeeds.

**You review**

- The volume layout. Is that where HIC would keep the instance and results?
- Whether the image should ship to a registry, and which one.

## Status, 11 September 2026

Steps 2 and 3 delivered; step 1 held back at the user's request pending a decision on the CSV
and DDL. `simd_ingest.lookup` and `docs/EXAMPLES.md` are in place with the five statuses and the
explicit recommended-edition helper. The image `simd-ingest:1.1` builds on a digest-pinned
`python:3.12-slim`, passes the test suite inside the container, serves the Dagster UI, and a
download-mode build from an empty cache inside it produced a Parquet file byte-identical to the
native macOS build under the same decision log. Byte parity across the two platforms therefore
holds for the pinned versions, beyond the rows-only fingerprint the plan required.

The Docker path was then walked end to end in a directory containing only the repository files:
build the image, download-mode build, test suite, a Dagster run with the instance on the host,
the UI showing that run, and audit. `docs/DOCKER.md` is that walkthrough. Inside Docker the
default mode is download, overridable with `SIMD_SOURCE_MODE=offline` for air-gapped machines.

## Precondition

Step 3 needs Docker on the machine that runs it. I will check before starting and stop at
that gate if it is missing.

## Decisions this adds to the log

CSV rendering rules; the lookup statuses and consensus rule; the recommended-edition helper
being explicit rather than implicit; the image base and where it is published.
