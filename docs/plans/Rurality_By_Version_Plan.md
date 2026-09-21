# Plan: a contemporary urban-rural class for every postcode life

Drafted 21 September 2026. Status: proposed, nothing implemented. The feasibility check in
step 2 gates everything after it.

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
- **"The same method SG and NRS use" is a claim, not a fact, until step 2.** The SPD is
  understood to allocate geography from the postcode's own grid reference, which is what makes
  the test below possible.
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

The published 2022 codes are a built-in ground truth for the method. Proceed only if agreement
is very high and the disagreements are explicable: points on a boundary, points off the coast,
boxes. Record the agreement rate and a breakdown of every disagreement. If agreement is poor,
stop and write down why; the rest is not worth building.

### 3. The geometry step

A new module, `simd_ingest/core/rurality.py`. It needs a geometry library, which is the first
non-trivial dependency this project has added; pin it like the others. Requirements:

- British National Grid throughout; assert each shapefile's reference system rather than
  reproject silently.
- A spatial index, so 247,773 points against up to several thousand polygons stays fast.
- A stated rule for a point that falls in no polygon (off the coast, in a gap): null with a
  reason, never the nearest polygon unless that is decided and recorded.
- A stated rule for a point exactly on a shared boundary, so the result is deterministic.
- Deterministic output, so the history table's fingerprint stays reproducible.

### 4. Schema

History table only. Per version, the 6-fold and 8-fold code where that version publishes
them, named on the pattern of the existing columns, for example `UrbanRural6Fold2016Code`.
Up to eighteen new columns, all nullable, source marked as derived rather than directory.

Keep the two published 2022 columns exactly as NRS supplies them. The derived 2022 columns
sit beside them, which keeps the validation permanently visible instead of overwriting a
publisher's value with ours.

The schema version moves to `postcode_simd_wide_v2` and the fingerprint changes. The CSV gains
the columns, so the digest and the local loader's expectations change too, and a table
already loaded in a database becomes out of date.

### 5. Which version for which year

There is no PHS table for this, unlike SIMD's Table 4, so the mapping from the year of the
health data to a classification version is a **project choice** and must be labelled as one
wherever it appears. Proposal: the version in force in that year, mirroring Table 4's logic,
with years before 2003 taking none. To be settled with the team before step 6.

### 6. SQL

`link_as_of.sql` and the walkthrough gain a rurality chosen by that mapping, returned beside
the published 2022 code, and both take it from the matched record as today. The PO-box rule
applies: blank when the status is `po_box`. `link_by_era.sql` can use the same mapping;
`link_latest.sql` keeps the 2022 code.

### 7. Record, test, document

- Decision entries: the method and its validation result; the year mapping as a project
  choice; the no-polygon and boundary rules.
- Tests: the 2022 agreement as a build check with a threshold; synthetic points inside,
  outside and on a boundary; a recycled postcode whose lives land in different classes.
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
