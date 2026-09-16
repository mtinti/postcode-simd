# Plan: what leaves the building, a CSV rendering of each table and coordinate-free SQL output

Implemented on 16 September 2026 in version 2.2.0. Kept as the record of what was decided and
why; the current contract is simd_ingest/export_contract.yaml, the recipe and its verification
are in docs/LINKAGE_BY_ERA.md, and the decisions are shared-exports and database-load-check.

## Aim

Two things, governed by one contract:

- Each build writes a gzipped CSV of each table beside the Parquet. This is the form in which
  the table is presented to the team and to researchers.
- The SQL examples stop returning the coordinate columns, so linkage results and the CSV follow
  the same exclusion policy. Their fields are not otherwise identical: the CSV carries every
  edition, while each SQL result selects one edition and echoes its input.

One list of columns that are not exported, read by both the CSV writer and the SQL generator.
The Parquet keeps every column and remains the authoritative artefact inside HIC, so anyone who
does need a grid reference reads it there.

Proposed version 2.2.0. The SQL output contract changes: the shared 41-column core is untouched
and the own-record context shrinks. Document the removed fields as a breaking change for
consumers of the full SQL result, even though the Parquet schemas stay unchanged.

| Query | Columns before | After |
| --- | ---: | ---: |
| `sspl/link_by_era.sql`, `sspl/link_latest.sql` | 91 | 89 |
| `spd/link_by_era.sql`, `spd/link_latest.sql` | 107 | 103 |
| `spd/link_as_of.sql` | 110 | 106 |

## What was measured, 16 September 2026

| Table | Rows by columns | Parquet | CSV | CSV gzipped |
| --- | --- | ---: | ---: | ---: |
| main | 230,103 by 146 | 13.7 MB | 146 MB | 8.0 MB |
| history | 247,773 by 162 | 17.6 MB | 184 MB | 11.9 MB |

- **No delimiter characters exist in the data today.** Zero commas, tabs and quotes across every
  text cell of both tables. Escaping is not what decides the format, but the writer must still
  handle it, because a future release could introduce one.
- **The postcode sources are already CSV and contain no text nulls.** Both readers use
  `dtype=str, keep_default_na=False`, so an empty source field becomes an empty string.
- **Nulls and blanks are different things, and both are common.** In the history table the text
  nulls are structural, created by stacking two files with different column sets: nine columns
  exist only in SmallUser.csv (the eight census counts and NeverDigitised) and one only in
  LargeUser.csv (LinkedSmallUserPostcode). Nine columns across 51,004 large-user rows plus one
  across 196,769 small-user rows is 655,805, exactly the measured null count. Separately there
  are 1,923,400 blanks, in the same columns: NeverDigitised alone is blank on 195,372 small-user
  records. The date columns add their own nulls, 162,049 undeleted records in the history table
  and 161,822 in the main table.
- **The main table has no text nulls**, because the lookup is a single file. Its 187,490
  small-user blanks in LinkedSmallUserPostcode are blanks, not nulls.
- **Dropping the coordinates saves a third of the gzip.** Coordinates compress badly, so the
  plain text shrinks by 2 to 5% while the gzip shrinks by 17 to 34%.

## The export contract

`simd_ingest/export_contract.yaml`, version 1. A separate file from the output schemas, so the
Parquet contracts and their hashes stay untouched and both exporters read the same list.

**Columns not exported**: `GridReferenceEasting` and `GridReferenceNorthing` from both tables,
and `Latitude` and `Longitude` from the history table as well. Two reasons, recorded separately
because they have different standing:

- Do not carry coordinate fields into outputs whose purpose is deprivation and area context.
  This is a project data-minimisation choice, not an anonymisation guarantee.
- NRS supplies its index and lookup products under the Open Government Licence and restricts
  "postcode boundaries and grid references" separately, but its licensing page does not settle
  which of the two governs a grid reference column inside an index file. Removal is a
  conservative project policy pending confirmation from NRS or HIC information governance, not
  a settled legal requirement. It is on the list of questions for Research Data Scotland.

`GridLinkIndicator` and `GridLinkPositionalAccuracy` stay in both exports: they describe how the
grid reference was matched and reveal no location.

**The release boundary.** The CSVs are postcode lookup tables, not patient datasets. A SQL
linkage result still contains the input id, the full postcode and the postcode keys, so removing
coordinates does not make it anonymous or approve it for release. Disclosure review and release
approval remain downstream; this plan implements neither.

**CSV format**

