# The SQL lookups, step by step

Two sets of queries, one per NRS postcode product, and no default. Read
[docs/sql/README.md](sql/README.md) for how to run them; this page explains what each step
does and which guidance it follows. The files are generated from the schemas by
`python -m simd_ingest.sql_examples`, so this page describes the generator's output.

| | `docs/sql/spd/` | `docs/sql/sspl/` |
| --- | --- | --- |
| Reads | `postcode_simd_history`, key `(pc_norm, introduced_on)` | `postcode_simd`, key `pc_norm` |
| NRS did upstream | nothing: every life, split parts as A/B/C rows | kept the latest life; made split postcodes whole on the A part |
| The query does | steps 1 to 8 | steps 1 to 3 and 6 to 8 |
| Data-zone allocation | zone containing the postcode's grid reference | zone containing the 2022 output-area centroid |

Each set has `link_by_era.sql` (edition by the year of the health data) and `link_latest.sql`
(one edition throughout). Within a set the two files differ only in steps 1 to 3; the text
from `-- BEGIN shared` to `-- END shared` is identical and a test checks it.

## The steps

**Step 1, input.** The first `SELECT` is the worked example, AB24 2TY in 2020. Replace it with
a `SELECT id, postcode, analysis_year FROM your_cohort` (or `id, postcode` for
`link_latest.sql`). Every input row returns exactly one output row; duplicate and null ids
are kept. `analysis_year` is the year of the health data as an integer.

**Step 2, key.** The postcode is uppercased and ASCII spaces are removed, keeping the original
text; this is ingestion's rule for `pc_norm`. Nothing is repaired, and an NRS A/B/C suffix is
not removed, so an input with a suffix is simply not found. Project choice.

**Step 3, edition.** `link_by_era.sql` maps the year to an edition with PHS v3.5 Table 4,
printed p.17: 1996 to 2003 SIMD 2004, 2004 to 2006 SIMD 2006, 2007 to 2009 SIMD 2009v2, 2010
to 2013 SIMD 2012, 2014 to 2016 SIMD 2016, 2017 onwards SIMD 2020v2. The edition fixes the
data-zone vintage, 2001 or 2011. Before 1996 there is no SIMD and the guidance points to
Carstairs, which these tables do not carry. `link_latest.sql` instead takes the edition from
one line marked `-- EDIT EDITION`, for the one-edition-throughout approach of section
3.2.1.2; the vintage still follows from the edition.

**Step 4, latest life, SPD only.** The directory keeps every life of a postcode. PHS's postcode
file is "based on the most recent version of a postcode" and the SSPL keeps "only the latest
version", so the query takes the newest introduction of each full NRS key across both user
types. This is not matching on the event date; that belongs to the Python API.

**Step 5, split parts, SPD only.** An ordinary postcode can be several A, B and C rows. PHS
"lookups include only the A part"; NRS uses A because it "contains more addresses". The
order of preference is a project choice: a live record first, then the whole record or the A
part, then the newest introduction. A postcode whose best record is a B or C part gets
`split_a_missing` and no SIMD; two equally good records get `ambiguous_postcode` and no
SIMD. The SSPL already holds one whole row per postcode with `SplitIndicator` Y where it was
split, reported as `a_part`.

**Step 6, large users, both sets.** PHS v3.5 Appendix A, printed p.30: a large-user postcode
has no boundary; where NRS could link it to a small-user postcode, that postcode supplies the
geography; a PO box or an unlinked large user has no geography. Both queries therefore follow
`LinkedSmallUserPostcode` to a small-user record in the same product. The SPD keeps the
linked key's suffix, so "AB1 2CDB" resolves to that B part exactly. The SSPL keeps an A
suffix on a link although its small-user rows are whole, so a link with an A suffix matches
the record flagged `SplitIndicator` Y; a B or C suffix cannot resolve. `NO LINKP` is reported
as `po_box` and `NO LINK`, blank or null as `unlinked_large_user`, both without SIMD. There is
no fallback to the large user's own zone, no chain through a second large user and no use of
the other product. The large user's own fields are returned as context so the effect of the
link is visible. NRS publishes nothing against following the link; its SPD dictionary calls
PO-box grid references low quality because they point at the sorting office.

