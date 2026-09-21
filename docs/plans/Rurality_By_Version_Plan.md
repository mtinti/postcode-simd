# Plan: a contemporary urban-rural class for every postcode life

Drafted 21 September 2026 and revised the same day after review of a511f6a. Status: proposed,
nothing implemented. The feasibility check in step 2 gates everything after it.

The review found three gaps, all accepted: the saved rurality columns would escape readback
(step 7), the gate was not measurable (step 2), and a bare code cannot say why it is empty
(step 6). It also separated reference year from publication date (step 5).

## Aim

The history table carries one rurality, `UrbanRural6Fold2022Code` and its 8-fold companion, as
NRS published them in the downloaded directory. A 2005 address therefore gets today's
classification, while its data zone and SIMD are read at the right vintage. The walkthrough
says so in a comment; this plan removes the limitation.

Attach the Scottish Government Urban Rural Classification of every published version to every
postcode life, by placing the life's own grid reference inside that version's polygons. One
postcode file, one method, every version, no archived lookups to chase.

## What was checked before writing this

Verified on 21 September 2026 against the built table and the live publisher.

| Fact | Evidence |
| --- | --- |
| Every life has a grid reference | 247,773 lives, none missing, including all 85,724 deleted lives |
| A recycled postcode's lives carry their own points | 7,101 of 7,419 multi-life small-user postcodes have different points between lives |
| Nine versions are downloadable, not five | The catalogue record 564db46c-3153-423c-ac84-90d41ec2652c links 2011-2012, 2013-2014, 2016, 2020 and 2022; the same URL pattern also returns 2003-2004, 2005-2006, 2007-2008 and 2009-2010 |
| The directory's published code is the postcode's own, not its link's | Of 13,933 large users whose link resolves, 44 have a published 2022 code different from the linked small user's |
| Every post-office box carries a published code | All 31,725 `NO LINKP` rows have one, so suppression must not enter the comparison |
| The 2022 version describes 2022 but appeared in 2024 | gov.scot: published 16 December 2024, built on the Census 2022 settlements released May 2024 |
| The separate government postcode lookup is withdrawn | gov.scot: removed because "the SPD has a ... 2022 lookup incorporated into it" |
| Readback would not see the new columns | `core/output.py` `readback` compares the index columns with the source files and re-looks-up the SIMD and PHS columns from saved data zones; nothing else. The reviewer changed a derived code from 1 to 6 after writing and no check failed |
| Licence of the polygons | Open Government Licence; attribution "Copyright Scottish Government, contains Ordnance Survey data (c) Crown copyright and database right (year)" |

URL pattern: `https://maps.gov.scot/ATOM/shapefiles/SG_UrbanRural_<version>.zip`, the same
service the six SIMD shapefiles already come from.

## Known limits, stated before any code

- **One point per life, not a track.** The directory holds a life's last known position. A
  postcode that moved within a life is placed where it ended.
- **Point quality is unknown for most deleted lives.** `GridLinkPositionalAccuracy` is blank on
  84,307 of the 85,724 deleted rows, although the NRS dictionary says it holds the value from
  before termination. Report this beside the result rather than filter on it.
- **Post-office boxes are not places.** Their point is the Royal Mail sorting or delivery
  office (NRS dictionary). 31,725 large-user rows are boxes. They get no SIMD today and must
  get no derived rurality either.
- **"The same method SG and NRS use" is a claim, not a fact, until step 2.** The evidence so
  far is that the directory's code follows the postcode's own point, large users included,
  which makes an own-point comparison like for like.
- **Unverified.** The review states that the Scottish Government's own lookup handled large
  users through their linked small user and split postcodes through the A part. That lookup is
  withdrawn and its method was not found on the publication pages. If it is right, the
  directory and that lookup legitimately differed for some rows. Step 2 compares against the
  directory only, and says so.
- **SSPL is out of scope.** It allocates from the 2022 output-area centroid and keeps one life
  per postcode, so it has no per-life point to place. The main table keeps the single
  published 2022 code.

## Steps

### 1. Pin the nine shapefiles

Add nine entries to `simd_ingest/sources.yaml` under the existing `maps_gov_scot` publisher,
each with the archive hash and the member hashes. Unlike the SIMD entries, which extract only
the `.dbf`, these need the geometry: `.shp`, `.shx`, `.dbf` and `.prj`.

### 2. Feasibility check, the gate

Before any pipeline work, in a scratch script:

1. Read each attribute table. Record per version the column names, which folds are present
   (2, 3, 6, 8), the code values, the polygon count and the coordinate reference system. The
   early versions are expected to differ; do not assume a common layout.
