"""Scottish Government unweighted bands and population, one edition at a time, read from the
shapefile attribute tables; the published domain bands, read from the statistics.gov.scot
datasets and admitted only where their ranks are ours. Nothing is calculated and nothing needs
inverting."""

from __future__ import annotations

import functools
from pathlib import Path

import numpy as np
import pandas as pd
from dbfread import DBF

from .checks import Report
from .weighted import add_weighted_domain_bands, weighted_domain_fields
from .sources import (DOMAIN_BANDS, DOMAINS, RANK_SOURCES_DISAGREE, Registry, banded_domains, declared_domains,
                      domain_band_fields, status_domains)

COLUMNS = ["edition", "dz_vintage", "dz_code", "rank", "uw_scotland_quintile", "uw_scotland_decile",
           "uw_scotland_vigintile", "population"]
WIDTH = {"uw_scotland_quintile": 5, "uw_scotland_decile": 10, "uw_scotland_vigintile": 20}


def read_dbf(path: Path) -> pd.DataFrame:
    """The attribute table of a shapefile as a DataFrame with lower-case column names."""
    return pd.DataFrame(iter(DBF(str(path), lowernames=True)))


def read_gov_edition(ed: dict, root: Path, report: Report) -> pd.DataFrame:
    """One edition's table: the declared columns picked by name, typed and checked."""
    key, cols, label = ed["key"], ed["columns"], f"govscot.{ed['key']}"
    d = read_dbf(Path(root) / ed["file"])
    missing = [c for c in cols.values() if c not in d.columns]
    if not report.equal(f"{label}.columns_present", missing, [], detail=f"missing {missing}" if missing else "all declared columns present"):
        return pd.DataFrame(columns=COLUMNS)
    # Do not truncate a future file's fractional values when converting to integers.
    for kind, column in cols.items():
        if kind != "datazone":
            values = pd.to_numeric(d[column], errors="raise")
            report.equal(f"{label}.{kind}.integral", bool((values.notna() & values.mod(1).eq(0)).all()), True)
    report.require()
    out = pd.DataFrame({
        "edition": key, "dz_vintage": int(ed["dz_vintage"]), "dz_code": d[cols["datazone"]].astype(str),
        "rank": d[cols["rank"]].astype("int64"),
        "uw_scotland_quintile": d[cols["quintile"]].astype("int64"),
        "uw_scotland_decile": d[cols["decile"]].astype("int64"),
        "uw_scotland_vigintile": d[cols["vigintile"]].astype("int64"),
        "population": d[cols["population"]].astype("int64"),
    })
    # Domain ranks, copied exactly as published. They are not whole numbers: many end in .5 and
    # ties are only mostly averaged, so nothing here recalculates or rounds them. A value that is
    # not a whole multiple of 0.5, is outside 1 to the zone count, or is missing is a corrupted
    # source, not a tie.
    for domain in declared_domains(ed):
        column = ed["domains"][domain]
        if not report.add(f"{label}.{domain}_domain.present", column in d.columns, f"column {column}"):
            continue
        values = pd.to_numeric(d[column], errors="coerce").astype("float64")
        report.equal(f"{label}.{domain}_domain.complete", int(values.isna().sum()), 0)
        report.equal(f"{label}.{domain}_domain.half_units", int(((values * 2) % 1 != 0).sum()), 0)
        report.equal(f"{label}.{domain}_domain.range", bool(values.between(1, ed["rows"]).all()), True)
        shared = values.value_counts()
        report.observe(f"{label}.{domain}_domain.tied_values", int((shared > 1).sum()))
        out[f"{domain}_domain_rank"] = values.to_numpy()
    report.equal(f"{label}.rows", len(out), ed["rows"])
    report.equal(f"{label}.key_unique", bool(out["dz_code"].is_unique), True)
    report.equal(f"{label}.rank_dense", sorted(out["rank"]) == list(range(1, ed["rows"] + 1)), True)
    report.equal(f"{label}.population_nonnegative", bool(out["population"].ge(0).all()), True)
    ordered = out.sort_values("rank")
    for band, k in WIDTH.items():
        report.equal(f"{label}.{band}.range", bool(out[band].between(1, k).all()), True)
        report.equal(f"{label}.{band}.monotone", int(ordered[band].diff().lt(0).sum()), 0)
    if ed.get("bands"):
        report.require()
        out = read_published_bands(ed, root, report, out)
    # Computed, not published: the population-weighted bands of each domain rank, cut here from
    # every zone of the edition once (core/weighted.py). The build checks the rule against PHS.
    return add_weighted_domain_bands(out, ed)


