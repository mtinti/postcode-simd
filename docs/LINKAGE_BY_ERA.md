# Default SQL lookup: postcode and analysis year

The default takes a postcode and the year of the health data. It returns **both PHS
population-weighted and Scottish Government unweighted measures for the selected SIMD
edition**, using the postcode's own SSPL geography. It does not decide which measures to
publish or whether an address is suitable for a residential analysis.

## Run it

1. Import `results/postcode_simd.parquet` as `postcode_simd`, preserving its natural primary
   key `pc_norm`, column names and values. Use date types for `introduced_on`/`deleted_on`
   and bit/boolean for `is_current`. Postcode keys must not be truncated or reformatted.
2. Run [create_latest_postcode_lookup.sql](sql/create_latest_postcode_lookup.sql) once.
   It creates `simd_postcode_by_edition`: six explicitly named edition blocks, with one
   row per `(pc_norm, simd_edition)`. This is a view, not another imported table.
3. Open [link_by_era.sql](sql/link_by_era.sql), edit the postcode and integer analysis year
   in its first SELECT, and run it. The supplied example is `AB24 2TY`, year `2020`.

For SQL Server, execute the setup's CREATE VIEW in its own batch. The query's input SELECT
can instead use your parameters, `SELECT 1 AS id, @postcode AS postcode,
@analysis_year AS analysis_year`; declare/bind postcode as text and analysis year as an
integer. SQL Server's `timestamp` type is **not** a date type. Agree postcode collation with
your database team, including cohort/temp-table joins. See [Microsoft CREATE VIEW](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-view-transact-sql).

The scripts execute unchanged in DuckDB. SQL Server runtime behaviour is not yet verified.
A postcode refresh is visible through the view without choosing a new SIMD edition.
If the imported schema changes, review/recreate the view and its column mappings.

For a cohort, replace just the first SELECT with:

```sql
SELECT id, postcode, analysis_year FROM your_cohort
```

Use an event/row identifier, not necessarily a patient identifier. Repeated/null IDs and
duplicate input rows are retained. Output order is unspecified; add ORDER BY if needed.
Validate year text before calling the query; do not silently coerce invalid input to a year.

To run the single-postcode example locally:

```python
from pathlib import Path
import duckdb

sql = Path("docs/sql")
with duckdb.connect() as con:
    con.execute("CREATE VIEW postcode_simd AS SELECT * FROM 'results/postcode_simd.parquet'")
    con.execute((sql / "create_latest_postcode_lookup.sql").read_text())
    result = con.execute((sql / "link_by_era.sql").read_text()).df()
```

## What each step means

| Step | Why it is done | Basis |
| --- | --- | --- |
| Normalise a separate join key | Match case/spacing differences while retaining the input | Project key convention: uppercase, remove ASCII spaces only |
| Map analysis year to SIMD | Select an edition suitable for the year of health data | PHS v3.5 Table 4, printed p.17 |
| Join directly to SSPL | Use the latest whole postcode and its published allocation | NRS SSPL information note |
| Select stored edition columns | Keep the correct data-zone vintage; do not recompute values | PHS Table 4 and sections 3.1.1–3.1.2 |
| Return both publishers with distinct names | Make later analytical choices explicit; never mix weighting methods | PHS sections 3.1 and 3.4 |
| Flag address concerns separately | A matched geography is not proof of a valid residential address | PHS Appendix A, printed pp.28–30; warning-only behaviour is project policy |

