# Two SQL postcode-to-SIMD lookups

Choose a postcode product first, then a SIMD edition policy. These are separate decisions.
The default is the SSPL main table. An explicitly named setup retains the SPD alternative.

| Postcode product | Import as | Run this setup |
| --- | --- | --- |
| SSPL main: latest whole postcodes, output-area-based geography | `postcode_simd` | [create_latest_postcode_lookup.sql](sql/create_latest_postcode_lookup.sql) |
| SPD history: select latest records, postcode-based geography | `postcode_simd_history` | [create_latest_postcode_lookup_history.sql](sql/create_latest_postcode_lookup_history.sql) |

Run **one setup**, not both. Each creates `simd_postcode_latest` with one row per ordinary
`postcode_key`. This is a view-level key: the SSPL file itself has `pc_norm`, not `pc_base`.
Both setups support the same two cohort queries:

| Question | Query | Edition choice |
| --- | --- | --- |
| One edition for the whole cohort | [link_latest.sql](sql/link_latest.sql) | Explicit choice; defaults to 2020v2 |
| Appropriate edition for each event year | [link_by_era.sql](sql/link_by_era.sql) | PHS v3.5 Table 4 |

Neither query reconstructs an address at an event date. Even for an old event, both use the
latest postcode geography in the chosen product. In the era query the date selects the
**SIMD edition**, not a postcode life. Date-valid matching is a separate Python policy,
documented in [EXAMPLES.md](EXAMPLES.md), and needs SPD history.

## Run the default SSPL examples

For DuckDB, from the repository root:

```python
from pathlib import Path
import duckdb
import pandas as pd

sql = Path("docs/sql")
events = pd.read_csv("my_cohort.csv", dtype={"postcode": "string"})
# Required for link_by_era.sql only. Reject invalid text rather than silently coercing it.
events["event_date"] = pd.to_datetime(events["event_date"], errors="raise")

with duckdb.connect() as con:
    con.execute("CREATE VIEW postcode_simd AS SELECT * FROM 'results/postcode_simd.parquet'")
    con.execute((sql / "create_latest_postcode_lookup.sql").read_text())
    con.register("events", events)
    latest = con.execute((sql / "link_latest.sql").read_text()).df()
    by_era = con.execute((sql / "link_by_era.sql").read_text()).df()
```

For the SPD alternative replace just the two setup lines:

```python
con.execute("CREATE VIEW postcode_simd_history AS SELECT * FROM 'results/postcode_simd_history.parquet'")
con.execute((sql / "create_latest_postcode_lookup_history.sql").read_text())
```

For SQL Server, import the chosen table under the name above with its actual natural key:
SSPL `pc_norm`; SPD `(pc_norm, introduced_on)`. Preserve date types and a bit/boolean
`is_current`. Execute the shared `CREATE VIEW` in its own batch, as required by
[Microsoft](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-view-transact-sql?view=sql-server-ver17).
The SQL is tested on DuckDB; SQL Server execution has not been verified.

The fixed-edition query needs `events(id, postcode)`; the era query also needs date-typed
`event_date`. Establish the study's time zone before deriving years. Repeated/null IDs and
identical rows are retained. Only the listed columns are returned; use an event identifier
and `ORDER BY` if order matters. A view reflects refreshed source rows; recreate it if your
import drops/recreates its table. Changing the setup intentionally changes the allocation
method, so record that choice for the study.

## Postcode selection and links

1. **SSPL, default.** NRS already selects the latest life, retains deleted latest records,
   and makes ordinary splits whole on the A part. No history selection, split voting or
   additional geographic allocation is performed by the SQL.
2. **SPD, alternative.** Select the newest introduction for each complete NRS key across
   both user types. For each ordinary postcode prefer live, whole/A, then newest introduction.
   A newer B/C never displaces a live A. Missing A and equal-priority ties receive no SIMD.
   This ordering is a project implementation policy, not a reproduced PHS algorithm.
3. **Large users, both products.** Follow the supplied `LinkedSmallUserPostcode` to a
   small-user record in the **same product**. Missing, blank and `NO LINKP`/`NO LINK`
   links receive no SIMD. There is no own-geography fallback, chain through a large user,
   older-life fallback, or mixing of SSPL and SPD.
4. **Split links differ by product.** SPD keeps the exact linked A/B/C key. SSPL has only
   whole keys: an A-suffixed link can match a small-user record flagged `SplitIndicator=Y`,
   since NRS kept A's geography. B/C links and A links to unflagged targets cannot resolve
   and return `linked_small_user_not_found`. The original requested link is returned so
   the reason can be inspected. A whole-key link still matches exactly.
