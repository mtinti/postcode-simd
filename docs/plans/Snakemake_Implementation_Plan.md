# Postcode–SIMD ingestion: Snakemake implementation plan

Prepared for Michele Tinti. 10 September 2026.

Superseded for implementation by the [stepwise Dagster plan](SIMD_Dagster_Implementation_Plan.md).
That plan selects offline-first delivery and a 156-column target, with approval after each
step. The requirements below are retained as historical context, not additional Dagster
scope; the downloaded-source evidence and explicitly carried-forward data rules still apply.

Status: proposed implementation, not an implemented workflow. This is the replacement
delivery plan for the smaller ingestion pipeline discussed: download pinned sources,
validate them, and produce one combined postcode–SIMD table. It supersedes the delivery
architecture in [the full plan](SIMD_Full_Implementation_Plan.md), while retaining the
audited data rules in [the gap-closure evidence](SIMD_Plan_Gap_Closure.md).

## 1. Outcome and scope

One Snakemake command must produce a validated Parquet table containing small-user and
large-user postcode records together, with all six SIMD editions attached. For the pinned
SPD 2026/2 cut release, the main table has **247,773 rows**: 196,769 small-user and 51,004
large-user records, including deleted records. The importable file represents exactly
one SPD release at a time. A successful new release recreates and replaces the complete
snapshot; releases are not appended together in the file or imported table.

Consumers import the fixed path `results/postcode_simd.parquet`. Keep each validated build
and its evidence separately for safe completion/recovery:

```text
results/
  postcode_simd.parquet               # current complete snapshot, atomically replaced
  2026_2/<build_id>/                   # internal build/evidence bundle, not appended data
    postcode_simd.parquet
    source_validation.json
    output_validation.json
    manifest.json
  runs/<run_id>/                     # execution evidence, not importable data
    run.json                         # attempt outcome and build/artifact references
    report.html                      # exported after a successful workflow
```

The manifest identifies the exact inputs, code, environment, schema and output hashes.
The validation reports establish both source acceptance and correctness of the saved
table. A failed build must not replace the current good snapshot. Internal build folders
do not change the single-snapshot import model and are never concatenated for import.

Included in the first delivery:

- Workflow orchestration and retained source-to-output lineage, not just a build script.
- Pinned downloads, safe archive extraction and an offline mode for existing downloads.
- One combined wide table; all original postcode fields; all six SIMD editions.
- Complete NRS keys, ordinary-postcode search keys and explicit date/current-record rules.
- Source checks, independent Parquet readback, provenance, tests and a quick start.

Deferred: a second orchestration engine, separately published reference products, a long postcode–edition
bridge, database loading, change-data capture, a search API, scheduling and a general
publication service. SQL Server can later consume the validated Parquet as a downstream
step; access to it is not a prerequisite for this delivery. A live-only table or CSV is
also optional later, not a second required output now.

This deliberately narrows the old plan's data products. Separate canonical data-zone
tables, duplicated raw PHS columns and calculated-band columns are not first-delivery
outputs. The pinned raw files remain the source of those original values. Published
government percentiles are included where available; an unverified historical percentile
will not be presented as a published value.

### Orchestration decision: lineage is a requirement

Decision recorded 10 September 2026: the user explicitly requires a workflow orchestrator
for lineage control. The prototype's approximately six-second runtime is not a reason to
remove orchestration. Python remains the reusable transformation/validation layer; a
Python-only script is not the proposed delivery. No existing HIC tooling standard is assumed.

Retain **Snakemake as the proposed first implementation**, following the earlier choice.
The distinctions below are selection guidance, not a decision to implement three engines:

