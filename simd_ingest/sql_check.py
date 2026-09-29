"""Generate the SQL Server script that checks an imported table against the build.

    python -m simd_ingest.sql_check          # rewrites docs/sql/check_loaded_digest.sql

The script does two things a file hash cannot: it confirms the loaded table has the declared
columns, types, nullability and key, and it recomputes the row digest the build recorded. The
digest is compact and probabilistic, not a proof of identity, and it is compared against the
manifest rather than against a second copy of the CSV, so an import mistake cannot appear on
both sides. Running it is a manual step; the CLI never connects to a database.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from .core.output import load_schema
from .core.text_output import exported_columns, load_contract
from .sql_examples import PRODUCTS

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
OUT = ROOT / "docs" / "sql" / "check_loaded_digest.sql"
IMPORT_OUT = ROOT / "docs" / "sql" / "import_csv.sql"
# Text is staged and stored generously: the longest value in either table is 19 characters.
STAGING_WIDTH, TEXT_WIDTH = 400, 200

# The declared SQL type for each schema type. The import recipe must use these.
SQL_TYPE = {"string": "nvarchar", "date32": "date", "bool": "bit", "int8": "tinyint", "int16": "smallint"}
# UTF-8 bytes, so HASHBYTES sees exactly what Python hashed. Verified on SQL Server 2022.
COLLATION = "Latin1_General_100_BIN2_UTF8"


def _render(name: str, kind: str) -> str:
    """One column as the text the digest hashes. Every column is wrapped: CONCAT_WS drops a
    NULL argument outright, which would shift every later field in the row."""
    if kind == "date32":
        return f"ISNULL(CONVERT(varchar(10), [{name}], 23), NCHAR(0))"
    if kind == "bool":
        return f"ISNULL(CONVERT(varchar(1), CONVERT(tinyint, [{name}])), NCHAR(0))"
    if kind in ("int8", "int16"):
        return f"ISNULL(CONVERT(varchar(11), [{name}]), NCHAR(0))"
    return f"ISNULL([{name}], NCHAR(0))"


def _table_sql(table: str, product: dict, schema: dict, contract: dict) -> str:
    columns = exported_columns(schema, contract, table)
    kinds = {f["name"]: f["type"] for f in schema["fields"]}
    nullable = {f["name"]: bool(f["nullable"]) for f in schema["fields"]}
    name = product["table"]
    declared = ",\n".join(
        f"    (N'{c}', {i}, N'{SQL_TYPE[kinds[c]]}', {1 if nullable[c] else 0})"
        for i, c in enumerate(columns, 1))
    key = ", ".join(f"[{k}]" for k in schema["key"])
    rendered = [_render(c, kinds[c]) for c in columns]
    # The first argument fixes the result type: without max, CONCAT_WS returns nvarchar(4000).
    rendered[0] = f"CONVERT(nvarchar(max), {rendered[0]})"
    expression = ",\n           ".join(rendered)
    text_columns = [c for c in columns if kinds[c] == "string"]
    reserved = "\n       OR ".join(
        f"DATALENGTH(REPLACE(REPLACE([{c}] COLLATE {COLLATION}, NCHAR(0), N''), NCHAR(31), N'')) "
        f"<> DATALENGTH([{c}])" for c in text_columns)
    return f"""
-- ============================================================================================
-- {name}: structure, key, then the digest
-- ============================================================================================
IF OBJECT_ID(N'{name}', N'U') IS NULL
    INSERT INTO #result VALUES (N'{name}', N'table exists', N'a table', N'not found', NULL, 0);
