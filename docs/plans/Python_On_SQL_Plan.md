# Plan: the Python API answers through the committed SQL

Drafted 24 September 2026. Status: proposed, for review before any code. Deferred: not part of
the 3.0.0 release, which shipped the rurality work without it. Decision 4 below is therefore settled
as a later release.

## Aim

One question, one answer. Today the same cohort can get different deprivation depending on
whether an analyst runs the SQL or the Python API, and nothing in the output shows it. Make
`simd_ingest.lookup` a thin wrapper that runs the committed queries in `docs/sql` through
DuckDB, so that Python, SQL Server and any future container give identical answers by
construction, and the rules live in one place.

## Where the two differ today

| Question | SQL | Python |
| --- | --- | --- |
| Large user with a link | the linked small-user postcode's geography, PHS v3.5 Appendix A | the large user's own geography |
| PO box, unlinked large user | returned with `po_box` or `unlinked_large_user` and no value | removed from the table, so `not_found`; with `include_po_boxes=True`, its own value |
| No date | the latest life, deleted or not (`link_latest.sql`) | the current record only, so a retired postcode is `deleted` |
| Split postcode | whole or A part; B or C alone, or a tie, has no value | A part, or `split="report"` comparing the parts |
| Status names | `matched`, `a_part`, `linked_small_user` and eleven more | `unique`, `a_part`, `deleted`, `not_found` and a few more |

The large-user row changes values: AB24 2TY is quintile 5 on its own geography and quintile 1
through its linked postcode. The others change statuses and coverage.

## Why align, and why now

- **The SQL follows the guidance.** Appendix A gives a large user its linked small user's
  geography. Python's own-record rule is a historical choice, documented as a difference but not
  justified by guidance.
- **Two implementations have cost real faults.** The review of 9fa39d4 found four faults, all
  in Python alone: the PO-box exclusion order, split nulls, cohort shapes and missing dates.
  The SQL was right in every case. Each rule written twice can drift.
- **3.0.0 already breaks.** The history schema, the CSV digest and the dated query's statuses
  change in 3.0.0. Aligning Python in the same release means one set of breaking changes.

## Design

### One engine

A private function registers the cohort and the reference table with DuckDB and runs one of
the committed queries:

| Python call | Query | Year passed |
| --- | --- | --- |
| `attach(..., date_col, edition=E)` | `spd/link_as_of.sql` | a year inside E's Table 4 window |
| `attach(..., date_col=None, edition=E)` | `link_latest.sql` of the table's product, with the edition line set to E | none |
| `attach_by_era(..., date_col)` | `spd/link_as_of.sql` | null: the year of the address date |
| `attach_rurality(..., date_col)` | `spd/link_as_of.sql` | null, or the chosen version's reference year |
| `lookup(...)` | the same as `attach`, with one row | as above |

The table argument stays a DataFrame: it is registered as the view the query reads,
`postcode_simd_history` or `postcode_simd`, chosen from the table's own metadata, so the SSPL
table keeps answering current questions and keeps refusing dated ones.

### Injecting the cohort

The tests replace each query's demonstration input by matching its text. That is fine for
tests, fragile for an API. The generator will wrap the input block in two fixed marker comments,
`-- BEGIN INPUT` and `-- END INPUT`, and the wrapper replaces exactly what lies between them. A
test fails if a committed query lacks them. The hand-written walkthrough gets the same markers.

### Output

Every input row back, in order and by position, never by index label, with the query's
columns under a prefix: the statuses, provenance, keys, the requested measure as `value`, and
optionally every measure. Measure names map to query columns through the generator's own
table, so `pw_scotland_quintile` means `phs_pw_scotland_quintile` in both. A text label per
row states edition, weighting, level, direction and split rule, as today.

### What is removed or changed

- **`include_po_boxes` and `include_large_users` go.** The query applies Appendix A. An analyst
  who wants large users out filters on `matched_user_type` afterwards.
- **`split="report"` leaves the main path.** The SQL has no equivalent. It survives as
  `split_report(table, postcode, on)`, a diagnostic that lists the parts valid on a date and
  their values, and attaches nothing.
- **`Result.candidates`** becomes the matched record's key and introduction date from the query,
  plus the context dates. The raw candidate frame goes.
- **`scope`** goes from the public API. `PO_BOX_SENTINELS` stays, used by `ground_truth.py`.
- **Status names become the SQL's.** A migration table goes in `EXAMPLES.md`:

| Python today | After |
| --- | --- |
| `unique` | `matched`, `a_part` or `linked_small_user` |
| `a_part` | `a_part` |
| `split_consensus`, `split_conflict` | `split_report()` only |
| `deleted` | `previous_life`, or rarely `between_lives` or `postcode_deleted_by_date` |
| `not_found` | `not_found`, `po_box`, `unlinked_large_user` or `missing_postcode` |
| `no_edition` | `no_edition` in `simd_status` |
| `previous_life` | `previous_life` |
| `missing_date` | `missing_address_date` and `missing_year` |
| rurality statuses | `rurality_status`, unchanged values |

### What stays in Python

`recommended_edition`, `edition_for`, `column`, `label`, `load`, `rurality_versions`,
`rurality_version_for` and `rurality_label`: helpers with no linkage rule in them.

## Findings to fix on the way

- **Table 4 is written twice.** `lookup.py` holds it as year ranges and `dictionary.py` holds a
  second copy as display text. They agree today. Generate the dictionary's table from the one in
  `lookup.py`.
- **DuckDB becomes a runtime dependency.** It is pinned today only for development. Move the pin
  to the runtime list in `pyproject.toml` and `requirements.txt`, and confirm the Docker image.

## Decisions for review

1. **Forcing an edition through a year.** `attach(edition=E)` passes a year inside E's window
   instead of adding an edition input to the SQL. No SQL change, and the year window is the
   guidance's own. The side effect is that the rurality version moves with it, which `attach`
   does not return. The alternative is an optional `edition` input column on the dated query,
   which changes its contract.
2. **Latest life for undated questions.** Following `link_latest.sql`, an undated lookup on a
   retired postcode returns its last life instead of `deleted`. This matches PHS's postcode
   files, which are built from the most recent version of each postcode.
3. **Keep `split_report` or drop it.** Nothing in the project uses it outside tests.
4. **Where.** On `feature/rurality-by-version`, released together as 3.0.0, or on a new branch
   after that merge, released as 3.1.0 with its own breaking note.

## Tests

- The SQL sets already test the rules. The Python tests shrink to: the wrapper returns what the
  query returns, row for row, on the built table; row order and shape, including repeated index
  labels and an empty cohort; the measure and label mapping; SSPL refusing a dated question.
- A performance check: one million synthetic cohort rows against the built history table,
  with the time recorded in the decision log. The acceptance threshold is set before the run.
- The documented examples in `EXAMPLES.md` rerun as tests, with their new statuses.

## Documents

`EXAMPLES.md` is rewritten around the new outputs, with the migration table.
`LINKAGE_BY_ERA.md`, `NRS_GUIDANCE_CHECK.md` and the README lose their caveats that Python is a
separate policy. A decision entry records the change and the four review decisions.
