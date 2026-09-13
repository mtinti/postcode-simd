# Legacy SPD linked-small-user SQL

These examples preserve the earlier, explicitly chosen SPD linkage policy. They are **not
the default** and do not read SSPL. For postcode + analysis year and both publishers, use
the [default SSPL guide](../../LINKAGE_BY_ERA.md).

Import `results/postcode_simd_history.parquet` as `postcode_simd_history`, with primary key
`(pc_norm, introduced_on)`. Run this folder's `create_latest_postcode_lookup.sql` to create
`simd_postcode_latest`, then choose:

- `link_latest.sql`: `events(id, postcode)`, one chosen PHS quintile edition (2020v2 by default).
- `link_by_era.sql`: `events(id, postcode, event_date)`, edition selected by PHS Table 4.

The date must be a real date/datetime, not text. On SQL Server, `timestamp` is not a date
type. Execute CREATE VIEW in its own batch. Tests use DuckDB; SQL Server remains unverified.

## Retained policy

Select the newest life per full NRS key across both user types. Prefer live, whole/A,
then newest introduction per ordinary postcode. Missing A and equal-priority ties get no
SIMD. Large users follow the exact named small-user key, including A/B/C. A latest deleted
small-user target can supply geography, but a latest large-user target cannot. No chains,
older-life fallback, own-large-user fallback, or mixing of postcode products is allowed.

Keep every input event. Return original and SIMD-source keys, current flags, product
provenance and status. Missing/blank/NO LINKP/NO LINK links receive `unlinked_large_user`;
unavailable or wrong-role targets receive `linked_small_user_not_found`. Missing A and ties
receive `split_a_missing` and `ambiguous_postcode`. These exclusions return null SIMD.
An accepted ordinary/A/linked record reports `matched`, `a_part` or `linked_small_user`;
a missing selected value reports `missing_simd`. Null/blank input is `missing_postcode`,
an absent ordinary key is `not_found`. Missing dates and pre-1996 events have `missing_date`
and `no_edition`, taking precedence over postcode problems.

Both queries use the latest postcode, **not** date-valid postcode history. PHS v3.5 sections
3.1–3.2 inform weighting and edition selection. The exact representative selection,
deleted-record retention and link-following choices are project policies; PHS-equivalence
has not been established. See the [PHS guidance](../../../manual_data/2023-12-phs-deprivation-guidance-v35.pdf)
and [postcode documentation](https://publichealthscotland.scot/resources-and-tools/health-intelligence-and-data-management/geography-population-and-deprivation-support/geography/postcode-file/).

Do not run these queries against the new `simd_postcode_by_edition` view. They intentionally
keep their old quintile-only interface. The shared SPD comparison tests still use their
representative selection as a regression check.