5. **Deleted link targets.** A retained latest small-user target may be deleted. Its
   `simd_source_is_current` flag makes this visible. The Python current-only policy differs.

Input must be an ordinary postcode, not an NRS A/B/C key. The queries uppercase and remove
ASCII spaces while retaining the original input. This normalisation does not repair an
invalid postcode. Original NRS postcode fields and source SIMD are unchanged by ingestion.

## What the guidance establishes

References: downloaded [PHS deprivation guidance v3.5](../manual_data/2023-12-phs-deprivation-guidance-v35.pdf),
[PHS postcode-file documentation](https://publichealthscotland.scot/resources-and-tools/health-intelligence-and-data-management/geography-population-and-deprivation-support/geography/postcode-file/)
and the [NRS SSPL information note](https://www.nrscotland.gov.uk/publications/geography-scottish-statistics-postcode-lookup-information-note/).

PHS describes latest postcode versions and A representatives. Appendix A, printed pp. 28–30,
describes postcode geography and large-user links. Following the linked-small-user route is
our explicit project choice; Appendix A does not settle every own-versus-linked disagreement.
Neither setup has been validated against an official PHS postcode-level lookup, including
its exact deleted-record retention policy. Sharing the SPD source does not establish parity.

NRS recommends SSPL for statistical production and SPD for operational/administrative
location questions. Their allocation methods can give different data zones and SIMD bands.
Choose one product consistently for an analysis. The pipeline's cross-table report compares
own-record values before link following; it is not a PHS-equivalence check.

PHS sections 3.2.1.1 and 3.2.1.2 describe edition-by-period and one-edition-throughout analyses.
Choose for the study. In `link_latest.sql`, change both lines marked `EDIT EDITION` together.
Both queries use PHS population-weighted within-Scotland quintiles, 1 most deprived, as
discussed in sections 3.1.1–3.1.2. Ingestion already reverses the 2004/2006 bands. Do not
reverse them again or substitute Government unweighted bands.

## Edition by event year

The era query transcribes Table 4, printed p. 17:

| Years of health data | SIMD edition |
| --- | --- |
| 1996–2003 | 2004 |
| 2004–2006 | 2006 |
| 2007–2009 | 2009v2 |
| 2010–2013 | 2012 |
| 2014–2016 | 2016 |
| 2017 onwards | 2020v2 |

Missing dates return `missing_date`; dates before 1996 return `no_edition`. Edition and
value are null, but postcode provenance can remain. These date statuses take precedence
over postcode problems. No Carstairs values are invented.

A postcode refresh does not change this mapping. After adding a SIMD edition, expose its
column in **both** setups and review the query edit points and year mapping against the new
guidance. Ingestion must not silently reclassify old events.

## Read the result

`simd_edition` and `simd_measure` identify edition, weighting, scope and direction.

| Status | Meaning |
| --- | --- |
| `matched` | Ordinary small user's own SIMD |
| `a_part` | A representative: already whole in SSPL, explicit A in SPD |
| `linked_small_user` | Named small-user target supplied SIMD |
| `missing_postcode` / `not_found` | Blank/null input / no ordinary key |
| `unlinked_large_user` | Blank, missing or sentinel link |
| `linked_small_user_not_found` | Unavailable target, wrong user type, or unavailable split part |
| `split_a_missing` / `ambiguous_postcode` | SPD only: no eligible representative / tied representatives |
| `missing_simd` | Resolved geography lacks the selected edition's value |
| `missing_date` / `no_edition` | Era query only: missing date / no recommended SIMD |

Failure statuses have null values. Matched and SIMD-source keys are separate. SSPL's key is
`pc_norm`; SPD's is `(pc_norm, introduced_on)`. Dates are also returned for SSPL provenance,
not as a second key. `requested_link_postcode` preserves the raw link, including its suffix.
For ambiguous SPD matches, the returned matched key is diagnostic, not an accepted match.

`index_source`, `index_release` and `allocation` identify the matched product, release and
method; unmatched postcodes have null record provenance. Record the chosen setup even when
a cohort has no matches. Current flags distinguish live from retained deleted records.

Tests execute both setups on synthetic edge cases and the downloaded tables. They check era
boundaries, missing links, A/B/C handling, changed user type, deleted targets, duplicate
events, one row per postcode and no SIMD leaked from excluded records. These validate the
documented policy, not PHS-equivalence. For rates, use separately supplied denominators with
matching definitions; postcode deprivation is not an individual measurement.
