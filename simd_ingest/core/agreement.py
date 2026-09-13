"""How far the two NRS products agree, recorded for the reader. Never a gate.

The main table holds the latest life of each whole postcode with the lookup's output-area-based
data zones. The history table holds every life with the directory's own data zones. Reduce the
history table to the same grain (latest lives, live first, whole/A representative) and count
what differs. These observations do not establish whether release or allocation caused them.
"""

from __future__ import annotations

import pandas as pd

from .sources import Registry


def latest_per_postcode(history: pd.DataFrame) -> pd.DataFrame:
    """The SPD SQL's representative policy, before following any large-user link.

    Newest life per full key, then live, whole/A, newest introduction. Ties and missing A
    are kept for diagnostics but excluded from value comparisons.
    """
    h = history.copy()
    h["_intro"] = pd.to_datetime(h["introduced_on"])
    h = h.sort_values("_intro", ascending=False, kind="stable").drop_duplicates("pc_norm")
    h["_eligible"] = h["pc_norm"].eq(h["pc_base"]) | h["pc_norm"].str.endswith("A")
    priority = ["pc_base", "is_current", "_eligible", "_intro"]
    h["_ties"] = h.groupby(priority)["pc_norm"].transform("size")
    latest = h.sort_values(priority + ["pc_norm"], ascending=[True, False, False, False, True],
                           kind="stable").drop_duplicates("pc_base").copy()
    latest["comparison_status"] = "resolved"
    latest.loc[~latest["_eligible"], "comparison_status"] = "split_a_missing"
    latest.loc[latest["_ties"].gt(1), "comparison_status"] = "ambiguous_postcode"
    return latest.set_index("pc_base").drop(columns=["_intro", "_eligible", "_ties"])


def compare_tables(main: pd.DataFrame, history: pd.DataFrame, registry: Registry) -> dict:
    latest = latest_per_postcode(history)
    m = main.set_index("pc_norm").join(latest, how="inner", rsuffix="_history")
    shared = len(m)
    unresolved = latest.loc[latest["comparison_status"].ne("resolved"), "comparison_status"].value_counts().to_dict()
    m = m[m["comparison_status"].eq("resolved")]
    both_current = m["is_current"].astype(bool) & m["is_current_history"].astype(bool)
    cur = m[both_current]
    out = {
        "grain": "whole postcodes; history uses latest full-key lives, then live, whole/A and newest introduction",
        "main_rows": len(main), "history_whole_postcodes": len(latest), "shared": shared,
        "only_in_main": int(len(main) - shared), "only_in_history": int(len(latest) - shared),
        "unresolved_history_representatives": unresolved,
        "shared_resolved": len(m),
        "record_differences": {
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