ELSE
BEGIN
    -- 1. Structure. A digest cannot establish any of this: a missing column, a wrong type, a
    -- column that should not accept NULL, or a changed order would all be invisible to it.
    DECLARE @declared_{table} TABLE (name sysname, ordinal int, type_name sysname, is_nullable bit);
    INSERT INTO @declared_{table} (name, ordinal, type_name, is_nullable) VALUES
{declared};

    INSERT INTO #result
    SELECT N'{name}', N'columns declared and in order', N'0 differences',
           CONVERT(nvarchar(200), COUNT(*)) + N' differences', COUNT(*), CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
    FROM (
        SELECT d.name FROM @declared_{table} d
        LEFT JOIN INFORMATION_SCHEMA.COLUMNS c
               ON c.TABLE_NAME = PARSENAME(N'{name}', 1) AND c.COLUMN_NAME = d.name
              AND c.ORDINAL_POSITION = d.ordinal AND c.DATA_TYPE = d.type_name
              AND c.IS_NULLABLE = CASE d.is_nullable WHEN 1 THEN 'YES' ELSE 'NO' END
        WHERE c.COLUMN_NAME IS NULL
        UNION ALL
        SELECT c.COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS c
        WHERE c.TABLE_NAME = PARSENAME(N'{name}', 1)
          AND c.COLUMN_NAME NOT IN (SELECT name FROM @declared_{table})
    ) AS differences;

    -- 2. The natural key, which the digest also cannot see: it is order independent, so a
    -- duplicated row and a missing one can cancel out.
    INSERT INTO #result
    SELECT N'{name}', N'natural key {key} unique and not null', N'0 offending rows',
           CONVERT(nvarchar(200), COUNT_BIG(*)) + N' offending rows', COUNT_BIG(*),
           CASE WHEN COUNT_BIG(*) = 0 THEN 1 ELSE 0 END
    FROM (SELECT {key} FROM {name} GROUP BY {key} HAVING COUNT_BIG(*) > 1) AS duplicates;

    -- 3. Reserved characters in the text columns. The digest frames fields with them, so text
    -- containing one could make two different rows hash alike. The export refuses them; so does
    -- this. A rendered null is legitimately NCHAR(0), which is why this reads the columns.
    INSERT INTO #result
    SELECT N'{name}', N'no reserved framing characters in text', N'0 rows',
           CONVERT(nvarchar(200), COUNT_BIG(*)) + N' rows', COUNT_BIG(*),
           CASE WHEN COUNT_BIG(*) = 0 THEN 1 ELSE 0 END
    FROM {name}
    WHERE {reserved};

    -- 4. The digest. Each row is rendered as the CSV renders it, with NCHAR(0) for a null so a
    -- null and a blank differ, the fields joined with NCHAR(31) in contract order, converted to
    -- UTF-8 and hashed. The signed eight-byte prefixes are summed as decimal: converting after
    -- SUM would be too late, because SUM over bigint can overflow.
    INSERT INTO #result
    SELECT N'{name}', N'row count', CONVERT(nvarchar(200), e.row_count),
           CONVERT(nvarchar(200), q.n), ABS(q.n - e.row_count),
           CASE WHEN q.n = e.row_count THEN 1 ELSE 0 END
    FROM #expected e CROSS JOIN (SELECT COUNT_BIG(*) AS n FROM {name}) AS q
    WHERE e.name = N'{name}';

    INSERT INTO #result
    SELECT N'{name}', N'row digest, definition version ' + CONVERT(nvarchar(10), e.digest_version),
           CONVERT(nvarchar(200), e.digest_total), CONVERT(nvarchar(200), ISNULL(q.total, 0)),
           CASE WHEN ISNULL(q.total, 0) = e.digest_total THEN 0 ELSE 1 END,
           CASE WHEN ISNULL(q.total, 0) = e.digest_total THEN 1 ELSE 0 END
    FROM #expected e CROSS JOIN (
        SELECT SUM(CONVERT(decimal(38,0), CONVERT(bigint, SUBSTRING(HASHBYTES('SHA2_256',
                   CONVERT(varchar(max), CONCAT_WS(NCHAR(31),
           {expression}) COLLATE {COLLATION})), 1, 8)))) AS total
        FROM {name}) AS q
    WHERE e.name = N'{name}';
