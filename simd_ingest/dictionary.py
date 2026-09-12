"""Generate docs/DATA_DICTIONARY.md from output_schema.yaml and the registry.

    python -m simd_ingest.dictionary

The dictionary is generated, not hand-written, so it cannot drift from the schema.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import yaml

from .core.output import BAND_CONVENTION
from .core.sources import load_registry

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


def render(schema: dict, registry, manifest: dict | None) -> str:
    fields = schema["fields"]
    by_source = Counter(f["source"] for f in fields)
    editions = [e["key"] for e in registry.phs_editions]
    lines = [f"# Data dictionary: postcode_simd, schema `{schema['version']}`", ""]
    lines += ["One row per Scottish Postcode Directory record, both user types, current and deleted, with all",
              f"{len(editions)} SIMD editions attached. Generated from `simd_ingest/output_schema.yaml`; do not edit by hand.", ""]
    if manifest:
        o = manifest["output"]
        lines += [f"Current build: {o['rows']:,} rows by {o['columns']} columns, SPD release {manifest['spd_release']}, ",
                  f"built {manifest['built_at'][:19]}Z. Parquet SHA256 `{o['sha256']}`; rows-only fingerprint ",
                  f"`{o.get('logical_fingerprint', '')}`. The file hash also covers the embedded provenance metadata, ",
                  "so it changes when the decision log changes; compare fingerprints under the same pinned runtime.", ""]
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
    lines += ["## Things that will catch you out", "",
              "- **Split postcodes.** NRS splits a postcode that straddles a boundary into A, B or C parts, each its",
              "  own record with its own data zone. `pc_base` is the postcode as a person writes it. Filter current",
              "  records on `pc_base` and you may get more than one row with different SIMD values. The lookups",
              "  in `simd_ingest.lookup` resolve that to the A part by default, as NRS does, and say so; a report",
              "  rule shows the ambiguity instead. Never average or vote.",
              "- **Large-user postcodes and PO boxes.** The directory assigns them a data zone, so SIMD is attached.",
              "  PHS practice attaches no deprivation to PO boxes. Filter on `spd_user_type` and on",
              "  `LinkedSmallUserPostcode` in (`NO LINKP`, `NO LINK`) if you want that behaviour.",
              "- **Within-geography bands.** `simd{ed}_pw_hb_*` is computed within the health board in",
              "  `phs_dz{vintage}_hb`, which on a few records differs from the directory's own `HealthBoardArea2019Code`.",
              "  Use the PHS code with the PHS band.",
              "- **Directory columns are text.** Every original column keeps its source text, including leading",
              "  zeros and blanks. A blank is `\"\"`; a column absent from that user type is null.", ""]
    lines += ["## Sources", "", "| Publisher | Object | SHA256 |", "| --- | --- | --- |"]
    lines += [f"| {o.publisher} | {o.url.rsplit('/', 1)[-1]} | `{o.sha256[:16]}…` |" for o in registry.objects]
    lines += ["", f"Licences: " + "; ".join(f"{k}: {v}" for k, v in registry.licences.items()), ""]
    lines += ["## Columns", "", f"{len(fields)} columns: {by_source['directory']} from the directory, {by_source['derived']} derived, ",
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
    return "\n".join(lines) + "\n"


def main() -> int:
    schema = yaml.safe_load((PACKAGE / "output_schema.yaml").read_text())
    registry = load_registry(PACKAGE / "sources.yaml")
    man_path = Path("results/manifest.json")  # relative to the working directory
    manifest = json.loads(man_path.read_text()) if man_path.is_file() else None
    out = Path("docs/DATA_DICTIONARY.md")
    out.parent.mkdir(exist_ok=True)
    out.write_text(render(schema, registry, manifest))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
