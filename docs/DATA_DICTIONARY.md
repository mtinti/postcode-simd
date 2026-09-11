# Data dictionary: postcode_simd, schema `postcode_simd_wide_v1`

One row per Scottish Postcode Directory record, both user types, current and deleted, with all
six SIMD editions attached. Generated from `simd_ingest/output_schema.yaml`; do not edit by hand.

Current build: 247,773 rows by 162 columns, SPD release 2026_2, 
built 2026-09-11T09:09:47Z. Parquet SHA256 `054f56ac0e469597265825a5ebb1c7d868ac8a1f5232eac144d3a0ee6b66f4d4`; rows-only fingerprint 
`59369357e44e45a5ac74b217692fd8e4799fd0aafc3b04e4e2c255abf722dc97`. The file hash also covers the embedded provenance metadata, 
so it changes when the decision log changes; the fingerprint changes only when the data does.

## Key

Primary key: `pc_norm` with `introduced_on`. Unique across both user types. A postcode alone repeats
up to seven times across its history, so never join on `pc_norm` without the date.

Validity of a record is the half-open interval `introduced_on <= day < deleted_on`, with a null
`deleted_on` meaning current. A record whose two dates are equal is retained but is never valid
on any day.

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

Editions on 2001 data zones cannot be used with 2011 data zones and vice versa; the join here
already uses the right vintage for each edition. The file carries SIMD only; the Carstairs index
the same guidance describes for pre-1996 data is not included.

## Things that will catch you out

- **Split postcodes.** NRS splits a postcode that straddles a boundary into A, B or C parts, each its
  own record with its own data zone. `pc_base` is the postcode as a person writes it. Filter current
  records on `pc_base` and you may get more than one row with different SIMD values. Report that as
  ambiguous; never pick A.
- **Large-user postcodes and PO boxes.** The directory assigns them a data zone, so SIMD is attached.
  PHS practice attaches no deprivation to PO boxes. Filter on `spd_user_type` and on
  `LinkedSmallUserPostcode` in (`NO LINKP`, `NO LINK`) if you want that behaviour.
- **Within-geography bands.** `simd{ed}_pw_hb_*` is computed within the health board in
  `phs_dz{vintage}_hb`, which on a few records differs from the directory's own `HealthBoardArea2019Code`.
  Use the PHS code with the PHS band.
- **Directory columns are text.** Every original column keeps its source text, including leading
  zeros and blanks. A blank is `""`; a column absent from that user type is null.

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
| maps_gov_scot | SG_SIMD_2004.zip | `3bc179d9eebac787…` |
| maps_gov_scot | SG_SIMD_2006.zip | `fe7c662ee48cfe28…` |
| maps_gov_scot | SG_SIMD_2009.zip | `438a14225afcfd1d…` |
| maps_gov_scot | SG_SIMD_2012.zip | `c91aea4cbf39d116…` |
| maps_gov_scot | SG_SIMD_2016.zip | `bffbec7c3f45da16…` |
| maps_gov_scot | SG_SIMD_2020.zip | `33f166949c0e8a54…` |

Licences: phs: Open Government Licence v3.0, stated in the PHS open data package metadata; nrs: NRS terms; confirm before redistributing copies of the index; maps_gov_scot: Open Government Licence, stated in each shapefile's .shp.xml

## Columns