END
"""


def _import_sql(table: str, product: dict, schema: dict, contract: dict) -> str:
    """Stage the file as text, then restore the declared types and the empty-cell rules."""
    columns = exported_columns(schema, contract, table)
    kinds = {f["name"]: f["type"] for f in schema["fields"]}
    nullable = {f["name"]: bool(f["nullable"]) for f in schema["fields"]}
    spec, name = contract["tables"][table], product["table"]
    role_column = spec.get("role_column", "spd_user_type")
    structural = {c: role for role, cols in (spec.get("structural_nulls") or {}).items() for c in cols}
    empty_is_null = set(spec.get("empty_is_null") or [])

    staging = ",\n    ".join(
        f"[{c}] varchar({STAGING_WIDTH}) COLLATE {COLLATION} NULL" for c in columns)
    typed = ",\n    ".join(
        f"[{c}] " + ({"string": f"nvarchar({TEXT_WIDTH})"}.get(kinds[c], SQL_TYPE[kinds[c]]))
        + ("" if nullable[c] else " NOT NULL") for c in columns)
    key = ", ".join(f"[{k}]" for k in schema["key"])

    restore = []
    for c in columns:
        kind = kinds[c]
        if kind == "date32":
            # The reader turns an empty field into NULL; NULLIF also covers one that does not.
            # Never let an empty string reach a date: SQL Server makes it 1900-01-01 as a
            # datetime and raises an error as a date. Neither is the value in the file.
            restore.append(f"CONVERT(date, NULLIF([{c}], ''), 23)")
        elif kind == "bool":
            restore.append(f"CASE [{c}] WHEN '1' THEN CONVERT(bit, 1) WHEN '0' THEN CONVERT(bit, 0) END")
        elif kind in ("int8", "int16"):
            # NULLIF for the same reason as a date: an empty string converts to 0, which is a
            # value the file never held. Only a nullable integer can be empty at all.
            restore.append(f"CONVERT({SQL_TYPE[kind]}, NULLIF([{c}], ''))")
        elif c in empty_is_null:
            # Never blank by construction, so an empty cell is a null for every row.
            restore.append(f"NULLIF([{c}], N'')")
        elif c in structural:
            # This column exists in only one of the two source files, so it is a real null for
            # the other record type and a source blank for its own.
            restore.append(f"CASE WHEN [{role_column}] = '{structural[c]}' THEN NULL ELSE ISNULL([{c}], N'') END")
        else:
            restore.append(f"ISNULL([{c}], N'')")
    select = ",\n    ".join(f"{expression}" for expression in restore)
    names = ",\n    ".join(f"[{c}]" for c in columns)
    note = ("Every text empty in this table is a source blank." if not structural else
            "A column that exists in only one directory file is a real null for the other "
            f"record type: see [{role_column}] below.")
    return f"""
-- --------------------------------------------------------------------------------------------
-- {name}: stage as text, then restore the declared types. {note}
-- --------------------------------------------------------------------------------------------
DROP TABLE IF EXISTS staging_{name};
CREATE TABLE staging_{name} (
    {staging}
);

-- EDIT the path. FORMAT = 'CSV' honours RFC 4180 quoting; the field terminator defaults to a
-- tab without it. ROWTERMINATOR is LF, as the contract specifies. CODEPAGE is not supported on
-- Linux, which is why the UTF-8 encoding is declared on the staging columns above.
BULK INSERT staging_{name}
FROM '/path/to/{spec["file"][:-3]}'
WITH (FORMAT = 'CSV', FIELDQUOTE = '"', FIELDTERMINATOR = ',', ROWTERMINATOR = '0x0a',
      FIRSTROW = 2, TABLOCK);

DROP TABLE IF EXISTS {name};
CREATE TABLE {name} (
    {typed},
    CONSTRAINT PK_{name} PRIMARY KEY ({key})
);

-- The reader gives an empty field as NULL, so every empty cell arrives the same way. This is
-- where the contract's rules put them back: a blank where the source had a blank, a null only
-- where the column does not apply to that record.
INSERT INTO {name} (
    {names}
)
SELECT
    {select}
FROM staging_{name};

DROP TABLE staging_{name};
"""


def render_import() -> str:
    contract = load_contract(PACKAGE / "export_contract.yaml")
    sections = [_import_sql(spec["contract_table"], spec, load_schema(PACKAGE / spec["schema"]), contract)
                for spec in PRODUCTS.values()]
    return f"""-- Import both shared CSVs into SQL Server, then check them with check_loaded_digest.sql.