| Property | Value |
| --- | --- |
| Dialect | Comma separated, RFC 4180 quoting, quote only where needed |
| Encoding | UTF-8, no byte order mark |
| Line ending | LF, an explicit variation from RFC 4180's CRLF |
| Compression | gzip, always |
| Header | the table's column order, minus the columns not exported |
| Dates | `date32` fields as `YYYY-MM-DD`, empty when null; the original date-text columns are unchanged source text |
| `is_current` | `1` and `0`, so it loads into a bit column |
| Integers | plain digits, no separators |
| Text | exactly as stored, so leading zeros in island and 1995 board codes survive |
| Names | `results/postcode_simd.csv.gz`, `results/postcode_simd_history.csv.gz` |

| Table | Columns | CSV | Gzipped |
| --- | --- | ---: | ---: |
| main | 146 to 144 | 143 MB | 6.7 MB |
| history | 162 to 158 | 174 MB | 7.8 MB |

**Reading an empty cell.** The CSV writes the same empty cell for a null and a blank, so
reconstruct from the table, the column and the record type, never from the cell alone:

- **Main, from the SSPL:** every text empty is a source blank, for both user types.
- **History, from the SPD:** in the eight census counts and NeverDigitised an empty cell is a
  structural null for a large-user record and a source blank for a small-user one. In
  LinkedSmallUserPostcode it is a structural null for a small-user record and a source blank for
  a large-user one.
- **Both tables:** an empty `deleted_on` is a date null and agrees with `is_current = 1`. The
  source text column `DateOfDeletion` stays blank. Every other text empty is a source blank.
- An empty required date, key, boolean or SIMD value is an error, never zero or a fabricated
  date. An unexpected null outside these rules stops the export.

The inference runs from the record type to the kind of empty, never the other way: a small-user
record can have an empty NeverDigitised, and 195,372 of them do. Readers must load every column
as text first, keeping leading zeros and literal strings such as `NA`; restoring the declared
types is a separate step.