2. Run point-in-polygon for the 2022 version over every life and compare with the published
   `UrbanRural6Fold2022Code` and `UrbanRural8Fold2022Code`.

The published 2022 codes are a built-in ground truth for the method. The gate, stated so it
can be failed:

- **What is compared.** The raw own-point result for every one of the 247,773 lives, with no
  suppression applied. The post-office-box rule is a later policy step (step 4); applying it
  here would manufacture 31,725 disagreements or hide them.
- **Denominator.** Every life. A point that falls in no polygon counts as a disagreement, and
  is also counted on its own line.
- **Both folds.** The 6-fold and the 8-fold are scored separately.
- **Cohorts, each reported with its own count and rate**, because an overall rate dominated
  by current small users could conceal poor historical coverage: current against deleted;
  small user against large user, with boxes as their own line; split parts against whole
  postcodes; and deleted lives with a blank positional accuracy against the rest.
- **Threshold.** At least 99.5% agreement among current small-user lives, and at least 99%
  in every other cohort of more than 1,000 lives. These are proposals to be confirmed once the
  first run shows what the disagreements look like; whatever is chosen is written down before
  the result is judged against it, not after.
- **Every disagreement is classified**, not just counted: on a boundary, outside every
  polygon, or a genuinely different class. A cohort that fails is a finding about that
  cohort, and may narrow the scope rather than end the work.

If the gate fails for current small users, stop and write down why; the rest is not worth
building.

### 2a. Feasibility result, 21 September 2026: the gate passes

Run in a scratch environment (geopandas 1.1.4, shapely 2.1.2), thresholds fixed beforehand at
99.5% for current small users and 99% for every other cohort over 1,000 lives. Raw own-point
results, no suppression, every life in the denominator, a point in no polygon counted wrong.

| Cohort | Lives | Agreement, 6-fold and 8-fold alike | Wrong |
| --- | ---: | ---: | ---: |
| All | 247,773 | 99.9988% | 3 |
| Current small user (the 99.5% gate) | 157,282 | 100% | 0 |
| Deleted small user | 39,487 | 99.9924% | 3 |
| Large user, not a box | 19,279 | 100% | 0 |
| Post-office box | 31,725 | 100% | 0 |
| Split part | 1,263 | 99.92% | 1 |
| Deleted, blank positional accuracy | 84,307 | 99.9964% | 3 |

No point fell in more than one class, so the boundary rule in step 3 has nothing to decide in
2022. Every disagreement is a point outside every polygon; none is a different class. The
three: G84 7BD (0.2 m from a polygon of its published class), DG6 4UF (820 m, nearest matches
the published class) and DD11 2PTB (17 km out to sea, nearest does not match). NRS therefore
appears to use point-in-polygon with a nearest-polygon fallback of some kind, which this
project does not need to imitate for three deleted lives from the 1970s.

Attribute tables: all nine versions carry the 6-fold and the 8-fold, in British National Grid
(EPSG:27700), as eight multipolygons. Columns are `UR6FOLD`/`UR8FOLD` to 2013-2014 and
`UR6Class`/`UR8Class` from 2016; the 2-fold and 3-fold appear from 2013-2014. Seven of the
nine files contain self-intersecting rings; repairing them changed no result in 2022.

All nine versions, every life:

| Version | In no polygon | 6-fold differs from the published 2022 code |
| --- | ---: | ---: |
| 2003-2004 | 30 | 12.3% |
| 2005-2006 | 870 | 12.7% |
| 2007-2008 | 34 | 11.7% |
| 2009-2010 | 34 | 11.2% |
| 2011-2012 | 34 | 10.7% |
| 2013-2014 | 7 | 11.9% |
| 2016 | 3 | 11.1% |
| 2020 | 4 | 7.4% |
| 2022 | 3 | 0 |

Two findings for the steps that follow. The work is worth doing: about one life in nine has
a different class in an earlier version than the 2022 code it carries today. And 2005-2006 is
an outlier: 870 points fall outside its polygons, spread across Scotland, of which 851 sit
inside both neighbouring versions. Repairing the geometry recovers none; 612 lie within 50 m
and 864 within 250 m of a polygon, so that file's coastline is drawn tighter than the others.
Step 3's no-polygon rule therefore matters for one version.

**Decided, 21 September 2026: a point outside every polygon stays null, with status
`outside_polygons`, in every version.** No nearest-polygon fallback initially, although NRS
appears to use one. The cost is known and small: 870 lives in 2005-2006 and at most 34 in any
other version. The build report counts them per version, so a later tolerance rule can be
judged against real numbers.

### 3. The geometry step

A new module, `simd_ingest/core/rurality.py`. It needs a geometry library, which is the first
non-trivial dependency this project has added; pin it like the others. Requirements:

