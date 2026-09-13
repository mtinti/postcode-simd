# Historical plan: SSPL main table, SPD retained for history

Drafted 12 September 2026, revised the same day after checking the SSPL 2026/1 file.
Status: superseded implementation proposal, retained as the original investigation record.
Option A was implemented on 12 September and corrected by the review on 13 September 2026.
For the current contract read [How it is built](../HOW_IT_IS_BUILT.md),
[SQL linkage](../LINKAGE_BY_ERA.md) and [NRS guidance check](../NRS_GUIDANCE_CHECK.md).

Corrections to the historical text below:

- Current main source is SSPL 2026/2, not 2026/1; history remains SPD 2026/2.
- The preliminary cross-table counts used incorrect representatives for 19 postcodes.
  They did not isolate release effects from allocation methods or prove PHS equivalence.
  Use the generated build report for current observations, never the counts below as gates.
- The default SQL reads main; an explicitly named SPD setup supports the same queries.
  Selecting an edition by event year does not require historical postcode matching.
- Both tables build together; no `--table` build switch was introduced. Trace has `--table`;
  ground-truth cases stay SPD-based and main values are checked against their own source zones.
- Package 2.0.1 and main schema `postcode_simd_sspl_v2` incorporate the coherence fixes.
  Local validation and source fingerprints are recorded by the current tests/build report;
  release tagging and external publication are separate human actions.

Everything below records the original proposal, including alternatives not selected and
claims corrected above. It is not the current maintenance or acceptance checklist.

## 1. What was checked

Downloaded `https://www.nrscotland.gov.uk/media/jypjymup/sspl-2026-1.zip` (8,901,207 bytes,
SHA256 `b8bc805567a167dd23a8891dddf44855a8174ddff3885c7f3caa0defc8d83478`). Members:

| Member | Size | Content |
| --- | ---: | --- |
| `SingleRecord.csv` | 76,435,515 | the lookup, 229,708 records, 50 columns; SHA256 `f239c2bab4850c22b04fbb05029336dec5720d1e216ae77a4ec6f3f5c5a6a563` |
| `SSPL Data Dictionary 2026-1.docx` | 121,713 | field list and the "making unique postcodes" rule |
| `SSPL News Bulletin 2026-1.docx` | 107,010 | version note: no changes, no known errors |
| `SSPL261_PreOpSPR25_SPC25.zip` | 2,789,927 | pre-operational 2025 Scottish Parliament boundaries lookup; not needed |

The dictionary calls the product "SPD SG Version". The CSV is built from the January 2026
PAF; SPD 2026/2 has introductions up to 30 July 2026. So they are different cuts.

### Answers to the step 0 questions

| Question | Answer from the file |
| --- | --- |
| Column list | 50 columns, the same names as the SPD for shared fields, plus `PostcodeType` (S/L). The dictionary lists three fields the CSV does not contain: `DeliveryPointCount`, `DeliveryPointCountNonResidential`, `HouseholdCount`. Dictionary order differs from CSV order. |
| `DataZone2001Code` | present, never blank, 6,498 distinct codes, all inside the PHS 2001 table |
| `DataZone2011Code` | present, never blank, 6,972 distinct codes, all inside the PHS 2011 table |
| Blank geography | none in any output area, data zone, health board, council, HSCP or grid reference column. The only blanks are the link field on small users, deletion date on live records, census counts, and the strategic development planning area. The dictionary says undigitised postcodes receive imputed values. |
| Large users | 42,535 records, `PostcodeType = L`. `LinkedSmallUserPostcode` has `NO LINKP` on 27,162 and `NO LINK` on 5; 15,368 real links, 9 of them with an A suffix (the dictionary says suffixes on links are kept), 1 pointing at a small-user postcode absent from the file (EH3 9RW to EH3 9PE, deleted 1999). |
| Large-user geography | own record, from its own grid reference, not the linked postcode's |
| Deleted postcodes | included: the latest life of every postcode, 68,143 of them deleted. `DateOfDeletion` present. |
| Dates | `DD/MM/YYYY` without the SPD's ` 00:00:00`; no deletion before introduction; no same-day records |
| Split postcodes | none in the text; `SplitIndicator = Y` on 337 small users and 23 large users marks records that were split in the SPD, made whole on the A part with counts summed |
| `Postcode` unique | yes |
| Published totals | none in the bulletin or dictionary. Counted: 229,708 all; 187,173 small user (156,748 live); 42,535 large user (4,817 live); 161,565 live |
| SIMD 2020 rank | present, never blank, 1 to 6,976, and equal to the PHS 2020v2 rank of the record's own `DataZone2011Code` on all 229,708 records |
| Licence | not in the zip; the page links "Geography products - licensing and pricing" |