-- Generated by python -m simd_ingest.sql_check from the output schemas and the export contract.
--
-- Decompress the files first and edit the two paths below. Nothing here converts a value the
-- schema does not declare: text is stored as it arrives, including leading zeros and values
-- that look like numbers or dates. Run it against a database of your own, not beside data you
-- care about: it drops and recreates the four tables it names.
--
-- Verify the file hashes against results/manifest.json before importing. After importing, run
-- check_loaded_digest.sql with that manifest's row counts and digest totals.

SET NOCOUNT ON;
SET XACT_ABORT ON;
{"".join(sections)}"""


def render() -> str:
    contract = load_contract(PACKAGE / "export_contract.yaml")
    digest = contract["digest"]
    sections = []
    for product, spec in PRODUCTS.items():
        table = spec["contract_table"]
        schema = load_schema(PACKAGE / spec["schema"])
        sections.append(_table_sql(table, spec, schema, contract))
    # The comma has to come before the comment, or it ends up inside it.
    rows = list(PRODUCTS.values())
    names = "\n".join(
        f"    (N'{spec['table']}', 0, 0, {digest['version']}){',' if n < len(rows) - 1 else ''}"
        f"   -- EDIT: rows and total from manifest tables.{spec['contract_table']}.csv.digest"
        for n, spec in enumerate(rows))
    return f"""-- Check two imported tables against the build that produced their CSVs.
-- Generated by python -m simd_ingest.sql_check from the output schemas and the export contract.
--
-- Run it after importing, by the recipe in ../LINKAGE_BY_ERA.md, against tables that are not
-- being changed while it runs. It reads them; it never repairs, replaces or promotes anything.
-- The expected values come from results/manifest.json, which is the build's own record. They
-- must not be taken from the loaded table, which is what is being checked.
--
-- What this does establish: the declared columns, types, nullability and order are present, the
-- natural key is unique and not null, no text contains the characters the digest frames with,
-- the row count matches, and the recomputed digest matches.
-- What it does not: the digest truncates each SHA-256 to eight bytes and adds the results, so
-- collisions and cancelling changes are possible. It detects accidental load corruption. It is
-- neither an exact cell-by-cell comparison nor a signature, and it says nothing about the
-- columns the export contract withholds.

SET NOCOUNT ON;
SET XACT_ABORT ON;

-- STEP 1. EDIT. Paste this build's numbers from results/manifest.json.
IF OBJECT_ID(N'tempdb..#expected', N'U') IS NOT NULL DROP TABLE #expected;
CREATE TABLE #expected (name sysname PRIMARY KEY, row_count bigint NOT NULL,
                        digest_total decimal(38,0) NOT NULL, digest_version int NOT NULL);
INSERT INTO #expected (name, row_count, digest_total, digest_version) VALUES
{names}
;

IF EXISTS (SELECT 1 FROM #expected WHERE digest_version <> {digest['version']})
    THROW 51000, 'This script implements digest definition version {digest['version']} only.', 1;
IF EXISTS (SELECT 1 FROM #expected WHERE row_count <= 0)
    THROW 51000, 'Expected row counts and digest totals have not been filled in from the manifest.', 1;

IF OBJECT_ID(N'tempdb..#result', N'U') IS NOT NULL DROP TABLE #result;
CREATE TABLE #result (table_name sysname, check_name nvarchar(200), expected nvarchar(200),
                      actual nvarchar(200), difference bigint NULL, passed bit NOT NULL);
{"".join(sections)}
-- ============================================================================================
-- The result. A skipped check is not a pass, so an absent row fails the count below.
-- ============================================================================================
SELECT table_name, check_name, expected, actual, difference,
       CASE passed WHEN 1 THEN 'pass' ELSE 'FAIL' END AS outcome
FROM #result ORDER BY table_name, check_name;

DECLARE @failed int = (SELECT COUNT(*) FROM #result WHERE passed = 0);
DECLARE @ran int = (SELECT COUNT(*) FROM #result);
IF @failed > 0 OR @ran <> {len(PRODUCTS) * 5}
    THROW 51000, 'The imported tables do not match the build: see the result above.', 1;
"""


def main(argv=None) -> int:
    directory = Path(argv[0]) if argv else OUT.parent
    for path, text in ((directory / IMPORT_OUT.name, render_import()), (directory / OUT.name, render())):
        path.write_text(text)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
