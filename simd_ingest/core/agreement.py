"""How far the two NRS products agree, recorded for the reader. Never a gate.

The main table holds the latest life of each whole postcode with the lookup's output-area-based
data zones. The history table holds every life with the directory's own data zones. Reduce the
history table to the same grain (newest life per whole postcode, A part for splits) and count
what differs. Cut differences and allocation differences are both reported, separately.
"""

from __future__ import annotations

import pandas as pd

from .sources import Registry


def latest_per_postcode(history: pd.DataFrame) -> pd.DataFrame:
    """Newest introduction per ordinary postcode, then the whole record or the A part."""
    h = history.copy()
    h["_intro"] = pd.to_datetime(h["introduced_on"])
    h["_suffix"] = h["pc_norm"].str[-1].where(h["pc_norm"].ne(h["pc_base"]), "")
    newest = h["_intro"].eq(h.groupby("pc_base")["_intro"].transform("max"))
    latest = h[newest].sort_values(["pc_base", "_suffix"], kind="mergesort").drop_duplicates("pc_base")
    return latest.set_index("pc_base").drop(columns=["_intro", "_suffix"])


def compare_tables(main: pd.DataFrame, history: pd.DataFrame, registry: Registry) -> dict:
    latest = latest_per_postcode(history)
    m = main.set_index("pc_norm").join(latest, how="inner", rsuffix="_history")
    both_current = m["is_current"].astype(bool) & m["is_current_history"].astype(bool)
    cur = m[both_current]
    out = {
        "grain": "latest life per whole postcode in both tables; history reduced to the newest introduction and the A part",
        "main_rows": len(main), "history_whole_postcodes": len(latest), "shared": len(m),
        "only_in_main": int(len(main) - len(m)), "only_in_history": int(len(latest) - len(m)),
        "cut_differences": {
            "introduced_on": int(pd.to_datetime(m["introduced_on"]).ne(pd.to_datetime(m["introduced_on_history"])).sum()),
            "is_current": int(m["is_current"].astype(bool).ne(m["is_current_history"].astype(bool)).sum()),
            "spd_user_type": int(m["spd_user_type"].ne(m["spd_user_type_history"]).sum()),
        },
        "shared_and_current_in_both": int(both_current.sum()),
        "geography_differences": {},
        "band_differences_among_current": {},
    }
    for col in [c for c in main.columns if c.startswith(("OutputArea", "DataZone", "IntermediateZone", "HealthBoardArea2019",
                                                          "CouncilArea", "IntegrationAuthority"))]:
        if f"{col}_history" in m:
            out["geography_differences"][col] = {"all": int(m[col].ne(m[f"{col}_history"]).sum()),
                                                 "current": int(cur[col].ne(cur[f"{col}_history"]).sum())}
    for ed in registry.phs_editions:
        k = ed["key"]
        out["band_differences_among_current"][k] = {
            f: int(cur[f"simd{k}_{f}"].ne(cur[f"simd{k}_{f}_history"]).sum())
            for f in ("pw_scotland_quintile", "pw_scotland_decile", "most15pc", "uw_scotland_quintile")}
    return out
