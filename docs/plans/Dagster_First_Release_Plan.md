# Postcode-SIMD on Dagster: first release in three steps

Proposed 10 September 2026. Replaces the seven-step sequence in
[the full plan](SIMD_Dagster_Implementation_Plan.md). Two sections of that plan stay in
force unchanged and are not repeated here: **Frozen target contract** and **Validation
decision: source fidelity blocks; population reconstruction does not**. Everything else in
it becomes the post-release backlog at the end of this document.

The rule for what stays in the first release: it must be needed to produce the table, to
prove the table is right, or to record where it came from. Protection against failures that
have not happened yet is hardening, and hardening comes after a release exists.

## The deliverable

`results/postcode_simd.parquet`, 247,773 records by 162 columns, with `manifest.json` beside
it, built by one Dagster job from sources downloaded and hash-verified inside the run, with
every check result and the decision log recorded in the run history.

## Step 1. Core and fetch, no Dagster

**Build**

- `decisions.yaml`, `output_schema.yaml`, and `sources.yaml` extended with URL, remote
  object hash and archive member mapping for the 13 objects and 17 files. Retire the four
  government pins as already decided.
- `core/`: `fetch.py`, `phs.py`, `govscot.py`, `spd.py`, `join.py`, `checks.py`. Plain
  functions. Each builder returns its table; each check returns a structured result marked
  blocking or diagnostic per the validation decision.
- `cli.py` with `fetch`, `build`, `audit`. `build` runs fetch or offline verification, the
  four builders, the checks, writes the Parquet to a temporary path, reopens it, verifies
  schema, row count, key uniqueness and a sample of values against the source lookups, then
  renames it into place and writes the manifest. `audit` reruns the readback on the
  existing file without building.
- One test that the columns shared with the prototype, rank, the eight PHS bands and the
  two flags for all six editions, are value-identical to the prototype's output on every
  record. That replaces the compatibility CLI: same assurance, no second code path.
- Migrate the checks from `acceptance.py` that still apply into `core/checks.py`, keeping
  the fingerprints and counts in `acceptance_baselines.yaml` as the expected values. One
  suite, not two.

**Done when**

- From an empty cache, `cli build` downloads 13 objects, verifies 17 files, and writes
  the 247,773 by 162 table with all blocking checks passing.
- Offline mode over `manual_data/` produces the same Parquet hash and manifest content.
- A wrong pin fails the build before anything is written. A modified cell in the saved
  file fails `audit`.
- The prototype comparison test passes.

**You review**

- `decisions.yaml` and `output_schema.yaml`.
- The manifest, read as if you had only the file.

## Step 2. Dagster

**Build**

- `orchestration/definitions.py` with the instance directory pinned. Seventeen source
  assets and the decision log, generated from the registry, each materialised by
  `core.fetch` and versioned by its content hash. Four table assets calling the four
  builders. Blocking checks as asset checks with error severity; the population
  diagnostic as warning severity. Metadata on every materialisation: rows, hashes
  consumed, band provenance, inverted editions.
- One job that materialises everything from sources to output. The output asset writes
  the same way the CLI does, through the same `core` functions.

**Done when**

- One click in the UI produces the same Parquet hash as step 1's CLI.
- A rerun on unchanged sources shows unchanged data versions on every asset.
- A one-byte change to a fixture source turns its check red and nothing downstream runs.
- Editing `decisions.yaml` shows as a changed upstream on every table asset.

**You review**

- The graph and one materialisation's metadata.
- The instance location.

## Step 3. Release

**Build**

- A runbook: install pinned dependencies, set the instance directory, run the job or the
  CLI, run `audit`, find a decision, use the current-postcode and as-of queries.
- Data dictionary from `output_schema.yaml`, including the PHS guidance year-to-edition
  table and the band convention statement.
- Full-data acceptance run and tag `v1.0`.

**Done when**

- A colleague follows the runbook on a clean machine and gets the same Parquet hash.
- Every done condition from steps 1 and 2 still holds on the tagged code.

## Backlog for after v1.0

Each of these exists in the full plan with its rationale. None changes the table.

| Item | Why it can wait |
| --- | --- |
| Deterministic `build_id` and code hashes | Dagster's run record plus source hashes identify a build well enough for one site |
| Acceptance receipts bound to run and inputs | The blocking check on the source asset already gates downstream |
| Writer lock and second-publisher rejection | One person runs this |
| Two-phase Parquet and manifest replacement with interruption fixtures | Rebuild takes seconds; a mismatch is caught by `audit` |
| Evidence directory per run | The manifest and the Dagster event log hold the same content |
| Row-level trace query | Every key needed for a trace is already a column in the table |
| Download failure fixtures beyond a wrong hash | Truncation and error pages fail the hash check anyway |
| Cross-platform byte parity | Logical fingerprint is enough until a second platform exists |
| Percentile, long bridge, database targets, partitions | Unchanged from the full plan's deferred list |

## Status, 10 September 2026

All three steps delivered and reviewed on the same day. The v1.0 table is
`results/postcode_simd.parquet`, 247,773 rows by 162 columns, rows-only fingerprint
`59369357e44e45a5` and file SHA256 `e1a58230706ab9f6` under decision log `443c34c2ad632a43`,
produced identically by the CLI, by the Dagster job (run `54c6aded`), and by a clean virtual
environment installed from `requirements.txt`. The file hash covers embedded provenance metadata and so
moves when the decision log changes; the fingerprint moves only when the data does. Twenty-nine tests
pass. The reference tables were renamed `phs_bands` and `govscot_bands` at the step 2 review. Tagging
awaits the repository being placed under git.

## Review protocol

Three gates. At each, I report what was built, the evidence for each done condition and
anything I could not demonstrate. Work on the next step starts on your say-so. Accepted
changes go into `decisions.yaml` with the date.
