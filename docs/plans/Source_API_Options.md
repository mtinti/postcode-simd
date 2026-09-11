# Machine-readable sources for the SIMD pipeline

Checked 10 September 2026. Every candidate below was queried live and its content compared
with the hash-pinned files under `manual_data/` and with the PHS ranks. Nothing here is
taken from a catalogue description; every equivalence claim was computed.

## Verdict by data family

| Data family | Recommended source | API | Verified against pinned files | Licence |
| --- | --- | --- | --- | --- |
| PHS population-weighted SIMD, six editions | PHS open data, CKAN | `datastore_search` JSON, or dated CSV URL | 2020v2 API frame identical to the pinned CSV, all 6,976 rows and 16 columns | OGL, stated in package metadata |
| Government ranks and equal-count bands, six editions | SpatialData.gov.scot, ArcGIS REST | JSON query per layer, paginated at 1,000 | Ranks identical to PHS in all six editions; quintile, decile, vigintile identical to statistics.gov.scot; 2020 bands identical to the rank workbook | OGL v3 with attribution, stated on data.gov.uk |
| Same, as a cross-check | statistics.gov.scot, SPARQL | One endpoint, three cubes, one shape | 2020 cube rank identical to PHS 2020v2; historical cubes are the exact origin of the two downloaded CSVs | OGL v3, stated in cube metadata |
| Postcode directory | NRS, direct ZIP | None, fixed URL | All four members byte-identical to the pinned files | NRS terms, to confirm before redistribution |

Two platforms were checked and are not useful as sources. **data.gov.scot** is a static
front end that re-hosts CSV slices of statistics.gov.scot cubes; it has no API. The two
"historical" files you downloaded from it are those slices, row for row. **data.gov.uk**
is a catalogue only; its SIMD entries point at the ArcGIS services below.

## Why ArcGIS REST for the government side

Both government APIs verified clean. ArcGIS is recommended because it carries more, with
the simpler client.

| | ArcGIS REST | statistics.gov.scot SPARQL |
| --- | --- | --- |
| Client | Plain HTTPS GET returning JSON | SPARQL query, CSV or JSON back |
| Editions | Six layers, one per edition, 2009 is v2, 2020 is v2 | Three cubes covering the same six editions |
| Bands | Quintile, decile, vigintile, percentile | Quintile, decile, vigintile |
| Population per data zone | Every edition | None |
| Domain ranks | Every edition | Every edition |
| Version signal | None exposed | `dcterms:modified` per cube |
| Field naming | Differs by layer, needs a per-edition column map | Uniform |

The population columns matter. They are what made the PHS 2020v2 population-weighted bands
reproducible from the ranks workbook. ArcGIS supplies the same for 2004, 2006, 2009, 2012
and 2016, so that check can extend to every edition. The 2020 layer's population column is
identical to the ranks workbook's `Total_population` on all 6,976 zones.

On percentile: the historical layers publish one for 2001 data zones, which no other source
does. It does not follow either verified band rule, and the rank-to-percentile map differs
between 2004, 2006 and 2012. It is a published value but not a stable lookup. The decision
to leave percentile out stands; this note records that the value exists.

## Access patterns

PHS, one resource per edition. Resource IDs are in `sources.yaml`. The CSV URL carries a
date in the filename and has not changed since 2020, so the URL itself is a version pin.
CKAN exposes no content hash, so hashing stays on our side.

```text
https://www.opendata.nhs.scot/api/3/action/datastore_search?resource_id=<id>&limit=10000
https://www.opendata.nhs.scot/dataset/<pkg>/resource/<id>/download/<file>.csv
```

ArcGIS, one layer per edition. Layers 2 to 7 are 2004, 2006, 2009, 2012, 2016, 2020.
Seven pages of 1,000 per edition. Order by rank for a deterministic pull.

```text
https://maps.gov.scot/server/rest/services/ScotGov/PeopleSociety/MapServer/<layer>/query
  ?where=1%3D1&outFields=*&returnGeometry=false&orderByFields=rank
  &resultOffset=<n>&resultRecordCount=1000&f=json
```

statistics.gov.scot, one query per cube. Overall SIMD domain is `simdDomain/simd`.

```text
https://statistics.gov.scot/sparql        Accept: text/csv
cubes: scottish-index-of-multiple-deprivation              (2020, is v2)
       scottish-index-of-multiple-deprivation-historical-i (2004, 2006, 2009, 2012)
       scottish-index-of-multiple-deprivation-historical-ii (2016)
```

NRS, one ZIP with four flat members. The earlier HTTP 403 in the plan was a user-agent
rejection; a browser-style agent gets the file.

```text
https://www.nrscotland.gov.uk/media/hy3j3g1s/spd_postcodeindex_cut_26_2_csv.zip
sha256 4e93069ddb9c39c211cafdc56eeb16c4b0ed4872c9a95c20e23ec73c3b499057
members: SmallUser.csv, LargeUser.csv, spd-indexdatadictionary-2026-2.docx, spd-newsbulletin-2026-2.docx
```

## Evidence

| Check | Result |
| --- | --- |
| PHS datastore 2020v2 vs pinned CSV | Identical frame, 6,976 rows |
| ArcGIS rank vs PHS rank, 2004 / 2006 / 2009 / 2012 / 2016 / 2020 | 6,505 / 6,505 / 6,505 / 6,505 / 6,976 / 6,976 identical |
| ArcGIS quintile, decile, vigintile vs statistics.gov.scot, five historical editions | Identical on every zone |
| ArcGIS 2020 quintile, decile, vigintile, percentile vs rank workbook | Identical on all 6,976 |
| ArcGIS 2020 population vs ranks workbook | Identical on all 6,976 |
| statistics.gov.scot 2020 cube rank vs PHS 2020v2 | Identical on all 6,976 |
| statistics.gov.scot cube row counts vs downloaded CSVs | 806,620 and 223,232, identical |
| NRS ZIP members vs pinned files | All four SHA256 identical |

## What this changes in the plan

The download step that was deferred is now specified rather than open. Every source has
a fixed URL or query, and the pinned hashes already in `sources.yaml` are the acceptance
values for what comes back. The government workbook and the two data.gov.scot CSVs remain
valid pins, but they are no longer the only route; the same values are reachable through
an API and were shown to be identical.
