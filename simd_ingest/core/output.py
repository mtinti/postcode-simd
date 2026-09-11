"""Write the frozen schema to Parquet with table-level metadata, and read it back to verify."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from .checks import Report
from .join import attach
from .sources import Registry, sha256

ARROW = {"string": pa.string(), "date32": pa.date32(), "bool": pa.bool_(), "int8": pa.int8(), "int16": pa.int16()}

BAND_CONVENTION = (
    "Every band column reads 1 as most deprived. The PHS 2004 and 2006 population-weighted "
    "deciles and quintiles were re-derived from the published values, 11 - decile and 6 - "
    "quintile, so that they follow the ordering used by every other edition. Ranks and the "
    "Most15pc and Least15pc flags are as published in all editions. Columns named "
    "simd{edition}_pw_* are PHS population-weighted; columns named simd{edition}_uw_* are "
    "Scottish Government unweighted; the two must not be combined in one analysis. The "
    "vigintile is available only unweighted. No percentile is carried."
)


def logical_fingerprint(table: pd.DataFrame) -> str:
    """Fingerprint of the rows alone. Unlike the Parquet hash it ignores embedded metadata,
    so two builds with the same data and a different decision log share it."""
    import hashlib
    return hashlib.sha256(pd.util.hash_pandas_object(table, index=False).values.tobytes()).hexdigest()


def load_schema(path: Path) -> dict:
    raw = yaml.safe_load(Path(path).read_text())
    return {"version": raw["version"], "fields": raw["fields"], "sha256": sha256(path)}


def arrow_schema(schema: dict, metadata: dict) -> pa.Schema:
    fields = [pa.field(f["name"], ARROW[f["type"]], nullable=bool(f["nullable"])) for f in schema["fields"]]
    return pa.schema(fields, metadata={k: (v if isinstance(v, str) else json.dumps(v)) for k, v in metadata.items()})


def _column(series: pd.Series, field: dict) -> pa.Array:
    kind = field["type"]
    if kind == "date32":
        values = [None if pd.isna(v) else v.date() for v in series]
        return pa.array(values, type=pa.date32())
    if kind == "string":
        values = [None if (v is None or (isinstance(v, float) and pd.isna(v))) else str(v) for v in series]
        return pa.array(values, type=pa.string())
    if kind == "bool":
        return pa.array(series.astype(bool).tolist(), type=pa.bool_())
    return pa.array(series.astype("int64").tolist(), type=ARROW[kind])


def write_table(table: pd.DataFrame, schema: dict, path: Path, metadata: dict) -> str:
    """Write to a temporary sibling, then rename into place. Returns the file hash."""
    arrow = arrow_schema(schema, metadata)
    arrays = [_column(table[f["name"]], f) for f in schema["fields"]]
    pa_table = pa.Table.from_arrays(arrays, schema=arrow)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    pq.write_table(pa_table, part, compression="zstd", write_statistics=True)
    os.replace(part, path)
    return sha256(path)


def readback(path: Path, schema: dict, index: pd.DataFrame, simd: pd.DataFrame, gov: pd.DataFrame,
             registry: Registry, report: Report) -> dict:
    """Reopen the saved file and compare it with the accepted sources, not with memory.

    Original columns are compared with the index built from the source files. SIMD and
    geography columns are re-looked-up from the saved file's own data-zone codes, so a
    value that drifted between build and save is caught.
    """
    file = pq.ParquetFile(path)
    saved_schema = file.schema_arrow
    expected_names = [f["name"] for f in schema["fields"]]
    report.equal("readback.column_names", saved_schema.names, expected_names)
    report.equal("readback.column_types", [str(t) for t in saved_schema.types], [str(ARROW[f["type"]]) for f in schema["fields"]])
    report.equal("readback.nullability", [f.nullable for f in saved_schema], [bool(f["nullable"]) for f in schema["fields"]])
    meta = saved_schema.metadata or {}
    report.equal("readback.metadata_present", sorted(k.decode() for k in meta), sorted(["band_convention", "schema_version", "spd_release", "sources", "decisions_sha256"]))

    saved = file.read().to_pandas(date_as_object=False)
    report.equal("readback.rows", len(saved), len(index))
    report.equal("readback.primary_key_unique", int(saved.duplicated(["pc_norm", "introduced_on"]).sum()), 0)

    # Source fidelity for the original and derived index columns.
    idx = index.reset_index(drop=True)
    for column in idx.columns:
        a, b = saved[column], idx[column]
        if column in ("introduced_on", "deleted_on"):
            a, b = pd.to_datetime(a), pd.to_datetime(b)
        elif column == "is_current":
            a, b = a.astype(bool), b.astype(bool)
        else:
            a, b = a.astype("string"), b.astype("string")
        same = (a.eq(b) | (a.isna() & b.isna()))
        if not same.all():
            report.add(f"readback.index.{column}", False, f"{int((~same).sum())} value(s) differ from source")
    report.add("readback.index_columns", not report.blocking_failures, f"{len(idx.columns)} index columns compared")

    # Re-lookup every attached value from the saved file's own data-zone codes.
    expected = attach(saved, simd, gov, registry)
    differing = {c: int(saved[c].astype("int64" if not c.startswith("phs_dz") else "string").ne(expected[c].astype("int64" if not c.startswith("phs_dz") else "string")).sum()) for c in expected.columns}
    bad = {c: n for c, n in differing.items() if n}
    report.equal("readback.attached_values", bad, {}, detail=f"{len(expected.columns)} attached columns re-looked-up" if not bad else f"differ: {bad}")
    return {"rows": len(saved), "columns": len(saved.columns), "sha256": sha256(path),
            "logical_fingerprint": logical_fingerprint(saved),
            "note": "sha256 covers the file including embedded provenance metadata; logical_fingerprint covers the rows only"}


def manifest(registry: Registry, schema: dict, decisions_sha256: str, baselines_sha256: str, mode: str,
             output: dict, report: Report, extra: dict) -> dict:
    return {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "spd_release": registry.spd_release,
        "source_mode": mode,
        "schema_version": schema["version"],
        "schema_sha256": schema["sha256"],
        "registry_sha256": registry.sha256,
        "decisions_sha256": decisions_sha256,
        "baselines_sha256": baselines_sha256,
        "band_convention": BAND_CONVENTION,
        "licences": registry.licences,
        "sources": [{"key": o.key, "publisher": o.publisher, "url": o.url, "sha256": o.sha256,
                     "files": [{"path": f.path, "sha256": f.sha256, "role": f.role} for f in o.files]} for o in registry.objects],
        "output": output,
        "summary": report.summary(),
        "diagnostic_differences": [c.name for c in report.diagnostic_differences],
        "checks": report.to_records(),
        **extra,
    }
