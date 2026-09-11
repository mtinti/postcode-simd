"""phs_bands: the six PHS editions as one long table, one row per edition and data zone,
carrying rank, the eight population-weighted bands, the two 15% flags and PHS geography codes.

Bands are canonicalised so that 1 means most deprived everywhere. Only the 2004 and 2006
population-weighted bands need inverting; ranks and the 15% flags are never touched.
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


def build_phs_bands(registry: Registry, root: Path, report: Report) -> pd.DataFrame:
    frames = []
    for ed in registry.phs_editions:
        frames.append(_read_edition(ed, Path(root) / ed["file"], report))
    table = pd.concat(frames, ignore_index=True)[COLUMNS]
    report.equal("phs.total_rows", len(table), sum(e["rows"] for e in registry.phs_editions))
    return table


def _read_edition(ed: dict, path: Path, report: Report) -> pd.DataFrame:
    key, prefix, vintage = ed["key"], ed["prefix"], int(ed["dz_vintage"])
    label = f"phs.{key}"
    d = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    expected = GEOGRAPHY_ORDER[vintage] + [prefix + s for s in ["Rank", *BANDS, *FLAGS]]
    report.equal(f"{label}.schema", list(d.columns), expected)
    report.equal(f"{label}.rows", len(d), ed["rows"])
    report.equal(f"{label}.key_unique", bool(d["DataZone"].is_unique), True)
    report.equal(f"{label}.blanks", int(d.eq("").sum().sum()), 0)
    for s in ["Rank", *BANDS, *FLAGS]:
        d[prefix + s] = d[prefix + s].astype("int64")
    rank = d[prefix + "Rank"]
    report.equal(f"{label}.rank_dense", sorted(rank) == list(range(1, ed["rows"] + 1)), True)

    out = pd.DataFrame({"edition": key, "dz_vintage": vintage, "dz_code": d["DataZone"],
                        "hb": d["HB"], "hscp": d["HSCP"], "ca": d["CA"], "rank": rank})
    for src, canon in BANDS.items():
        k = 10 if canon.endswith("decile") else 5
        published = d[prefix + src]
        report.equal(f"{label}.{canon}.range", bool(published.between(1, k).all()), True)
        out[canon] = (k + 1 - published) if ed["invert_bands"] else published
        # After canonicalisation, bands must never decrease as rank increases within the
        # geography they were computed in. This is the direction check.
        scope = SCOPE[canon.split("_")[1]]
        groups = pd.Series("scotland", index=d.index) if scope is None else d[scope]
        ordered = pd.DataFrame({"rank": rank, "band": out[canon], "group": groups}).sort_values("rank")
        report.equal(f"{label}.{canon}.monotone", int(ordered.groupby("group")["band"].diff().lt(0).sum()), 0)
    for src, canon in FLAGS.items():
        out[canon] = d[prefix + src]
        report.equal(f"{label}.{canon}.binary", bool(out[canon].isin([0, 1]).all()), True)
    # Semantic anchors: the most deprived zone is flagged Most15pc and not Least15pc.
    top, bottom = out.loc[rank.idxmin()], out.loc[rank.idxmax()]
    report.equal(f"{label}.flag_anchors", [int(top["most15pc"]), int(top["least15pc"]), int(bottom["most15pc"]), int(bottom["least15pc"])], [1, 0, 0, 1])
    report.equal(f"{label}.rank1_in_band1", [int(top[c]) for c in BANDS.values()], [1] * len(BANDS))
    return out