- British National Grid throughout; assert each shapefile's reference system rather than
  reproject silently.
- A spatial index, so 247,773 points against up to several thousand polygons stays fast.
- A point that falls in no polygon (off the coast, in a gap) is null with status
  `outside_polygons`. Decided; see section 2a. No nearest-polygon fallback.
- A stated rule for a point exactly on a shared boundary, so the result is deterministic.
- Deterministic output, so the history table's fingerprint stays reproducible.

### 4. Schema

Post-office boxes: the derived columns are null where the link is `NO LINKP`, applied here as
a rule after the geometry, and counted in the build report. The published 2022 columns keep
whatever NRS supplied.

History table only. Per version, the 6-fold and 8-fold code where that version publishes
them, named like the SIMD columns, for example `urbanrural2016_6fold`, plus one status column
per version, `urbanrural2016_status`, null where the codes are present and otherwise the reason
they are not, row by row. Twenty-seven new columns, all nullable, source marked as derived
rather than directory. Review of 7bfd3c4 asked for the per-row status: an aggregate count
cannot tell the SQL which rows were outside the polygons.

Keep the two published 2022 columns exactly as NRS supplies them. The derived 2022 columns
sit beside them, which keeps the validation permanently visible instead of overwriting a
publisher's value with ours.

The schema version moves to `postcode_simd_wide_v2` and the fingerprint changes. The CSV gains
the columns, so the digest and the local loader's expectations change too, and a table
already loaded in a database becomes out of date.

### 5. Which version for which year

There is no PHS table for this, unlike SIMD's Table 4, so the mapping from the year of the
health data to a classification version is a **project choice** and must be labelled as one
wherever it appears.

Two mappings are possible and they differ, so the choice has to be explicit:

- **By reference year.** The version that describes that year. The 2022 version describes
  Census Day 2022.
- **By publication date.** The version an analyst could have used at the time. The 2022
  version was published on 16 December 2024, so under this rule events in 2022, 2023 and most
  of 2024 take the 2020 version.

Proposal: reference year, because the purpose is to describe where a person lived, not what
was knowable when. Years before the first version's reference year take none. Before step 6,
pin each version's reference year and publication date as evidence, from the publisher, and
settle the choice with the team.

### 6. SQL

`link_as_of.sql` and the walkthrough gain a rurality chosen by that mapping, returned beside
the published 2022 code, and both take it from the matched record as today. `link_by_era.sql`
can use the same mapping; `link_latest.sql` keeps the 2022 code.

A bare code cannot say why it is empty, and the SIMD edition and status cannot say it either,
so rurality gets its own provenance, on the pattern SIMD already follows:

- `rurality_version`: the classification version selected, null when none applies.
- `rurality_policy`: the mapping used, labelled as a project choice.
- `rurality_status`: `matched`; `before_first_version`; `outside_polygons`; `po_box`;
  `missing_year`; and the postcode failures inherited from `postcode_status`.

All of this is implemented in `simd_ingest/sql_examples.py`, which generates the committed
queries; the walkthrough is changed by hand to match, and the equivalence test extended to
the new columns.

### 7. Record, test, document

- Decision entries: the method and its validation result; the year mapping as a project
  choice; the no-polygon and boundary rules.
- **Independent validation of the saved columns.** Extend `readback` and `audit` to re-run
  the point-in-polygon from the saved file's own grid references against the pinned
  shapefiles and compare every rurality column, the way SIMD is re-looked-up from saved data
  zones. Comparing the file with the frame held in memory would not be independent.
- Tests: the 2022 agreement as a build check with the step 2 thresholds; synthetic points
  inside, outside and on a boundary; a recycled postcode whose lives land in different
  classes; and corruption tests, a derived code changed after writing in a historical version
  as well as in 2022, each of which readback and audit must catch.
- Data dictionary regenerated; `LINKAGE_BY_ERA.md`, the SQL README and the walkthrough's
  rurality comment updated; attribution text extended with the Scottish Government and
  Ordnance Survey statement.

## Licensing, to confirm before release

The pipeline already keeps grid references out of the shared CSV, as a conservative policy
pending confirmation (see `export_contract.yaml`). This plan uses them as an input and
publishes only derived classification codes, so the exclusion policy is unchanged. Two things
still need a named answer from HIC information governance: that HIC's public-sector
geospatial agreement covers using the grid references this way, and that codes derived from
them may be shared in the CSV.

## Out of scope

Reconstructing other historical geographies, moving SSPL to a per-life model, and any change
to how SIMD itself is attached.

## Proposed version

3.0.0 if the history schema version changes as described, since a loaded table and the
loader's expectations both break; otherwise 2.4.0.
