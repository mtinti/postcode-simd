# Updating the sources

Two maintenance jobs, with different frequencies. Neither requires a scheduler or a new
implementation plan. Use a branch and review the configuration diff, test results and
generated build report before promoting a release.

## Routine: new Scottish Postcode Directory

1. Obtain the intended NRS cut release and read its bulletin and data dictionary. Choose
   the release explicitly; a build never searches for or accepts “latest”.
2. In `simd_ingest/sources.yaml`, update `spd_release`, the NRS archive key/URL/hash,
   the selected member paths/hashes, `spd_files` and the bulletin's all/live/deleted counts.
   Keep the PHS and Government source pins and edition declarations unchanged.
   Compute hashes of the obtained bytes (for example `shasum -a 256 <file>`), and review
   them with their official origin. A matching self-computed hash proves byte identity,
   not that a download came from the right publisher.
3. If the headers are unchanged, leave `spd_schema.yaml` and `output_schema.yaml` alone.
   If NRS changed them, stop and review the new fields: update both explicit schemas,
   nullability/descriptions and output schema version as appropriate. If the directory's
   own SIMD rank changes edition or name, update `directory_rank`; do not silently remove
   the agreement check to get a green build.
4. Build with a review configuration whose `results_root` is separate from production.
   To get a change comparison, seed that directory with copies of the previous Parquet
   and its manifest. Do not edit source files/configuration while the build is running.
5. Read `BUILD_REPORT.md`: published counts, added/removed/newly deleted records,
   field changes, split/ambiguity profile and all join/readback checks. “Removed” means
   absent from the new snapshot; “newly deleted” means a retained record now has deletion
   recorded. Both are legitimate changes that deserve review.
6. Run `pytest` and `simd-ingest audit --config <review-config>` with the same source mode.
   After approval, run the approved configuration against the production results directory.
   This replaces the entire table, never appends or keeps rows absent from the new release.
   Import only a snapshot whose current manifest hash and audit agree.

A changed split count or touching-date count is not an error. Invalid keys, source/hash
mismatches, unpublished count discrepancies or missing SIMD matches are errors; investigate
rather than bypass them. A new source format may require a small parser change and fixture.
The historical examples/fingerprint in `tests/known_snapshot.json` apply only to their exact
source pins and schema. General build/audit tests apply to every configured release.
Update an approved fingerprint only after reviewing the new source-to-output evidence,
never just to clear a failing regression.

## Occasionally: new SIMD edition

1. Obtain and review the PHS and Government sources and guidance. Pin both sources and any
   documentation in `sources.yaml`; retain the existing editions.
2. Add a PHS declaration (unique key, CSV path/prefix, geography header order, data-zone
   vintage, published zone count and explicit band direction) and a matching Government
   declaration (same key/vintage/count, DBF path and column map).
3. Confirm the postcode directory supplies `DataZone<vintage>Code`. Every record must match
   in the new edition; the pipeline does not manufacture codes or silently allow nulls.
   If a future publication does not cover the archived records, that needs a reviewed
   policy/schema change, not an automatic exception.
4. Add the 14 edition columns to `output_schema.yaml`: rank, eight PHS bands, two flags,
   three Government bands. Add HB/HSCP/CA columns if this is a new data-zone vintage.
   Review storage types and descriptions, bump the schema version and record the decision.
   For shared vintages, PHS geography must agree across editions; disagreement needs an
   explicit contract change, not choosing an arbitrary edition's geography.
5. Add a fixture for the published format and known values, build and audit in a review
   directory. Check that the existing edition columns have not changed unexpectedly.
   Regenerate the data dictionary after reviewing the resulting manifest.
6. Separately review analyst edition-by-year recommendations and consumer schema imports.
   Ingestion supports explicitly selecting the new edition; it does not infer a new
   recommendation from the edition's date.

The tests include a synthetic seventh edition on 2022 data zones requiring only registry
and schema additions. That proves extension for the supported CSV/DBF layout, not that
every future publisher format can be handled without code changes.

## What to keep

Keep the code revision, original hash-pinned sources/archives and `results/runs/<run-id>`.
Each attempted build has a small record; only the current Parquet is kept by the pipeline.
Do not run competing writers. If publication is interrupted, audit before importing;
a clean rebuild is the recovery procedure.
