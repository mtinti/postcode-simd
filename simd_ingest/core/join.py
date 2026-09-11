"""postcode_simd: the index with all six editions attached, in the frozen column order."""

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


def attach(index: pd.DataFrame, simd: pd.DataFrame, gov: pd.DataFrame, registry: Registry) -> pd.DataFrame:
    """Look up every edition through the data zone of its vintage. Returns only the added columns."""
    added = {}
    for vintage in sorted({int(e["dz_vintage"]) for e in registry.phs_editions}):
        first = next(e["key"] for e in registry.phs_editions if int(e["dz_vintage"]) == vintage)
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


def build_postcode_simd(index: pd.DataFrame, simd: pd.DataFrame, gov: pd.DataFrame,
                        registry: Registry, columns: list, report: Report) -> pd.DataFrame:
    added = attach(index, simd, gov, registry)
    table = pd.concat([index, added], axis=1)
    missing = [c for c in columns if c not in table.columns]
    extra = [c for c in table.columns if c not in columns]
    report.equal("join.schema_columns", {"missing": missing, "extra": extra}, {"missing": [], "extra": []})
    table = table[columns]

    report.equal("join.rows", len(table), registry.spd_published_totals["all"])
    report.equal("join.primary_key_unique", int(table.duplicated(["pc_norm", "introduced_on"]).sum()), 0)
    simd_cols = [c for c in added.columns if c.startswith("simd")]
    geo_cols = [c for c in added.columns if c.startswith("phs_dz")]
    report.equal("join.simd_values_nonnull", int(added[simd_cols].isna().sum().sum()), 0)
    report.equal("join.geography_nonnull", int(added[geo_cols].isna().sum().sum()), 0)
    editions = len(registry.phs_editions)
    report.equal("join.logical_matches", int(added[[f"simd{e['key']}_rank" for e in registry.phs_editions]].notna().sum().sum()), len(table) * editions)
    for c in simd_cols:
        kind = c.rsplit("_", 1)[-1]
        if kind in WIDTH:
            report.equal(f"join.{c}.range", bool(added[c].between(1, WIDTH[kind]).all()), True)
        elif kind in ("most15pc", "least15pc"):
            report.equal(f"join.{c}.binary", bool(added[c].isin([0, 1]).all()), True)
    own = table["ScottishIndexOfMultipleDeprivation2020Rank"].astype("int64")
    report.equal("join.directory_rank_agreement", int(own.ne(table["simd2020v2_rank"]).sum()), 0)
    return table