| Engine | Fit for this requirement |
| --- | --- |
| Snakemake | File-oriented dependencies and an archived HTML report containing workflow topology, runtime information and provenance. This is the current proposal. [Reports documentation](https://snakemake.readthedocs.io/en/stable/snakefiles/reporting.html) |
| Dagster | Prefer if browsing assets, their materializations and run history in an ongoing web UI is a first-delivery requirement; plan persistent instance storage and operation of that UI. [Assets](https://docs.dagster.io/guides/build/assets), [webserver and UI](https://docs.dagster.io/guides/operate/webserver) |
| Nextflow | A reasonable alternative if it fits the team's existing workflows. Its documented lineage command tracks input/output/task relationships but is currently marked experimental and requires enabling; verify the chosen release before relying on it. [Data lineage](https://docs.seqera.io/nextflow/cli#data-lineage) |

The current proposal delivers inspectable, archived provenance, not a hosted asset catalog.
If an interactive cross-run asset UI is essential, settle that requirement before writing
the workflow and reconsider Dagster. Switching the engine does not change the table key,
snapshot-replacement model, source acceptance or ntile-consensus policy. Lineage also does
not require a multi-product publication service or establish a need for elaborate recovery.

## 2. Starting point and authoritative configuration

| Existing asset | Reuse | Work still required |
| --- | --- | --- |
| [sources.yaml](simd_ingest/sources.yaml) | Fourteen logical source identities, hashes, editions and vintage-specific methods | Add direct download/archive metadata and the workbook percentile column |
| [acceptance_baselines.yaml](simd_ingest/acceptance_baselines.yaml) | Independently reviewed schemas, counts, fingerprints and exceptions | Retain unchanged unless an explained source-contract review requires a change |
| [acceptance.py](simd_ingest/acceptance.py) | Hash verification and audited source checks; alternate source-root support | File-report adapter and complete helper-code provenance |
| [build.py](simd_ingest/build.py) | Source readers, edition joins and published-band lookups | Combined table, explicit schema/output paths, stricter parsing and readback |
| [source tests](tests/test_source_acceptance.py) | Existing regression cases | Downloader, output, workflow and failure-recovery tests |
| `manual_data/` and `out/` | Audited downloads and prototype outputs | Preserve them; do not use either as disposable workflow output |

Keep `simd_ingest/sources.yaml` as the single authority for source identities and methods.
Do not copy its hashes into a second hand-maintained manifest. Add a separate operational
configuration, with schema validation and these proposed defaults:

```yaml
# Planned file: config/workflow.yaml
source_manifest: simd_ingest/sources.yaml
acceptance_baselines: simd_ingest/acceptance_baselines.yaml
source_mode: offline                 # offline | download
manual_source_root: manual_data
cache_root: .cache/simd
work_root: work
results_root: results
schema_version: postcode_simd_wide_v1
```

Resolve project-relative paths consistently, independently of script locations. Accept
explicit absolute paths for local data and outputs. Validate that manual inputs, cache,
work and results cannot overlap destructively. Release and edition selection come from
the source manifest, not a second editable release setting. Unknown configuration keys
or source modes fail clearly.

## 3. Acquisition: online and offline use the same data contract

The existing source set comprises six PHS CSVs, two government historical CSVs, two
government workbooks, two postcode CSVs and two postcode guides: **14 logical files**.
The guides participate in identity checks even though they are not table inputs.

Before claiming download support, extend the manifest with verified direct URLs for
each download, an explicit format, and any archive-to-member mapping. Catalogue links
alone are insufficient. Use the official [PHS catalogue](https://www.opendata.nhs.scot/dataset/scottish-index-of-multiple-deprivation),
the government links already recorded in the source manifest, and the
[NRS 2026/2 release page](https://www.nrscotland.gov.uk/publications/scottish-postcode-directory-20262/)
as discovery starting points. Do not discover a moving "latest" release during a build.

For SPD, verify the postcode-index ZIP and its actual member paths. Record its SHA256
separately from the existing hashes of the two CSVs and two guides. If a guide must be
retrieved separately, encode that explicitly. The archive is a transport object, not a
fifteenth logical source. Its hash and exact extraction mapping are not established by
the current manifest and are an implementation prerequisite.

Download requirements:

- Download each unique remote object once into a workflow-owned, hash-addressed cache.
  Preserve the logical relative file paths expected by the existing readers under a
  resolved source root.
- Use bounded HTTP timeouts and retries with backoff. Reject failed HTTP responses,
  unexpected HTML, invalid archives and checksum mismatches. Keep useful per-source logs.
- Write a temporary sibling file, verify it, then rename it into place. A partial
  download must never have the accepted source filename.
- Extract only declared members; reject absolute paths, traversal, symlinks, duplicate
  member names and excessive expansion. Verify every extracted member against its pin.
- Never accept changed bytes by automatically updating a hash or acceptance baseline.
  A provider replacing a file requires investigation and an explicit source update.
- Keep downloaded data outside version control. Confirm redistribution terms before
  distributing source bundles; local ingestion does not require shipping them in the repo.

In **offline mode**, the 14 files under `manual_source_root` are external inputs, never
Snakemake outputs. Disable download rules; missing files fail without a network fallback.
In **download mode**, use only workflow-owned cache paths as download/extraction outputs.
Do not download, extract or create environments while parsing the Snakefile or dry-running.

Offline data mode does not by itself make environment installation offline. The runner
and rule environments must already be provisioned for a genuinely disconnected run.

## 4. Final-table contract

### Row grain and original fields

One row represents one directory record in one SPD release, not one ordinary postcode
and not one postcode–edition pair. Preserve both user types and both current/deleted
records. Use a natural composite primary key, with no generated record ID:

```sql
PRIMARY KEY (pc_norm, introduced_on)
```

A targeted check on 10 September 2026, against both hash-verified postcode files, found
zero duplicate combinations and zero null key components across all 247,773 records.
The pair is unique across both user types in this release. This is an observed contract
for the pinned data, not a guarantee about future NRS releases. Validate it on every new
release and stop for review if it fails; never deduplicate or extend the key silently.

Require both key columns to be non-null in Parquet's schema and any imported
database table. Keep `deleted_on` nullable and outside the key: it is unnecessary for
uniqueness here, and SQL Server primary-key columns cannot be nullable. See
[Microsoft's primary-key constraints](https://learn.microsoft.com/en-us/sql/relational-databases/tables/primary-and-foreign-key-constraints?view=sql-server-ver16).
Keep `spd_release` and `spd_user_type` as attributes, not key components. Do not replace the complete
NRS key `pc_norm` with the potentially ambiguous ordinary-postcode key `pc_base`.

The import contract is full replacement: a new accepted release supersedes the old one.
Assert that every row has the single configured `spd_release`. Do not append new releases
or perform an insert-only load; records absent from the replacement must not linger in
the imported table. A future database loader must stage and validate the complete new
table before switching it into use. The same natural key may occur in successive releases
without conflict because only one release is loaded at a time.

The two source schemas contain 65 distinct column names: all 64 small-user columns plus
`LinkedSmallUserPostcode`. Keep that union in source order: the small-user header followed
by the large-user-only column. Fields absent from a user type are null. This includes the
eight census-count fields and `NeverDigitised` for large users, and the linked-postcode
field for small users.

Preserve original source fields as strings, including leading zeros, original postcode
spacing, date text, sentinel strings and empty strings. Distinguish a source empty string
from a field absent from that source schema. Add typed derived fields rather than silently
changing the meaning or precision of source values.

### Eleven derived record fields

| Field | Contract |
| --- | --- |
| `pc_norm` | Non-null primary-key component; uppercase, remove ASCII spaces, retain the complete NRS split suffix; maximum eight characters |
| `pc_base` | Ordinary-postcode search key; remove only a validated A/B/C suffix from a flagged small-user split record |
| `spd_user_type` | `small_user` or `large_user` |
| `spd_release` | Non-null provenance attribute, not part of the key; one manifest release per file, initially `2026_2` |
| `source_file` | Logical manifest-relative CSV path, not a machine-specific absolute path |
| `source_row` | One-based data-record ordinal, excluding the CSV header; provenance, not identity |
| `introduced_on` | Non-null primary-key component; parsed day-precision date |
| `deleted_on` | Parsed day-precision date; null when the source deletion value is empty |
| `is_current` | `deleted_on` is null; current in this directory release, not a claim about today's live world |
| `is_same_day_record` | Introduction and deletion dates are equal |
| `current_candidate_count` | Number of live complete NRS keys sharing `pc_base`; populated for current records only, otherwise null |

Use explicit Arrow types and field nullability: strings, `date32`, booleans and
appropriately sized integers. The primary-key fields must be non-null; nullable fields
retain their documented null semantics. Dates must parse the documented day/month/year
format without ambiguous locale inference. Validate midnight timestamps before discarding
the time component. The key identifies a record within a release, not a cross-release
lifetime identity.

A large-user split flag describes its linked small-user postcode; it must not shorten
the large-user key. Ordinary-postcode queries enumerate **all** candidates valid for the
chosen date/snapshot. The candidate-count statuses `not_found`, `unique` and `ambiguous`
describe the returned records, not whether a particular ntile can be resolved or whether
geographical coverage is complete. Never choose suffix A arbitrarily. Ntile-only releases
use the consensus rule below instead of requiring one uniquely identified split record.

Keep the 28 same-day records and flag them. Document historical selection as
`introduced_on <= date < deleted_on`, with null deletion treated as open-ended. A same-day
record has no match under this convention. This interprets directory validity dates; it
does not reconstruct the geography as it was known in every historical release.

Keep `NO LINKP` and `NO LINK` in the raw linked-postcode field and treat both as missing
links when validating. A real link resolving to a postcode key does not establish one
unique historical record. Do not join the combined table through that link or multiply
rows because of it.

### Split-postcode consensus for ntile-only releases

Decision recorded 10 September 2026: when the patient-level release contains only the
requested ntile, resolve that value rather than insisting on a unique split postcode.
Ambiguous geography can still have an unambiguous ntile. This is the agreed policy to
implement; the existing prototype and acceptance helper do not yet implement this resolver.

For each ordinary postcode `pc_base`, select current records or records valid on the
relevant date **before** checking agreement. Compare one exact field at a time: the same
SIMD edition, band definition, source/method and geographical scope. Do not mix PHS and
government bands, or country and within-health-board/council bands. Agreement on a band
does not identify a common rank, data zone, council or health board.

| Relevant candidate ntile values | Released value | Internal resolution status |
| --- | --- | --- |
| One candidate: `3`, with complete relevant coverage | `3` | `unique` |
| Multiple split candidates: `3, 3`, with complete relevant coverage | `3` | `split_consensus` |
| Complete, non-missing split candidates: `3, 4` | `NULL` | `split_conflict` |
| Any missing value or incomplete/unestablished relevant coverage, including `3, NULL` | `NULL` | `incomplete` |
| No candidate records for the selected date/snapshot | `NULL` | `not_found` |

Evaluate no-candidate, coverage and missing-value checks before deciding agreement. Do
not rely on `COUNT(DISTINCT ntile) = 1` alone: SQL distinct counts ignore nulls. Consensus
requires every relevant candidate to have a value, complete relevant coverage, and exactly
one distinct value. Never average bands, take a majority, choose a minimum/maximum, or
default to the A part when candidates conflict. A confirmed common value is copied from
the candidates; it is not a newly calculated deprivation band.

Coverage is not established merely by finding one suffixed record, or by observing the
letters A/B/C. NRS can omit the English part of a cross-border postcode. Resolve against
a validated coverage reference or reliable address/geographical scope; otherwise leave
the band `NULL` with status `incomplete`. CHI registration alone is not evidence that a
particular address belongs to the Scottish part. The
[NRS split-postcode policy](https://www.nrscotland.gov.uk/publications/geography-split-postcode-policy/)
documents the omitted cross-border part.

Reduce candidates to one resolved row per `pc_base` for each selected date/snapshot and
ntile field, then **left join** that lookup to the patient input. Keep every patient/input
row, including conflicting, incomplete and unmatched ones, without multiplying rows.
When patient rows have different relevant dates, resolve for each date rather than using
one current lookup for all of them. A postcode may have a resolved quintile but a null
decile; resolve each requested edition/field independently.

Keep statuses, candidate keys/values and coverage reasons in internal audit data. If only
ntiles are permitted in the downstream release, do not add those diagnostic fields,
postcodes, ranks or geography identifiers to it. Report internal outcome counts per
requested ntile; the existing count of 203 bases with differing 2020v2 ranks is **not** an
ntile-conflict count. Band-level consensus/conflict totals remain to be measured.

The internal postcode reference still retains every source record and its natural key
`(pc_norm, introduced_on)`. This consensus lookup does not deduplicate that reference,
change its schema, or imply a new independently published product.

### Fifteen SIMD fields per edition

For `2004`, `2006`, `2009v2`, `2012`, `2016` and `2020v2`, retain the existing naming:

- `simd{ed}_rank`.
- Eight PHS population-weighted bands: `country_decile`, `country_quintile`, and the
  corresponding `hb_`, `hscp_` and `ca_` fields.
- `simd{ed}_most15pc` and `simd{ed}_least15pc`.
- `simd{ed}_gov_quintile`, `simd{ed}_gov_decile`, `simd{ed}_gov_vigintile`.
- New: `simd{ed}_gov_percentile`, using the published 2011-vintage rank lookup for 2016
  and 2020v2, and a typed null for the four 2001-vintage editions.

This gives **166 columns** in schema v1: 65 original, 11 record-level and 90 SIMD fields.
Freeze exact order, types and nullability in a machine-readable output schema. Use integer
types for ranks and bands, preserve the documented 0/1 flag representation, and avoid
floating-point columns caused by nullable joins.

Join 2004–2012 on `DataZone2001Code` and 2016/2020v2 on `DataZone2011Code`. Preserve the
directory's 2022 geography fields, but do not use them for any of these six editions.
Record vintage and band provenance per edition in the manifest/data dictionary.

Ranks always retain the source direction: 1 is most deprived. Invert only the eight PHS
bands for 2004 and 2006: `11 - decile`, `6 - quintile`. Never invert the semantic 15% flags.
PHS population-weighted bands and government equal-count bands are distinct measures;
their audited differences are expected, not errors to overwrite.

Copy government bands from their published sources. Filter the historical extracts to
the overall `SIMD` domain before integer conversion; reject non-integral values and
duplicate `(DateCode, GeographyCode, Measurement)` keys. Replace the prototype's
`pivot_table(..., aggfunc="first")` with a duplicate-rejecting pivot. Map source `2009`
to edition `2009v2`. Read the rank workbook's actual N:R per-rank table, not its left-hand
cut-point tables; add `Percentile: 17` to the manifest's zero-based column mapping.

Use the configured vintage-specific formulae for validation, not as replacements for
published values. There is no published historical percentile in these downloads. Its
calculation remains an explicitly unverified convention and is deferred from the table.
Preserve the exact Shetland exceptions; their cause remains unresolved.

## 5. Workflow and Python responsibilities

```text
Pinned downloads → verified extraction ─┐
                                       ├→ validate_sources → build_table
Existing offline files ────────────────┘                       ↓
                                                       validate_output
                                                              ↓
                                                       finalise_release
                                                              ↓
                                                       replace_snapshot
                                                              ↓
                                                    all: check current file
```

Both validation stages receive the actual source files and their contracts. Output
validation must reopen the saved Parquet; an in-memory builder check is insufficient.

| Rule | Declared inputs | Output / behaviour |
| --- | --- | --- |
| `download_source` | Relevant download specification and downloader code | One pinned object in the owned cache; online mode only |
| `extract_spd` | Pinned archive, member specification and extraction code | Explicitly named source members, not ownership of the whole cache |
| `validate_sources` | All 14 files, source manifest, baselines, validator and helper code | `work/<build_id>/source_validation.json`; nonzero exit on any failure |
| `build_table` | Passing source report, actual table sources, schema, manifest and builder/helper code | `work/<build_id>/postcode_simd.parquet` |
| `validate_output` | Saved candidate, all comparison sources, source report, schema, baselines and validation code | `work/<build_id>/output_validation.json`, tied to the candidate SHA256 |
| `finalise_release` | Candidate, both passing reports, identity inputs and finalisation code | Complete release directory described in section 1 |
| `replace_snapshot` | Completed release directory, its manifest and replacement code | Atomically replace `results/postcode_simd.parquet` with the complete validated file; never append |
| `all` (default) | Current snapshot, selected completed release directory and release-check code | Always-run, read-only check that current file and evidence agree; no new output |
| `audit` (explicit) | Existing current snapshot, original sources and validation code/contracts, without producer dependencies | Fresh source and saved-table checks; missing inputs fail without building/downloading; no modification of the snapshot |

Keep business logic in importable Python functions with thin command-line adapters.
Snakemake should select inputs, declare dependencies/resources and call those adapters.
Do not put data transformations or HTTP requests into Snakefile top-level code.

Planned additions, keeping the existing package location:

```text
workflow/Snakefile
workflow/envs/ingest.yaml             # rule environment plus platform pins
config/workflow.yaml
config/output_schema.yaml
simd_ingest/download.py               # download and safe extraction
simd_ingest/contracts.py              # shared keys, dates and source contracts
simd_ingest/validate_output.py        # independent saved-table comparison
simd_ingest/release.py                # identity, finalisation and artifact checks
tests/                               # extend existing tests; add workflow fixtures
```

Refactor `build.py` to accept explicit source and output paths, reuse the established
readers, and write the combined candidate. Retain the existing acceptance CLI and its
tests; add a structured report-file option or a thin adapter. Reports must bind to the
inputs actually read, not merely a previously created success marker. The supported
workflow must not use the prototype's `--skip-hash` option.

Declare imported helper files, schemas, baselines, manifests and environment definitions
as dependencies; do not assume an imported Python module is automatically tracked.
Start with two concurrent download jobs and a single-process table build. Measure runtime
and peak memory on the full release before setting the documented resource requirements.

Snakemake orders jobs through input/output dependencies; `ruleorder` is not sequencing.
Its `ensure(..., sha256=...)` checks generated outputs, not every already-cached file on
every invocation. Therefore retain the explicit source-acceptance gate and fresh `audit`
target. See the [official rules documentation](https://snakemake.readthedocs.io/en/stable/snakefiles/rules.html).

### Minimum lineage evidence

A declared DAG describes possible dependencies; it is not proof of which bytes were read
or which checks ran. Retain the following evidence alongside the workflow's execution
metadata, using the existing manifest and validation reports rather than a separate catalog:

- **Sources:** all 14 logical source IDs and verified hashes, release/edition, source URLs
  and archive/member relationships where applicable. Label roles as table input,
  validation reference or documentation; the guides must not appear to supply table values.
  For offline files, record local acquisition mode without inventing a download timestamp.
- **Dependencies and meaning:** named rules and their actual input/output identities;
  code/helper hashes, resolved configuration, schema and locked/actual environment versions.
  The data dictionary maps output fields to source fields, join vintage/keys and applied
  transformations. In particular, record suffix handling, early PHS band inversion and
  the distinct published band methods. A workflow graph does not infer these Python rules.
- **Execution:** a unique `run_id` for each real invocation, start/end times where known,
  requested target/mode, rule outcomes and log references. Distinguish executed checks and
  builds from reused artifacts; a no-op is not a fresh validation. Keep failed/incomplete
  attempts identifiable without claiming that they produced an accepted snapshot.
- **Accepted output:** `build_id`, Parquet hash, logical fingerprint, counts, schema and
  both validation report identities. Record a successful snapshot replacement separately
  from merely building a candidate, tying the action to its run and accepted build.

`build_id` identifies the deterministic data/build specification; `run_id` identifies an
execution attempt. Several attempts may refer to the same build. Keep run IDs/timestamps
outside the deterministic Parquet bytes and build-ID calculation, and do not use them as
rule inputs that force data rebuilding. Neither identifier is part of the row primary key.

Retain run records/logs under `results/runs/<run_id>/`, separate from immutable build
bundles. Export a Snakemake HTML report there after a successful workflow, with the
manifest and compact validation summaries available for inspection. Document the export
command using the same selected configuration/targets, and capture the report before later
runs can change the working metadata. Snakemake keeps its default provenance metadata in
`.snakemake/metadata`; that working directory must not be the sole long-term evidence store.
See [provenance storage](https://snakemake.readthedocs.io/en/stable/executing/provenance.html)
and [report rendering](https://snakemake.readthedocs.io/en/stable/snakefiles/reporting.html#rendering-reports).

Replacing the current data file must not erase earlier manifests, validation evidence or
run records. Export/report failure must be visible and must not be confused with a failed
data validation or silently roll back a valid snapshot. Do not embed source datasets,
credentials or downstream patient-level data in shareable reports. The future ntile-only
resolver must record its selected date, band definition and consensus-policy version in
its own internal provenance; patient linkage is not added to this ingestion workflow.

## 6. Reproducibility and safe completion

Compute `build_id` from a canonical specification containing the logical source hashes,
release, data-affecting settings, schema, baselines, all processing/workflow code hashes
and the platform-specific environment lock, including the runner pin. The lock is
available before environments are created; verify that the resolved runtime matches it
before accepting a build. Record both lock identity and actual runtime versions in the
manifest. Exclude absolute paths, download/offline mode, core count and execution
timestamps from data identity. Identical local source bytes and downloaded source bytes
must produce the same table under the same code and environment.

Fix ascending row order by `(pc_norm, introduced_on)`, column order through
the schema, and Parquet writer settings. Use deterministic lexical order for the canonical
string keys and date order for introduction dates, not locale-dependent collation.
Record both the Parquet SHA256 and a versioned canonical logical-table fingerprint.
Define that fingerprint as SHA256 over compact UTF-8 JSON lines: first the schema version
and ordered field/type pairs, then one typed row array per sorted record. Encode dates as
ISO dates, use JSON null/booleans/integers, reject NaN, and terminate every line with LF.
Repeat builds in the same locked environment must be byte-identical; do not promise
identical Parquet bytes across different Arrow versions or platforms. Audit timestamps
can differ without changing the logical dataset identity.

Pin the Snakemake runner and one rule environment containing Python, pandas, numpy,
PyArrow, openpyxl, PyYAML and the selected HTTP client. Test macOS on the development
machine and Linux in CI; native Windows support is not part of this first delivery.
Use external scripts/commands in the declared environment, not heavy Python work in
`run:` blocks. Environment creation can be performed ahead of an offline run. Snakemake
supports per-platform explicit Conda pins, but can fall back to solving the YAML if pin
installation fails: verify the resolved environment and reject an unexpected environment
for a release build. See [distribution and reproducibility](https://snakemake.readthedocs.io/en/stable/snakefiles/deployment.html).

Safe completion is a small finalisation step, not a multi-product publication system:

1. Build and validate only under `work/<build_id>/`. Keep diagnostic logs outside final
   release directories and never expose the working candidate as the completed table.
2. Verify that both reports pass, refer to this build's source identities, and that output
   validation names the exact candidate hash. Rehash inputs before completion to detect
   changes during processing.
3. Assemble the four release files in a temporary sibling directory on the results
   filesystem. Record counts, ordered schema/types, code/environment hashes, band methods,
   known limitations and all artifact hashes in the manifest. Do not make it self-hash.
4. Verify the staged copies, then atomically rename the new directory into the unused
   `results/<release>/<build_id>/` path. Serialize finalisation for a build ID; never
   replace a conflicting existing directory. If the same completed build already exists,
   verify its identity, table checksum and logical fingerprint and leave its files unchanged.
5. Copy the completed Parquet to a temporary sibling of `results/postcode_simd.parquet`,
   verify its checksum, then atomically replace that one current file. Serialize current
   snapshot replacement even across different build IDs, and recheck the selected build
   before committing. Leave the current file untouched if it already has the expected
   hash. Its Parquet metadata must identify the build/evidence bundle without adding a
   row-level key column. Never delete the old current file before the replacement is ready.
6. Let the default `all` target verify both the current file and the selected completed
   bundle on every invocation. Missing/corrupt artifacts must fail clearly, not be hidden
   behind a cached success marker. Repair is explicit; never silently overwrite a damaged
   build bundle. New accepted releases replace the current snapshot through step 5 only.

Important Snakemake detail: ordinary declared outputs are removed before a job reruns.
For the build bundle, use `update(directory(...))`, with one finalisation rule as its
sole owner; use `update(...)` on the current Parquet output of `replace_snapshot` too.
The documented update flag preserves an existing output and restores it on a handled
job failure. Pin and test this behaviour, including forced reruns; an atomic writer alone
is not enough. See [updating existing outputs](https://snakemake.readthedocs.io/en/stable/snakefiles/rules.html#updating-existing-output-files).

Keep this separate from normal disposable candidate outputs. Do not declare `manual_data/`,
`results/`, or a shared parent directory as a rule output. No automatic deletion of old
build bundles or automatic cleanup of user-supplied files. Only the fixed current snapshot
is replaced automatically, after validation.

## 7. Validation and test acceptance

Source validation must preserve the existing check coverage, not merely match its check
count. The fixed expectations remain in `acceptance_baselines.yaml`, not values regenerated
from the same inputs during a test. Small CI fixtures use a separate, explicitly named
test contract; they must not weaken the production one.

Full-release acceptance includes:

| Check | Pinned expectation |
| --- | --- |
| Input identities | All 14 logical hashes; additional transport hashes in download mode |
| Source schemas | Six 16-column PHS files; 64/56-column postcode files; exact government schemas |
| SIMD universe | 39,972 data-zone rows across six editions; all ranks match independent government sources |
| Final shape | 247,773 rows × 166 columns; zero duplicates or null components in `(pc_norm, introduced_on)` |
| Snapshot scope | All rows carry the one configured `spd_release`; no rows appended from another release |
| User types and dates | 196,769 / 51,004 records; 162,049 current; 85,724 deleted |
| Full join coverage | Every record matches every edition: 1,486,638 successful logical joins, not that many output rows |
| Directory rank | Every source SIMD 2020 rank agrees with attached `simd2020v2_rank` |
| Current search keys | 162,049 complete NRS keys; 161,822 ordinary keys; 226 multi-candidate groups, 203 with differing 2020v2 ranks |
| Date boundaries | All 818 touching pairs; 28 retained same-day records; no negative or positive-duration overlapping intervals |
| Large-user links | 31,725 `NO LINKP`, six `NO LINK`, 19,273 real links, zero unresolved real postcode keys |
| Band evidence | Both vintage methods, all 12 divergence fingerprints and exact Shetland exception values retained |
| Percentile | Published values for 2016/2020v2; typed nulls for the four earlier editions |

The saved-output validator must reconstruct expected values from the source records and
independent government references, then compare **every row and every output column**.
Cover source-field preservation, type/null rules, keys, dates, candidate counts and all
SIMD values, and bind the report to the candidate and source evidence hashes. The final
release check verifies the manifest and artifact hashes after finalisation. Do not
validate just counts, samples, or the builder's own in-memory frame. Avoid calling the
full builder again as the sole validation oracle.

Add adversarial tests for duplicate government measurements, wrong-vintage joins,
leading-zero loss, malformed dates, false suffix stripping, sentinel handling, missing
columns, modified Parquet cells and stale success reports. Explicitly retain the
`AB123GQA` / `AB123GQB` example: two candidates, ranks 5484 and 5522.

For `ntile` resolution, add fixtures for all five statuses in the consensus table,
including all-null values and a lone cross-border part with unestablished coverage.
Confirm that differing ranks with the same requested band resolve by consensus, that
agreement on one edition/field does not resolve another, and that candidate ordering does
not affect results. Exercise date changes and retained same-day records before grouping.
Assert that the patient left join preserves input row count, including repeated input
postcodes and unresolved rows, and that ntile-only releases exclude internal diagnostics.

Extend the existing source checker, which currently checks the larger
`(pc_norm, intro, deleted)` combination, to enforce the shorter primary key too. Add
fixtures proving that a duplicate postcode/introduction pair is rejected even when its
deletion date or user type differs, while different introduction dates remain distinct
records. Reject mixed-release files. This new executable gate is implementation work;
the targeted full-data key check above has already been performed without changing the
source files.

Workflow tests must prove:

- Dry-run performs no downloads or data writes; offline execution makes no network calls
  once environments are provisioned.
- A clean online run retrieves the pinned bytes and matches the offline table.
- A normal repeat run does no downloading or table rebuilding; the final integrity check
  still runs. A fresh `audit` actually reruns source and saved-table validation.
- With two fixture releases, replacement leaves only the second release's complete set
  in the current file, including removal of records absent from that release. A failed
  replacement leaves the previous current file usable and unchanged.
- Changing helper code, schema, method settings or an environment pin invalidates the
  appropriate build. A changed source hash is not accepted without reviewed baselines.
- Timeouts, truncated downloads, archive traversal and checksum errors cannot produce an
  accepted source or completed release.
- Injected failures during building, readback, copy and finalisation leave earlier
  completed releases byte-for-byte unchanged. Test forced reruns of the same build ID,
  concurrent finalisation, a missing completion manifest, and restart after interruption.
- A missing or modified final artifact is detected even if the workflow metadata says
  the prior job succeeded. Audit checks actual source bytes, including changes that
  preserve file timestamps.
- Lineage resolves the current snapshot hash to its accepted build, source identities,
  code/configuration/environment and validation evidence. Repeated invocations have
  distinct run records without changing deterministic table bytes; reused work is labelled
  correctly. Replacing a snapshot preserves earlier provenance. An archived report remains
  inspectable without the original `.snakemake` directory and includes no patient data.

## 8. Implementation sequence and completion criteria

| Milestone | Work | Exit criterion |
| --- | --- | --- |
| 1. Freeze the contract | Add output schema, operational config, dependency pins, lineage fields and manifest download/member metadata; test final-output update behaviour | Config/schema tests pass; exact URLs/member hashes established; lineage/report scope confirmed; no ambiguity about output shape or release ownership |
| 2. Offline vertical slice | Refactor shared helpers and builder; add source gate and combined-table rules | Existing downloads produce the 247,773-row candidate without modifying `manual_data/` or prototype `out/` |
| 3. Independent readback | Implement saved-table validator, provenance, build finalisation and atomic snapshot replacement | Full output reconciliation passes; a new release replaces the whole current file; corruption/failure tests preserve the previous snapshot |
| 4. Acquisition | Implement pinned downloads/extraction, cache reuse, retries and logs | Fresh empty-cache download produces the same validated table; unsafe/mismatched inputs fail |
| 5. Operational handoff | Add integration tests, clean-environment CI, quick start, lineage report export, data dictionary and measured resource requirements | Documented commands work on tested platforms; lineage from current snapshot to exact inputs is inspectable; no-op, offline, fresh audit and recovery demonstrations pass |

Implement the offline slice first because the source bytes are already available and
audited. Download automation is still required before calling the pipeline complete.
Keep the existing prototype usable until the replacement passes full readback acceptance.

Proposed user-facing commands, **available after implementation**, from the project root
with the pinned Snakemake runner installed:

```bash
# Inspect the offline DAG without executing it.
snakemake --snakefile workflow/Snakefile --cores 2 --sdm conda \
  --configfile config/workflow.yaml --dry-run

# Build from the existing downloaded sources (the default mode).
snakemake --snakefile workflow/Snakefile --cores 2 --sdm conda \
  --configfile config/workflow.yaml

# Download the pinned release, then build and validate it.
snakemake --snakefile workflow/Snakefile --cores 2 --sdm conda \
  --configfile config/workflow.yaml --config source_mode=download

# Fresh validation, not just reuse of successful rule metadata.
# Add --config source_mode=download when auditing downloaded-cache inputs.
snakemake audit --snakefile workflow/Snakefile --cores 2 --sdm conda \
  --configfile config/workflow.yaml

# Export the preceding successful build's report before another workflow run.
# Replace RUN_ID with that run's recorded ID; match its config/overrides.
# Add --config source_mode=download for a download-mode build.
snakemake --snakefile workflow/Snakefile --cores 2 --sdm conda \
  --configfile config/workflow.yaml --report results/runs/RUN_ID/report.html
```

Provide linting and interrupted-run instructions using the tested runner's `--lint` and
`--rerun-incomplete` options; resumption must never bypass validation. The option syntax
above follows the [official CLI documentation](https://snakemake.readthedocs.io/en/stable/executing/cli.html).

Delivery is complete when one command can build from freshly downloaded inputs, the same
workflow can run offline, the saved combined table passes full reconciliation, and the
retained lineage is inspectable and failure/repeat-run tests demonstrate that completed
data is safe. Writing a Snakefile or
reproducing source counts alone is not completion.
