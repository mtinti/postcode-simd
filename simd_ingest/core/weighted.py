"""Computed population-weighted bands of the SIMD domain ranks (docs/plans/Weighted_Domain_Bands_Plan.md).

The only values in the tables the build computes rather than copies: nobody publishes weighted
domain bands. They are cut per data zone, from the Government shapefile's own rows, every zone of
the edition once with that edition's population, never from a postcode table. The rule is a
population midpoint; it must reproduce PHS's published overall Scotland bands, from the overall
rank and the same population, before any domain band is used (gate_against_phs).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .checks import Report
from .sources import declared_domains

WEIGHTED_BANDS = {"quintile": 5, "decile": 10}


def weighted_domain_fields(ed: dict) -> list:
    """The computed fields of one edition, without the edition prefix: each published domain's
    weighted quintile and decile, then the population they were weighted by."""
    return [f"{d}_domain_pw_scotland_{b}" for d in declared_domains(ed) for b in WEIGHTED_BANDS] + ["population"]


def population_bands(rank, population, k: int) -> np.ndarray:
    """Each zone's band of k by the population midpoint, in input order.

    Zones are ordered by rank and equal ranks are one block: its cumulative population is taken
    through the whole block, minus half the block's population, so equal ranks share a band.
    band = max(1, min(k, ceil(midpoint * k / total))); a zero-population block ranked first has
    midpoint 0 and goes to band 1. Exact integer arithmetic: twice the midpoint is a whole number.
    """
    frame = pd.DataFrame({"rank": np.asarray(rank, dtype="float64"), "pop": np.asarray(population, dtype="int64")})
    if frame["rank"].isna().any() or frame["pop"].isna().any() or (frame["pop"] < 0).any():
        raise ValueError("ranks and populations must be complete, and populations not negative")
    total = int(frame["pop"].sum())
    if total <= 0:
        raise ValueError("a total population of zero has nothing to weight by")
    block = frame.groupby("rank", sort=True)["pop"].sum()
    twice_mid = 2 * block.cumsum() - block                       # 2 * (cumulative - half the block)
    numerator = frame["rank"].map(twice_mid).to_numpy(dtype="int64") * k
    band = -(-numerator // (2 * total))                         # ceil, exactly
    return np.clip(band, 1, k)


def add_weighted_domain_bands(gov: pd.DataFrame, ed: dict) -> pd.DataFrame:
    """The edition table with each published domain's computed quintile and decile beside it. A
    declared rank missing from the file is already a blocking failure of the reader; it is
    skipped here, so that failure is reported as itself."""
    out = gov.copy()
    for d in [d for d in declared_domains(ed) if f"{d}_domain_rank" in out]:
        for band, k in WEIGHTED_BANDS.items():
            out[f"{d}_domain_pw_scotland_{band}"] = population_bands(out[f"{d}_domain_rank"], out["population"], k)
    return out


def gate_against_phs(phs: pd.DataFrame, gov: pd.DataFrame, key: str, report: Report) -> None:
    """The rule must reproduce PHS's published Scotland quintile and decile exactly, from the
    overall rank and this edition's population, on every zone, or no computed band is trusted."""
    both = phs[["dz_code", "rank", "pw_scotland_quintile", "pw_scotland_decile"]].merge(
        gov[["dz_code", "population"]], on="dz_code", how="inner", validate="one_to_one")
    report.equal(f"weighted.{key}.zones", len(both), len(gov))
    for band, k in WEIGHTED_BANDS.items():
        mine = population_bands(both["rank"], both["population"], k)
        wrong = int((mine != both[f"pw_scotland_{band}"].to_numpy()).sum())
        report.equal(f"weighted.{key}.reproduces_phs_scotland_{band}", wrong, 0,
                     detail=f"the rule against PHS's published {band}: {wrong} zones differ")


def observe_shares(gov: pd.DataFrame, ed: dict, report: Report) -> None:
    """The population share of each computed band, on the complete source zones, as observations:
    each within a few hundredths of a percentage point of an equal share."""
    total = gov["population"].sum()
    for d in declared_domains(ed):
        for band, k in WEIGHTED_BANDS.items():
            shares = gov.groupby(f"{d}_domain_pw_scotland_{band}")["population"].sum() / total * 100
            report.observe(f"weighted.{ed['key']}.{d}.{band}.max_share_deviation_pp",
                           round(float((shares - 100 / k).abs().max()), 4))