**Step 7, values.** The stored values of the chosen edition are copied from the record that
supplies the geography, through the data zone of that edition's vintage. All 14 measures come
back: PHS population-weighted Scotland, board, HSCP and council quintiles and deciles, the two
15% flags, and the Scottish Government unweighted Scotland quintile, decile and vigintile.
The three PHS geography codes are the areas PHS used for the local bands (section 3.4); use
them with those bands, not the NRS administrative codes. Nothing is recalculated. Band 1 is
most deprived in every edition; ingestion already reversed the 2004 and 2006 PHS bands.

**Step 8, report.** `postcode_status` says what happened to the postcode. `simd_status` says
whether the SIMD columns can be used: a year problem first (`missing_year`, `invalid_year`,
`no_edition`, or `unknown_edition` in `link_latest.sql`), then a postcode problem, then
`missing_simd` if any stored value is absent, else `matched`. Product provenance and both
keys are returned so the route can be reviewed, which covers the PHS checklist on p.25:
index, edition, weighting, direction and level.

## The output, the same in both sets

| Group | Columns |
| --- | --- |
| Input | `id`, `postcode`, `analysis_year` (null in `link_latest.sql`), `postcode_key` |
| Statuses | `postcode_status`, `simd_status` |
| Provenance | `index_source`, `index_release`, `allocation`, `simd_edition`, `edition_policy`, `data_zone_vintage` |
| Keys | `matched_pc_norm`, `matched_introduced_on`, `matched_is_current`, `matched_user_type`, `requested_link_postcode`, `simd_source_pc_norm`, `simd_source_introduced_on`, `simd_source_is_current` |
| Geography used | `data_zone_code`, `phs_hb_code`, `phs_hscp_code`, `phs_ca_code` |
| Measures | `simd_rank`, `phs_pw_scotland_quintile`, `phs_pw_scotland_decile`, `phs_pw_hb_quintile`, `phs_pw_hb_decile`, `phs_pw_hscp_quintile`, `phs_pw_hscp_decile`, `phs_pw_ca_quintile`, `phs_pw_ca_decile`, `phs_pw_most15pc`, `phs_pw_least15pc`, `gov_uw_scotland_quintile`, `gov_uw_scotland_decile`, `gov_uw_scotland_vigintile`, `band_direction` |
| Own-record context | the matched record's NRS fields as ingested, names unchanged except `Postcode`, returned as `matched_postcode`; the SPD set adds `matched_pc_base` |

`postcode_status` values: `matched`, `a_part`, `linked_small_user`, `linked_small_user_not_found`,
`unlinked_large_user`, `po_box`, `split_a_missing` (SPD), `ambiguous_postcode` (SPD),
`not_found`, `missing_postcode`. SIMD is present only for the first three.

For a large user the own-record context holds its own data zone while `simd_source_pc_norm`
names the small-user postcode that supplied the values. A deleted latest life is matched and
reported with `matched_is_current` false; whether to keep it is the study's decision.

## Worked example

AB24 2TY is a large-user postcode linked to AB24 2TN. In both products it sits in 2011 data
zone S01006671 (2020v2 quintile 5) while AB24 2TN sits in S01006676 (quintile 1).

| Column | SPD set | SSPL set |
| --- | --- | --- |
| `postcode_status` | `linked_small_user` | `linked_small_user` |
| `matched_pc_norm` | AB242TY | AB242TY |
| `simd_source_pc_norm` | AB242TN | AB242TN |
| `data_zone_code` | S01006676 | S01006676 |
| `phs_pw_scotland_quintile` | 1 | 1 |
| `DataZone2011Code` (own record) | S01006671 | S01006671 |

Where both products supply a value for the same postcode from the same small-user postcode,
the values agree whenever the two products place that postcode in the same data zone. Where
they differ, the difference is the allocation method described in
[How it is built](HOW_IT_IS_BUILT.md), never the SQL. A test checks both statements on the
built tables.

## What is not claimed

The queries are tested on DuckDB; SQL Server syntax is intended but not verified. Neither
set has been compared with PHS's own postcode-level lookup, which is not published openly.
The representative order in step 5 and the SSPL suffix reading in step 6 are project
choices, stated as such in the files.
