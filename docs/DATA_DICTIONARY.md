# Data dictionary: postcode_simd, schema `postcode_simd_sspl_v2`

The **main table**: one row per whole postcode from the Scottish Statistics Postcode Lookup (SSPL), both user types, the
latest life of each postcode (deleted ones included), with all 6 SIMD editions attached.
Every geography, including both data-zone vintages, is the one containing the centroid of the postcode's
2022 output area, as NRS allocates it in the SSPL. For postcode history and the directory's own
postcode-in-zone allocation see the history table, [DATA_DICTIONARY_HISTORY.md](DATA_DICTIONARY_HISTORY.md).
Generated from `simd_ingest/output_schema.yaml`; do not edit by hand.

Current build: 230,103 rows by 146 columns, main index release 2026_2,
allocation `oa2022_centroid`, built 2026-09-16T11:15:57Z. Parquet SHA256 `3e2eae514df9e28987a1739c9c9edce2533522dc633d2a3a592d80a3b555927a`; rows-only fingerprint
`9515021d99099b437950960380313e6fac7a9a6393858c4d6115fef43a94e564`. The file hash also covers the embedded provenance metadata,
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
It carries 144 of the 146 columns in the same order: `GridReferenceEasting`, `GridReferenceNorthing` are not exported.

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

Licences: phs: Open Government Licence v3.0, stated in the PHS open data package metadata; nrs: NRS terms; confirm before redistributing copies of the index; maps_gov_scot: Open Government Licence, stated in each shapefile's .shp.xml

## Columns

146 columns: 50 from the lookup, 6 derived,
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
