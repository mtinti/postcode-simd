# Plan: a column provenance site on GitHub Pages

Drafted 1 October 2026, revised the same day after review (provenance per table, inputs with
conditions and scope, a reviewed description source, stronger tests; check evidence from the
manifest, no file sizes). Status: proposed.

## Aim

A public documentation site, published on GitHub Pages and regenerated on every push to `main`,
with **one page per column** of both tables. Anyone given a link such as
`https://mtinti.github.io/postcode-simd/columns/simd2020v2_income_domain_decile/` sees what the
column is, the exact source field it comes from, what was done to it, how the build checks it,
and why it is done that way: the column's provenance, end to end.

## What exists, and what does not

Most facts the site needs are already committed, spread across files and not joined per column:

| Fact | Where it lives today |
| --- | --- |
| name, type, nullability, description, source category | `output_schema.yaml`, `output_schema_history.yaml` |
| the pinned source files: publisher, URL, SHA256, licence | `sources.yaml` (`remote_objects`, `licences`); file sizes are not recorded, and the pages do not show them |
| which source column feeds which output column | `sources.yaml` (PHS prefix and band names, Government `columns` and `domains` maps, `bands` blocks, rurality shapefile columns), and the readers |
| the transformation | the readers: `core/spd.py`, `core/sspl.py`, `core/phs.py`, `core/govscot.py`, `core/rurality.py`, `core/weighted.py` |
| the checks | every check a build emits, with its name and result, in that build's `manifest.json` (`checks`); `BUILD_REPORT.md` is only a narrative summary of them |
| the reasons | `decisions.yaml` |
| what is exported, and as what in SQL Server | `export_contract.yaml`, `sql_check.py` |

Two things are missing (review, 1 October 2026):

- **An explicit, tested lineage**: from each column of each table to its inputs, transformation and
  checks (section 2).
- **Descriptions**: 55 of the 65 history source fields and 44 of the 50 main source fields have an
  empty description in the schemas, so a page built from them alone would say only the column's
  name. The NRS data dictionaries that would supply them are already pinned with the sources:
  `spd-indexdatadictionary-2026-2.docx`, `SSPL Data Dictionary 2026-2.docx`, and the Government's
  `SIMD2020v2 - GIS files - glossary.xlsx` (section 3).

The data dictionaries already show that generating documentation from these files works and stays
in step.

The site carries metadata only, never data values. The repository is public, so it publishes
nothing that is not already published.

## Design

### 1. Pages

- **One page per column name**, 444 in all: 397 names are in both tables, 47 in one. Provenance is
  kept **per table and column**, never per name: 49 of the shared names differ between the tables
  in type, nullability or source. `CensusPopulationCount2022` is nullable in history (large users
  have none) and not in main; `spd_user_type` comes from which SPD file a record is in for history,
  and from `PostcodeType` in the SSPL for main. A shared page shows each table's variant side by
  side, and says so where they agree. Sections: *What it is* (description, type, nullability, tables); *Where it comes
  from* (publisher, dataset, pinned file, URL, SHA256, licence); *The exact source field*;
  *What was done to it*; *How it is checked*; *Why* (decision links); *Where it is exported*
  (CSV or withheld, the SQL Server type).
- **Index pages**: all columns grouped as the dictionaries group them, filterable by edition and
  source; one page per pinned source file, listing the columns it feeds; one page per decision,
  listing the columns it governs.
- **Cross-links throughout**, so a reader can walk from a column to its file to its reason and back.

### 2. The lineage map: the new, tested piece

A function, `simd_ingest/lineage.py`, returns one record per **(table, column)**: 442 for history and
399 for main. It is **derived from the registry and the readers' constants, never typed by hand**.
A single source field per column cannot describe several existing columns, so a record holds:

