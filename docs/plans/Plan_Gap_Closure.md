# SIMD implementation plan: gap closure from the downloaded sources

Source-evidence companion to [the current Dagster implementation plan](SIMD_Dagster_Implementation_Plan.md), originally prepared for `SIMD_Full_Implementation_Plan.md`. Prepared 9 September 2026 and independently reconciled on 10 September 2026 from the files in `manual_data/`.

The review-revised Dagster plan now controls implementation: offline-first, one combined
156-column table, six separately approved steps. References below to Snakemake or the
original plan describe earlier delivery proposals; they do not override that scope.
Source findings, pinned checks and the split-postcode consensus policy remain in force.

This document records source evidence and remaining limitations. References below to numbered sections of the original plan retain their historical meaning and do not reinstate its wider delivery requirements. Source access, historical bands and independent rank comparisons are resolved; automated downloading is unimplemented and deferred from the Dagster offline version. The independent audit corrected the large-user schema and link counts, split-postcode interpretation, interval coverage and the unsupported Shetland explanation. Run `python simd_ingest/acceptance.py` to reproduce the source checks, or add `--json` for structured evidence. Authoritative source identities and method selection are in `simd_ingest/sources.yaml`; reviewed expectations are in `simd_ingest/acceptance_baselines.yaml`.

## 1. What each gap was, and what closes it

| Plan gap | Status | Evidence source |
| --- | --- | --- |
| Access to postcode files and guides, release identity and source contract | **Resolved with corrections below** | `manual_data/SPD/spd_postcodeindex_cut_26_2_csv/` |
| Historical 2001-geography band lookup | **Resolved** | data.gov.scot historical SIMD 2004-2012 extract |
| Independent comparison of all six PHS overall ranks | **Resolved: all six identical** | data.gov.scot historical extracts and the SIMD 2020v2 ranks workbook |
| Population-weighted PHS bands assumed unverifiable (plan section 5) | **Closed for 2020v2** | `SIMD+2020v2+-+ranks.xlsx` population columns |
| Postcode record, live and deleted counts | **Resolved** | SPD 2026/2 news bulletin |
| Rank-to-band workbook access and hash | **Resolved on 10 September 2026** | Downloaded workbook; all four bands match the 2011-vintage rule |
| HIC SQL Server access | Deferred from the Snakemake first delivery | Not established by the downloaded data |

## 2. Correction: the band formula differs by data-zone vintage

The original plan used one integer formula for every edition:

```python
band = (rank * k + n - 1) // n      # ceil(rank * k / n)
```

That formula reproduces the published 2011-data-zone bands exactly, as the plan states. It does **not** reproduce the published 2001-data-zone bands. Checked against the official published deciles, quintiles and vigintiles for 2004, 2006, 2009 and 2012:

| Geography vintage | n | Quintile errors | Decile errors | Vigintile errors |
| --- | ---: | ---: | ---: | ---: |
| 2001 (each of 2004, 2006, 2009, 2012) | 6,505 | 0 | 5 | 10 |
| 2011 (2016) | 6,976 | 0 | 0 | 0 |

The 2001 publications place the larger decile first. Published decile sizes run 651, 650, 651, 650 and so on; the original formula produces 650, 651, 650, 651. A half-up cut point, `cut(j) = round(j * n / k)` rounding halves up, reproduces the published overall SIMD bands exactly. Its integer expression is:

```python
band = (k * (2 * rank - 1) + 2 * n - 1) // (2 * n)   # 2001 data zones
```

This reproduces all three published band series for all four 2001-geography editions with **zero mismatches**. It fails on 2011 geography, where the `ceil` rule is correct. The reconciled plan and executable acceptance command select the rule by geography vintage through `rank_band_methods` in `simd_ingest/sources.yaml`.

Practical consequences:

