"""Trace one output record back through the join to the PHS and government rows it came from.

    python -m simd_ingest.trace "AB12 3GQA"                 # the current record
    python -m simd_ingest.trace "AB10 1BF" --introduced 2003-04-15

Rebuilds the two reference tables from the pinned sources, so the trace is independent of
whatever Dagster or the CLI produced, and reports for every edition whether the value in
the saved table equals the value in the source row. Row-level lineage, for one record.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

from .cli import load_config
from .core.checks import Report
from .core.govscot import build_govscot_bands
from .core.phs import BANDS, FLAGS, build_phs_bands
from .core.sources import load_registry
from .core.spd import normalise_postcode


def trace(table: pd.DataFrame, phs: pd.DataFrame, gov: pd.DataFrame, registry, postcode: str, introduced=None) -> list:
    key = normalise_postcode(pd.Series([postcode])).iloc[0]
    rows = table[table["pc_norm"] == key]
    if rows.empty:
        raise SystemExit(f"{postcode}: no record with pc_norm {key}")
    if introduced is not None:
        rows = rows[pd.to_datetime(rows["introduced_on"]) == pd.Timestamp(introduced)]
    elif len(rows) > 1:
        rows = rows[rows["is_current"]]
    if len(rows) != 1:
        raise SystemExit(f"{key}: {len(rows)} records match; pass --introduced with one of "
                         f"{sorted(str(d) for d in table.loc[table['pc_norm'] == key, 'introduced_on'])}")
    row = rows.iloc[0]
    lines = [f"record   {row['Postcode']!r} ({row['spd_user_type']}), introduced {row['introduced_on']}, "
             f"deleted {row['deleted_on'] if pd.notna(row['deleted_on']) else 'not deleted'}",
             f"zones    2001 {row['DataZone2001Code']}   2011 {row['DataZone2011Code']}   2022 {row['DataZone2022Code']} (unused)",
             f"geography 2001 hb {row['phs_dz2001_hb']} hscp {row['phs_dz2001_hscp']} ca {row['phs_dz2001_ca']}   "
             f"2011 hb {row['phs_dz2011_hb']} hscp {row['phs_dz2011_hscp']} ca {row['phs_dz2011_ca']}   "
             f"directory hb {row['HealthBoardArea2019Code']}", ""]
    ok = True
    for ed in registry.phs_editions:
        key_, vintage = ed["key"], int(ed["dz_vintage"])
        dz = row[f"DataZone{vintage}Code"]
        p = phs[(phs["edition"] == key_) & (phs["dz_code"] == dz)].iloc[0]
        g = gov[(gov["edition"] == key_) & (gov["dz_code"] == dz)].iloc[0]
        gov_file = next(e["file"] for e in registry.govscot_editions if e["key"] == key_)
        lines.append(f"SIMD {key_:<7} via DataZone{vintage}Code = {dz}")
        lines.append(f"  PHS row     {ed['file']}  rank {p['rank']}"
                     + ("  (bands inverted from source: 11 - decile, 6 - quintile)" if ed["invert_bands"] else ""))
        lines.append(f"  gov row     {gov_file}  rank {g['rank']}  population {g['population']}")
        checks = []
        for f in ["rank", *BANDS.values(), *FLAGS.values()]:
            out, src = row[f"simd{key_}_{f}"], p[f]
            checks.append((f, out, src))
        for f in ["uw_scotland_quintile", "uw_scotland_decile", "uw_scotland_vigintile"]:
            checks.append((f, row[f"simd{key_}_{f}"], g[f]))
        bad = [(f, o, s) for f, o, s in checks if int(o) != int(s)]
        ok &= not bad
        shown = ", ".join(f"{f}={int(o)}" for f, o, _ in checks[:4]) + ", ..."
        lines.append(f"  output      {shown}")
        lines.append(f"  agreement   {'all 14 values equal the source rows' if not bad else 'DIFFER: ' + str(bad)}")
        lines.append("")
    lines.append("result   " + ("every attached value traces to its source row" if ok else "MISMATCH FOUND"))
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("postcode")
    ap.add_argument("--introduced", help="introduction date, YYYY-MM-DD, to pick one life of a postcode")
    ap.add_argument("--config", default=os.environ.get("SIMD_WORKFLOW_CONFIG", "config/workflow.yaml"))
    ap.add_argument("--table", default="results/postcode_simd.parquet")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    registry = load_registry(cfg["source_manifest"])
    root = cfg["source_roots"][cfg["source_mode"]]
    report = Report()
    phs = build_phs_bands(registry, root, report)
    gov = build_govscot_bands(registry, root, report)
    report.require()
    table = pd.read_parquet(args.table)
    print("\n".join(trace(table, phs, gov, registry, args.postcode, args.introduced)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
