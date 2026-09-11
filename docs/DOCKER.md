# Docker, end to end

From a machine with Docker and nothing else, to a built table, a passing test suite and a
Dagster instance with a recorded run. About ten minutes, most of it downloading.

## What you need

- Docker with Compose, any recent version.
- A copy of this repository. No Python, no source data.
- Network access to `opendata.nhs.scot`, `nrscotland.gov.uk` and `maps.gov.scot`, unless you
  are bringing the sources yourself (see the air-gapped section).

## 1. Build the image

```bash
docker compose build
```

One image, `simd-ingest:1.1`, on a digest-pinned `python:3.12-slim`, with the pipeline and its
pinned dependencies and nothing else. No data is baked in.

## 2. Build the table

```bash
docker compose run --rm build
```

Inside Docker the default mode is download. The container fetches the 13 pinned objects into
`./data/cache`, places the 17 files under `./data/sources`, verifies every hash, builds the
four tables, runs about 450 checks, writes the Parquet to a temporary file, reads it back,
renames it into place and writes the manifest. The last lines you see:

```text
  393 blocking checks passed, 0 failed; 60 diagnostics agree, 0 differ
Wrote /app/results/postcode_simd.parquet  247,773 rows x 162 columns  <hash>
```

The outputs are on your machine, not in the container:

```text
./results/postcode_simd.parquet     the table
./results/manifest.json             sources, hashes, decisions, every check result
./data/                             the cache and the placed sources; reusable, disposable
```

A second `docker compose run --rm build` downloads nothing and re-verifies everything.

## 3. Run the tests

```bash
docker compose run --rm test
```

The suite finds the sources the build fetched. Expect every test to pass.

## 4. Open the Dagster UI

```bash
docker compose up dagster
```

Then open <http://localhost:3000>. The graph shows eighteen source assets, the decision log
and the four tables. Select the job `build_postcode_simd` and materialise all. The run, its
materialisations with metadata and data versions, and every check result are written to
`./.dagster` on your machine, which is the provenance record. Stop the server with Ctrl-C or
`docker compose down`; the record stays.

## 5. Check the table later without rebuilding

```bash
docker compose run --rm build audit
```

Re-verifies the sources, reopens the saved table and compares every attached value with the
source lookups and the manifest's recorded hash.

## Air-gapped machines

Do steps 1 and 2 on a connected machine, then copy `./data/sources` to the target as
`./manual_data`, or obtain the 17 files listed in `simd_ingest/sources.yaml` by other means and
place them under `./manual_data` with the same relative paths. Then run with the mode set to
offline:

```bash
SIMD_SOURCE_MODE=offline docker compose run --rm build
SIMD_SOURCE_MODE=offline docker compose up dagster
```

Offline mode performs no network access and fails on a missing or changed file rather than
fetching. The result is byte-identical to the download-mode build.

## Notes

- On Linux hosts, files the container writes under `./data`, `./results` and `./.dagster` are
  owned by root. Run with `--user "$(id -u):$(id -g)"` if that matters to you.
- The image is about 950 MB, almost all of it Dagster and its web server.
- In download mode a placed file whose hash no longer matches is replaced from the verified
  object in the cache. Offline mode never modifies a file; a changed file fails the build.
- To use a different configuration file, mount it and set `SIMD_WORKFLOW_CONFIG` to its path
  inside the container.
