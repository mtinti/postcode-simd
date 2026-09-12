"""Ground-truth cases taken straight from the source files, for tests.

For every SIMD edition and both publishers, take the data zones that sit at the rank
boundaries of each Scotland-level quintile and decile: the lowest-ranked and the
highest-ranked zone inside each band. Then pick one random current postcode in that
zone from the postcode directory. Nothing here reads the built table, so the cases can
be used to test it.

    python -m simd_ingest.ground_truth            # writes tests/ground_truth.csv
    python -m simd_ingest.ground_truth --seed 7   # a different random postcode draw
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

import pandas as pd
import yaml

from .config import load_config
from .core.checks import Report
from .core.govscot import read_gov_edition
from .core.phs import canonicalise_phs, read_phs_source
from .core.sources import load_registry, verify_root
from .core.spd import build_postcode_index
from .lookup import PO_BOX_SENTINELS

BANDS = {"quintile": 5, "decile": 10}
COLUMNS = ["publisher", "edition", "dz_vintage", "band", "value", "edge", "rank", "dz_code",
           "published_value", "expected_value", "pc_norm", "postcode", "introduced_on", "selection"]


def boundary_zones(table: pd.DataFrame, band: str, value_col: str, published_col: str) -> list:
    """The first and last zone by rank inside every band value."""
    rows = []
    for value, group in table.sort_values("rank").groupby(value_col, sort=True):
        for edge, row in (("first", group.iloc[0]), ("last", group.iloc[-1])):
            rows.append({"band": band, "value": int(value), "edge": edge, "rank": int(row["rank"]),
                         "dz_code": row["dz_code"], "published_value": int(row[published_col]),
                         "expected_value": int(row[value_col])})
    return rows


def phs_cases(ed: dict, root: Path, report: Report) -> list:
    source = read_phs_source(ed, root, report)
    canon = canonicalise_phs(ed, source, report)
    rows = []
    for band in BANDS:
        canon_col = f"pw_scotland_{band}"
        # published_value is the file's own number; for 2004/2006 it is the inverted one.
        table = canon[["dz_code", "rank", canon_col]].copy()
        table["published"] = source[ed["prefix"] + ("CountryDecile" if band == "decile" else "CountryQuintile")].values
        rows += boundary_zones(table, band, canon_col, "published")
    return [{"publisher": "phs", "edition": ed["key"], "dz_vintage": int(ed["dz_vintage"]), **r} for r in rows]


def gov_cases(ed: dict, root: Path, report: Report) -> list:
    table = read_gov_edition(ed, root, report)
    rows = []
    for band in BANDS:
        col = f"uw_scotland_{band}"
        rows += boundary_zones(table, band, col, col)
    return [{"publisher": "govscot", "edition": ed["key"], "dz_vintage": int(ed["dz_vintage"]), **r} for r in rows]


def pick_postcode(index: pd.DataFrame, vintage: int, dz_code: str, rng: random.Random) -> dict:
    """A random postcode in the zone. Prefer an ordinary, current, small-user, non-PO-box record
    so a test can look it up without any split or scope option; fall back in stated steps."""
    zone = index[index[f"DataZone{vintage}Code"].eq(dz_code)]
    plain = zone["spd_user_type"].eq("small_user") & zone["pc_norm"].eq(zone["pc_base"]) \
        & ~zone["LinkedSmallUserPostcode"].isin(PO_BOX_SENTINELS)
    steps = [("current_ordinary", zone[zone["is_current"] & plain]),
             ("current_any", zone[zone["is_current"]]),
             ("deleted_any", zone)]
    for selection, candidates in steps:
        if not candidates.empty:
            keys = sorted(candidates["pc_norm"].unique())
            pc = rng.choice(keys)
            row = candidates[candidates["pc_norm"].eq(pc)].sort_values("introduced_on").iloc[-1]
            return {"pc_norm": pc, "postcode": row["Postcode"],
                    "introduced_on": row["introduced_on"].date().isoformat(), "selection": selection}
    return {"pc_norm": "", "postcode": "", "introduced_on": "", "selection": "no_postcode"}


def build_ground_truth(cfg: dict, seed: int) -> pd.DataFrame:
    registry = load_registry(cfg["source_manifest"])
    schema = yaml.safe_load(cfg["spd_schema"].read_text())
    root = cfg["source_roots"][cfg["source_mode"]]
    report = Report()
    verify_root(registry, root, report)
    report.require()
    index = build_postcode_index(registry, root, report, schema)
    cases = []
    for ed in registry.phs_editions:
        cases += phs_cases(ed, root, report)
    for ed in registry.govscot_editions:
        cases += gov_cases(ed, root, report)
    report.require()
    rng = random.Random(seed)
    for case in cases:  # cases are in a fixed order, so the draw is reproducible for a seed
        case.update(pick_postcode(index, case["dz_vintage"], case["dz_code"], rng))
    return pd.DataFrame(cases)[COLUMNS]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.environ.get("SIMD_WORKFLOW_CONFIG", "config/workflow.yaml"))
    ap.add_argument("--out", default="tests/ground_truth.csv")
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args(argv)
    table = build_ground_truth(load_config(args.config), args.seed)
    Path(args.out).write_text(table.to_csv(index=False, lineterminator="\n"))
    print(f"{len(table)} cases written to {args.out}; selection: {table['selection'].value_counts().to_dict()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