# The published datasets name the domains in words; the registry's vocabulary is fixed.
PUBLISHED_DOMAINS = {"Income": "income", "Employment": "employment", "Health": "health",
                     "Education Skills And Training": "education", "Access To Services": "access",
                     "Crime": "crime", "Housing": "housing", "SIMD": "overall"}
PUBLISHED_COLUMNS = ["FeatureCode", "FeatureName", "FeatureType", "DateCode", "Measurement", "Units", "Value", "SIMD Domain"]
MEASUREMENTS = ["Rank", "Quintile", "Decile", "Vigintile"]


@functools.lru_cache(maxsize=4)
def _published(path: str) -> pd.DataFrame:
    """One statistics.gov.scot dataset, long format, read once per build."""
    return pd.read_csv(path, dtype={"FeatureCode": str, "FeatureName": str, "FeatureType": str, "Units": str,
                                    "Measurement": str, "SIMD Domain": str})


def read_published_bands(ed: dict, root: Path, report: Report, gov: pd.DataFrame) -> pd.DataFrame:
    """The edition's published domain bands, as columns beside the shapefile table `gov`.

    Every band is copied as published, never derived: the publisher places some tied zones in
    adjacent bands, which no rule on the rank alone reproduces. A band belongs to the ranking it
    was cut from, so every published rank must equal the shapefile's, or differ in one of the
    declared ways, zone by zone. Anything else is a different ranking and stops the build.
    """
    bands, key = ed["bands"], ed["key"]
    label = f"govscot.{key}.bands"
    raw = _published(str(Path(root) / bands["file"]))
    if not report.equal(f"{label}.columns", list(raw.columns), PUBLISHED_COLUMNS):
        return gov
    # The whole file first: every year in it must be one the registry declares for this file.
    report.equal(f"{label}.years", sorted(int(y) for y in raw["DateCode"].unique()),
                 bands.get("file_date_codes", [bands["date_code"]]),
                 detail="the file holds exactly the declared editions' years")
    report.require()
    d = raw[raw["DateCode"] == bands["date_code"]]
    report.equal(f"{label}.feature_type", sorted(d["FeatureType"].unique()), [f"{ed['dz_vintage']} Data Zone"])
    report.equal(f"{label}.measurements", sorted(d["Measurement"].unique()), sorted(MEASUREMENTS))
    names = d["SIMD Domain"].map(PUBLISHED_DOMAINS)
    report.equal(f"{label}.domain_names_known", int(names.isna().sum()), 0,
                 detail=f"unknown: {sorted(d.loc[names.isna(), 'SIMD Domain'].unique())}")
    report.equal(f"{label}.domains", sorted(names.dropna().unique()), sorted(declared_domains(ed) + ["overall"]),
                 detail="the published domains are exactly the declared ones, and the overall index")
    report.equal(f"{label}.unique", int(d.duplicated(["FeatureCode", "SIMD Domain", "Measurement"]).sum()), 0)
    report.require()
    wide = (d.assign(domain=names).pivot(index=["FeatureCode", "domain"], columns="Measurement", values="Value")
              .astype("float64"))
    zones = set(gov["dz_code"])
    out = gov.set_index("dz_code")
    for domain in ["overall"] + banded_domains(ed):
        part = wide.xs(domain, level="domain")
        report.equal(f"{label}.{domain}.zones", sorted(part.index) == sorted(zones), True,
                     detail=f"{len(part)} published zones against {len(zones)}")
        report.require()
        part = part.reindex(out.index)
        for band, k in DOMAIN_BANDS.items():
            values = part[band.capitalize()]
            report.equal(f"{label}.{domain}.{band}.whole", bool((values % 1 == 0).all()), True)
            report.equal(f"{label}.{domain}.{band}.range", bool(values.between(1, k).all()), True)
            # Never decreasing as the published rank rises; a tie may straddle adjacent bands.
            ordered = pd.DataFrame({"rank": part["Rank"], "band": values}).sort_values(["rank", "band"])
            report.equal(f"{label}.{domain}.{band}.monotone", int(ordered["band"].diff().lt(0).sum()), 0)
            split = pd.DataFrame({"rank": part["Rank"], "band": values}).groupby("rank")["band"].nunique()
            report.observe(f"{label}.{domain}.{band}.split_ties", int((split > 1).sum()))
        if domain == "overall":
            # The same index in both publications: the overall rank and bands agree everywhere.
            report.equal(f"{label}.overall.rank_agrees", int((part["Rank"] != out["rank"]).sum()), 0)
            for band in DOMAIN_BANDS:
                report.equal(f"{label}.overall.{band}_agrees",
                             int((part[band.capitalize()] != out[f"uw_scotland_{band}"]).sum()), 0)
            continue
        ours, theirs = out[f"{domain}_domain_rank"], part["Rank"]
        differ = ours != theirs
        allowed = pd.Series(False, index=out.index)
        if bands["half_ranks"] == "rounded_up":
            allowed |= (ours % 1 == 0.5) & (theirs == ours + 0.5)
        listed = (bands.get("rank_disagreements") or {}).get(domain)
        if listed:
            pinned = pd.read_csv(listed, comment="#", dtype={"data_zone": str}).set_index("data_zone")
            found = pd.DataFrame({"shapefile_rank": ours[differ & ~allowed], "published_rank": theirs[differ & ~allowed]})
            same_list = sorted(found.index) == sorted(pinned.index)
            report.equal(f"{label}.{domain}.rank_disagreements_as_pinned",
                         same_list and bool((found.loc[pinned.index].to_numpy() == pinned[["shapefile_rank", "published_rank"]].to_numpy()).all()),
                         True, detail=f"{len(found)} differing zones against {len(pinned)} pinned")
            allowed |= out.index.isin(pinned.index)
            out[f"{domain}_domain_rank_source_status"] = np.where(out.index.isin(pinned.index), RANK_SOURCES_DISAGREE, None)
        report.equal(f"{label}.{domain}.ranks_agree", int((differ & ~allowed).sum()), 0,
                     detail="every published rank equals the shapefile's, or differs as declared")
        for band in DOMAIN_BANDS:
            out[f"{domain}_domain_{band}"] = part[band.capitalize()].astype("int64")
    return out.reset_index()


def build_govscot_bands(registry: Registry, root: Path, report: Report) -> pd.DataFrame:
    """All configured edition tables stacked, for readback and the trace."""
    frames = [read_gov_edition(ed, Path(root), report) for ed in registry.govscot_editions]
    # The fixed columns, then every domain rank any edition published. An edition without a
    # domain has no value for it here; nothing reads it, because every reader asks the registry.
    domains = [f"{d}_domain_rank" for d in DOMAINS if any(d in declared_domains(ed) for ed in registry.govscot_editions)]
    extra = list(dict.fromkeys(f for ed in registry.govscot_editions
                               for f in domain_band_fields(ed) + weighted_domain_fields(ed) if f != "population"))
    return pd.concat(frames, ignore_index=True)[COLUMNS + domains + extra]
