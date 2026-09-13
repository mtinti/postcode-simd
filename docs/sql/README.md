# SQL lookups: one set per postcode product

A study makes two choices, in this order. Neither has a default.

1. **Which postcode product.** `spd/` reads the history table, `sspl/` reads the main table.
   The two NRS products allocate data zones differently, so the SIMD attached to a postcode
   can differ between them. Use one product for the whole study and say which.
2. **Which edition policy.** `link_by_era.sql` chooses the SIMD edition from the year of the
   health data (PHS v3.5 Table 4). `link_latest.sql` uses one edition throughout, edited on
   one marked line.

The SPD set has a third query, `link_as_of.sql`, for a postcode that comes with the date it
was recorded against the person: it uses the postcode life valid on that date, not the latest
life, and still chooses the edition from the year of the health data. The SSPL cannot answer
that question, because NRS kept one life per postcode.

| Set | Import this file | As table | With key | The query does |
| --- | --- | --- | --- | --- |
| `spd/` | `results/postcode_simd_history.parquet` | `postcode_simd_history` | `(pc_norm, introduced_on)` | latest life or the life on the address date, A part, large-user links, values |
| `sspl/` | `results/postcode_simd.parquet` | `postcode_simd` | `pc_norm` | large-user links, values |

Every query is standalone: no view, no other script, no other product. Each reads top to
bottom as numbered steps, and each step names the guidance it follows or says it is a
project choice. The four files are generated from the schemas by
`python -m simd_ingest.sql_examples`, so a new SIMD edition or a changed header regenerates
them; a test fails if a committed file drifts from the generator.

Both sets return the same columns in the same order, so a pipeline switches product by
changing the file path and the table name. The columns and statuses are described in
[LINKAGE_BY_ERA.md](../LINKAGE_BY_ERA.md).

Run one, from the repository root, with DuckDB:

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