### Agreement with the SPD 2026/2 table

Compared with the latest life of each whole postcode in the current table (A part for splits):

| Comparison | Result |
| --- | --- |
| Postcodes | every SSPL postcode is in the SPD; 395 SPD postcodes are missing from the SSPL, all introduced from January 2026 onwards (cut difference) |
| Introduction date | equal on 229,595; 109 earlier in the SSPL, where the SPD has a later re-introduction |
| Live/deleted | 233 live in the SSPL but deleted in the SPD, 92 the reverse, both from the cut difference |
| User type | differs on 37, all re-introduced with a new type after January 2026 |
| `OutputArea2022Code` | differs on 67 |
| `OutputArea2011Code` | differs on 146 |
| **`DataZone2011Code`** | **differs on 10,695 postcodes, 6,234 of them current** |
| **`DataZone2001Code`** | **differs on 15,338 postcodes, 9,312 of them current** |
| `DataZone2022Code` | differs on 128 |
| Health board 2019 | differs on 3 |

The data-zone differences are not cut differences. They come from how the SSPL is built:
every higher geography is taken from the centroid of the postcode's **2022** output area.
Evidence in the file itself: in the SSPL each 2022 output area maps to exactly one 2011 data
zone and one 2001 data zone, whereas 2,344 of its 2011 output areas map to more than one
2011 data zone. In the SPD it is the other way round: every 2011 output area maps to exactly
one 2011 data zone, and 3,411 of the 2022 output areas span more than one 2011 data zone.
So the SSPL's `DataZone2011Code` is the 2011 data zone that contains the 2022 output area
centroid, not the 2011 data zone that contains the postcode. The same holds for 2001.

Effect on the attached SIMD for current postcodes present in both products:

| Measure | Current postcodes that would change |
| --- | ---: |
| 2020v2 PHS Scotland quintile | 3,839 of 161,233 (2.4%) |
| 2020v2 PHS Scotland decile | 4,878 |
| 2020v2 most-deprived 15% flag | 1,007 |
| 2012 PHS Scotland quintile | 5,842 |

Quintile moves: 2,355 by one band, 970 by two, 409 by three, 94 by four. The postcodes
whose 2011 data zone changes hold 101,659 of the 5,434,519 people in the 2022 census counts.

For a future SIMD published on 2022 data zones the two products would agree except for
the 128 cut-related differences.

## 2. What this means for the choice

The SSPL is a clean file for this pipeline: no blank geography, unique postcodes, both
vintages of data zone, sentinels for PO boxes, latest life including deleted postcodes.
Every existing gate would pass with the count and date-format changes noted below.

But the SSPL answers a different question from the SPD. It gives the 2022-output-area-based
best-fit data zone, designed so that statistics aggregated from 2022 output areas nest
consistently. The SPD gives the data zone the postcode sits in. PHS builds its own postcode
lookups from the SPD, and the guidance this project follows attaches SIMD through the data
zone of the postcode. An SSPL-based main table therefore disagrees with a PHS-style lookup
on 2.4% of current postcodes for the 2020v2 quintile, and more for the 2001-vintage
editions.

Three ways to proceed:

- **A. SSPL main table, as requested.** Correct if the requirement is GSS Geography Policy
  alignment for published statistics. The divergence from the SPD must be stated in the
  table metadata, the dictionary and the report, with the counts above regenerated each
  release.
- **B. Keep the SPD as the source of the data zone and add a latest-postcode table.** The
  SQL view `simd_postcode_latest` already defines "latest life, A part, linked large users".
  Materialising it as a second Parquet gives the SSPL's convenience (one row per whole
  postcode) with the SPD's allocation, and agrees with PHS practice.
- **C. Both.** The SPD history table, the SPD-derived latest table, and the SSPL table, each
  labelled with its allocation method. More to maintain, and two current answers per
  postcode invite mistakes.

Recommendation: B for record-level health linkage, A only if the outputs must follow the
GSS policy. The rest of this plan is written for A, since that is what was asked; B is a
smaller change and mostly reuses the SQL already written.

## 3. Steps for option A

### Step 1. Record the decisions

Add to `decisions.yaml`:

1. Two tables and two keys: main from the SSPL keyed on `pc_norm`; history from the SPD
   keyed on `(pc_norm, introduced_on)`, unchanged.
