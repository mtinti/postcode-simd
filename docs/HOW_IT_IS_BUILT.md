# How the table is built

Read this once for the rules; read `results/BUILD_REPORT.md` for a particular run's evidence.
The [updating runbook](UPDATING.md) covers postcode refreshes and new SIMD editions.
The [decision log](../simd_ingest/decisions.yaml) records policy; [old plans](plans/README.md)
are historical, not an additional implementation specification.

## Follow one path

```text
Pinned files ──► verify hashes
                    ├─ SSPL SingleRecord ──────► latest life per whole postcode   (main index)
                    ├─ SPD SmallUser + LargeUser ► every postcode life, keys, dates (history index)
                    ├─ PHS CSVs ────────────────► population-weighted edition tables
                    └─ Government DBFs ────────► unweighted edition tables
                                    │
                    check zones/ranks and shared PHS geography
                                    │
                    join each edition on its declared data-zone vintage, once per index
                                    │
                    compare the two tables (an observation, never a gate)
                                    │
                    write both candidates → reopen → compare → replace both snapshots
                                    │
                    human report + manifest + retained run record
```

The sequence is in [pipeline.py](../simd_ingest/pipeline.py), `prepare`, `build` and
`write_output`; `TABLES` there names the two outputs. No alternate execution path, persisted
intermediate tables or server. All steps run every time; hash-verified downloads can be reused.

## Two tables, one question each

| | Main table `postcode_simd.parquet` | History table `postcode_simd_history.parquet` |
| --- | --- | --- |
| Postcode source | Scottish Statistics Postcode Lookup | Scottish Postcode Directory |
| Grain | latest life of each whole postcode, deleted ones included | every life, NRS split parts kept |
| Key | `pc_norm` | `pc_norm`, `introduced_on` |
| Data-zone allocation | zone containing the 2022 output-area centroid (`oa2022_centroid`) | zone containing the postcode (`postcode_grid_reference`) |
| Use for | present-day SIMD of a postcode; the latest-postcode SQL | SIMD valid on a date; era linkage; split parts |

The allocation difference is the one to remember. NRS builds the SSPL so that every geography
nests through 2022 output areas; its 2011 and 2001 data zones are therefore best fits of the
2022 output area, and differ from the directory's on a few percent of postcodes. The build
report section "Agreement between the two tables" counts the differences and the SIMD bands
that change because of them. Neither table is corrected towards the other. `lookup.load`
reads which product a table came from and refuses a dated question against the main table.

## The rules to review

| Decision | Implementation | Evidence |
| --- | --- | --- |
| Main table from the SSPL: one latest life per whole postcode, no suffix, counted totals | `core/sspl.py: build_latest_index` | Header contract; counted all/live/small/large totals; `pc_norm` unique; link values are sentinels or postcodes |
| Each table carries its allocation method and key in its metadata | `output_schema*.yaml`, `core/output.py: table_metadata` | Readback checks index source, release, allocation and key against the build inputs |
| Keep every directory record, including deleted and large-user records | `core/spd.py: union_index` | Published all/live/deleted counts; original fields retained as text |
| Key = postcode without spaces + introduction date | `postcode_keys`, `parse_dates` | Valid shapes/dates; unique non-null natural key |
| Only flagged small-user split suffixes are removed from `pc_base` | `postcode_keys` | Malformed or unexpected suffixes stop the build; original text and full key remain |
| Validity is introduction inclusive, deletion exclusive | `parse_dates`, `active_on` | No strict overlaps; same-day records retained but never active |
| Turn only the eight early-edition PHS bands | `core/phs.py: canonicalise_phs` | 2004/2006: `11 - decile`, `6 - quintile`; ranks and flags unchanged |
| Use the right data-zone vintage for each edition | `sources.yaml`, `core/join.py` | Same rows after each join; every record matched |
| PHS within-area bands use PHS geography | `pipeline.prepare`, `join_edition` | HB/HSCP/CA codes agree across editions sharing a vintage before storing one set |
| Copy published values, do not reconstruct bands | `core/phs.py`, `core/govscot.py` | Source pins, value ranges/direction, PHS/Government zone and rank agreement |

The directory's own published SIMD rank is also compared with the attached rank; its column
and edition are explicit in `sources.yaml`. Population is read as supplied, but no
population-weighting reconstruction is run. Published PHS and Government bands are not
compared with each other, averaged or substituted.

## Checks versus observations

A changed source hash, header, published or counted total, invalid key/date, overlapping life,
unresolved real large-user link in the directory, blank data zone, missing joined value or
failed readback blocks publication. Differences between the two tables never do.

Split counts, repeated-key counts, key lengths, touching dates, link-category counts and
current ambiguity describe a release. They are recorded, not compared with 2026/2 constants.
The report also compares the new table with the previous hash-verified snapshot by natural
key: added, removed, changed and newly deleted records, plus changes by field. The release
label alone is ignored. An unavailable/untrusted previous snapshot is stated explicitly;
it does not prevent building a source-faithful new snapshot.

Published bulletin counts are independent acceptance inputs in `sources.yaml`. Do not change
them merely to make a failing build pass.

## Saved-file validation and lineage

`core/output.py: readback` reopens the candidate. It checks ordered columns, types,
nullability, keys and metadata. Original/derived postcode fields must equal the accepted
index; a source blank is not null. Attached values are looked up again using the saved
data-zone codes, independently of the join sequence. This verifies the saved transformation,
not the publisher's deprivation methodology.

The run directory retains the accepted source registry, both schemas and decision log,
the resolved configuration, Python/dependency versions, code hashes and all checks.
The manifest links that run to the final file hash and rows-only fingerprint.
The fingerprint is a regression aid under pinned runtime versions, not a cross-version
data standard. A changed decision log can change the file hash without changing its rows.

Validation happens before publication; table/report/manifest replacements are individually
atomic, not one transaction. Use one writer and do not edit inputs while a build runs.
After interruption, a hash/readback audit tells you whether to rebuild. No restart or
concurrency state machine is maintained.

## Check one record

```bash
python -m simd_ingest.trace "AB12 3GQ"                     # main table
python -m simd_ingest.trace "AB12 3GQA" --table history    # history table, full NRS key
```

The trace verifies pinned sources, shows the saved record's data-zone join for each edition,
and compares its SIMD values with the reference rows. In the history table use
`--introduced YYYY-MM-DD` to choose a life and a full `pc_norm`/NRS split key, not an
ambiguous base postcode.

Analyst choices remain outside ingestion. The [two SQL examples](LINKAGE_BY_ERA.md) share
latest-postcode selection, A-part resolution and linked-small-user geography; one uses a
chosen SIMD edition and one uses event-year recommendations. The [Python helper](EXAMPLES.md)
keeps its separate current/as-of and own-record geography policy. Adding an edition does
not silently change either consumer policy.
