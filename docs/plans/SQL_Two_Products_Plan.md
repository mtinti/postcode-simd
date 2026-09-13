# Plan: two SQL sets, one per postcode product, no default

Drafted 13 September 2026. Status: implemented on 13 September 2026 (version 2.1.0). The SSPL set follows large-user links: NRS publishes no guidance against it (checked 13 September 2026).

## Aim

Two postcode products, two SQL sets, the same interface. Neither is the default: a study
chooses the product first, and the choice is visible in every output row. Each query reads
its table as ingested, with no setup view:

| Set | Reads | Imported key | What NRS already did | What the SQL must do |
| --- | --- | --- | --- | --- |
| `docs/sql/spd/` | `postcode_simd_history` | `(pc_norm, introduced_on)` | nothing: every life, split parts as A/B/C | pick the latest life, pick the A part, follow large-user links |
| `docs/sql/sspl/` | `postcode_simd` | `pc_norm` | latest life, whole postcodes on the A part, counts summed | follow large-user links |

Each set has the same two queries with the same input and the same output columns:

- `link_by_era.sql`: input `id, postcode, analysis_year`; the year selects the edition by
  PHS v3.5 Table 4 (section 3.2.1.1, more than one release in an analysis).
- `link_latest.sql`: input `id, postcode`; one edition for the whole study, edited in one
  marked place (section 3.2.1.2, one release throughout).

Every query is self-contained and reads top to bottom as numbered steps, each step naming
the guidance it implements or stating that it is a project choice.

## The steps, and where each comes from

The SPD query has eight steps; the SSPL query has the same steps with 4 and 5 removed,
because NRS performed them when it built the SSPL.

| Step | SPD | SSPL | Source of the rule |
| --- | --- | --- | --- |
| 1. Inputs | `id, postcode, analysis_year` from the study's table | same | project interface |
| 2. Normalise | uppercase, remove ASCII spaces, keep the original; no repair, no suffix removal | same | project key rule, matches ingestion |
| 3. Edition | Table 4 maps the year to an edition and its data-zone vintage; `link_latest` uses a constant instead | same | PHS v3.5 Table 4, printed p.17 |
| 4. Latest life | newest introduction per full NRS key, across both user types | not needed: the file holds one life per postcode | PHS postcode file: "based on the most recent version of a postcode"; NRS SSPL note: "only the latest version" |
| 5. Split parts | for each ordinary postcode prefer live, then the whole record or the A part, then newest introduction; a B/C-only postcode gets no SIMD and status `split_a_missing`; an equal-priority tie gets `ambiguous_postcode` | not needed: NRS made the postcode whole on the A part; `SplitIndicator` Y records that it was split | PHS postcode file: "PHS lookups include only the A part"; NRS note: A part, "contains more addresses"; tie rule is a project choice |
| 6. Large users | follow `LinkedSmallUserPostcode` to the small-user record with exactly that key, A/B/C suffix included; `NO LINKP` is a PO box and `NO LINK` is unlinked: no SIMD | follow the link to the whole small-user postcode; a link with an A suffix matches the flagged small-user record; a B or C suffix cannot resolve; sentinels as SPD | PHS v3.5 Appendix A, printed p.30: linked where possible, PO boxes none; the SSPL suffix rule is a project reading of the SSPL dictionary |
| 7. Select the edition's values | copy the 14 stored measures of the selected edition through the vintage's data-zone code, with the three PHS geography codes for the local bands; nothing recalculated, early bands not reversed again | same | PHS v3.5 sections 3.1.2, 3.3, 3.4; ingestion decision `bands-are-looked-up` |
| 8. Report | one row per input row, statuses for postcode, address and SIMD, product provenance, the matched key and the key that supplied the geography | same | project interface; PHS checklist p.25 |