- The configured methods are `halfup_cut_2001_v1` and `integer_ceil_rank_fraction_v1` for vintages 2001 and 2011 respectively. Unknown vintages fail; no global fallback is permitted.
- All available published bands are independently reconciled. The 2020v2 bands are obtained from the published 2011-vintage rank lookup, joined to its verified ranks.
- Percentile is still calculated-only for 2001 geography. If exposed, use the configured half-up rule as an explicit project convention, labelled `calculated_unverified`. No published 2001 percentile is present in this source set, so the convention is not independently established as a government method. The Snakemake first-delivery table leaves its published-percentile field null and defers calculated-percentile columns.

## 3. Verified divergence baselines

The original plan's decile mismatch counts for the 2001-geography editions used the wrong vintage rule. The corrected counts and full fingerprints in the current plan were independently reproduced on 10 September 2026 against published government bands:

| Edition | Superseded ceil comparison | Verified decile mismatches | Verified decile fingerprint (first 16 hex) |
| --- | ---: | ---: | --- |
| 2004 | 172 | **173** | `bae0a5bcaa7872b5` |
| 2006 | 281 | **276** | `8113af887dc16b5e` |
| 2009v2 | 473 | **468** | `ee002c41013c0578` |
| 2012 | 594 | **589** | `921e7a6dcf688586` |
| 2016 | 395 | 395 (unchanged) | `c59dab4d58954187` |
| 2020v2 | 481 | 481 (unchanged) | `b807713f26b511a5` |

All quintile counts and fingerprints in the plan are confirmed unchanged, because the quintile cut points coincide for both rules at n = 6,505. The downloaded rank-to-band workbook supplies the published 2020v2 comparison by rank. All 12 full fingerprints match the plan; maximum absolute difference remains 1 everywhere.

Fingerprints follow the plan's stated encoding rule, applied to the canonical PHS country band against the published government band rather than against a calculated band.

## 4. Rank direction is now independently confirmed

The original direction evidence used within-resource inferences. Independent comparison now establishes that the overall SIMD rank in each PHS file is identical, row for row, to the official government rank:

| Edition | Data zones | PHS rank identical to official rank |
| --- | ---: | ---: |
| 2004 | 6,505 | 6,505 / 6,505 |
| 2006 | 6,505 | 6,505 / 6,505 |
| 2009v2 | 6,505 | 6,505 / 6,505 |
| 2012 | 6,505 | 6,505 / 6,505 |
| 2016 | 6,976 | 6,976 / 6,976 |
| 2020v2 | 6,976 | 6,976 / 6,976 |

Rank 1 is the most deprived zone in all six editions, confirming the plan's setting and confirming that the PHS documentation sentence about 2004 and 2006 is wrong for rank. The band direction correction is confirmed too. At rank 1 the 2004 PHS country decile is 10 while the official decile is 1, and at rank 6,505 the PHS decile is 1 against an official 10. The plan's `11 - published_decile` and `6 - published_quintile` transforms are therefore correct.

The current plan records `independent_original_government_rank_comparison: performed_identical` for all six editions. Section 8 identifies the comparison sources and hashes.

## 5. PHS population-weighted reconstruction: exact national bands, local exceptions

The 2020v2 ranks workbook carries `Total_population` per data zone, identified in its notes as NRS 2017 small-area population estimates. With zones ordered by overall rank ascending, the published PHS country bands are reproduced exactly by a population-midpoint rule:

```python
band = min(k, ceil((cumulative_population - zone_population / 2) * k / total_population))
```

| PHS band | Mismatches against the reconstruction |
| --- | ---: |
| Country decile | 0 / 6,976 |
| Country quintile | 0 / 6,976 |
| Health board decile and quintile | 2 / 6,976 |
| HSCP decile and quintile | 2 / 6,976 |
| Council area decile and quintile | 2 / 6,976 |

The Scotland-level reconstruction is exact. The two sub-geography exceptions are both in Shetland Islands, which has 30 data zones. Their cause remains unexplained: midpoint percentages are approximately 20.052% and 40.130%, not exact boundary ties. Do not modify published PHS values to fit the reconstruction. Pin these exceptions separately for each HB, HSCP and CA measure:

| Data zone | Published / reconstructed decile | Published / reconstructed quintile |
| --- | --- | --- |
| S01012409 | 2 / 3 | 1 / 2 |
| S01012387 | 4 / 5 | 2 / 3 |

