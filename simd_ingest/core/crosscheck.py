"""The one check that needs both reference tables: PHS and the Scottish Government must
describe the same data zones with the same ranks in every edition. Nothing is calculated
and no band is compared; both sources are trusted for their own values."""

from __future__ import annotations

import pandas as pd

from .checks import Report


def cross_check(simd: pd.DataFrame, gov: pd.DataFrame, baselines: dict, report: Report) -> None:
    for edition in simd["edition"].unique():
        p = simd[simd["edition"] == edition].set_index("dz_code")
        g = gov[gov["edition"] == edition].set_index("dz_code")
        label = f"cross.{edition}"
        if not report.equal(f"{label}.same_zones", set(p.index) == set(g.index), True):
            continue
        report.equal(f"{label}.rank_identical", int(p["rank"].ne(g.reindex(p.index)["rank"]).sum()), 0,
                     detail=f"{len(p):,} zones, ranks identical in both sources")
