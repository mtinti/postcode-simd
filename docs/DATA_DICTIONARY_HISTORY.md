# Data dictionary: postcode_simd_history, schema `postcode_simd_wide_v5`

The **history table**: one row per Scottish Postcode Directory (SPD) record, both user types, current and deleted,
every life of every postcode, with all 6 SIMD editions attached. Data zones are the ones
containing the postcode's own grid reference. For one row per whole postcode see the main table,
[DATA_DICTIONARY.md](DATA_DICTIONARY.md). Generated from `simd_ingest/output_schema_history.yaml`; do not edit by hand.

Current build: 247,773 rows by 442 columns, history index release 2026_2,
allocation `postcode_grid_reference`, built 2026-10-03T11:29:41Z. Parquet SHA256 `70c226e71843c483bca8bcc326e24e1b133a039499603cc65568e5eabe9b2572`; rows-only fingerprint
`0f16a678a0723d8ce6a31f83ff6c9cc0335849ed30ca7cb2f2ea125571ea420a`. The file hash also covers the embedded provenance metadata,
so it changes when the decision log changes; compare fingerprints under the same pinned runtime.

## Key

Primary key: `pc_norm` with `introduced_on`. Unique across both user types. A postcode alone repeats
across its history, so use the date or explicitly select current records.

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

Data-zone vintages are not interchangeable; the join here
already uses the right vintage for each edition. The file carries SIMD only; the Carstairs index
the same guidance describes for pre-1996 data is not included.

## Things that will catch you out

- **Split postcodes.** NRS splits a postcode that straddles a boundary into A, B or C parts, each its
  own record with its own data zone. `pc_base` is the postcode as a person writes it. Filter current
  records on `pc_base` and you may get more than one row with different SIMD values. The lookups
  in `simd_ingest.lookup` resolve that to the A part by default, as NRS does, and say so; a report
  rule shows the ambiguity instead. Never average or vote.
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

Every build also writes `results/postcode_simd_history.csv.gz`, the form in which this table is shared.
It carries 438 of the 442 columns in the same order: `GridReferenceEasting`, `GridReferenceNorthing`, `Latitude`, `Longitude` are not exported.

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

| For a record whose `spd_user_type` is | these columns are structural nulls |
| --- | --- |
| `large_user` | `CensusHouseholdCount2022`, `CensusPopulationCount2022`, `CensusHouseholdCount2011`, `CensusPopulationCount2011`, `CensusHouseholdCount2001`, `CensusPopulationCount2001`, `CensusHouseholdCount1991`, `CensusPopulationCount1991`, `NeverDigitised` |
| `small_user` | `LinkedSmallUserPostcode` |

An empty cell in one of those columns for any other record is a source blank.

These text columns are never blank, so an empty cell in one is a null for every record: `urbanrural2003_2004_status`, `urbanrural2005_2006_status`, `urbanrural2007_2008_status`, `urbanrural2009_2010_status`, `urbanrural2011_2012_status`, `urbanrural2013_2014_status`, `urbanrural2016_status`, `urbanrural2020_status`, `urbanrural2022_status`, `simd2020v2_housing_domain_rank_source_status`.

An empty cell in a numeric column is always a null, never zero and never a blank. 18 numeric
columns can be empty: `urbanrural2003_2004_6fold`, `urbanrural2003_2004_8fold`, `urbanrural2005_2006_6fold`, `urbanrural2005_2006_8fold`, `urbanrural2007_2008_6fold`, `urbanrural2007_2008_8fold`, `urbanrural2009_2010_6fold`, `urbanrural2009_2010_8fold`, `urbanrural2011_2012_6fold`, `urbanrural2011_2012_8fold`, `urbanrural2013_2014_6fold`, `urbanrural2013_2014_8fold`, `urbanrural2016_6fold`, `urbanrural2016_8fold`, `urbanrural2020_6fold`, `urbanrural2020_8fold`, `urbanrural2022_6fold`, `urbanrural2022_8fold`.

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

