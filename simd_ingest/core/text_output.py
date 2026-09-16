"""The CSV rendering of a table, and the row digest a database load is checked against.

One contract, simd_ingest/export_contract.yaml, decides which columns leave the build and how a
value becomes text. The same rendering feeds both: the CSV writes an empty cell for a null and
for a blank, while the digest writes a marker for the null, so the two can still be told apart
after a load. Both are computed from the accepted table, never from a re-read of the file.
"""

from __future__ import annotations

import datetime as dt
import gzip
import hashlib

from pathlib import Path

import pandas as pd
import yaml

from .checks import Report
from .sources import sha256


class ReservedCharacter(ValueError):
    """Source text contains a character the digest framing needs. Never stripped."""


def load_contract(path: Path) -> dict:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if raw.get("version") != 1:
        raise ValueError(f"Unsupported export contract version {raw.get('version')!r}")
    if raw["digest"]["version"] != 1 or raw["digest"]["hash"] != "sha256":
        raise ValueError("Unsupported digest definition")
    raw["sha256"] = sha256(path)
    return raw


def exported_columns(schema: dict, contract: dict, table: str) -> list:
    """The schema's column order, minus the columns this contract does not export."""
    spec = contract["tables"][table]
    excluded = set(spec["exclude"])
    names = [f["name"] for f in schema["fields"]]
    missing = excluded - set(names)
    if missing:
        raise ValueError(f"{table}: excluded columns are not in the schema: {sorted(missing)}")
    return [name for name in names if name not in excluded]


def render(table: pd.DataFrame, schema: dict, columns: list, contract: dict) -> pd.DataFrame:
    """Every exported value as text, with nulls marked. Only the schema's date, boolean and
    integer fields are converted; text is written exactly as stored."""
    kinds = {f["name"]: f["type"] for f in schema["fields"]}
    marker, reserved = contract["digest"]["null_marker"], contract["digest"]["reserved"]
    date_format, false_true = contract["values"]["date"], contract["values"]["boolean"]
    out = {}
    for name in columns:
        column, kind = table[name], kinds[name]
        if kind == "date32":
            values = column.map(lambda v: marker if v is None or pd.isna(v)
                                else (v if isinstance(v, dt.date) else pd.Timestamp(v).date()).strftime(date_format))
        elif kind == "bool":
            values = column.map(lambda v: false_true[1] if bool(v) else false_true[0])
        elif kind == "string":
            values = column.astype("string")
            found = [c for c in reserved if values.str.contains(c, regex=False, na=False).any()]
            if found:
                raise ReservedCharacter(f"{name}: source text contains {found!r}, which the digest framing reserves")
            values = values.fillna(marker)
        else:
            values = column.map(lambda v: str(int(v)))
        out[name] = values.astype("string")
    return pd.DataFrame(out, index=table.index)[columns]


def write_csv(rendered: pd.DataFrame, contract: dict, path: Path) -> dict:
    """The rendered table as CSV, nulls and blanks alike written as an empty cell."""
    dialect = contract["dialect"]
    path = Path(path)
    frame = rendered.replace(contract["digest"]["null_marker"], contract["values"]["empty"])
    text = frame.to_csv(index=False, sep=dialect["delimiter"], lineterminator=dialect["line_ending"])
    body = text.encode(dialect["encoding"])
    # The same rows must give the same bytes, as they do for the Parquet: gzip stores both a
    # timestamp and, when it can see one, the file name, so neither may reach the header.
    with open(path, "wb") as fh, gzip.GzipFile(filename="", fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(body)
    return {"file": path.name, "sha256": sha256(path), "bytes": path.stat().st_size,
            "uncompressed_bytes": len(body), "rows": len(rendered), "columns": len(rendered.columns),
            "compression": dialect["compression"]}


def row_digest(rendered: pd.DataFrame, contract: dict) -> dict:
    """One SHA-256 per row over the marked, separated fields; the signed eight-byte prefixes
    summed exactly, so the total does not depend on row order."""
    spec = contract["digest"]
    separator, size, signed = spec["separator"], spec["prefix_bytes"], spec["signed"]
    joined = rendered.iloc[:, 0]
    for name in rendered.columns[1:]:
        joined = joined + separator + rendered[name]
    total = 0
    for line in joined.to_numpy():
        total += int.from_bytes(hashlib.sha256(line.encode("utf-8")).digest()[:size], "big", signed=signed)
    return {"version": spec["version"], "rows": len(rendered), "total": str(total),
            "note": "compact probabilistic check for accidental load corruption, not a proof of identity"}


def readback_csv(path: Path, rendered: pd.DataFrame, contract: dict, report: Report, label: str) -> None:
    """Reopen the saved file with ingestion's reader settings and compare every cell with the
    accepted table. A row count would not catch a shifted column or a lost leading zero."""
    expected = rendered.replace(contract["digest"]["null_marker"], contract["values"]["empty"])
    with gzip.open(path, "rt", encoding=contract["dialect"]["encoding"], newline="") as fh:
        saved = pd.read_csv(fh, dtype=str, keep_default_na=False, sep=contract["dialect"]["delimiter"])
    report.equal(f"{label}.header", list(saved.columns), list(expected.columns))
    report.equal(f"{label}.rows", len(saved), len(expected))
    report.require()
    differences = {}
    for name in expected.columns:
        differs = int((saved[name].to_numpy() != expected[name].to_numpy()).sum())
        if differs:
            differences[name] = differs
    report.equal(f"{label}.cells", differences, {}, detail=f"{len(expected.columns)} columns compared")


def attribution_text(contract: dict, registry, manifest_like: dict) -> str:
    """The acknowledgements every source requires, beside the files they apply to."""
    lines = ["Postcode-SIMD reference tables, CSV rendering", "",
             f"Built {manifest_like['built_at'][:19]}Z from Scottish Postcode Directory "
             f"{registry.spd_release} and Scottish Statistics Postcode Lookup {registry.sspl_release}.", ""]
    lines += ["Attribution", ""] + [f"  {line}" for line in contract["attribution"]] + [""]
    lines += ["Columns not included", "",
              "  " + contract["exclude_reasons"]["minimisation"].strip().replace("\n", "\n  "), "",
              "  " + contract["exclude_reasons"]["licensing"].strip().replace("\n", "\n  "), ""]
    for name, spec in contract["tables"].items():
        lines.append(f"  {spec['file']}: {', '.join(spec['exclude'])}")
    lines += ["", "Files", ""]
    for name, info in manifest_like["tables"].items():
        csv = info["csv"]
        lines.append(f"  {csv['file']}  {csv['rows']:,} rows x {csv['columns']} columns  sha256 {csv['sha256']}")
    lines += ["", "Read every column as text first, keeping leading zeros and literal values such",
              "as NA; restore the declared types afterwards. In this CSV a null and a source blank",
              "are the same empty cell. See docs/DATA_DICTIONARY.md for how to tell them apart.", ""]
    return "\n".join(lines)
