# Plan: the published SIMD domain bands

Drafted 30 September 2026, revised the same day after review (nullable status, the flag in
Python results, the status scoped by table, split-part consensus,
the status in the SQL and the walkthrough). Status: implemented for release 5.0.0 (decision
simd-domain-bands). Implements the decision recorded in
[Domain_Ntiles_Test_Plan.md](Domain_Ntiles_Test_Plan.md) on 30 September 2026; the evidence is
there and is not repeated here.

## Aim

Attach the Scottish Government's published quintile, decile and vigintile of every SIMD domain,
for every edition, to both tables, **copied as published**, never derived. Every rank keeps its
current source; the new source supplies the bands only, and is admitted only where its ranks
match ours.

## Decisions carried in

1. **Copy, never derive.** No rule based on the rank alone reproduces every published band: the
   publisher splits some ties and treats the same 2016 and 2020 tie two ways.
2. **Ranks stay from the shapefiles.** The 4.0.0 domain rank columns do not change.
3. **Bands come from three statistics.gov.scot CSVs**, the only publication of domain bands.
4. **Gate rank against rank.** A CSV band is used only where the CSV's rank for that edition,
   domain and zone equals the shapefile's, or differs in a way pinned exactly.
5. **2020v2 housing, option 2.** Copy its bands and mark the 628 zones where the two Government
   sources disagree on the housing rank. The mark means the sources disagree on the rank, never
   that the band is wrong.
6. **Scope.** Unweighted, Scotland only: quintile, decile, vigintile. No weighted domain bands,
   no health board, HSCP or council domain bands, no derived value of any kind.
7. **Release 5.0.0.** New columns change both schemas, the CSV digests, the SQL output and the
   loader's expectations; a loaded table is out of date, as for 3.0.0 and 4.0.0.

## Step 0: before any code

**Done 30 September 2026.** All three statistics.gov.scot CSVs are byte-identical across
downloads hours apart (2004 to 2012 `d9745d9d...`, 2016 `3be67d03...`, 2020 `25fea7dd...`), so
they are pinned by SHA256 like every other source. Each dataset page states the Open Government
Licence v3.0, publisher the Scottish Government, contact simd@gov.scot. statistics.gov.scot is
the host: it has all three datasets in one format. data.gov.scot (Data about Scotland) is a
known mirror: it holds the 2016 dataset under the same licence and shows no 2020 dataset. Its
2004 to 2012 and 2016 files were pinned on 9 September and retired on 10 September, when only
their overall bands were needed (`government-bands-from-shapefile-tables`); they still sit in
`manual_data/gov.scot/` and carry the same values as the statistics.gov.scot files, row for
row, with different column names (`GeographyCode`, `Simd Domain`). The email to the SIMD team
is drafted, for Michele to send; the feature does not wait for the reply.

The checklist as planned:

- **The sources are stable to pin.** Checked 30 September: two downloads of the 2020 CSV hours
  apart are byte-identical (SHA256 `25fea7dd...`). The download answers with a redirect and a
  generated file name, so the pin is the content hash, not the name. Re-check the two historical
  files the same way.
- **The addresses.** statistics.gov.scot may be moving platform (the review calls it the Data
  about Scotland portal). Record the dataset pages and the download address for each; the build
  reads the pinned copies in `manual_data` offline and never depends on the site.
- **The licence.** Confirm it is the Open Government Licence, from each dataset's page, and
  record it under `licences`.
- **Write to the SIMD team** asking which 2020 housing ranking is authoritative, citing both
  ranks for S01008634 (2093 and 2092.5). The feature does not wait for the answer.

## Design

### 1. Sources and registry

Three `remote_objects`, pinned by URL, SHA256 and size, stored under
`manual_data/statistics.gov.scot/`:

| Key | Dataset | Editions | Rows | Size |
| --- | --- | --- | --- | --- |
| `sgs_simd_historical_i` | `scottish-index-of-multiple-deprivation-historical-i` | 2004, 2006, 2009, 2012 | 806,620 | 57.5 MB |
| `sgs_simd_historical_ii` | `scottish-index-of-multiple-deprivation-historical-ii` | 2016 | 223,232 | 18.7 MB |
| `sgs_simd_2020` | `scottish-index-of-multiple-deprivation` | 2020 | 223,232 | 18.7 MB |

Each `govscot_editions` entry gains a `bands` block naming its file and the CSV's `DateCode`
(`2009` for 2009v2, `2020` for 2020v2); the domain names map through one fixed table from the
CSV's `SIMD Domain` values (`Access To Services` to `access`, `Education Skills And Training` to
`education`, and so on), so the registry stays the single statement of which domain exists in
which edition. The CSV's `SIMD` rows (the overall index) are read for the cross-check in
section 2 only; the overall bands stay from the shapefile.