**Attribution travels with the files.** `results/CSV_README.txt` carries the acknowledgement
every source requires, not only the NRS one: "Contains NRS data © Crown copyright and database
right 2026", "Incorporates data from PAF® the copyright in which is owned by Royal Mail Group
Limited and/or Royal Mail Group plc", and the Open Government Licence acknowledgements for the
Public Health Scotland SIMD files and the Scottish Government shapefile tables. It also names
both releases, the build date, the columns not exported and the file hashes. A comment line
inside a CSV would break the readers this format exists for. Review the statements and the year
against [the NRS licensing page](https://www.nrscotland.gov.uk/publications/geography-products-licensing-and-pricing/)
and each pinned source on a refresh; 2026 is not a permanent value.

## Loading the CSV into a database

**The typed import.** Load the decompressed CSV into an all-text staging table first, then
restore the declared types into the target table. Keep source text as Unicode with sufficient
lengths, including text that looks numeric or like a date. Convert only the schema's dates,
booleans and integers. Turn an empty `deleted_on` into `NULL` before any date conversion,
require booleans to be exactly `0` or `1`, and reject conversion failures rather than letting
them become nulls. Enforce the natural key, `pc_norm` for main and `(pc_norm, introduced_on)`
for history. SQL Server converts an empty string to `1900-01-01`, so implicit date conversion is
not acceptable. Bulk insert also defaults to a tab field terminator and needs `FORMAT = 'CSV'`
with explicit comma, UTF-8 and LF settings. See
[bulk insert](https://learn.microsoft.com/en-us/sql/t-sql/statements/bulk-insert-transact-sql)
and [char and varchar](https://learn.microsoft.com/en-us/sql/t-sql/data-types/char-and-varchar-transact-sql).

**Verifying the load with a row digest.** The build records, per table, a digest computed from
the accepted table itself, not from a re-read of the CSV, so an import mistake cannot appear on
both sides of the comparison. The export contract versions this exact recipe:

- Render logical field values, before CSV quoting: unchanged Unicode text, dates as
  `YYYY-MM-DD`, booleans as `1` or `0`, and integers in base 10 without separators. Do not trim
  spaces or normalise Unicode. A null becomes U+0000 and a blank stays empty.
- Before adding that framing, reject U+0000 and U+001F in every non-null text value, both in
  the accepted table and in the loaded SQL table. They are reserved characters, not merely
  assumed absent; never remove or replace them. Use code-point-safe checks, not a
  collation-dependent text search that may ignore a control character.
- Join the columns in contract order with U+001F. In UTF-8 the null marker is the single byte
  `0x00` and the separator is `0x1F`; commas, quotes and newlines stay literal field content.
- Hash the UTF-8 bytes with SHA-256 to get a row digest.
- Aggregate order independently: read the first eight bytes of each digest as a signed
  big-endian integer and sum them exactly. Python uses arbitrary-precision integers; SQL uses
  `SUM(CONVERT(decimal(38,0), signed_prefix))`. Convert **before** summing: `SUM(bigint)` can
  overflow, and casting its result is too late. An empty table has count zero and sum zero.
- Store the total as a decimal **string**, so JSON readers cannot round it, alongside the row
  count, table identity and digest-definition version. The manifest's export-contract hash
  identifies the rendering and column order. This is separate from the existing rows-only
  Parquet fingerprint, which stays unchanged.

The SQL rendering keeps `nvarchar(max)` throughout concatenation, supplies `NCHAR(0)` for
every null, and uses `NCHAR(31)` between fields. `CONCAT_WS` otherwise drops null arguments.
Hash an explicit UTF-8 conversion, for example
`HASHBYTES('SHA2_256', CONVERT(varchar(max), canonical_text COLLATE Latin1_General_100_BIN2_UTF8))`.
A UTF-8 collation on an `nvarchar` expression alone still hashes UTF-16 bytes; `max` types also
prevent intermediate truncation. Pin the Python/SQL byte agreement with independently stated
test vectors. See Microsoft's [SUM return types](https://learn.microsoft.com/en-us/sql/t-sql/functions/sum-transact-sql),
[UTF-8 varchar encoding](https://learn.microsoft.com/en-us/sql/t-sql/data-types/char-and-varchar-transact-sql)
and [CONCAT return types](https://learn.microsoft.com/en-us/sql/t-sql/functions/concat-transact-sql).

This is a compact, probabilistic check for accidental load corruption, not an exact comparison
of every cell or a tamper-proof signature. Truncating each SHA-256 to eight bytes and adding the
results permits collisions and cancelling changes. Matching counts and totals give useful
assurance, but do not prove identical tables; the plan accepts that trade-off explicitly.

**The compact SQL check.** Generate `docs/sql/check_loaded_digest.sql` from the contracts, with
one check per product. Supply expected build/contract identifiers, versions, counts and totals
from the verified manifest, never from the candidate database table. Check the CSV file hashes
before import and run against a candidate table that is not being changed during validation.
The script does not load another reference table or promote or repair the candidate:

- First verify the exported column set and the documented SQL mapping of types, nullability
  and text capacities, plus the natural primary-key constraint, non-null keys and uniqueness.
  A digest cannot establish any of these structural properties.
- Reject missing or incompatible expected metadata and reserved characters; compare
  `COUNT_BIG(*)` and the recomputed total with the manifest values.
- Report pass/fail for each required check and `THROW` on failure. Stop before computing a
  digest if its structural or framing prerequisites fail; a skipped check is not a pass.

**Confirming the queries run.** The five generated queries are executed against SQL Server on a
small reviewed cohort of dummy identifiers, and their statuses, source keys, selected geography
and measures compared with the expectations already used in the DuckDB tests: AB24 2TY resolving
through its link to quintile 1 rather than its own 5, FK17 8DS before, inside and after its gap,
and TD9 7PQ on either side of its deletion. This closes the "SQL Server syntax intended but not
verified" caveat that the documentation has carried since v1.1. A SQL Server 2022 container is
already available on the build machine.

## Steps of the work

1. **Contract.** Write `simd_ingest/export_contract.yaml`: the dialect, the value renderings,
   the per-table file names, the columns not exported, the two reasons, the table-specific null
   reconstruction, the versioned digest definition including reserved characters, and the
   attribution lines. Document the SQL type mapping used by import and validation. Archive the
   contract with each run record and record the policy in the decision log, leaving the Parquet
   schemas unchanged.
2. **CSV writer.** `simd_ingest/core/text_output.py` with `write_csv` and `readback_csv`. The
   readback reopens the file with ingestion's reader settings and compares every cell with the
   accepted table rendered by the contract's rules, catching a shifted column, a mangled value
   and a lost leading zero, which a row count would not.
3. **SQL generator.** `sql_examples.py` reads the same contract and omits those columns from the
   own-record context, including any intermediate reference to them, so the queries also run
   against a coordinate-free imported table. Regenerate the five files. The core is unchanged.
4. **Digest and SQL check.** Compute the digest from the accepted table in the same step as the
   CSV, rejecting reserved characters first. Record the decimal-string total, row count, table
   identity and definition version in the manifest. Generate the compact SQL script above,
   including structural checks and explicit failure, with the same rendering and overflow-safe
   sum. Keep expected manifest values separate from values computed from the loaded table.
5. **Pipeline.** Write both CSVs, the attribution file and the digests into the existing staging
   directory after the Parquet readback passes. Replace the outputs one at a time, then the
   build report, and the manifest last, so a manifest naming a set of hashes is evidence that
   those files were written. Publication is atomic per file, not across the set: an interruption
   between replacements can leave a mixed directory, which is why a consumer checks the hashes
   before using anything, and why `audit` exists.
6. **Always on.** No switch, so a results directory cannot hold yesterday's CSV beside today's
   Parquet after a successful build.
7. **Manifest and audit.** Each table gains a `csv` entry with file name, sha256, byte size, row
   count, column count, the columns omitted and the digest. The manifest records
   `export_contract_sha256` beside the other contract hashes, and the attribution file's hash.
   `audit` recomputes those hashes, checks each CSV header against the contract, and compares
   the active contract hash with the manifest. It also recomputes each export digest and row
   count from the verified, saved Parquet's exported columns and compares them with the
   manifest; it rejects an unsupported digest version. The full CSV cell comparison stays at
   build time.
8. **Tests.** On the synthetic fixture: header order, row count, round trip equality, a leading
   zero, a column where a blank and a null sit side by side and are reconstructed correctly by
   table and record type, the date and boolean renderings, and quoting of values containing a
   comma, a quote, a newline and non-ASCII characters even though the real data has none.
   Corruption cases: a changed cell, a dropped column and a truncated file must each fail the
   readback. Independently stated Python/SQL digest vectors cover null versus blank, leading
   zeros, trailing spaces, non-ASCII and supplementary Unicode, a row exceeding 8,000 bytes,
   signed prefixes, a sum outside the bigint range and an empty table. Both sides reject
   U+0000 and U+001F in source text. Audit tests reject altered manifest counts, totals and
   unsupported versions. A test asserts that no CSV header and no SQL output contains a column
   named in the contract. The SQL tests' column counts and context list move to the contract,
   while their expected headers, the 41-column core and the measure mapping stay independently
   stated, so the production renderer is never the only oracle. On the real tables, behind the
   source-pinned skip, both files round trip to the same rows as their Parquet. On SQL Server:
   import both CSVs by the documented recipe, pass the structural and digest checks, and run
   the five queries against the reviewed cohort. In disposable test tables, verify failure for
   a missing primary key, a wrong type or nullability, duplicate keys, a removed row, and changed
   cells outside that cohort: a lost leading zero, truncated text, blank turned null and date
   turned `1900-01-01`. These are specific regression cases, not a claim to catch every possible
   digest collision.
9. **Docs.** A conventions section in both data dictionaries, generated from the contract so it
   cannot drift. The SQL guide's column counts and context table updated. The import recipe, the
   compact SQL check, its manifest inputs, failure behaviour and assurance limits. A line in the
   README, the results list in DOCKER.md, and a note in UPDATING.md that the columns not exported
   are reviewed if NRS changes its licensing or if information governance rules differently.

## Acceptance

- Both rows-only fingerprints unchanged: `59369357e44e45a5…` for history, `9515021d99099b43…`
  for main. The Parquet **file** hashes will change, because recording this policy changes the
  decision log and its hash is embedded in the file. That is expected, and is why the criterion
  is the fingerprint.
- Each CSV has its table's row count, the contract's column order, and reads back cell for cell.
- Reconstruction keeps main's source blanks and history's structural nulls apart, and restores
  the declared dates, booleans and integers.
- No CSV header and no SQL result contains a grid reference, latitude or longitude column.
- `results/CSV_README.txt` is present, names both releases and all four publishers' terms, and
  its hash is in the manifest.
- `audit` verifies both CSVs, the attribution file and the contract hash, and reproduces the
  manifest's export digests and row counts from the verified saved Parquet.
- On the SQL Server container, both imported tables pass the structural, key, framing, count
  and digest checks. The specified mutation tests fail explicitly, and all five lookup queries
  agree with their reviewed expectations. Without that run, SQL Server support stays explicitly
  unverified rather than inferred from DuckDB.
- Suite green natively and in the container.

## Deferred to a separate plan

A generated `check_loaded_tables.sql`, shipped with every build, that loads an independent
reference from the CSVs inside the database and compares all 144 or 158 exported columns cell by
cell, with its own mutation suite and an acceptance record before table promotion. It is a
validation product in its own right and should be reviewed as one, not as part of shipping a
CSV. The compact digest is cheaper but does not offer the same assurance as exact comparison.
The larger harness would add both-direction key coverage against the reference, exact text
comparison rather than SQL Server's default case and trailing-space equality, and readable
per-column expected/actual samples. Basic structure, nullability, natural-key, count and
explicit failure checks are **not deferred**: they belong to the compact SQL script above.

## What this plan does not do

The Parquet keeps every column and its schemas are unchanged. There is no second, slimmer CSV:
one file per table, the same one shown to the team, so there is never a second artefact that can
disagree with it. Nothing here changes how a postcode is linked to SIMD, or any stored value.
The plan does not implement anonymisation, authorise release of patient data, or make promotion
of an imported table automatic.
