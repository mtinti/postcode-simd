"""Checks that need both reference tables: PHS against Scottish Government.

Blocking: same zones, same ranks, and the pinned divergence fingerprints between the
canonical PHS Scotland-level bands and the published unweighted bands.
Diagnostic: reconstructing the PHS population-weighted bands from rank and population.
"""

from __future__ import annotations

import pandas as pd

from .checks import DIAGNOSTIC, Report, divergence, reconstruct_population_bands
from .phs import SCOPE


def cross_check(simd: pd.DataFrame, gov: pd.DataFrame, baselines: dict, report: Report) -> None:
    expected_recon = baselines.get("reconstruction_expected", {})
    for edition in simd["edition"].unique():
        p = simd[simd["edition"] == edition].set_index("dz_code")
        g = gov[gov["edition"] == edition].set_index("dz_code")
        label = f"cross.{edition}"
        if not report.equal(f"{label}.same_zones", set(p.index) == set(g.index), True):
            continue
        g = g.reindex(p.index)
        report.equal(f"{label}.rank_identical", int(p["rank"].ne(g["rank"]).sum()), 0)
        for band, width in (("Decile", "decile"), ("Quintile", "quintile")):
            actual = divergence(p[f"pw_scotland_{width}"], g[f"uw_scotland_{width}"])
            report.equal(f"{label}.divergence.{width}", actual, baselines["divergence"][edition][band])

        # Diagnostic: does the midpoint rule on the published population reproduce PHS?
        expected = expected_recon.get(edition, {})
        for scope, column in SCOPE.items():
            groups = pd.Series("scotland", index=p.index) if column is None else p[column.lower()]
            recon = reconstruct_population_bands(p["rank"], g["population"], groups)
            for measure in ("decile", "quintile"):
                published = p[f"pw_{scope}_{measure}"]
                diff = recon[measure].ne(published)
                actual = {z: {"published": int(published[z]), "reconstructed": int(recon.loc[z, measure])} for z in p.index[diff]}
                report.equal(f"{label}.reconstruction.{scope}.{measure}", actual,
                             expected.get(f"{scope}_{measure}", {}), severity=DIAGNOSTIC,
                             detail=f"{len(actual)} zone(s) differ from the published value")
            if scope == "scotland":
                for flag in ("most15pc", "least15pc"):
                    diff = recon[flag].ne(p[flag])
                    actual = {z: {"published": int(p.loc[z, flag]), "reconstructed": int(recon.loc[z, flag])} for z in p.index[diff]}
                    report.equal(f"{label}.reconstruction.{flag}", actual, expected.get(flag, {}),
                                 severity=DIAGNOSTIC, detail=f"{len(actual)} zone(s) differ from the published flag")