### 2. The gate

Read each CSV once, long format, and check before any band is used. Every failure stops the
build.

- **Shape.** Columns exactly as expected; `FeatureType` is the edition's data-zone vintage;
  `DateCode` only the declared editions; `Measurement` only Rank, Quintile, Decile, Vigintile;
  every zone of the edition present exactly once per domain and measure; no 2004 crime rows.
- **Ranks against the shapefile.** For every edition, domain and zone, the CSV rank equals the
  shapefile rank, except two pinned kinds of difference:
  - **2004 to 2012: a half rank rounded up.** The shapefile rank ends in .5 and the CSV holds the
    next whole number. Checked zone by zone, so any other difference, including a half rounded
    down, fails.
  - **2020v2 housing: the 628 zones**, listed in a committed audit file,
    `simd_ingest/audit/sgs_2020_housing_rank_disagreements.csv`, with zone code, shapefile rank
    and CSV rank. The set must match exactly: a zone missing from the list, an extra zone, or a
    listed zone with other ranks all fail.
- **The overall index agrees.** The CSV's overall rank and bands equal the shapefile's for every
  edition and zone: an independent check that the two publications describe the same index.
- **Bands.** Whole numbers within 1 to 5, 10 or 20; never decreasing as the CSV's own rank
  rises, split ties allowed (the publisher places some tied zones in adjacent bands).
- **Observations, not failures.** Per edition and domain: the number of tied groups the
  publication splits across bands, and the band sizes, recorded in the build report.

### 3. Schema

Per edition and published domain, three columns, type `int8`, not nullable, source
`govscot_bands`: `simd{edition}_{domain}_domain_quintile`, `_decile`, `_vigintile`. Described as
the Scottish Government's published unweighted band of the domain rank, 1 most deprived, copied
as published; the publisher places some tied zones in different bands. 41 pairs, 123 columns.

One more column, `simd2020v2_housing_domain_rank_source_status`, type `string`, nullable: null,
or `rank_sources_disagree` for the 628 zones. Described as: the Scottish Government's
statistics.gov.scot dataset and its shapefile give this zone different housing ranks; the rank
here is the shapefile's and the bands are the published ones; for 626 of the 628 zones the band
is the same under either ranking. It is never set for a zone whose ranks agree.

All 124 columns are appended at the end of both tables, so the 230 history and 187 main columns
keep their positions and fingerprints. Schemas become `postcode_simd_wide_v4` (354 columns) and
`postcode_simd_sspl_v4` (311).

### 4. Join, readback and trace

The bands join on the edition's data-zone vintage, like the ranks. `gov_fields(ed)` in
`core/join.py` gains the declared band fields and, for 2020v2, the status, so readback and
trace cover them from the registry, as for the ranks. Readback compares them exactly.

The status is the first nullable text field among the Government fields, and every layer that
today assumes a whole-number measure must treat it by type, not by position in the list
(review, 30 September: listing it in `gov_fields()` alone breaks all three):

- **Join checks** (`core/join.py`), both places: the per-edition null check in
  `join_edition()` and the final checks in `finish()`. The band checks (not null, whole number,
  range) skip it; its own check is that it is null or `rank_sources_disagree`, and set exactly on the
  table's zones in the audit list (see Tests).
- **Readback** (`core/output.py`): compare it as nullable text, null equal to null, never
  through an integer conversion.
- **Trace** (`trace.py`): compare it as text, a null source against a null saved value being a
  match, and report it by name, not as a numeric difference.
- **SQL** `missing_simd`: never counts the status; a null status is the normal case, not a
  missing value.

### 5. SQL output

The shared core gains, chosen by edition like every other measure: `gov_{domain}_domain_quintile`,
`_decile`, `_vigintile` for the seven domains (21 columns), and `gov_housing_domain_rank_source_status`,
null except for 2020v2 housing's 628 zones: 48 to 70 columns. An edition that did not publish a
domain gives a literal NULL, as for the ranks, and the `missing_simd` test covers only published
measures. The walkthrough carries the Scotland decile and quintile of each domain for the chosen
edition, not the vigintiles, to stay readable, and `gov_housing_domain_rank_source_status` beside
the housing rank and bands. The status describes the rank, not the band: for these zones the
Government publishes a second housing rank, 0.5 to 4.5 places away, and for 626 of the 628 the
band is the same under either. Its comment says so plainly: transparency, not a reason to
exclude the zone; the rank carried agrees with two Government files.

