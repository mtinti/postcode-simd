# SQL lookups: one set per postcode product

A study makes two choices, in this order. Neither has a default.

1. **Which postcode product.** `spd/` reads the history table, `sspl/` reads the main table.
   The two NRS products allocate data zones differently, so the SIMD attached to a postcode
   can differ between them. [NRS recommends SSPL for statistical production and SPD for
   operational/administrative use](https://www.nrscotland.gov.uk/publications/geography-scottish-statistics-postcode-lookup-information-note/).
   The project leaves the choice explicit; that does not make them equally recommended for
   statistics. Use one product for the whole study and say which.
2. **Which edition policy.** `link_by_era.sql` chooses the SIMD edition from the year of the
   health data (PHS v3.5 Table 4). `link_latest.sql` uses one edition throughout, edited on
   one marked line.

The SPD set has a third query, `link_as_of.sql`, for a postcode with a reliable address date:
it uses the postcode life valid on that date, not the latest life, and still chooses the
edition from the year of the health data. This is a project policy, not a reconstruction of
historical administrative snapshots. All three SPD queries also return the Urban Rural
Classification version that suits the year, with its version, policy and status. A general record edit date is not necessarily
an address date. The SSPL cannot answer a postcode-life question, because NRS kept one life
per postcode.

| Set | Import this file | As table | With key | The query does |
| --- | --- | --- | --- | --- |
| `spd/` | `results/postcode_simd_history.parquet` | `postcode_simd_history` | `(pc_norm, introduced_on)` | latest life or the life on the address date, A part, large-user links, values |
| `sspl/` | `results/postcode_simd.parquet` | `postcode_simd` | `pc_norm` | large-user links, values |

Every query is standalone: no view, no other script, no other product. Each reads top to
bottom as numbered steps, and each step names the guidance it follows or says it is a
project choice. The five files are generated from the schemas by
`python -m simd_ingest.sql_examples`, so a new SIMD edition or a changed header regenerates
them; a test fails if a committed file drifts from the generator.

All five queries share the first **41 columns**, through `band_direction`. They then append
different own-record context: **89 columns** in SSPL, **108** in SPD era/latest, **111** in
SPD as-of. To combine products, select the shared columns by name; do not use `SELECT *` or
a positional union of the full results. The columns and statuses are described in
[LINKAGE_BY_ERA.md](../LINKAGE_BY_ERA.md).

Both sets follow large-user links and withhold SIMD for PO boxes and unlinked large users.
Applying that rule to SSPL is a project interpretation of PHS Appendix A: it does not
explicitly settle overriding geography already allocated in SSPL. Own-record geography is
kept as context; exact equivalence to PHS's postcode-level lookup remains unverified.

`spd/walkthrough_as_of.sql` is the dated query written short, with every step and its reason,
returning the rank, both publishers' within-Scotland quintile and decile, and the urban-rural
classification. Read it to satisfy yourself the logic
is right, then use the generated query to produce values. A test runs both on the built table and
requires them to agree case for case, so the short one cannot quietly drift.

Both dated queries take one date per row. The address date selects the postcode life, and its
year selects the SIMD edition, so an episode needs only its own date. `analysis_year` is an
override for the cases where those two differ: hold it constant to compare a long period on a
single classification, or set it to the year of the health data when the address was recorded
at another time.

Two further generated scripts load the shared CSVs into SQL Server and check the result:
[import_csv.sql](import_csv.sql) stages each file as text and restores the declared types, and
[check_loaded_digest.sql](check_loaded_digest.sql) verifies the structure, the key and the row
digest the build recorded. Both come from `python -m simd_ingest.sql_check`. The recipe and
what it does and does not establish are in [LINKAGE_BY_ERA.md](../LINKAGE_BY_ERA.md).

Run one of the five lookups, from the repository root, with DuckDB:

```python
from pathlib import Path
import duckdb

with duckdb.connect() as con:
    con.execute("CREATE TABLE postcode_simd AS SELECT * FROM 'results/postcode_simd.parquet'")
    con.execute("ALTER TABLE postcode_simd ADD PRIMARY KEY (pc_norm)")
    print(con.execute(Path("docs/sql/sspl/link_by_era.sql").read_text()).df().T)
```

For a cohort, replace the first `SELECT` of the query, marked STEP 1, with a `SELECT` from
your own table. The queries are tested on DuckDB; the syntax is meant to run on SQL Server
but that has not been verified.