This is two differing zones per measure and 12 differing cells across the six sub-geography measures. Both 15% flags reproduce exactly using the country population midpoint at thresholds of 15% and 85%. The workbook's population total is 5,424,800.

This upgrades the plan's PHS band check from a monotonicity assertion to an exact reconciliation for 2020v2. It also confirms the plan's warning that the 15% flag is not 15% of zones: the most-deprived flag covers 15.41% of zones and 14.993% of population.

Three data zones have a total population of zero: S01010206, S01010226 and S01010227. Preserve them in the rank universe and population reconstruction.

**Operational decision, 10 September 2026 (implementation pending):** retain population
reconstruction comparisons as non-blocking diagnostics, including new or changed
differences in any edition. The published PHS values remain the output authority, with
only the documented 2004/2006 band reversals. The blocking guarantee is that the reopened
saved table preserves the accepted source values and satisfies the integrity/join contract,
not that our reconstruction agrees with PHS. Keep the exact evidence above and the
Shetland cause unresolved. See the
[Dagster validation decision](SIMD_Dagster_Implementation_Plan.md#validation-decision-source-fidelity-blocks-population-reconstruction-does-not)
for report contents and the distinction between source failures and diagnostic warnings.

## 6. The postcode source contract, established from the actual files

Release 2026/2, published August 2026, built on the July 2026 Royal Mail Postcode Address File. The downloaded set is the **cut** version, which excludes three Royal Mail fields present in the full version: delivery point count, non-residential delivery point count and household count. Record that omission in the source register; the plan's "all original fields" wording should say all fields of the cut version.

**Record counts reconcile exactly against the published bulletin.**

| File | Records | Live | Deleted |
| --- | ---: | ---: | ---: |
| Small user | 196,769 | 157,282 | 39,487 |
| Large user | 51,004 | 4,767 | 46,237 |
| Total | 247,773 | 162,049 | 85,724 |

All file and combined totals match the bulletin and are pinned acceptance values. The published figure of 156,125 live digitised small-user postcodes also matches: 1,157 of the live small-user records carry the never-digitised flag.

**The natural composite primary key is settled for the pinned release.** A targeted follow-up check on 10 September 2026 found that normalised postcode and parsed introduction date are already unique across all 247,773 records in the combined files, with zero null key components. Both source hashes still match their pins. The Snakemake table therefore uses `(pc_norm, introduced_on)` as its primary key, with no hash-based record ID. Release, deletion date and user type remain attributes. Each new accepted release replaces the entire current file/imported table rather than being appended, so release is not a key component. Uniqueness must be checked again for each future release rather than assumed to be an NRS guarantee.

The previously checked larger combination of postcode and both dates is also unique, but deletion date is unnecessary for identity in these files and is null for live records. The existing acceptance command still checks that larger combination; enforcement of the shorter key is new implementation work in the Snakemake plan. There are no fully identical duplicate rows. Postcode alone is not unique: 7,006 small-user and 4,562 large-user postcodes have more than one record, in groups of up to seven. Never deduplicate on postcode alone.

**The current lookup is unique by complete NRS key.** The live union contains 162,049 records for 162,049 complete NRS postcode keys, with suffixes preserved; no key is live in both files. Ordinary postcodes have different semantics. Removing validated small-user suffixes produces 161,822 ordinary-postcode search keys; 226 have multiple live candidates (225 pairs and one triple), and 203 have different 2011 data zones and 2020v2 ranks. Searches by ordinary postcode must return all candidates with `selection_status: ambiguous`; a unique complete-NRS-key table does not prove a unique ordinary-postcode mapping. For example, AB12 3GQA has rank 5484 and AB12 3GQB has rank 5522. Keep both for an AB12 3GQ search.

**Ntile-only release decision, recorded 10 September 2026.** Record-level ambiguity does not necessarily make the requested band ambiguous. The [ntile-consensus policy](SIMD_Snakemake_Implementation_Plan.md#split-postcode-consensus-for-ntile-only-releases) permits a common non-null band when all relevant, date-valid split candidates agree and coverage is complete. Conflicting bands, missing values or unestablished coverage yield a null band; a left join retains the patient row without duplication. Resolve each edition/field independently, keep diagnostic statuses internal, and never infer a consensus from an absent English border part. This resolver is not yet implemented, and ntile-level consensus/conflict counts have not yet been measured. The 203 rank-divergent bases above are not a count of conflicting ntiles.

**Dates are `D/M/YYYY 00:00:00`.** Day values run to 31 and month values to 12, so the order is unambiguous. The time component is always midnight and carries no information. Introduction dates run from 1973 to 2026, deletion dates from 1975 to 2026. Deletion is null for live records, so no date needs fabricating.

**Date boundaries and same-day records need explicit handling.** Across both files there are 818 touching record pairs on the same complete NRS postcode key: 479 small-to-small, 12 large-to-large, 72 small-to-large and 255 large-to-small. Eight are the 18 February 2026 split corrections named in the bulletin: AB31 5AS, AB54 7NS, FK14 7JX and KA6 6EY, each in an A and a B part. There are no strict overlaps between positive-duration intervals and no deletion-before-introduction records.

Use half-open date filtering `[introduction, deletion)`, retaining the original date values and null deletion dates. Preserve and flag the 28 same-day introduction/deletion records (27 small-user and one large-user); they remain in the canonical index and bridge but have no matching as-of date under this convention. Do not fabricate duration or fail ingestion on equality. Pin all these counts and the eight named February pairs as acceptance fixtures.

**Normalised postcodes reach exactly eight characters.** Split postcodes carry an NRS suffix of A, B or C appended to the unit, giving 594 small-user records of normalised length 8, all flagged as split. The plan's `VARCHAR(8)` is correct and has zero headroom. Lengths otherwise run 5 to 7. No postcode contains a character outside A-Z, 0-9 and space, and none contains whitespace other than the single separating space, so the plan's malformed-value branch has no cases in this release.

Split indicator is Y on 1,263 small-user and 28 large-user records. **Every small-user split record has an NRS suffix**, including 667 seven-character and two six-character normalised keys. Length alone does not identify a suffix. In the large-user dictionary the flag describes the linked small-user postcode; all 28 flagged large-user postcodes are themselves unsuffixed. Define `pc_base` by validated small-user suffix parsing, never by trimming all flagged or eight-character keys.

**Large-user links have two sentinel spellings.** `LinkedSmallUserPostcode` is never null: 31,725 records contain `NO LINKP`, documented as PO boxes, and six contain the undocumented `NO LINK` sentinel. Excluding both leaves **19,273 real links, all resolving to a small-user postcode key**. The previously reported six unresolved links were the six `NO LINK` sentinels, not real postcode references. Preserve each source spelling and classify it separately. Postcode-key existence does not establish a unique historical record-level link.

**Source schemas are exact.** SmallUser.csv has 64 columns on all 196,769 records. LargeUser.csv has **56**, not 55, on all 51,004 records. Both files contain ASCII bytes and only one separating ASCII space in each postcode value. The fixed acceptance baseline retains the complete ordered headers, including all source fields.

## 7. Join coverage is complete, and confirmed by a third source

Both files carry `DataZone2001Code`, `DataZone2011Code` and `DataZone2022Code`, all fully populated on every record. That satisfies the plan's requirement that the selected source supply both 2001 and 2011 mappings for all six editions, with 2022 retained as the plan asks.

Coverage is total in both directions:

| Check | Result |
| --- | --- |
| Distinct 2001 data zones in the directory | 6,505, all present in the PHS 2004-2012 universe |
| Distinct 2011 data zones in the directory | 6,976, all present in the PHS 2016 and 2020v2 universe |
| PHS data zones with no postcode | 0 for both vintages |
| Bridge cardinality, 247,773 records by six editions | 1,486,638 rows, all `matched` |

The four 2001-geography editions share one identical data-zone universe, and the two 2011-geography editions share another. The `missing_datazone` and `unknown_datazone` branches should still be implemented, but for this release they carry no rows, so the acceptance test asserts zero.

An independent cross-check comes free: the directory's own SIMD 2020 rank column agrees with the PHS 2020v2 rank, resolved through `DataZone2011Code`, on all 247,773 records. That validates the join contract against a third party rather than against itself.

## 8. Source evidence register

```yaml
inspected_on: 2026-09-09
govscot_historical_bands:
  - id: govscot_hist_2004_2012
    publication: https://data.gov.scot/dataset/scottish_index_of_multiple_deprivation__historical____2004_2012
    resource_id: "92eb1022-dd78-48a7-8ea6-08283b6c9adf"
    file: "92eb1022-dd78-48a7-8ea6-08283b6c9adf.csv"
    sha256: "99dd8f8adaf5a35bb933f98bbe27867347413fdc0e60c74c8302700c2d17bc30"
    rows: 806620
    geography_type: "2001 Data Zones"
    date_codes: ["2004", "2006", "2009", "2012"]
    measurements: [Rank, Quintile, Decile, Vigintile]
    domains_present: 8   # 7 for 2004; Crime absent that year
    overall_domain_label: "SIMD"
    rank_universe: 6505
    verified_band_rule: "(k * (2 * rank - 1) + 2 * n - 1) // (2 * n)"
    verified_band_rule_mismatches: 0   # k = 5, 10, 20; all four editions
    plan_ceil_rule_mismatches: {quintile: 0, decile: 5, vigintile: 10}   # per edition
    percentile_published: false
  - id: govscot_hist_2016
    publication: https://data.gov.scot/dataset/scottish_index_of_multiple_deprivation__historical____2016
    resource_id: "36465db2-8378-40e9-9bf8-fd016b0ee821"
    file: "36465db2-8378-40e9-9bf8-fd016b0ee821.csv"
    sha256: "760636a8ff03b85bb8c4d6d589f43b52a8e15866acaab9123c17cd9486f44151"
    rows: 223232
    geography_type: "2011 Data Zones"
    date_codes: ["2016"]
    rank_universe: 6976
    verified_band_rule: "(rank * k + n - 1) // n"
    verified_band_rule_mismatches: 0
    note: "Domain sub-indices contain tied half-ranks; the overall SIMD domain does not."
govscot_2020v2_ranks:
  publication: https://www.gov.scot/publications/scottish-index-of-multiple-deprivation-2020v2-ranks/
  file: "SIMD+2020v2+-+ranks.xlsx"
  sha256: "9904aa957a8177853564415e848e08553c17491d1578ff631a5074cacc9fb296"
  sheet: "SIMD 2020v2 ranks"
  rows: 6976
  columns: [Data_Zone, Intermediate_Zone, Council_area, Total_population,
            Working_age_population, SIMD2020v2_Rank, "7 domain ranks"]
  phs_rank_agreement: 6976
  population_band_rule: "min(k, ceil((cum_pop - zone_pop / 2) * k / total_pop))"
  population_band_mismatches: {country: 0, hb: 2, hscp: 2, ca: 2}
  fifteen_pc_flag_rule: "population midpoint within 15% of total population"
  fifteen_pc_flag_mismatches: 0
  zero_population_zones: 3
postcode_index:
  release: "2026_2"
  published: 2026-08
  paf_basis: "July 2026"
  edition: cut          # full version adds delivery point and household counts
  documentation:
    - {file: "spd-indexdatadictionary-2026-2.docx",
       sha256: "b543a10df0155caf3bc642c30371ccf848657ef52fb25922afcc0f938fc4214a"}
    - {file: "spd-newsbulletin-2026-2.docx",
       sha256: "5e050523a4319267e81c6ef7a71961f2e2f988953e6ff9923c8590c94c8dfac5"}
  small_user:
    file: "SmallUser.csv"
    sha256: "fc82f1091ac160b4d7c4a8f923466cbb1c8292f4fe30d15c7252446a86f14d6b"
    columns: 64
    rows: 196769
    live: 157282
    deleted: 39487
  large_user:
    file: "LargeUser.csv"
    sha256: "dcb060cbce01b3a6a133aad61d0453d250bc2d8fa0890b5f6dab3e82553a0f87"
    columns: 56
    rows: 51004
    live: 4767
    deleted: 46237
  published_totals: {all: 247773, live: 162049, deleted: 85724, live_digitised_small_user: 156125}
  record_key: [pc_norm, introduced_on]
  release_loading: full_snapshot_replacement
  record_key_unique_across_both_files: true
  record_key_null_components: 0
  record_key_basis: targeted_check_2026_09_10
  record_key_gate_status: shorter_key_check_to_be_added_to_acceptance
  complete_nrs_key: pc_norm
  ordinary_postcode_search_key: pc_base
  live_ordinary_postcodes: 161822
  ordinary_postcodes_with_multiple_candidates: 226
  ordinary_postcodes_with_differing_2011_zones: 203
  date_format: "D/M/YYYY 00:00:00"
  date_precision: day
  interval_model: half_open
  touching_pairs: 818
  touching_transitions: {small_to_small: 479, large_to_large: 12, small_to_large: 72, large_to_small: 255}
  same_day_records: {small_user: 27, large_user: 1}
  same_day_policy: preserve_flag_no_asof_match
  normalised_postcode_max_length: 8
  split_suffixes: [A, B, C]
  link_sentinels: ["NO LINKP", "NO LINK"]
  link_sentinel_counts: {"NO LINKP": 31725, "NO LINK": 6}
  real_links: 19273
  unresolved_real_links: 0
  datazone_vintages: [2001, 2011, 2022]
  datazone_coverage: complete_both_directions
  bridge_rows: 1486638
  bridge_unmatched: 0
```

## 9. Reconciliation status

| Finding | Status in the current contract |
| --- | --- |
| Global band formula and old divergence policy | Corrected; vintage-specific methods configured once, all 12 fingerprints retained |
| Large-user schema and sentinel arithmetic | Corrected to 56 columns, 19,273 real links and zero unresolved real postcode keys |
| Split suffixes and ordinary-postcode ambiguity | Corrected; complete NRS key and ordinary search key distinguished; all candidates retained |
| Date boundary and zero-duration coverage | Expanded to all 818 touching pairs and 28 retained same-day records |
| Shetland cause asserted as a boundary tie | Removed; exact differing values pinned, cause unresolved |
| Missing source files and postcode access critical path | Resolved; all 14 downloaded data/guide files are hash-pinned |
| Reproducible source acceptance | `python simd_ingest/acceptance.py`; JSON evidence with `--json`, nonzero exit on failure |

Source acceptance proves the contracts against the downloaded inputs. It does not prove automated downloading, saved-table readback or safe completion/recovery; those remain requirements of the Snakemake plan. A database target, multi-product publication and a deployed ordinary-postcode search endpoint are deferred, not prerequisites for this first delivery. The `bridge_rows` baseline above describes 1,486,638 logical postcode–edition matches; the combined wide table itself has 247,773 rows.

## 10. What is still genuinely open

- **Download automation and saved-output validation.** Source URLs/archive mappings need completing, and the Snakemake workflow, combined output and readback gate remain to be implemented.
- **HIC SQL Server access.** Unchanged; nothing in the download bears on it. Deferred from the first Snakemake delivery.
- **Percentile for 2001 geography.** No published 2001-geography percentile exists in these files. The new table leaves published percentile null; any future calculated column must retain its unverified-method label.
- **Shetland sub-geography reconstruction cause.** The two zones' published values are preserved as exact exceptions; no explanation is established by these files.
- **Redistribution terms for the postcode files.** The bulletin restricts delivery point counts and postcode boundaries, but the licence for the cut index itself needs confirming before the repository ships copies.

The 2020v2 band source is resolved: the government rank-to-band workbook was downloaded on 10 September 2026 and matches the pinned hash. Its quintile/decile/vigintile table is identical to the one reduced from the 2016 extract, and its percentile also matches the 2011-vintage formula. A separate edition-specific band file is not a delivery prerequisite.