Licences: phs: Open Government Licence v3.0, stated in the PHS open data package metadata; nrs: NRS terms; confirm before redistributing copies of the index; maps_gov_scot: Open Government Licence; the evidence for each file is under redistribution_evidence; statistics_gov_scot: Open Government Licence v3.0, stated on each dataset page; publisher the Scottish Government, contact simd@gov.scot

## Columns

442 columns: 65 from the directory, 7 derived,
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
| 163 | `urbanrural2003_2004_6fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2003-2004, 6-fold, placed from this record's own grid reference; null where urbanrural2003_2004_status says why |
| 164 | `urbanrural2003_2004_8fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2003-2004, 8-fold, placed from this record's own grid reference; null where urbanrural2003_2004_status says why |
| 165 | `urbanrural2003_2004_status` | string | yes | rurality | null where the 2003-2004 codes are present; otherwise outside_polygons, ambiguous_polygons or po_box |
| 166 | `urbanrural2005_2006_6fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2005-2006, 6-fold, placed from this record's own grid reference; null where urbanrural2005_2006_status says why |
| 167 | `urbanrural2005_2006_8fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2005-2006, 8-fold, placed from this record's own grid reference; null where urbanrural2005_2006_status says why |
| 168 | `urbanrural2005_2006_status` | string | yes | rurality | null where the 2005-2006 codes are present; otherwise outside_polygons, ambiguous_polygons or po_box |
| 169 | `urbanrural2007_2008_6fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2007-2008, 6-fold, placed from this record's own grid reference; null where urbanrural2007_2008_status says why |
| 170 | `urbanrural2007_2008_8fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2007-2008, 8-fold, placed from this record's own grid reference; null where urbanrural2007_2008_status says why |
| 171 | `urbanrural2007_2008_status` | string | yes | rurality | null where the 2007-2008 codes are present; otherwise outside_polygons, ambiguous_polygons or po_box |
| 172 | `urbanrural2009_2010_6fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2009-2010, 6-fold, placed from this record's own grid reference; null where urbanrural2009_2010_status says why |
| 173 | `urbanrural2009_2010_8fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2009-2010, 8-fold, placed from this record's own grid reference; null where urbanrural2009_2010_status says why |
| 174 | `urbanrural2009_2010_status` | string | yes | rurality | null where the 2009-2010 codes are present; otherwise outside_polygons, ambiguous_polygons or po_box |
| 175 | `urbanrural2011_2012_6fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2011-2012, 6-fold, placed from this record's own grid reference; null where urbanrural2011_2012_status says why |
| 176 | `urbanrural2011_2012_8fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2011-2012, 8-fold, placed from this record's own grid reference; null where urbanrural2011_2012_status says why |
| 177 | `urbanrural2011_2012_status` | string | yes | rurality | null where the 2011-2012 codes are present; otherwise outside_polygons, ambiguous_polygons or po_box |
| 178 | `urbanrural2013_2014_6fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2013-2014, 6-fold, placed from this record's own grid reference; null where urbanrural2013_2014_status says why |
| 179 | `urbanrural2013_2014_8fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2013-2014, 8-fold, placed from this record's own grid reference; null where urbanrural2013_2014_status says why |
| 180 | `urbanrural2013_2014_status` | string | yes | rurality | null where the 2013-2014 codes are present; otherwise outside_polygons, ambiguous_polygons or po_box |
| 181 | `urbanrural2016_6fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2016, 6-fold, placed from this record's own grid reference; null where urbanrural2016_status says why |
| 182 | `urbanrural2016_8fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2016, 8-fold, placed from this record's own grid reference; null where urbanrural2016_status says why |
| 183 | `urbanrural2016_status` | string | yes | rurality | null where the 2016 codes are present; otherwise outside_polygons, ambiguous_polygons or po_box |
| 184 | `urbanrural2020_6fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2020, 6-fold, placed from this record's own grid reference; null where urbanrural2020_status says why |
| 185 | `urbanrural2020_8fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2020, 8-fold, placed from this record's own grid reference; null where urbanrural2020_status says why |
| 186 | `urbanrural2020_status` | string | yes | rurality | null where the 2020 codes are present; otherwise outside_polygons, ambiguous_polygons or po_box |
| 187 | `urbanrural2022_6fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2022, 6-fold, placed from this record's own grid reference; null where urbanrural2022_status says why |
| 188 | `urbanrural2022_8fold` | int8 | yes | rurality | Scottish Government Urban Rural Classification 2022, 8-fold, placed from this record's own grid reference; null where urbanrural2022_status says why |
| 189 | `urbanrural2022_status` | string | yes | rurality | null where the 2022 codes are present; otherwise outside_polygons, ambiguous_polygons or po_box |
| 190 | `simd2004_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 191 | `simd2004_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 192 | `simd2004_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 193 | `simd2004_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 194 | `simd2004_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 195 | `simd2004_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2004 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 196 | `simd2006_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 197 | `simd2006_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 198 | `simd2006_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 199 | `simd2006_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 200 | `simd2006_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 201 | `simd2006_crime_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 crime domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 202 | `simd2006_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2006 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 203 | `simd2009v2_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 204 | `simd2009v2_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 205 | `simd2009v2_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 206 | `simd2009v2_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 207 | `simd2009v2_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 208 | `simd2009v2_crime_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 crime domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 209 | `simd2009v2_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2009v2 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 210 | `simd2012_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 211 | `simd2012_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 212 | `simd2012_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 213 | `simd2012_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 214 | `simd2012_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 215 | `simd2012_crime_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 crime domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 216 | `simd2012_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2012 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 217 | `simd2016_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 218 | `simd2016_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 219 | `simd2016_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 220 | `simd2016_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 221 | `simd2016_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 222 | `simd2016_crime_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 crime domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 223 | `simd2016_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2016 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 224 | `simd2020v2_income_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 income domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 225 | `simd2020v2_employment_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 employment domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 226 | `simd2020v2_health_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 health domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 227 | `simd2020v2_education_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 education domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 228 | `simd2020v2_access_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 access to services domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 229 | `simd2020v2_crime_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 crime domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 230 | `simd2020v2_housing_domain_rank` | rank | no | govscot | Scottish Government SIMD 2020v2 housing domain rank, unweighted, 1 = most deprived; copied exactly as published, may end in .5 |
| 231 | `simd2004_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 232 | `simd2004_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 233 | `simd2004_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 234 | `simd2004_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 235 | `simd2004_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 236 | `simd2004_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 237 | `simd2004_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 238 | `simd2004_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 239 | `simd2004_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 240 | `simd2004_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 241 | `simd2004_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 242 | `simd2004_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 243 | `simd2004_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 244 | `simd2004_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 245 | `simd2004_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 246 | `simd2004_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 247 | `simd2004_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 248 | `simd2004_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2004 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 249 | `simd2006_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 250 | `simd2006_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 251 | `simd2006_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 252 | `simd2006_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 253 | `simd2006_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 254 | `simd2006_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 255 | `simd2006_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 256 | `simd2006_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 257 | `simd2006_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 258 | `simd2006_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 259 | `simd2006_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 260 | `simd2006_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 261 | `simd2006_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 262 | `simd2006_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 263 | `simd2006_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 264 | `simd2006_crime_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 crime domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 265 | `simd2006_crime_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 crime domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 266 | `simd2006_crime_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 crime domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 267 | `simd2006_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 268 | `simd2006_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 269 | `simd2006_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2006 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 270 | `simd2009v2_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 271 | `simd2009v2_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 272 | `simd2009v2_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 273 | `simd2009v2_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 274 | `simd2009v2_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 275 | `simd2009v2_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 276 | `simd2009v2_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 277 | `simd2009v2_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 278 | `simd2009v2_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 279 | `simd2009v2_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 280 | `simd2009v2_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 281 | `simd2009v2_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 282 | `simd2009v2_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 283 | `simd2009v2_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 284 | `simd2009v2_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 285 | `simd2009v2_crime_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 crime domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 286 | `simd2009v2_crime_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 crime domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 287 | `simd2009v2_crime_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 crime domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 288 | `simd2009v2_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 289 | `simd2009v2_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 290 | `simd2009v2_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2009v2 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 291 | `simd2012_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 292 | `simd2012_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 293 | `simd2012_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 294 | `simd2012_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 295 | `simd2012_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 296 | `simd2012_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 297 | `simd2012_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 298 | `simd2012_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 299 | `simd2012_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 300 | `simd2012_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 301 | `simd2012_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 302 | `simd2012_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 303 | `simd2012_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 304 | `simd2012_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 305 | `simd2012_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 306 | `simd2012_crime_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 crime domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 307 | `simd2012_crime_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 crime domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 308 | `simd2012_crime_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 crime domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 309 | `simd2012_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 310 | `simd2012_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 311 | `simd2012_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2012 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 312 | `simd2016_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 313 | `simd2016_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 314 | `simd2016_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 315 | `simd2016_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 316 | `simd2016_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 317 | `simd2016_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 318 | `simd2016_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 319 | `simd2016_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 320 | `simd2016_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 321 | `simd2016_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 322 | `simd2016_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 323 | `simd2016_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 324 | `simd2016_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 325 | `simd2016_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 326 | `simd2016_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 327 | `simd2016_crime_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 crime domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 328 | `simd2016_crime_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 crime domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 329 | `simd2016_crime_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 crime domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 330 | `simd2016_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 331 | `simd2016_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 332 | `simd2016_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2016 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 333 | `simd2020v2_income_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 income domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 334 | `simd2020v2_income_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 income domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 335 | `simd2020v2_income_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 income domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 336 | `simd2020v2_employment_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 employment domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 337 | `simd2020v2_employment_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 employment domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 338 | `simd2020v2_employment_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 employment domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 339 | `simd2020v2_health_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 health domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 340 | `simd2020v2_health_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 health domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 341 | `simd2020v2_health_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 health domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 342 | `simd2020v2_education_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 education domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 343 | `simd2020v2_education_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 education domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 344 | `simd2020v2_education_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 education domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 345 | `simd2020v2_access_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 access domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 346 | `simd2020v2_access_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 access domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 347 | `simd2020v2_access_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 access domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 348 | `simd2020v2_crime_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 crime domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 349 | `simd2020v2_crime_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 crime domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 350 | `simd2020v2_crime_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 crime domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 351 | `simd2020v2_housing_domain_quintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 housing domain quintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 352 | `simd2020v2_housing_domain_decile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 housing domain decile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 353 | `simd2020v2_housing_domain_vigintile` | int8 | no | govscot_bands | Scottish Government SIMD 2020v2 housing domain vigintile, unweighted, 1 = most deprived; copied exactly as published on statistics.gov.scot, never derived; the publisher places some tied zones in adjacent bands |
| 354 | `simd2020v2_housing_domain_rank_source_status` | string | yes | govscot_bands | rank_sources_disagree where the Scottish Government's statistics.gov.scot dataset and its shapefile give this zone different housing ranks (the rank here is the shapefile's, equal to the SIMD 2020v2 ranks workbook, which the SIMD team confirmed on 2 October 2026 is the definitive version; the bands are the published ones, and for 626 of the 628 zones the same under either ranking); null otherwise |
| 355 | `simd2004_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 356 | `simd2004_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 357 | `simd2004_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 358 | `simd2004_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 359 | `simd2004_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 360 | `simd2004_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 361 | `simd2004_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 362 | `simd2004_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 363 | `simd2004_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 364 | `simd2004_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 365 | `simd2004_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2004 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 366 | `simd2004_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2004 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 367 | `simd2006_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 368 | `simd2006_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 369 | `simd2006_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 370 | `simd2006_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 371 | `simd2006_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 372 | `simd2006_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 373 | `simd2006_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 374 | `simd2006_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 375 | `simd2006_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 376 | `simd2006_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 377 | `simd2006_crime_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 crime domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 378 | `simd2006_crime_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 crime domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 379 | `simd2006_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2006 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 380 | `simd2006_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2006 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 381 | `simd2009v2_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 382 | `simd2009v2_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 383 | `simd2009v2_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 384 | `simd2009v2_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 385 | `simd2009v2_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 386 | `simd2009v2_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 387 | `simd2009v2_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 388 | `simd2009v2_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 389 | `simd2009v2_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 390 | `simd2009v2_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 391 | `simd2009v2_crime_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 crime domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 392 | `simd2009v2_crime_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 crime domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 393 | `simd2009v2_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2009v2 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 394 | `simd2009v2_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2009v2 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 395 | `simd2012_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 396 | `simd2012_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 397 | `simd2012_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 398 | `simd2012_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 399 | `simd2012_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 400 | `simd2012_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 401 | `simd2012_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 402 | `simd2012_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 403 | `simd2012_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 404 | `simd2012_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 405 | `simd2012_crime_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 crime domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 406 | `simd2012_crime_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 crime domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 407 | `simd2012_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2012 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 408 | `simd2012_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2012 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 409 | `simd2016_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 410 | `simd2016_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 411 | `simd2016_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 412 | `simd2016_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 413 | `simd2016_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 414 | `simd2016_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 415 | `simd2016_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 416 | `simd2016_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 417 | `simd2016_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 418 | `simd2016_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 419 | `simd2016_crime_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 crime domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 420 | `simd2016_crime_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 crime domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 421 | `simd2016_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2016 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 422 | `simd2016_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2016 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 423 | `simd2020v2_income_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 income domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 424 | `simd2020v2_income_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 income domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 425 | `simd2020v2_employment_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 employment domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 426 | `simd2020v2_employment_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 employment domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 427 | `simd2020v2_health_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 health domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 428 | `simd2020v2_health_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 health domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 429 | `simd2020v2_education_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 education domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 430 | `simd2020v2_education_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 education domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 431 | `simd2020v2_access_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 access domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 432 | `simd2020v2_access_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 access domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 433 | `simd2020v2_crime_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 crime domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 434 | `simd2020v2_crime_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 crime domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 435 | `simd2020v2_housing_domain_pw_scotland_quintile` | int8 | no | computed | SIMD 2020v2 housing domain, Scotland quintile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 436 | `simd2020v2_housing_domain_pw_scotland_decile` | int8 | no | computed | SIMD 2020v2 housing domain, Scotland decile, 1 = most deprived. Computed population-weighted band, using a midpoint rule validated against PHS's published overall bands; equal ranks grouped together; not published by PHS or the Government |
| 437 | `simd2004_population` | int16 | no | govscot | Population of the data zone in the SIMD 2004 shapefile (2001 Census), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
| 438 | `simd2006_population` | int16 | no | govscot | Population of the data zone in the SIMD 2006 shapefile (NRS small-area estimates for 2004), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
| 439 | `simd2009v2_population` | int16 | no | govscot | Population of the data zone in the SIMD 2009v2 shapefile (NRS small-area estimates for 2007), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
| 440 | `simd2012_population` | int16 | no | govscot | Population of the data zone in the SIMD 2012 shapefile (NRS small-area estimates for 2010), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
| 441 | `simd2016_population` | int16 | no | govscot | Population of the data zone in the SIMD 2016 shapefile (NRS small-area estimates for 2014), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
| 442 | `simd2020v2_population` | int16 | no | govscot | Population of the data zone in the SIMD 2020v2 shapefile (NRS small-area estimates for 2017), the weight behind the computed bands. The data zone's figure, repeated on every postcode in the zone; never sum it or weight by it across rows |