Step 6 is the one place the current working tree departs from this table: the standalone
SSPL query keeps a large user's own record geography and only warns. PHS Appendix A
attaches deprivation to a large user only through its linked small user. This plan puts the
PHS rule in both sets so that the two products differ only in what NRS did upstream, and
returns the large user's own data zone as context so nothing is hidden. If the project
prefers the own-record rule for the SSPL, the decision must say why and the README must
say so where the set is introduced.

## Output contract, identical for both sets

| Group | Columns |
| --- | --- |
| Input echo | `id`, `postcode`, `analysis_year` (era query only), `postcode_key` |
| Statuses | `postcode_status` (`matched`, `a_part`, `linked_small_user`, `linked_small_user_not_found`, `unlinked_large_user`, `po_box`, `split_a_missing`, `ambiguous_postcode`, `not_found`, `missing_postcode`), `simd_status` (`matched`, `missing_simd`, `no_edition`, `missing_year`, `invalid_year`, or the postcode status) |
| Provenance | `index_source`, `index_release`, `allocation`, `simd_edition`, `edition_policy`, `data_zone_vintage` |
| Keys | `matched_pc_norm`, `matched_introduced_on`, `matched_is_current`, `matched_user_type`, `requested_link_postcode`, `simd_source_pc_norm`, `simd_source_introduced_on`, `simd_source_is_current` |
| Geography used | `data_zone_code`, `phs_hb_code`, `phs_hscp_code`, `phs_ca_code` |
| Measures | `simd_rank`, eight `phs_pw_*` bands, `phs_pw_most15pc`, `phs_pw_least15pc`, three `gov_uw_*` bands, `band_direction` |
| Own-record context | the matched record's own `DataZone2001Code`, `DataZone2011Code`, `HealthBoardArea2019Code`, `CouncilArea2019Code`, `IntegrationAuthority2019Code`, `SplitIndicator`, `PostcodeType` or user type |

The SSPL set may append its remaining raw fields after these; the SPD set appends
`pc_base`. A consumer that reads only the contract columns can switch product by changing
the file path and the imported table name.

## Steps of the work

1. **Decisions.** Add `sql-two-products-no-default` and mark `sspl-direct-sql-both-publishers`
   and the two `sql-*` entries of 12 September superseded. Record the large-user rule chosen
   for the SSPL set and the tie rule for the SPD set.
2. **SPD set.** Write `docs/sql/spd/link_by_era.sql` and `link_latest.sql` as standalone
   queries with the eight steps. Steps 4 to 6 are identical text in both files, delimited by
   `-- BEGIN shared` and `-- END shared` markers; a test asserts the two blocks are equal.
3. **SSPL set.** Write `docs/sql/sspl/link_by_era.sql` and `link_latest.sql` the same way,
   with steps 4 and 5 replaced by one comment saying what NRS did and citing the note.
4. **Tests.** One parametrised suite over both sets with product-specific fixtures for every
   status, the year boundaries, duplicate and empty inputs, and deleted targets. On the real
   tables: one output row per input, every contract column present, every measure equal to
   the stored value through the reported `simd_source_pc_norm`, and the shared-block identity
   check. Keep the existing SPD representative parity test against `core/agreement.py`.
5. **Docs.** `docs/sql/README.md` states the two decisions a study makes and the interface.
   `LINKAGE_BY_ERA.md` becomes the step-by-step commentary with the table above. README,
   HOW_IT_IS_BUILT, UPDATING and the dictionaries lose the word "default" for SQL.
   `docs/sql/history/` is removed; its policy lives on in the SPD set.
6. **Acceptance.** Both sets run on both real tables in DuckDB; the suite is green natively
   and in the container; a worked example, AB24 2TY, is shown for both products in the docs
   with the linked and own-record values side by side.

## Open points for the review

- Large-user rule in the SSPL set: decided 13 September 2026, the PHS linked rule in both sets.
- Whether `link_latest.sql` is worth keeping as a file, or whether the era query with a
  documented "one edition throughout" input is enough. Two files keep the two PHS approaches
  visibly separate; this plan keeps both.
- Column naming for the own-record context: raw NRS names, or `own_` prefixed.
