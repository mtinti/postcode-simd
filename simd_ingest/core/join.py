"""postcode_simd: the index with every edition joined on, one edition at a time.

join_edition adds one edition's columns by one merge on one data zone column, then checks
that the row count is unchanged and that no new column is empty. The configured editions,
in registry order, take the index to the explicit output contract. Order does not affect the
result; each join uses its own key. It is fixed so that a reader can follow it.
"""

from __future__ import annotations

import pandas as pd

from .checks import Report
from .phs import BANDS, FLAGS
from .sources import Registry

PHS_FIELDS = ["rank", *BANDS.values(), *FLAGS.values()]
GOV_FIELDS = ["uw_scotland_quintile", "uw_scotland_decile", "uw_scotland_vigintile"]
GEOGRAPHY = ["hb", "hscp", "ca"]
WIDTH = {"decile": 10, "quintile": 5, "vigintile": 20}


def simd_columns(edition: str) -> list:
    return [f"simd{edition}_{f}" for f in PHS_FIELDS + GOV_FIELDS]


def geography_columns(vintage: int) -> list:
    return [f"phs_dz{vintage}_{g}" for g in GEOGRAPHY]


def first_edition_of_vintage(registry: Registry, vintage: int) -> str:
    return next(e["key"] for e in registry.phs_editions if int(e["dz_vintage"]) == vintage)


def join_edition(table: pd.DataFrame, edition_table: pd.DataFrame, ed: dict, kind: str,
                 registry: Registry, report: Report, label: str = "join") -> pd.DataFrame:
    """One merge: look the record's data zone up in one edition table and copy its values on.

    kind is "phs" or "gov". The first PHS edition of each data-zone vintage also brings the
    PHS geography codes for that vintage, which are identical across the vintage's editions.
    """
    key, vintage = ed["key"], int(ed["dz_vintage"])
    dz_col = f"DataZone{vintage}Code"
    fields = PHS_FIELDS if kind == "phs" else GOV_FIELDS
    right = edition_table.set_index("dz_code")[fields].rename(columns={f: f"simd{key}_{f}" for f in fields})
    if kind == "phs" and key == first_edition_of_vintage(registry, vintage):
        geo = edition_table.set_index("dz_code")[GEOGRAPHY].rename(columns={g: f"phs_dz{vintage}_{g}" for g in GEOGRAPHY})
        right = pd.concat([geo, right], axis=1)
    before = len(table)
    out = table.merge(right, left_on=dz_col, right_index=True, how="left", validate="many_to_one").reset_index(drop=True)
    label = f"{label}.{kind}.{key}"
    report.equal(f"{label}.rows_unchanged", len(out), before, detail=f"{len(out):,} rows before and after the merge on {dz_col}")
    empty = int(out[list(right.columns)].isna().sum().sum())
    report.equal(f"{label}.every_record_matched", empty, 0,
                 detail=f"{len(right.columns)} columns added, {empty} empty cells")
    return out


def build_postcode_simd(index: pd.DataFrame, phs_tables: dict, gov_tables: dict, registry: Registry,
                        schema: dict, report: Report, label: str = "join", extra: pd.DataFrame | None = None) -> pd.DataFrame:
    """The ladder: the index, then one join per PHS edition, then one per government edition.
    The output schema supplies the column order and the natural key; label prefixes the checks
    so that the two tables of one build stay apart."""
    out = index
    for ed in registry.phs_editions:
        out = join_edition(out, phs_tables[ed["key"]], ed, "phs", registry, report, label)
    for ed in registry.govscot_editions:
        out = join_edition(out, gov_tables[ed["key"]], ed, "gov", registry, report, label)
    if extra is not None:
        # Columns computed beside the ladder, row-aligned to the index (the rurality placements).
        # The index itself stays what the source files say, which is what readback compares.
        report.equal(f"{label}.extra_rows_aligned", bool(extra.index.equals(index.index)), True)
        out = pd.concat([out, extra], axis=1)
    return finish(out, index, registry, [f["name"] for f in schema["fields"]], schema["key"], report, label)


def finish(table: pd.DataFrame, index: pd.DataFrame, registry: Registry, columns: list, key: list,
           report: Report, label: str = "join") -> pd.DataFrame:
    """Order the columns to the frozen schema and run the whole-table checks."""
    missing = [c for c in columns if c not in table.columns]
    extra = [c for c in table.columns if c not in columns]
    report.equal(f"{label}.schema_columns", {"missing": missing, "extra": extra}, {"missing": [], "extra": []})
    report.require()
    table = table[columns]
    added = table[[c for c in columns if c.startswith("simd") or c.startswith("phs_dz")]]
    report.equal(f"{label}.rows", len(table), len(index), detail="every accepted index record, no more")
    report.equal(f"{label}.primary_key_unique", int(table.duplicated(key).sum()), 0, detail=f"key {key}")
    simd_cols = [c for c in added.columns if c.startswith("simd")]
    geo_cols = [c for c in added.columns if c.startswith("phs_dz")]
    report.equal(f"{label}.simd_values_nonnull", int(added[simd_cols].isna().sum().sum()), 0)
    report.equal(f"{label}.geography_nonnull", int(added[geo_cols].isna().sum().sum()), 0)
    editions = len(registry.phs_editions)
    report.equal(f"{label}.logical_matches", int(added[[f"simd{e['key']}_rank" for e in registry.phs_editions]].notna().sum().sum()), len(table) * editions)
    for c in simd_cols:
        kind = c.rsplit("_", 1)[-1]
        if kind in WIDTH:
            report.equal(f"{label}.{c}.range", bool(added[c].between(1, WIDTH[kind]).all()), True)
        elif kind in ("most15pc", "least15pc"):
            report.equal(f"{label}.{c}.binary", bool(added[c].isin([0, 1]).all()), True)
    if registry.directory_rank:
        check = registry.directory_rank
        own = pd.to_numeric(table[check["column"]], errors="raise")
        report.equal(f"{label}.directory_rank_agreement", int(own.ne(table[f"simd{check['edition']}_rank"]).sum()), 0)
    return table


def attach(index: pd.DataFrame, simd: pd.DataFrame, gov: pd.DataFrame, registry: Registry) -> pd.DataFrame:
    """Re-lookup of every attached column from the long reference tables, used by readback to
    check a saved file against the sources independently of the ladder. Returns only the
    added columns."""
    added = {}
    for vintage in sorted({int(e["dz_vintage"]) for e in registry.phs_editions}):
        first = first_edition_of_vintage(registry, vintage)
        geo = simd[simd["edition"] == first].set_index("dz_code")[GEOGRAPHY]
        codes = index[f"DataZone{vintage}Code"]
        for g in GEOGRAPHY:
            added[f"phs_dz{vintage}_{g}"] = codes.map(geo[g])
    for ed in registry.phs_editions:
        key, vintage = ed["key"], int(ed["dz_vintage"])
        codes = index[f"DataZone{vintage}Code"]
        p = simd[simd["edition"] == key].set_index("dz_code")
        g = gov[gov["edition"] == key].set_index("dz_code")
        for f in PHS_FIELDS:
            added[f"simd{key}_{f}"] = codes.map(p[f])
        for f in GOV_FIELDS:
            added[f"simd{key}_{f}"] = codes.map(g[f])
    return pd.DataFrame(added, index=index.index)