162 columns: 65 from the directory, 7 derived, 
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
| 1 | `Postcode` | string | no | directory |  |
| 2 | `PostcodeDistrict` | string | no | directory |  |
| 3 | `PostcodeSector` | string | no | directory |  |
| 4 | `DateOfIntroduction` | string | no | directory |  |
| 5 | `DateOfDeletion` | string | no | directory |  |
| 6 | `GridReferenceEasting` | string | no | directory |  |
| 7 | `GridReferenceNorthing` | string | no | directory |  |
| 8 | `Latitude` | string | no | directory |  |
| 9 | `Longitude` | string | no | directory |  |
| 10 | `SplitIndicator` | string | no | directory |  |
| 11 | `CouncilArea2019Code` | string | no | directory |  |
| 12 | `UKParliamentaryConstituency2024Code` | string | no | directory |  |
| 13 | `ScottishParliamentaryRegion2026Code` | string | no | directory |  |
| 14 | `ScottishParliamentaryConstituency2026Code` | string | no | directory |  |
| 15 | `ElectoralWard2022Code` | string | no | directory |  |
| 16 | `HealthBoardArea2019Code` | string | no | directory |  |
| 17 | `HealthBoardArea2006Code` | string | no | directory |  |
| 18 | `HealthBoardArea1995Code` | string | no | directory |  |
| 19 | `IntegrationAuthority2019Code` | string | no | directory |  |
| 20 | `OutputArea2022Code` | string | no | directory |  |
| 21 | `OutputArea2011Code` | string | no | directory |  |
| 22 | `OutputArea2001Code` | string | no | directory |  |
| 23 | `OutputArea1991Code` | string | no | directory |  |
| 24 | `DataZone2022Code` | string | no | directory |  |
| 25 | `DataZone2011Code` | string | no | directory |  |
| 26 | `DataZone2001Code` | string | no | directory |  |
| 27 | `IntermediateZone2022Code` | string | no | directory |  |
| 28 | `IntermediateZone2011Code` | string | no | directory |  |
| 29 | `IntermediateZone2001Code` | string | no | directory |  |
| 30 | `CensusHouseholdCount2022` | string | yes | directory | small-user only |
| 31 | `CensusPopulationCount2022` | string | yes | directory | small-user only |
| 32 | `CensusHouseholdCount2011` | string | yes | directory | small-user only |
| 33 | `CensusPopulationCount2011` | string | yes | directory | small-user only |
| 34 | `CensusHouseholdCount2001` | string | yes | directory | small-user only |
| 35 | `CensusPopulationCount2001` | string | yes | directory | small-user only |
| 36 | `CensusHouseholdCount1991` | string | yes | directory | small-user only |
| 37 | `CensusPopulationCount1991` | string | yes | directory | small-user only |
| 38 | `ScottishIndexOfMultipleDeprivation2020Rank` | string | no | directory |  |
| 39 | `LAU2025Level1Code` | string | no | directory |  |
| 40 | `ITL2025Level2Code` | string | no | directory |  |
| 41 | `ITL2025Level3Code` | string | no | directory |  |
| 42 | `Locality2020Code` | string | no | directory |  |
| 43 | `Locality2022Code` | string | no | directory |  |
| 44 | `Locality2001Code` | string | no | directory |  |
| 45 | `Locality1991Code` | string | no | directory |  |
| 46 | `Settlement2020Code` | string | no | directory |  |
| 47 | `Settlement2022Code` | string | no | directory |  |
| 48 | `Settlement2001Code` | string | no | directory |  |
| 49 | `CivilParish1930Code` | string | no | directory |  |
| 50 | `EnterpriseRegion2008Code` | string | no | directory |  |
| 51 | `IslandCode` | string | no | directory |  |
| 52 | `LocalGovernmentDistrict1995Code` | string | no | directory |  |
| 53 | `LocalGovernmentDistrict1991Code` | string | no | directory |  |
| 54 | `NationalPark2010Code` | string | no | directory |  |
| 55 | `RegistrationDistrict2007Code` | string | no | directory |  |
| 56 | `ROACommunityPlanningPartnership2006Code` | string | no | directory |  |
| 57 | `ROALocal2006Code` | string | no | directory |  |
| 58 | `StrategicDevelopmentPlanningArea2013Code` | string | no | directory |  |
| 59 | `TravelToWorkArea2011Code` | string | no | directory |  |
| 60 | `UrbanRural6Fold2022Code` | string | no | directory |  |
| 61 | `UrbanRural8Fold2022Code` | string | no | directory |  |
| 62 | `GridLinkIndicator` | string | no | directory |  |
| 63 | `GridLinkPositionalAccuracy` | string | no | directory |  |
| 64 | `NeverDigitised` | string | yes | directory | small-user only |
| 65 | `LinkedSmallUserPostcode` | string | yes | directory | large-user only |
| 66 | `pc_norm` | string | no | derived | primary key part 1: uppercased, spaces removed, NRS suffix kept |
| 67 | `pc_base` | string | no | derived | ordinary postcode: validated small-user split suffix removed; can be ambiguous |
| 68 | `spd_user_type` | string | no | derived | small_user or large_user |
| 69 | `spd_release` | string | no | derived | directory release this record came from |
| 70 | `introduced_on` | date32 | no | derived | primary key part 2 |
| 71 | `deleted_on` | date32 | yes | derived | null while current; validity is [introduced_on, deleted_on) |
| 72 | `is_current` | bool | no | derived | deleted_on is null |
| 73 | `phs_dz2001_hb` | string | no | phs | health board PHS assigned to the 2001 data zone when computing within-geography bands |
| 74 | `phs_dz2001_hscp` | string | no | phs | HSCP PHS assigned to the 2001 data zone when computing within-geography bands |
| 75 | `phs_dz2001_ca` | string | no | phs | council area PHS assigned to the 2001 data zone when computing within-geography bands |
| 76 | `phs_dz2011_hb` | string | no | phs | health board PHS assigned to the 2011 data zone when computing within-geography bands |
| 77 | `phs_dz2011_hscp` | string | no | phs | HSCP PHS assigned to the 2011 data zone when computing within-geography bands |
| 78 | `phs_dz2011_ca` | string | no | phs | council area PHS assigned to the 2011 data zone when computing within-geography bands |
| 79 | `simd2004_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 80 | `simd2004_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 81 | `simd2004_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 82 | `simd2004_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 83 | `simd2004_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 84 | `simd2004_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 85 | `simd2004_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 86 | `simd2004_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 87 | `simd2004_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 88 | `simd2004_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 89 | `simd2004_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 90 | `simd2004_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 91 | `simd2004_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 92 | `simd2004_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
| 93 | `simd2006_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 94 | `simd2006_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 95 | `simd2006_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 96 | `simd2006_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 97 | `simd2006_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 98 | `simd2006_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 99 | `simd2006_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 100 | `simd2006_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 101 | `simd2006_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 102 | `simd2006_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 103 | `simd2006_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 104 | `simd2006_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 105 | `simd2006_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 106 | `simd2006_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
| 107 | `simd2009v2_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 108 | `simd2009v2_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 109 | `simd2009v2_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 110 | `simd2009v2_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 111 | `simd2009v2_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 112 | `simd2009v2_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 113 | `simd2009v2_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 114 | `simd2009v2_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 115 | `simd2009v2_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 116 | `simd2009v2_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 117 | `simd2009v2_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 118 | `simd2009v2_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 119 | `simd2009v2_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 120 | `simd2009v2_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
| 121 | `simd2012_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 122 | `simd2012_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 123 | `simd2012_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 124 | `simd2012_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 125 | `simd2012_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 126 | `simd2012_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 127 | `simd2012_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 128 | `simd2012_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 129 | `simd2012_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 130 | `simd2012_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 131 | `simd2012_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 132 | `simd2012_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 133 | `simd2012_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 134 | `simd2012_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
| 135 | `simd2016_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 136 | `simd2016_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 137 | `simd2016_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 138 | `simd2016_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 139 | `simd2016_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 140 | `simd2016_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 141 | `simd2016_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 142 | `simd2016_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 143 | `simd2016_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 144 | `simd2016_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 145 | `simd2016_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 146 | `simd2016_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 147 | `simd2016_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 148 | `simd2016_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
| 149 | `simd2020v2_rank` | int16 | no | phs | 1 = most deprived; identical to the Scottish Government rank |
| 150 | `simd2020v2_pw_scotland_decile` | int8 | no | phs | PHS population-weighted decile within scotland; 1 = most deprived |
| 151 | `simd2020v2_pw_scotland_quintile` | int8 | no | phs | PHS population-weighted quintile within scotland; 1 = most deprived |
| 152 | `simd2020v2_pw_hb_decile` | int8 | no | phs | PHS population-weighted decile within hb; 1 = most deprived |
| 153 | `simd2020v2_pw_hb_quintile` | int8 | no | phs | PHS population-weighted quintile within hb; 1 = most deprived |
| 154 | `simd2020v2_pw_hscp_decile` | int8 | no | phs | PHS population-weighted decile within hscp; 1 = most deprived |
| 155 | `simd2020v2_pw_hscp_quintile` | int8 | no | phs | PHS population-weighted quintile within hscp; 1 = most deprived |
| 156 | `simd2020v2_pw_ca_decile` | int8 | no | phs | PHS population-weighted decile within ca; 1 = most deprived |
| 157 | `simd2020v2_pw_ca_quintile` | int8 | no | phs | PHS population-weighted quintile within ca; 1 = most deprived |
| 158 | `simd2020v2_most15pc` | int8 | no | phs | PHS population-weighted 15% most deprived flag, as published |
| 159 | `simd2020v2_least15pc` | int8 | no | phs | PHS population-weighted 15% least deprived flag, as published |
| 160 | `simd2020v2_uw_scotland_quintile` | int8 | no | govscot | Scottish Government unweighted quintile; 1 = most deprived |
| 161 | `simd2020v2_uw_scotland_decile` | int8 | no | govscot | Scottish Government unweighted decile; 1 = most deprived |
| 162 | `simd2020v2_uw_scotland_vigintile` | int8 | no | govscot | Scottish Government unweighted vigintile; 1 = most deprived |