References: [NRS SSPL information note](https://www.nrscotland.gov.uk/publications/geography-scottish-statistics-postcode-lookup-information-note/)
and the downloaded [PHS deprivation guidance v3.5](../manual_data/2023-12-phs-deprivation-guidance-v35.pdf).

SSPL already selected the latest postcode life and made ordinary split postcodes whole
using A. The SQL **does not** rank postcode lives, follow `LinkedSmallUserPostcode`, create
A/B/C aliases, or fall back to SPD. The link and split indicator are returned as context only.

The analysis year selects **SIMD, not postcode history**. A retained deleted postcode can
match, and a postcode introduced after the analysis year can match its latest record.
This is not evidence that the postcode existed in that year. Use SPD history and the
[separate Python date-valid policy](EXAMPLES.md) for that question. For patient analyses,
supply the appropriate recorded address; this query cannot reconstruct address history.

## Edition mapping

| Health-data years | SIMD edition | Data-zone vintage |
| --- | --- | --- |
| 1996–2003 | 2004 | 2001 |
| 2004–2006 | 2006 | 2001 |
| 2007–2009 | 2009v2 | 2001 |
| 2010–2013 | 2012 | 2001 |
| 2014–2016 | 2016 | 2011 |
| 2017 onwards | 2020v2 | 2011 |

This is PHS's **health-data** edition recommendation even when Government bands are used.
It is not a claim that all Government publications use this year mapping.
A new SIMD edition needs an explicit setup block and a separate review of this mapping;
a new postcode release does not alter it. No pre-1996 Carstairs values are invented.
For a study deliberately using one edition throughout, select that edition explicitly from
`simd_postcode_by_edition` rather than supplying a misleading analysis year.

## Read the output

One row is returned per input, with a fixed output structure:

- Input postcode/year and the matched original postcode and `pc_norm`.
- `sspl_release`, `index_source`, `allocation`, introduction/deletion dates, `is_current`,
  user type, split indicator and the raw linked-small-user field.
- `simd_edition`, `edition_policy`, `data_zone_code` and `data_zone_vintage`.
- `simd_rank`: the common rank, checked between PHS and Government during ingestion.
- `phs_pw_*`: population-weighted Scotland, health-board, HSCP and council quintiles/deciles,
  plus the published most/least-deprived 15% flags (0/1).
- `phs_hb_code`, `phs_hscp_code`, `phs_ca_code`: the actual geographies used for those
  local PHS bands. Do not substitute the NRS administrative codes.
- `gov_uw_*`: Government unweighted Scotland quintile, decile and vigintile.
- Clearly vintage-labelled NRS output-area, administrative and rurality context. These
  describe the current SSPL allocation, **not** historical rurality or boundaries for the input year.

Band 1 is most deprived for both publishers and every edition. Ingestion already reversed
the early PHS bands; SQL must not reverse them again. PHS quintiles are the recommended
routine health-reporting grouping (section 3.3). Returning both sources does not authorise
mixing their categories in one analysis. Rates need separately supplied matching denominators.

“Both full outputs” means all 14 per-edition measures in our imported table, with the
relevant geography/provenance. It does not include domain scores, percentiles, or extra
measures absent from the ingestion contract.

| Field/status | Meaning |
| --- | --- |
| `postcode_status = matched` | An ordinary key matches SSPL; no residence eligibility claim |
| `missing_postcode` / `not_found` | Null/blank input / no matching whole SSPL key |
| `simd_status = matched` | A supported edition, all 14 stored measures and their geography codes are available |
| `missing_year` / `invalid_year` / `no_edition` | Null year / outside 1–9999 / no recommended SIMD before 1996 |
| `missing_simd` | A selected measure or required geography code is missing; other available values remain visible |

Year errors take precedence in `simd_status`, while `postcode_status` separately records
the postcode match. Missing/unsupported years return no SIMD values but retain matched
postcode context. An unmatched postcode can still have a resolved edition. No errors are
silently replaced by 2020v2.

`address_warning` is `po_box` for large-user NO LINKP, `unlinked_large_user` for a missing,
blank or NO LINK field, and `large_user` for other large users. It is null for small users
and unmatched postcodes. These warnings **do not suppress values**. A downstream residential
analysis must decide its exclusions; this raw lookup is not a ready-filtered patient cohort.

## Migration and verification

The previous default redirected large users through their small-user links. That policy is
no longer used by the default SSPL query. In the reviewed 2026/2 snapshot, `AB24 2TY`
now keeps its own PHS 2020v2 quintile 5, not linked `AB24 2TN`'s quintile 1.

The older SPD linked-small-user examples are isolated under [sql/history](sql/history/README.md).
Their interface and output differ; they are not an SSPL fallback. The old
`simd_postcode_latest` view is not used by the new default.

Tests execute the default query on edge cases and compare every reshaped measure and PHS
geography against all six editions of the saved SSPL table. They check year boundaries,
unmatched inputs, duplicate events, deleted records and large-user own-value preservation.
These establish the documented contract, not exact equivalence to PHS's separately
published postcode-level lookup.