- **inputs**: a list, each with
  - a *reference*: a pinned published file (remote object, file, SHA256), or a versioned
    repository file (for example `simd_ingest/sgs_2020_housing_rank_disagreements.csv`, at the
    commit), or a registry or configuration entry (for example the edition's `bands` block);
  - the *field* read, and any *condition* (which of the two SPD files, `SIMD Domain = Income`,
    `Measurement = Decile`, `DateCode = 2020`, `spd_user_type = large_user`);
  - the *join key* by which it reaches the row (`DataZone2011Code`, `pc_norm`);
- **scope**: the row itself, or a wider universe the value is computed over (the weighted bands are
  cut over every data zone of the edition, never the table's rows);
- **transformation**: copied, renamed, inverted, normalised, parsed, placed, gated, computed, with
  the rule in words and the code that applies it;
- **checks**: the *definition* of each check that guards it (its name and what it tests), kept
  apart from the *evidence* that it passed (the check's result in a build's
  `manifest.json["checks"]`, phase 2). A check's reach is stated
  honestly: the direct comparison with NRS's published rurality codes covers the 2022 version only;
  the earlier versions share the placement algorithm and its gate, not a direct comparison;
- **decisions**: ids from `decisions.yaml`.

By category, with columns in history and main:

| Category | Inputs | Transformation |
| --- | --- | --- |
| `directory` (65 / none), `lookup` (none / 50) | the NRS column of the same name, in the SPD small-user or large-user file (a column in one file only is null for the other's records) or the SSPL file | copied as text |
| `derived` (7 / 6) | the NRS columns each is built from, which differ by table (`spd_user_type`: the SPD file a record is in; in main, `PostcodeType`) | normalised key, parsed dates, user type, release from the registry |
| `phs` (72 / 72) | `<prefix><Band>` in the PHS edition CSV, joined on the edition's data zone | copied; inverted for 2004 and 2006 bands |
| `govscot` (65 / 65) | the shapefile DBF column from the edition's `columns` or `domains` map; populations | copied |
| `govscot_bands` (124 / 124) | the statistics.gov.scot rows by domain, measurement and DateCode; the shapefile rank they are gated against; for the status, the committed disagreement list | copied, gated rank against rank |
| `computed` (82 / 82) | the domain rank and the population of every zone of the edition | computed by the population midpoint rule, gated on reproducing PHS |
| `rurality` (27 / none) | the version's shapefile and its fold columns; the life's grid reference | placed by point in polygon; 2022 compared directly with NRS's codes |

**Tests** (section Tests) require every (table, column) to resolve, every input reference to exist,
and every check name and decision id to be real.

### 3. Descriptions: a reviewed source

The schema notes stay the short form. The pages take their fuller *What it is* from a committed,
reviewed file, `simd_ingest/column_descriptions.yaml`, one entry per column name, each with its
text and its source:

- **NRS fields**: extracted once from the pinned SPD and SSPL data dictionaries by a small script,
  then reviewed, with attribution (the dictionary and its release). A difference between the SPD
  and SSPL wording is kept per table.
- **SIMD fields**: from the Government's pinned glossary and the PHS guidance where they define
  them; ours where neither does, marked as ours.
- **Derived, computed and placed columns**: written by us, marked as ours, with the decision behind
  them.

A column whose description is missing fails the coverage test, so the gap is closed before the site
publishes, not discovered on it.

### 4. Generation and publishing

- A generator, `python -m simd_ingest.provenance_site`, writes Markdown pages into a build folder
  from the schemas, registry, decisions, export contract, descriptions and lineage map.
- **MkDocs** with the Material theme renders them, with search. Both are documentation-only
  dependencies (a `docs` extra in `pyproject.toml`), never needed by the build or the image.
- A GitHub Actions workflow, `pages.yml`, on every push to `main`: install, generate, build, deploy
  to GitHub Pages. A pull request builds the site without deploying, so a broken generator fails
  review. Pages is enabled in the repository settings with GitHub Actions as its source.
- The site states its version: the commit, the package version, the schema versions and the SPD
  and SSPL release.

### 5. Open choices

1. **Build statistics per column** (null and blank counts, distinct values, the release they were
   measured on). They need the build output, which CI does not have. Recommendation: phase 2, from
   a small summary file each build writes and is committed with a release, so the site never
   depends on the data.
2. **The SQL query outputs** (`gov_income_domain_decile`, `computed_pw_*` and the rest). Each is
   chosen from one table column per edition. Recommendation: phase 2, one page per output column
   linking to the table column of each edition, generated from `sql_examples.py`'s own lists.

## Tests

- **Coverage**: every (table, column) of both schemas has a lineage record and a description.
- **References are real**: every input naming a pinned file resolves to a file in the registry;
  every repository input exists at the commit; every check name is one the build actually emits,
  read from a build's `manifest.json["checks"]` in the integration tests (never from
  `BUILD_REPORT.md`, which summarises and would wrongly reject valid names) and from the code's
  check-name patterns in unit tests; every decision id exists in `decisions.yaml`.
- **Hand-stated expectations for the exceptional cases**: `CensusPopulationCount2022`, nullable in
  history and not in main; `spd_user_type`, from the SPD file in history and `PostcodeType` in
  main; a field only one SPD file has, conditional on the record type;
  `simd2004_pw_scotland_decile`, PHS 2004, `SIMD2004CountryDecile`, inverted;
  `simd2020v2_housing_domain_rank_source_status`, whose input includes the committed disagreement
  list; `simd2020v2_income_domain_pw_scotland_decile`, computed over every zone of the edition, not
  the table's rows; `urbanrural2016_6fold`, placed, without a direct comparison with NRS codes.
- **Definition against evidence**: a page never states that a check passed unless it cites the
  build that ran it (phase 2); until then it states only what the check tests.
- The generator writes one page per column name, every internal link resolves, and the site builds
  in CI on every pull request.

## Out of scope

Data values, row-level lineage (the `trace` command already does that for one record), and
anything from `local/`.

## Effort

Two to three days: the lineage map and its tests, and extracting and reviewing about 100 NRS
descriptions; the generator and workflow are small.
