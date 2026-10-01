# Data dictionary: postcode_simd, schema `postcode_simd_sspl_v5`

The **main table**: one row per whole postcode from the Scottish Statistics Postcode Lookup (SSPL), both user types, the
latest life of each postcode (deleted ones included), with all 6 SIMD editions attached.
Every geography, including both data-zone vintages, is the one containing the centroid of the postcode's
2022 output area, as NRS allocates it in the SSPL. For postcode history and the directory's own
postcode-in-zone allocation see the history table, [DATA_DICTIONARY_HISTORY.md](DATA_DICTIONARY_HISTORY.md).
Generated from `simd_ingest/output_schema.yaml`; do not edit by hand.

Current build: 230,103 rows by 399 columns, main index release 2026_2,
allocation `oa2022_centroid`, built 2026-10-01T05:57:41Z. Parquet SHA256 `d10fb5d2aabea7eea38fe047f8397daeeed96141455deb9e4e3fab121027cefe`; rows-only fingerprint
`270e9bacc2901193044d83e21234fac4a5e60b4e548dcd17fa16fcafe7c5dff9`. The file hash also covers the embedded provenance metadata,
so it changes when the decision log changes; compare fingerprints under the same pinned runtime.

## Key

Primary key: `pc_norm`, the postcode uppercased without spaces. One row per postcode; no split suffix
exists because NRS resolved split postcodes to the A part before publishing. `is_current` says whether
the latest life is live; `introduced_on` and `deleted_on` describe that latest life only. This table
cannot select a past postcode life: use history for that. Choosing a past SIMD edition on this
latest postcode is supported by the SQL era query. These are different policies.

## Band convention

Every band column reads 1 as most deprived. The PHS 2004 and 2006 population-weighted deciles and quintiles were re-derived from the published values, 11 - decile and 6 - quintile, so that they follow the ordering used by every other edition. Ranks and the Most15pc and Least15pc flags are as published in all editions. Columns named simd{edition}_pw_* are PHS population-weighted; columns named simd{edition}_uw_* are Scottish Government unweighted; the two must not be combined in one analysis. The vigintile is available only unweighted. No percentile is carried.

## Which edition to use

From the PHS deprivation guidance for analysts, version 3.5, table 4. The file carries every
edition on every row; choosing one is the analyst's decision.

| Edition | Data zones | Population year | Use with health data for |
| --- | --- | --- | --- |
| SIMD 2004 | 2001 | 2001 | 1996 to 2003 |
| SIMD 2006 | 2001 | 2004 | 2004 to 2006 |
| SIMD 2009v2 | 2001 | 2007 | 2007 to 2009 |
| SIMD 2012 | 2001 | 2010 | 2010 to 2013 |
| SIMD 2016 | 2011 | 2014 | 2014 to 2016 |
| SIMD 2020v2 | 2011 | 2017 | 2017 onwards |

Data-zone vintages are not interchangeable; the join here
already uses the right vintage for each edition. The file carries SIMD only; the Carstairs index
the same guidance describes for pre-1996 data is not included.

## Things that will catch you out

- **Allocation.** The SSPL assigns every higher geography from the 2022 output-area centroid. Its 2011
  and 2001 data zones therefore differ from the directory's on a few percent of postcodes, and so do
  the SIMD values attached through them. The build report counts observed differences, without
  attributing every difference to method rather than release changes. Neither table establishes
  equivalence to PHS's published postcode lookup. Choose one product consistently for a study.
- **Split postcodes** are already whole here. `SplitIndicator` Y marks a postcode the directory holds
  as A/B/C parts; the SSPL keeps the A part's geography and sums the counts.
- **Large-user postcodes and PO boxes.** The source assigns them a data zone, so SIMD is attached.
  The [SQL sets](LINKAGE_BY_ERA.md) follow a large user's link and give PO boxes no SIMD. Applying
  this to SSPL is a project interpretation of PHS Appendix A, which does not explicitly settle
  overriding SSPL's own allocated geography. Exact PHS lookup parity remains unverified.
  Python keeps its own current/as-of, own-record geography and
  sentinel-exclusion policy. Residence eligibility and publication choices are downstream.
