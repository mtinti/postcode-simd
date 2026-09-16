"""Generate the data dictionaries from the two output schemas and the registry.

    python -m simd_ingest.dictionary [results/manifest.json]

docs/DATA_DICTIONARY.md describes the main table (SSPL), docs/DATA_DICTIONARY_HISTORY.md the
history table (SPD). Generated, not hand-written, so they cannot drift from the schemas.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import yaml

from .core.output import BAND_CONVENTION
from .core.sources import load_registry
from .core.text_output import load_contract

PACKAGE = Path(__file__).resolve().parent  # the schema and registry ship inside the package

# PHS deprivation guidance for analysts, version 3.5, table 4. A recommendation, not a rule.
GUIDANCE_TABLE_4 = [
    ("SIMD 2004", "2001", "2001", "1996 to 2003"),
    ("SIMD 2006", "2001", "2004", "2004 to 2006"),
    ("SIMD 2009v2", "2001", "2007", "2007 to 2009"),
    ("SIMD 2012", "2001", "2010", "2010 to 2013"),
    ("SIMD 2016", "2011", "2014", "2014 to 2016"),
    ("SIMD 2020v2", "2011", "2017", "2017 onwards"),
]


TABLES = {
    "main": dict(schema="output_schema.yaml", out="docs/DATA_DICTIONARY.md", product="Scottish Statistics Postcode Lookup (SSPL)",
                 release="sspl_release", other="DATA_DICTIONARY_HISTORY.md"),
    "history": dict(schema="output_schema_history.yaml", out="docs/DATA_DICTIONARY_HISTORY.md", product="Scottish Postcode Directory (SPD)",
                    release="spd_release", other="DATA_DICTIONARY.md"),
}


def csv_section(contract: dict, name: str, fields: list) -> list:
    """How the shared CSV renders this table. Generated, so it cannot drift from the contract."""
    spec = contract["tables"][name]
    kept = len(fields) - len(spec["exclude"])
    lines = ["## The CSV rendering", "",
             f"Every build also writes `results/{spec['file']}`, the form in which this table is shared.",
             f"It carries {kept} of the {len(fields)} columns in the same order: "
             + (f"`{'`, `'.join(spec['exclude'])}` are not exported." if spec["exclude"] else "nothing is excluded."), ""]
    if spec["exclude"]:
        lines += ["  " + contract["exclude_reasons"]["minimisation"].strip().replace("\n", " "), "",
                  "  " + contract["exclude_reasons"]["licensing"].strip().replace("\n", " "), "",
                  "The Parquet keeps them, so read it directly if you need a grid reference.", ""]
    lines += ["Comma separated with RFC 4180 quoting, UTF-8 without a byte order mark, LF line endings",
              "and gzip compression. Dates are `YYYY-MM-DD`, `is_current` is `1` or `0`, and every other",
              "value is written exactly as stored, so leading zeros survive. Load every column as text",
              "first, keeping literal values such as `NA`, and restore the declared types afterwards.", "",
              "### An empty cell", "",
              "CSV writes the same empty cell for a null and for a source blank, so read it from the",
              "column and the record type, never from the cell alone.", ""]
    nulls = spec.get("structural_nulls") or {}
    if nulls:
        lines += ["| For a record whose `" + spec.get("role_column", "spd_user_type") + "` is | these columns are structural nulls |",
                  "| --- | --- |"]
        lines += [f"| `{role}` | `{'`, `'.join(columns)}` |" for role, columns in nulls.items()]
        lines += ["", "An empty cell in one of those columns for any other record is a source blank.", ""]
    else:
        lines += ["This table comes from a single source file, so every text empty is a source blank.", ""]
    lines += ["An empty `deleted_on` is a null and agrees with `is_current`. The source text column",
              "`DateOfDeletion` stays blank. Every other empty cell is a source blank.", "",
              "`results/CSV_README.txt` beside the files carries the attribution every source requires.", ""]
    return lines


def render(schema: dict, registry, manifest: dict | None, name: str = "history", contract: dict | None = None) -> str:
    fields = schema["fields"]
    by_source = Counter(f["source"] for f in fields)
    editions = [e["key"] for e in registry.phs_editions]
    spec = TABLES[name]
    lines = [f"# Data dictionary: {schema['table']}, schema `{schema['version']}`", ""]
    if name == "main":
        lines += ["The **main table**: one row per whole postcode from the " + spec["product"] + ", both user types, the",
                  f"latest life of each postcode (deleted ones included), with all {len(editions)} SIMD editions attached.",
                  "Every geography, including both data-zone vintages, is the one containing the centroid of the postcode's",
                  "2022 output area, as NRS allocates it in the SSPL. For postcode history and the directory's own",
                  f"postcode-in-zone allocation see the history table, [{spec['other']}]({spec['other']}).",
                  f"Generated from `simd_ingest/{spec['schema']}`; do not edit by hand.", ""]
    else:
        lines += ["The **history table**: one row per " + spec["product"] + " record, both user types, current and deleted,",
                  f"every life of every postcode, with all {len(editions)} SIMD editions attached. Data zones are the ones",
                  "containing the postcode's own grid reference. For one row per whole postcode see the main table,",
                  f"[{spec['other']}]({spec['other']}). Generated from `simd_ingest/{spec['schema']}`; do not edit by hand.", ""]
    if manifest:
        o = manifest["tables"][name]
        lines += [f"Current build: {o['rows']:,} rows by {o['columns']} columns, {name} index release {o['index_release']}, ",
                  f"allocation `{o['allocation']}`, built {manifest['built_at'][:19]}Z. Parquet SHA256 `{o['sha256']}`; rows-only fingerprint ",
                  f"`{o.get('logical_fingerprint', '')}`. The file hash also covers the embedded provenance metadata, ",
                  "so it changes when the decision log changes; compare fingerprints under the same pinned runtime.", ""]
    if name == "main":
        lines += ["## Key", "",
                  "Primary key: `pc_norm`, the postcode uppercased without spaces. One row per postcode; no split suffix",
                  "exists because NRS resolved split postcodes to the A part before publishing. `is_current` says whether",
                  "the latest life is live; `introduced_on` and `deleted_on` describe that latest life only. This table",
                  "cannot select a past postcode life: use history for that. Choosing a past SIMD edition on this",
                  "latest postcode is supported by the SQL era query. These are different policies.", ""]
    else:
        lines += ["## Key", "",
                  "Primary key: `pc_norm` with `introduced_on`. Unique across both user types. A postcode alone repeats",
                  "across its history, so use the date or explicitly select current records.", "",
                  "Validity of a record is the half-open interval `introduced_on <= day < deleted_on`, with a null",
                  "`deleted_on` meaning current. A record whose two dates are equal is retained but is never valid",
                  "on any day.", ""]
    lines += ["## Band convention", "", BAND_CONVENTION, ""]
    lines += ["## Which edition to use", "",
              "From the PHS deprivation guidance for analysts, version 3.5, table 4. The file carries every",
              "edition on every row; choosing one is the analyst's decision.", "",
              "| Edition | Data zones | Population year | Use with health data for |", "| --- | --- | --- | --- |"]
    lines += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in GUIDANCE_TABLE_4]
    lines += ["", "Data-zone vintages are not interchangeable; the join here",
              "already uses the right vintage for each edition. The file carries SIMD only; the Carstairs index",
              "the same guidance describes for pre-1996 data is not included.", ""]
    lines += ["## Things that will catch you out", ""]
    if name == "main":
        lines += ["- **Allocation.** The SSPL assigns every higher geography from the 2022 output-area centroid. Its 2011",
                  "  and 2001 data zones therefore differ from the directory's on a few percent of postcodes, and so do",
                  "  the SIMD values attached through them. The build report counts observed differences, without",
                  "  attributing every difference to method rather than release changes. Neither table establishes",
                  "  equivalence to PHS's published postcode lookup. Choose one product consistently for a study.",
                  "- **Split postcodes** are already whole here. `SplitIndicator` Y marks a postcode the directory holds",
                  "  as A/B/C parts; the SSPL keeps the A part's geography and sums the counts."]
    else:
        lines += ["- **Split postcodes.** NRS splits a postcode that straddles a boundary into A, B or C parts, each its",
                  "  own record with its own data zone. `pc_base` is the postcode as a person writes it. Filter current",
                  "  records on `pc_base` and you may get more than one row with different SIMD values. The lookups",
                  "  in `simd_ingest.lookup` resolve that to the A part by default, as NRS does, and say so; a report",
                  "  rule shows the ambiguity instead. Never average or vote."]
    lines += [
              "- **Large-user postcodes and PO boxes.** The source assigns them a data zone, so SIMD is attached.",
              "  The [SQL sets](LINKAGE_BY_ERA.md) follow a large user's link and give PO boxes no SIMD. Applying",
              "  this to SSPL is a project interpretation of PHS Appendix A, which does not explicitly settle",
              "  overriding SSPL's own allocated geography. Exact PHS lookup parity remains unverified.",
              "  Python keeps its own current/as-of, own-record geography and",
              "  sentinel-exclusion policy. Residence eligibility and publication choices are downstream.",
              "- **Within-geography bands.** `simd{ed}_pw_hb_*` is computed within the health board in",
              "  `phs_dz{vintage}_hb`, which on a few records differs from the directory's own `HealthBoardArea2019Code`.",
              "  Use the PHS code with the PHS band.",
              "- **Directory columns are text.** Every original column keeps its source text, including leading",
              "  zeros and blanks. A blank is `\"\"`; a column absent from that user type is null.", ""]
    if contract:
        lines += csv_section(contract, name, fields)
    lines += ["## Sources", "", "| Publisher | Object | SHA256 |", "| --- | --- | --- |"]
    lines += [f"| {o.publisher} | {o.url.rsplit('/', 1)[-1]} | `{o.sha256[:16]}…` |" for o in registry.objects]
    lines += ["", f"Licences: " + "; ".join(f"{k}: {v}" for k, v in registry.licences.items()), ""]
    origin = "lookup" if name == "main" else "directory"
    lines += ["## Columns", "", f"{len(fields)} columns: {by_source[origin]} from the {origin}, {by_source['derived']} derived, ",
              f"{sum(1 for f in fields if f['name'].startswith('phs_dz'))} PHS geography, and 14 per edition for {len(editions)} editions.", "",
              "### Per-edition SIMD columns", "", "`{ed}` is one of " + ", ".join(editions) + ".", "",
              "| Column | Type | Meaning |", "| --- | --- | --- |"]
    seen = set()
    for f in fields:
        if f["name"].startswith("simd" + editions[0] + "_"):
            generic = f["name"].replace(editions[0], "{ed}", 1)
            if generic not in seen:
                seen.add(generic)
                lines.append(f"| `{generic}` | {f['type']} | {f['note']} |")
    lines += ["", "### All columns in file order", "", "| # | Column | Type | Nullable | Source | Note |", "| ---: | --- | --- | --- | --- | --- |"]
    lines += [f"| {i} | `{f['name']}` | {f['type']} | {'yes' if f['nullable'] else 'no'} | {f['source']} | {f.get('note', '')} |"
              for i, f in enumerate(fields, 1)]
    return "\n".join(line.rstrip() for line in lines) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    registry = load_registry(PACKAGE / "sources.yaml")
    contract = load_contract(PACKAGE / "export_contract.yaml")
    man_path = Path(argv[0] if argv else "results/manifest.json")  # relative to the working directory
    manifest = json.loads(man_path.read_text()) if man_path.is_file() else None
    for name, spec in TABLES.items():
        schema = yaml.safe_load((PACKAGE / spec["schema"]).read_text())
        out = Path(spec["out"])
        out.parent.mkdir(exist_ok=True)
        out.write_text(render(schema, registry, manifest, name, contract))
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