In the SQL, split postcodes need no rule of their own: every query resolves a postcode to one
record or none (step 5) before reading any value, and step 6 takes every value, the status
included, from the one record that supplies the geography: the chosen record, or for a large
user its linked small-user record. The status is stored like the bands, so it travels with them.

### 6. Python

`column(edition, "income_domain_decile")` works through the existing naming, with the same
availability rule as the ranks: registry-checked, null for an unpublished domain, an error for an
unknown one. `label()` names the band as the Scottish Government's published unweighted band.

A label cannot say whether the returned row is affected, so a **housing** lookup, rank or band,
also returns the row's own status: `Result` gains `source_status`, and a cohort attachment gains
`{prefix}_source_status`, taken from the same chosen postcode record as the value, through the
same record choice and exclusions. It is `rank_sources_disagree` where that record's 2020v2 zone
is in the audit list, and null otherwise: always null for other editions and other domains, and
null wherever the value itself is null (no record, excluded, unpublished).

Split postcodes: by default (`split="a_part"`) the A part answers, with the A part's own status.
With `split="report"`, parts reach `split_consensus` only if they agree on **both the value and
the status**; if either differs the result is `split_conflict`, with a null value and a null
status. Both APIs apply the same rule: the cohort attachment by including the status among the
value columns it already compares, the scalar `lookup` by comparing the status alongside the
requested column in `_resolve`, which today compares the column alone.

### 7. Exports and SQL Server

The CSV carries the new columns; `tinyint` in SQL Server, the status as `nvarchar`. The digest,
both generated scripts and the loader's expectations change.

### 8. Documents

Regenerate the dictionaries. `LINKAGE_BY_ERA.md` and `EXAMPLES.md`: domain bands are the
Government's published unweighted bands, a different basis from the PHS population-weighted
decile of the overall index; they are copied, never computed; published tied zones can sit in
adjacent bands; and the 2020v2 housing status. A decision entry, `simd-domain-bands`, and the
plan index.

## Tests

- **Gate refusals**, on small synthetic CSVs: a missing zone, a duplicate, a 2004 crime row, an
  unknown domain or `DateCode`, a band out of range, a band that falls as the rank rises, a CSV
  rank that differs from the shapefile outside the pinned kinds, a half rounded down instead of
  up, a 2020v2 housing zone added to or missing from the audit list.
- **Allowed**: a split tie across adjacent bands, a half rounded up in a 2001 edition.
- **Real values**, on the built table: S01001951 and S01006050, both 1952 in 2009v2
  employment, carry published deciles 3 and 4; S01008149 and S01012978, 2790.5 in housing, carry
  decile 5 in 2016 and decile 4 in 2020v2, with no status; S01008634 carries its published 2020v2
  housing decile and the status.
- **The status, scoped by table.** The audit list holds exactly 628 zones, asserted against the
  reference data. Each output table is then compared with the list intersected with the zones
  that table represents: the history table represents all 628, the main table 627, since
  S01011598 has no record in the SSPL. The flagged zones must equal that intersection exactly,
  never a count.
- **Null and set, through every layer.** A table holding both a null status and
  `rank_sources_disagree` passes the join checks, readback and trace; a changed status, either
  way, is caught by readback and reported by trace; the SQL `missing_simd` test is unaffected by
  a null status.
- **SQL carries the flag from the geography record.** A large user linked to a small user in a
  listed zone returns that small user's status with its bands, in the generated dated query and
  in the walkthrough, which also agree on the status column case for case.
- **Python carries the flag.** A housing lookup and a cohort attachment return the status of
  the record they chose: set for a postcode in a listed zone, null for one outside it, null for
  another edition or domain, and null where the value is null.
- **Split parts, through both APIs.** EH37 5TF, whose A part (housing decile 7, no status) and
  B part (decile 7, `rank_sources_disagree`) agree on the band but not the status: by default
  both APIs return A's decile 7 with a null status; with `split="report"` both return
  `split_conflict`, a null value and a null status. A split postcode whose parts agree on both
  gives `split_consensus` in both.
- **Copied, not derived**: for one edition and domain, every saved band equals the CSV value
  exactly, zone by zone.
- **Readback and trace**: a changed band is caught.
- **SQL**: the 70-column core; a 2004 result has null crime bands and is still `matched`; the
  walkthrough agrees with the generated dated query on the domain columns it carries.
- **Fingerprints**: the 230 existing history columns and 187 main columns unchanged.
- **SQL Server**: import and digest check on the local container, as for 4.0.0.

## Out of scope

Weighted domain bands, sub-geography domain bands, domain percentiles, indicators and scores,
and any comparison across editions.