- **Within-geography bands.** `simd{ed}_pw_hb_*` is computed within the health board in
  `phs_dz{vintage}_hb`, which on a few records differs from the directory's own `HealthBoardArea2019Code`.
  Use the PHS code with the PHS band.
- **Directory columns are text.** Every original column keeps its source text, including leading
  zeros and blanks. A blank is `""`; a column absent from that user type is null.

## The CSV rendering

Every build also writes `results/postcode_simd.csv.gz`, the form in which this table is shared.
It carries 397 of the 399 columns in the same order: `GridReferenceEasting`, `GridReferenceNorthing` are not exported.

  Do not carry coordinate fields into outputs whose purpose is deprivation and area context. A project data-minimisation choice, not an anonymisation guarantee.

  NRS supplies its index and lookup products under the Open Government Licence and restricts "postcode boundaries and grid references" separately, but its licensing page does not settle which governs a grid reference column inside an index file. Removal is a conservative project policy pending confirmation from NRS or HIC information governance.

The Parquet keeps them, so read it directly if you need a grid reference.

Comma separated with RFC 4180 quoting, UTF-8 without a byte order mark, LF line endings
and gzip compression. Dates are `YYYY-MM-DD`, `is_current` is `1` or `0`, and every other
value is written exactly as stored, so leading zeros survive. Load every column as text
first, keeping literal values such as `NA`, and restore the declared types afterwards.

### An empty cell

CSV writes the same empty cell for a null and for a source blank, so read it from the
column and the record type, never from the cell alone.

These text columns are never blank, so an empty cell in one is a null for every record: `simd2020v2_housing_domain_rank_source_status`.

This table comes from a single source file, so every text empty is a source blank.

An empty `deleted_on` is a null and agrees with `is_current`. The source text column
`DateOfDeletion` stays blank. Every other empty cell is a source blank.

`results/CSV_README.txt` beside the files carries the attribution every source requires.

## Sources

| Publisher | Object | SHA256 |
| --- | --- | --- |
| phs | simd2004_02042020.csv | `dcc871e88353884a…` |
| phs | simd2006_02042020.csv | `69f9fb1a2e51d464…` |
| phs | simd2009v2_23062019.csv | `effa76a989820f28…` |
| phs | simd2012_02042020.csv | `c4c12b6346ee9fa1…` |
| phs | simd2016_18052020.csv | `3a98af3b181d8273…` |
| phs | simd2020v2_22062020.csv | `686bc9aa38b61891…` |
| nrs | spd_postcodeindex_cut_26_2_csv.zip | `4e93069ddb9c39c2…` |
| nrs | sspl-2026-2.zip | `b3cc78a21b1cdecd…` |
| maps_gov_scot | SG_SIMD_2004.zip | `3bc179d9eebac787…` |
| maps_gov_scot | SG_SIMD_2006.zip | `fe7c662ee48cfe28…` |
| maps_gov_scot | SG_SIMD_2009.zip | `438a14225afcfd1d…` |
| maps_gov_scot | SG_SIMD_2012.zip | `c91aea4cbf39d116…` |
| maps_gov_scot | SG_SIMD_2016.zip | `bffbec7c3f45da16…` |
| maps_gov_scot | SG_SIMD_2020.zip | `33f166949c0e8a54…` |
| maps_gov_scot | SG_UrbanRural_2003_2004.zip | `1389441b25a2804c…` |
| maps_gov_scot | SG_UrbanRural_2005_2006.zip | `f792012c3f8b086a…` |
| maps_gov_scot | SG_UrbanRural_2007_2008.zip | `9aa388730b66f81f…` |
| maps_gov_scot | SG_UrbanRural_2009_2010.zip | `d5db1b102f4ce081…` |
| maps_gov_scot | SG_UrbanRural_2011_2012.zip | `5f6f57badf3508c2…` |
| maps_gov_scot | SG_UrbanRural_2013_2014.zip | `725ed5bb2b722848…` |
| maps_gov_scot | SG_UrbanRural_2016.zip | `f44f3b22237bf43d…` |
| maps_gov_scot | SG_UrbanRural_2020.zip | `5969d3377170c592…` |
| maps_gov_scot | SG_UrbanRural_2022.zip | `1b18bce2d4201d5f…` |
| statistics_gov_scot | cube-table?uri=http%3A%2F%2Fstatistics.gov.scot%2Fdata%2Fscottish-index-of-multiple-deprivation-historical-i | `d9745d9d7763fbe9…` |
| statistics_gov_scot | cube-table?uri=http%3A%2F%2Fstatistics.gov.scot%2Fdata%2Fscottish-index-of-multiple-deprivation-historical-ii | `3be67d034964cbbb…` |
| statistics_gov_scot | cube-table?uri=http%3A%2F%2Fstatistics.gov.scot%2Fdata%2Fscottish-index-of-multiple-deprivation | `25fea7ddaf54659a…` |

