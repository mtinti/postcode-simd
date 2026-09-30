"""Scottish Government unweighted bands and population, one edition at a time, read from the
shapefile attribute tables. Nothing is calculated and nothing needs inverting."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from dbfread import DBF

from .checks import Report
from .sources import DOMAINS, Registry, declared_domains

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
    return out


def build_govscot_bands(registry: Registry, root: Path, report: Report) -> pd.DataFrame:
    """All configured edition tables stacked, for readback and the trace."""
    frames = [read_gov_edition(ed, Path(root), report) for ed in registry.govscot_editions]
    # The fixed columns, then every domain rank any edition published. An edition without a
    # domain has no value for it here; nothing reads it, because every reader asks the registry.
    domains = [f"{d}_domain_rank" for d in DOMAINS if any(d in declared_domains(ed) for ed in registry.govscot_editions)]
    return pd.concat(frames, ignore_index=True)[COLUMNS + domains]