2. Which consumer reads which: as-of and era lookups need history and read the SPD table;
   latest-postcode lookups and the SQL examples read the main table. `lookup.load` reads
   `index_source` from the table metadata and refuses `on=` against the SSPL table.
3. Allocation method is part of the contract: the main table's data zones are 2022
   output-area-centroid best fits; the metadata carries `allocation: oa2022_centroid`
   for the SSPL and `allocation: postcode_grid_reference` for the SPD.
4. Split policy is NRS's, upstream. No `pc_base`, no `split=` option on the main table.
5. PO boxes and unlinked large users: same defaults as now; the sentinels exist in the SSPL.
6. Published totals: NRS publishes none for the SSPL. The pinned file's counted totals are
   recorded in `sources.yaml` as the expected values, marked as counted, not published.
7. Version alignment: the two NRS products are different PAF cuts; cross-table agreement
   is an observation, never a gate.
8. Package version `2.0.0`, because the main table's key and file name change.

### Step 2. Implementation

- `sources.yaml`: `sspl` remote object (zip above, member `SingleRecord.csv`, both hashes,
  licence), `sspl_release: '2026_1'`, `sspl_file` with counted totals
  `{all: 229708, live: 161565, small_user: 187173, large_user: 42535}`.
  Registry validation: totals consistent, exactly one SSPL file.
- `simd_ingest/sspl_schema.yaml`: the 50-column header, version 1.
- `simd_ingest/core/sspl.py`: `read_sspl` and `build_latest_index`. Reuse `postcode_keys`
  with a rule that forbids suffixes, and `parse_dates` extended to accept `DD/MM/YYYY`
  with or without the time. Derived columns: `pc_norm`, `spd_user_type` from
  `PostcodeType`, `sspl_release`, `introduced_on`, `deleted_on`, `is_current`.
  Gates: header, totals, `pc_norm` unique, no suffix, no blank data zone, link sentinels
  only from the known set, no deletion before introduction. Observations: link categories,
  links with a suffix, links to postcodes absent from the file, `SplitIndicator` counts.
- `core/join.py`, `core/output.py`, `core/changes.py`: the key comes from the output
  schema (`key: [pc_norm]` or `[pc_norm, introduced_on]`). No other join change; the
  SSPL index already has `DataZone2001Code` and `DataZone2011Code`.
- `output_schema_main.yaml` (SSPL fields plus the same derived, PHS geography and SIMD
  columns) and `output_schema_history.yaml` (today's file, renamed, rows unchanged).
- `pipeline.py`: `build` writes the history table first and confirms its fingerprint, then
  the main table; `--table main|history|all`; one run record; manifest gains `tables`.
- `core/report.py`: a main-table section and an "Agreement between the two tables"
  section reproducing the comparison above from the two tables of the run.
- `lookup.py`: `index_source` awareness; `scope` unchanged. `docs/sql/link_latest.sql`
  gets an SSPL variant with no latest-life selection.
- `trace.py`, `ground_truth.py`: `--table`. The 360 ground-truth cases are current
  ordinary small-user postcodes, so all should be in the SSPL; expect some to fail on the
  main table because of the allocation difference, and treat those as documented, not as
  errors.
- Tests: synthetic SSPL in `fixture_project.py`; unique key, forbidden suffix, blank zone,
  sentinel and date-format cases; both tables in one run; history fingerprint unchanged;
  as-of refused on the main table.
- Docs: README, HOW_IT_IS_BUILT, UPDATING (two NRS files, different cadences),
  NRS_GUIDANCE_CHECK (rewrite "why the SPD" as "which table for which question", with the
  allocation finding), DATA_DICTIONARY for both tables.

### Step 3. Acceptance

- History table rows-only fingerprint `59369357e44e45a5…` unchanged.
- Main table: 229,708 rows, `pc_norm` unique, every record matched in all six editions,
  readback passes, metadata names the SSPL release, key and allocation method.
- Report shows the cross-table comparison with the counts in section 1 (or the new
  release's), reviewed by hand.
- `pytest` green natively and in the container; `audit` covers both tables.
- Tag `v2.0.0`.

## 4. Steps for option B, for comparison

1. Decision: the latest-postcode table is derived from the SPD by the rules already in
   `create_latest_postcode_lookup.sql`; the SSPL is not used.
2. `core/latest.py` implements those rules in pandas; a test proves it matches the SQL view
   row for row, as `test_sql.py` does today.
3. `pipeline.build` writes `postcode_simd_latest.parquet` after the history table, with its
   own readback and a section in the report.
4. Docs and dictionary; version `1.4.0`, since nothing existing changes.
