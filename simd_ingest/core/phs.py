"""PHS SIMD, one edition at a time, in two visible steps.

read_phs_source     the file as published: typed, schema checked, ranks dense, nothing changed
canonicalise_phs    the edition table the joins use: bands turned so that 1 means most deprived,
                    which only the 2004 and 2006 files need; ranks and 15% flags never touched

build_phs_bands stacks the six canonical tables into one long table for readback and the trace.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .checks import Report
from .sources import Registry

# Source column suffix -> canonical name. The pw_ prefix marks PHS population weighting.
BANDS = {
    "CountryDecile": "pw_scotland_decile", "CountryQuintile": "pw_scotland_quintile",
    "HBDecile": "pw_hb_decile", "HBQuintile": "pw_hb_quintile",
    "HSCPDecile": "pw_hscp_decile", "HSCPQuintile": "pw_hscp_quintile",
    "CADecile": "pw_ca_decile", "CAQuintile": "pw_ca_quintile",
}
FLAGS = {"Most15pc": "most15pc", "Least15pc": "least15pc"}
# The PHS files order the geography columns differently by vintage. Parse by name.
GEOGRAPHY_ORDER = {2001: ["DataZone", "IntZone", "CA", "HSCP", "HB"], 2011: ["DataZone", "IntZone", "HB", "HSCP", "CA"]}
# Which geography column a band is computed within; None means all of Scotland.
SCOPE = {"scotland": None, "hb": "HB", "hscp": "HSCP", "ca": "CA"}

COLUMNS = ["edition", "dz_vintage", "dz_code", "hb", "hscp", "ca", "rank", *BANDS.values(), *FLAGS.values()]


def read_phs_source(ed: dict, root: Path, report: Report) -> pd.DataFrame:
    """One PHS file exactly as published, with its numbers typed and its shape checked."""
    key, prefix, vintage = ed["key"], ed["prefix"], int(ed["dz_vintage"])
    label = f"phs.{key}.source"
    d = pd.read_csv(Path(root) / ed["file"], dtype=str, keep_default_na=False, encoding="utf-8-sig")
    expected = GEOGRAPHY_ORDER[vintage] + [prefix + s for s in ["Rank", *BANDS, *FLAGS]]
    report.equal(f"{label}.schema", list(d.columns), expected)
    report.equal(f"{label}.rows", len(d), ed["rows"])
    report.equal(f"{label}.key_unique", bool(d["DataZone"].is_unique), True)
    report.equal(f"{label}.blanks", int(d.eq("").sum().sum()), 0)
    for s in ["Rank", *BANDS, *FLAGS]:
        d[prefix + s] = d[prefix + s].astype("int64")
    report.equal(f"{label}.rank_dense", sorted(d[prefix + "Rank"]) == list(range(1, ed["rows"] + 1)), True)
    for src, canon in BANDS.items():
        k = 10 if canon.endswith("decile") else 5
        report.equal(f"{label}.{src}.range", bool(d[prefix + src].between(1, k).all()), True)
    for src in FLAGS:
        report.equal(f"{label}.{src}.binary", bool(d[prefix + src].isin([0, 1]).all()), True)
    return d


def canonicalise_phs(ed: dict, source: pd.DataFrame, report: Report) -> pd.DataFrame:
    """The edition table the joins use. The only transformation in the pipeline lives here:
    for editions flagged invert_bands, decile becomes 11 - decile and quintile 6 - quintile."""
    key, prefix, vintage = ed["key"], ed["prefix"], int(ed["dz_vintage"])
    label = f"phs.{key}"
    rank = source[prefix + "Rank"]
    out = pd.DataFrame({"edition": key, "dz_vintage": vintage, "dz_code": source["DataZone"],
                        "hb": source["HB"], "hscp": source["HSCP"], "ca": source["CA"], "rank": rank})
    for src, canon in BANDS.items():
        k = 10 if canon.endswith("decile") else 5
        published = source[prefix + src]
        out[canon] = (k + 1 - published) if ed["invert_bands"] else published
        # After canonicalisation, bands must never decrease as rank increases within the
        # geography they were computed in. This is the direction check.
        scope = SCOPE[canon.split("_")[1]]
        groups = pd.Series("scotland", index=source.index) if scope is None else source[scope]
        ordered = pd.DataFrame({"rank": rank, "band": out[canon], "group": groups}).sort_values("rank")
        report.equal(f"{label}.{canon}.monotone", int(ordered.groupby("group")["band"].diff().lt(0).sum()), 0)
    for src, canon in FLAGS.items():
        out[canon] = source[prefix + src]
    # Semantic anchors: the most deprived zone is flagged Most15pc and not Least15pc.
    top, bottom = out.loc[rank.idxmin()], out.loc[rank.idxmax()]
    report.equal(f"{label}.flag_anchors", [int(top["most15pc"]), int(top["least15pc"]), int(bottom["most15pc"]), int(bottom["least15pc"])], [1, 0, 0, 1])
    report.equal(f"{label}.rank1_in_band1", [int(top[c]) for c in BANDS.values()], [1] * len(BANDS))
    report.add(f"{label}.inverted", True, "bands inverted from source: 11 - decile, 6 - quintile" if ed["invert_bands"] else "bands as published")
    return out[COLUMNS]


def build_phs_bands(registry: Registry, root: Path, report: Report) -> pd.DataFrame:
    """All six canonical edition tables stacked, for readback and the trace."""
    frames = [canonicalise_phs(ed, read_phs_source(ed, root, report), report) for ed in registry.phs_editions]
    table = pd.concat(frames, ignore_index=True)
    report.equal("phs.total_rows", len(table), sum(e["rows"] for e in registry.phs_editions))
    return table