Licences: phs: Open Government Licence v3.0, stated in the PHS open data package metadata; nrs: NRS terms; confirm before redistributing copies of the index; maps_gov_scot: Open Government Licence, stated in each shapefile's .shp.xml; statistics_gov_scot: Open Government Licence v3.0, stated on each dataset page; publisher the Scottish Government, contact simd@gov.scot

## Columns

399 columns: 50 from the lookup, 6 derived,
6 PHS geography, and 14 per edition for 6 editions.

### Per-edition SIMD columns

`{ed}` is one of 2004, 2006, 2009v2, 2012, 2016, 2020v2.

| Column | Type | Meaning |
| --- | --- | --- |
| `simd{ed}_rank` | int16 | 1 = most deprived; identical to the Scottish Government rank |
| `simd{ed}_pw_scotland_decile` | int8 | PHS population-weighted decile within scotland; 1 = most deprived |
| `simd{ed}_pw_scotland_quintile` | int8 | PHS population-weighted quintile within scotland; 1 = most deprived |
| `simd{ed}_pw_hb_decile` | int8 | PHS population-weighted decile within hb; 1 = most deprived |
| `simd{ed}_pw_hb_quintile` | int8 | PHS population-weighted quintile within hb; 1 = most deprived |
| `simd{ed}_pw_hscp_decile` | int8 | PHS population-weighted decile within hscp; 1 = most deprived |
| `simd{ed}_pw_hscp_quintile` | int8 | PHS population-weighted quintile within hscp; 1 = most deprived |
| `simd{ed}_pw_ca_decile` | int8 | PHS population-weighted decile within ca; 1 = most deprived |
| `simd{ed}_pw_ca_quintile` | int8 | PHS population-weighted quintile within ca; 1 = most deprived |
| `simd{ed}_most15pc` | int8 | PHS population-weighted 15% most deprived flag, as published |
| `simd{ed}_least15pc` | int8 | PHS population-weighted 15% least deprived flag, as published |
| `simd{ed}_uw_scotland_quintile` | int8 | Scottish Government unweighted quintile; 1 = most deprived |
| `simd{ed}_uw_scotland_decile` | int8 | Scottish Government unweighted decile; 1 = most deprived |
| `simd{ed}_uw_scotland_vigintile` | int8 | Scottish Government unweighted vigintile; 1 = most deprived |
| `simd{ed}_income_domain_rank` | rank | Scottish Government SIMD 2004 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| `simd{ed}_employment_domain_rank` | rank | Scottish Government SIMD 2004 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| `simd{ed}_health_domain_rank` | rank | Scottish Government SIMD 2004 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| `simd{ed}_education_domain_rank` | rank | Scottish Government SIMD 2004 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| `simd{ed}_access_domain_rank` | rank | Scottish Government SIMD 2004 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| `simd{ed}_housing_domain_rank` | rank | Scottish Government SIMD 2004 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| `simd{ed}_income_domain_quintile` | int8 | Scottish Government SIMD 2004 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_income_domain_decile` | int8 | Scottish Government SIMD 2004 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_income_domain_vigintile` | int8 | Scottish Government SIMD 2004 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_employment_domain_quintile` | int8 | Scottish Government SIMD 2004 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_employment_domain_decile` | int8 | Scottish Government SIMD 2004 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_employment_domain_vigintile` | int8 | Scottish Government SIMD 2004 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_health_domain_quintile` | int8 | Scottish Government SIMD 2004 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_health_domain_decile` | int8 | Scottish Government SIMD 2004 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_health_domain_vigintile` | int8 | Scottish Government SIMD 2004 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_education_domain_quintile` | int8 | Scottish Government SIMD 2004 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_education_domain_decile` | int8 | Scottish Government SIMD 2004 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_education_domain_vigintile` | int8 | Scottish Government SIMD 2004 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_access_domain_quintile` | int8 | Scottish Government SIMD 2004 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_access_domain_decile` | int8 | Scottish Government SIMD 2004 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_access_domain_vigintile` | int8 | Scottish Government SIMD 2004 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_housing_domain_quintile` | int8 | Scottish Government SIMD 2004 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_housing_domain_decile` | int8 | Scottish Government SIMD 2004 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_housing_domain_vigintile` | int8 | Scottish Government SIMD 2004 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| `simd{ed}_income_domain_pw_scotland_quintile` | int8 | SIMD 2004 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_income_domain_pw_scotland_decile` | int8 | SIMD 2004 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_employment_domain_pw_scotland_quintile` | int8 | SIMD 2004 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_employment_domain_pw_scotland_decile` | int8 | SIMD 2004 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_health_domain_pw_scotland_quintile` | int8 | SIMD 2004 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_health_domain_pw_scotland_decile` | int8 | SIMD 2004 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_education_domain_pw_scotland_quintile` | int8 | SIMD 2004 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_education_domain_pw_scotland_decile` | int8 | SIMD 2004 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_access_domain_pw_scotland_quintile` | int8 | SIMD 2004 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_access_domain_pw_scotland_decile` | int8 | SIMD 2004 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_housing_domain_pw_scotland_quintile` | int8 | SIMD 2004 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_housing_domain_pw_scotland_decile` | int8 | SIMD 2004 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| `simd{ed}_population` | int16 | Population of the data zone in the SIMD 2004 shapefile (2001 Census), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |

### All columns in file order

| # | Column | Type | Nullable | Source | Note |
| ---: | --- | --- | --- | --- | --- |
| 1 | `Postcode` | string | no | lookup | whole postcode as published; NRS has already resolved splits to the A part |
| 2 | `PostcodeDistrict` | string | no | lookup |  |
| 3 | `PostcodeSector` | string | no | lookup |  |
| 4 | `SplitIndicator` | string | no | lookup | Y when the SPD holds this postcode as split parts; counts here are the summed whole |
| 5 | `LinkedSmallUserPostcode` | string | no | lookup | large users only: small-user postcode containing the grid reference, NO LINKP for PO boxes, NO LINK otherwise unlinked; may retain an NRS split suffix; blank for small users |
| 6 | `DateOfIntroduction` | string | no | lookup |  |
| 7 | `DateOfDeletion` | string | no | lookup | blank while current |
| 8 | `PostcodeType` | string | no | lookup | S small user, L large user |
| 9 | `GridReferenceEasting` | string | no | lookup |  |
| 10 | `GridReferenceNorthing` | string | no | lookup |  |
| 11 | `OutputArea2022Code` | string | no | lookup |  |
| 12 | `OutputArea2011Code` | string | no | lookup |  |
| 13 | `DataZone2022Code` | string | no | lookup |  |
| 14 | `DataZone2011Code` | string | no | lookup |  |
| 15 | `IntermediateZone2022Code` | string | no | lookup |  |
| 16 | `IntermediateZone2011Code` | string | no | lookup |  |
| 17 | `OutputArea2001Code` | string | no | lookup |  |
| 18 | `DataZone2001Code` | string | no | lookup |  |
| 19 | `IntermediateZone2001Code` | string | no | lookup |  |
| 20 | `OutputArea1991Code` | string | no | lookup |  |
| 21 | `CouncilArea2019Code` | string | no | lookup |  |
| 22 | `RegistrationDistrict2007Code` | string | no | lookup |  |
| 23 | `LocalGovernmentDistrict1995Code` | string | no | lookup |  |
| 24 | `LocalGovernmentDistrict1991Code` | string | no | lookup |  |
| 25 | `ElectoralWard2022Code` | string | no | lookup |  |
| 26 | `ScottishParliamentaryRegion2026Code` | string | no | lookup |  |
| 27 | `ScottishParliamentaryConstituency2026Code` | string | no | lookup |  |
| 28 | `UKParliamentaryConstituency2024Code` | string | no | lookup |  |
| 29 | `HealthBoardArea2019Code` | string | no | lookup |  |
| 30 | `HealthBoardArea2006Code` | string | no | lookup |  |
| 31 | `HealthBoardArea1995Code` | string | no | lookup |  |
| 32 | `IntegrationAuthority2019Code` | string | no | lookup |  |
| 33 | `StrategicDevelopmentPlanningArea2013Code` | string | no | lookup |  |
| 34 | `CivilParish1930Code` | string | no | lookup |  |
| 35 | `TravelToWorkArea2011Code` | string | no | lookup |  |
| 36 | `IslandCode` | string | no | lookup |  |
| 37 | `UrbanRural6Fold2022Code` | string | no | lookup |  |
| 38 | `UrbanRural8Fold2022Code` | string | no | lookup |  |
| 39 | `LAU2025Level1Code` | string | no | lookup |  |
| 40 | `ITL2025Level2Code` | string | no | lookup |  |
| 41 | `ITL2025Level3Code` | string | no | lookup |  |
| 42 | `CensusHouseholdCount2022` | string | no | lookup |  |
| 43 | `CensusPopulationCount2022` | string | no | lookup |  |
| 44 | `CensusHouseholdCount2011` | string | no | lookup |  |
| 45 | `CensusPopulationCount2011` | string | no | lookup |  |
| 46 | `CensusHouseholdCount2001` | string | no | lookup |  |
| 47 | `CensusPopulationCount2001` | string | no | lookup |  |
| 48 | `CensusHouseholdCount1991` | string | no | lookup |  |
| 49 | `CensusPopulationCount1991` | string | no | lookup |  |
| 50 | `ScottishIndexOfMultipleDeprivation2020Rank` | string | no | lookup | the lookup's own 2020 rank, compared with simd2020v2_rank as a check |
| 51 | `pc_norm` | string | no | derived | primary key: uppercased, spaces removed; no split suffix exists in this table |
| 52 | `spd_user_type` | string | no | derived | small_user or large_user, from PostcodeType |
| 53 | `sspl_release` | string | no | derived | lookup release this record came from |
| 54 | `introduced_on` | date32 | no | derived | introduction of the latest life |
| 55 | `deleted_on` | date32 | yes | derived | null while current; the latest life may be deleted |
| 56 | `is_current` | bool | no | derived | deleted_on is null |
| 57 | `phs_dz2001_hb` | string | no | phs | health board PHS assigned to the 2001 data zone when computing within-geography bands |
| 58 | `phs_dz2001_hscp` | string | no | phs | HSCP PHS assigned to the 2001 data zone when computing within-geography bands |
| 59 | `phs_dz2001_ca` | string | no | phs | council area PHS assigned to the 2001 data zone when computing within-geography bands |
| 60 | `phs_dz2011_hb` | string | no | phs | health board PHS assigned to the 2011 data zone when computing within-geography bands |
| 61 | `phs_dz2011_hscp` | string | no | phs | HSCP PHS assigned to the 2011 data zone when computing within-geography bands |
| 62 | `phs_dz2011_ca` | string | no | phs | council area PHS assigned to the 2011 data zone when computing within-geography bands |
| 63 | `simd2004_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 64 | `simd2004_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 65 | `simd2004_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 66 | `simd2004_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 67 | `simd2004_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 68 | `simd2004_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 69 | `simd2004_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 70 | `simd2004_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 71 | `simd2004_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 72 | `simd2004_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 73 | `simd2004_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 74 | `simd2004_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 75 | `simd2004_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 76 | `simd2004_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
| 77 | `simd2006_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 78 | `simd2006_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 79 | `simd2006_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 80 | `simd2006_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 81 | `simd2006_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 82 | `simd2006_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 83 | `simd2006_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 84 | `simd2006_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 85 | `simd2006_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 86 | `simd2006_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 87 | `simd2006_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 88 | `simd2006_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 89 | `simd2006_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 90 | `simd2006_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
| 91 | `simd2009v2_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 92 | `simd2009v2_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 93 | `simd2009v2_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 94 | `simd2009v2_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 95 | `simd2009v2_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 96 | `simd2009v2_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 97 | `simd2009v2_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 98 | `simd2009v2_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 99 | `simd2009v2_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 100 | `simd2009v2_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 101 | `simd2009v2_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 102 | `simd2009v2_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 103 | `simd2009v2_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 104 | `simd2009v2_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
| 105 | `simd2012_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 106 | `simd2012_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 107 | `simd2012_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 108 | `simd2012_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 109 | `simd2012_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 110 | `simd2012_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 111 | `simd2012_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 112 | `simd2012_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 113 | `simd2012_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 114 | `simd2012_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 115 | `simd2012_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 116 | `simd2012_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 117 | `simd2012_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 118 | `simd2012_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
| 119 | `simd2016_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 120 | `simd2016_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 121 | `simd2016_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 122 | `simd2016_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 123 | `simd2016_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 124 | `simd2016_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 125 | `simd2016_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 126 | `simd2016_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 127 | `simd2016_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 128 | `simd2016_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 129 | `simd2016_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 130 | `simd2016_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 131 | `simd2016_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 132 | `simd2016_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
| 133 | `simd2020v2_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 134 | `simd2020v2_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 135 | `simd2020v2_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 136 | `simd2020v2_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 137 | `simd2020v2_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 138 | `simd2020v2_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 139 | `simd2020v2_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 140 | `simd2020v2_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 141 | `simd2020v2_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 142 | `simd2020v2_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 143 | `simd2020v2_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 144 | `simd2020v2_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 145 | `simd2020v2_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 146 | `simd2020v2_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
| 147 | `simd2004_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 148 | `simd2004_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 149 | `simd2004_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 150 | `simd2004_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 151 | `simd2004_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 152 | `simd2004_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 153 | `simd2006_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 154 | `simd2006_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 155 | `simd2006_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 156 | `simd2006_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 157 | `simd2006_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 158 | `simd2006_crime_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 crime domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 159 | `simd2006_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 160 | `simd2009v2_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 161 | `simd2009v2_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 162 | `simd2009v2_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 163 | `simd2009v2_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 164 | `simd2009v2_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 165 | `simd2009v2_crime_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 crime domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 166 | `simd2009v2_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 167 | `simd2012_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 168 | `simd2012_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 169 | `simd2012_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 170 | `simd2012_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 171 | `simd2012_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 172 | `simd2012_crime_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 crime domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 173 | `simd2012_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 174 | `simd2016_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 175 | `simd2016_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 176 | `simd2016_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 177 | `simd2016_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 178 | `simd2016_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 179 | `simd2016_crime_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 crime domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 180 | `simd2016_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 181 | `simd2020v2_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 182 | `simd2020v2_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 183 | `simd2020v2_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 184 | `simd2020v2_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 185 | `simd2020v2_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 186 | `simd2020v2_crime_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 crime domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 187 | `simd2020v2_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 188 | `simd2004_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 189 | `simd2004_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 190 | `simd2004_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 191 | `simd2004_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 192 | `simd2004_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 193 | `simd2004_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 194 | `simd2004_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 195 | `simd2004_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 196 | `simd2004_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 197 | `simd2004_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 198 | `simd2004_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 199 | `simd2004_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 200 | `simd2004_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 201 | `simd2004_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 202 | `simd2004_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 203 | `simd2004_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 204 | `simd2004_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 205 | `simd2004_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 206 | `simd2006_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 207 | `simd2006_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 208 | `simd2006_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 209 | `simd2006_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 210 | `simd2006_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 211 | `simd2006_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 212 | `simd2006_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 213 | `simd2006_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 214 | `simd2006_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 215 | `simd2006_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 216 | `simd2006_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 217 | `simd2006_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 218 | `simd2006_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 219 | `simd2006_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 220 | `simd2006_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 221 | `simd2006_crime_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 crime domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 222 | `simd2006_crime_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 crime domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 223 | `simd2006_crime_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 crime domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 224 | `simd2006_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 225 | `simd2006_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 226 | `simd2006_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 227 | `simd2009v2_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 228 | `simd2009v2_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 229 | `simd2009v2_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 230 | `simd2009v2_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 231 | `simd2009v2_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 232 | `simd2009v2_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 233 | `simd2009v2_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 234 | `simd2009v2_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 235 | `simd2009v2_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 236 | `simd2009v2_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 237 | `simd2009v2_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 238 | `simd2009v2_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 239 | `simd2009v2_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 240 | `simd2009v2_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 241 | `simd2009v2_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 242 | `simd2009v2_crime_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 crime domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 243 | `simd2009v2_crime_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 crime domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 244 | `simd2009v2_crime_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 crime domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 245 | `simd2009v2_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 246 | `simd2009v2_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 247 | `simd2009v2_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 248 | `simd2012_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 249 | `simd2012_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 250 | `simd2012_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 251 | `simd2012_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 252 | `simd2012_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 253 | `simd2012_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 254 | `simd2012_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 255 | `simd2012_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 256 | `simd2012_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 257 | `simd2012_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 258 | `simd2012_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 259 | `simd2012_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 260 | `simd2012_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 261 | `simd2012_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 262 | `simd2012_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 263 | `simd2012_crime_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 crime domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 264 | `simd2012_crime_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 crime domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 265 | `simd2012_crime_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 crime domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 266 | `simd2012_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 267 | `simd2012_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 268 | `simd2012_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 269 | `simd2016_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 270 | `simd2016_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 271 | `simd2016_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 272 | `simd2016_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 273 | `simd2016_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 274 | `simd2016_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 275 | `simd2016_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 276 | `simd2016_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 277 | `simd2016_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 278 | `simd2016_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 279 | `simd2016_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 280 | `simd2016_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 281 | `simd2016_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 282 | `simd2016_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 283 | `simd2016_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 284 | `simd2016_crime_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 crime domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 285 | `simd2016_crime_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 crime domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 286 | `simd2016_crime_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 crime domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 287 | `simd2016_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 288 | `simd2016_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 289 | `simd2016_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 290 | `simd2020v2_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 291 | `simd2020v2_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 292 | `simd2020v2_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 293 | `simd2020v2_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 294 | `simd2020v2_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 295 | `simd2020v2_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 296 | `simd2020v2_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 297 | `simd2020v2_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 298 | `simd2020v2_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 299 | `simd2020v2_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 300 | `simd2020v2_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 301 | `simd2020v2_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 302 | `simd2020v2_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 303 | `simd2020v2_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 304 | `simd2020v2_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 305 | `simd2020v2_crime_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 crime domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 306 | `simd2020v2_crime_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 crime domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 307 | `simd2020v2_crime_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 crime domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 308 | `simd2020v2_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 309 | `simd2020v2_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 310 | `simd2020v2_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 311 | `simd2020v2_housing_domain_rank_source_status` | string | yes | govscot_bands | rank_sources_disagree where the Scottish Government's statistics.gov.scot dataset and its shapefile give this zone different housing ranks (the rank here is the shapefile's, which the ranks workbook confirms; the bands are the published ones, and for 626 of the 628 zones the same under either ranking); null otherwise |
| 312 | `simd2004_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 313 | `simd2004_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 314 | `simd2004_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 315 | `simd2004_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 316 | `simd2004_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 317 | `simd2004_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 318 | `simd2004_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 319 | `simd2004_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 320 | `simd2004_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 321 | `simd2004_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 322 | `simd2004_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 323 | `simd2004_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 324 | `simd2006_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 325 | `simd2006_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 326 | `simd2006_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 327 | `simd2006_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 328 | `simd2006_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 329 | `simd2006_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 330 | `simd2006_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 331 | `simd2006_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 332 | `simd2006_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 333 | `simd2006_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 334 | `simd2006_crime_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 crime domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 335 | `simd2006_crime_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 crime domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 336 | `simd2006_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 337 | `simd2006_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 338 | `simd2009v2_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 339 | `simd2009v2_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 340 | `simd2009v2_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 341 | `simd2009v2_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 342 | `simd2009v2_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 343 | `simd2009v2_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 344 | `simd2009v2_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 345 | `simd2009v2_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 346 | `simd2009v2_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 347 | `simd2009v2_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 348 | `simd2009v2_crime_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 crime domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 349 | `simd2009v2_crime_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 crime domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 350 | `simd2009v2_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 351 | `simd2009v2_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 352 | `simd2012_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 353 | `simd2012_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 354 | `simd2012_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 355 | `simd2012_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 356 | `simd2012_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 357 | `simd2012_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 358 | `simd2012_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 359 | `simd2012_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 360 | `simd2012_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 361 | `simd2012_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 362 | `simd2012_crime_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 crime domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 363 | `simd2012_crime_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 crime domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 364 | `simd2012_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 365 | `simd2012_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 366 | `simd2016_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 367 | `simd2016_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 368 | `simd2016_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 369 | `simd2016_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 370 | `simd2016_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 371 | `simd2016_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 372 | `simd2016_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 373 | `simd2016_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 374 | `simd2016_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 375 | `simd2016_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 376 | `simd2016_crime_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 crime domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 377 | `simd2016_crime_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 crime domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 378 | `simd2016_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 379 | `simd2016_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 380 | `simd2020v2_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 381 | `simd2020v2_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 382 | `simd2020v2_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 383 | `simd2020v2_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 384 | `simd2020v2_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 385 | `simd2020v2_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 386 | `simd2020v2_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 387 | `simd2020v2_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 388 | `simd2020v2_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 389 | `simd2020v2_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 390 | `simd2020v2_crime_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 crime domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 391 | `simd2020v2_crime_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 crime domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 392 | `simd2020v2_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 393 | `simd2020v2_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 394 | `simd2004_population` | int16 | no | govscot | Population of the data zone in the SIMD 2004 shapefile (2001 Census), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
| 395 | `simd2006_population` | int16 | no | govscot | Population of the data zone in the SIMD 2006 shapefile (NRS small-area estimates for 2004), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
| 396 | `simd2009v2_population` | int16 | no | govscot | Population of the data zone in the SIMD 2009v2 shapefile (NRS small-area estimates for 2007), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
| 397 | `simd2012_population` | int16 | no | govscot | Population of the data zone in the SIMD 2012 shapefile (NRS small-area estimates for 2010), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
| 398 | `simd2016_population` | int16 | no | govscot | Population of the data zone in the SIMD 2016 shapefile (NRS small-area estimates for 2014), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
| 399 | `simd2020v2_population` | int16 | no | govscot | Population of the data zone in the SIMD 2020v2 shapefile (NRS small-area estimates for 2017), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
