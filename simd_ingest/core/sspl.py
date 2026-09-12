"""The Scottish Statistics Postcode Lookup: the latest life of every whole postcode, both user
types in one file, as NRS publishes it for statistical production.

Read the file, validate its contract, derive the key and dates, and record what this release
looks like. Nothing is resolved here: NRS already made split postcodes whole on the A part.
Every higher geography in this file, including both data-zone vintages, is the one containing
the centroid of the postcode's 2022 output area, not the one containing the postcode itself.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .checks import Report
from .sources import Registry
from .spd import LINK_SENTINELS, POSTCODE_PATTERN, normalise_postcode, parse_dates, postcode_keys

DERIVED = ["pc_norm", "spd_user_type", "sspl_release", "introduced_on", "deleted_on", "is_current"]
USER_TYPE = {"S": "small_user", "L": "large_user"}


def build_latest_index(registry: Registry, root: Path, report: Report, schema: dict) -> pd.DataFrame:
    """One lookup file: validate the contract, derive the key, record the release profile."""
    spec, label = registry.sspl_file, "sspl"
    d = pd.read_csv(Path(root) / spec["file"], dtype=str, keep_default_na=False, encoding="utf-8-sig")
    report.equal(f"{label}.schema", list(d.columns), schema["single_record"])
    report.equal(f"{label}.rows", len(d), spec["rows"], detail=f"{spec.get('totals_basis', 'counted')} total")
    report.equal(f"{label}.identical_duplicates", int(d.duplicated().sum()), 0)
    report.require()
    keys = postcode_keys(d, "sspl")  # no suffix is allowed on any record; a malformed value raises
    d["pc_norm"] = keys["pc_norm"]
    report.equal(f"{label}.postcode_type", sorted(d["PostcodeType"].unique()), sorted(USER_TYPE))
    report.require()
    d["spd_user_type"] = d["PostcodeType"].map(USER_TYPE)
    d["sspl_release"] = registry.sspl_release
    d = pd.concat([d, parse_dates(d)], axis=1)
    d["is_current"] = d["deleted_on"].isna()
    d = d.sort_values("pc_norm", kind="mergesort").reset_index(drop=True)
    report.equal(f"{label}.primary_key_unique", int(d["pc_norm"].duplicated().sum()), 0)
    by_type = d["spd_user_type"].value_counts()
    report.equal(f"{label}.live", int(d["is_current"].sum()), spec["live"])
    report.equal(f"{label}.small_user", int(by_type.get("small_user", 0)), spec["small_user"])
    report.equal(f"{label}.large_user", int(by_type.get("large_user", 0)), spec["large_user"])

    # Large-user links: a sentinel or a postcode, possibly with the SPD's split suffix, which
    # NRS keeps on the link. Whether the target is in this file is recorded, not required:
    # the file holds latest lives only, so an old link can point outside it.
    large = d[d["spd_user_type"] == "large_user"]
    links = large["LinkedSmallUserPostcode"]
    link_key = normalise_postcode(links)
    shaped = link_key.str.fullmatch(POSTCODE_PATTERN + "[ABC]?")
    report.equal(f"{label}.link_values_valid", int((~(links.isin(LINK_SENTINELS) | shaped)).sum()), 0)
    report.equal(f"{label}.small_user_links_blank", int(d.loc[d["spd_user_type"] == "small_user", "LinkedSmallUserPostcode"].ne("").sum()), 0)
    small_keys = set(d.loc[d["spd_user_type"] == "small_user", "pc_norm"])
    base = link_key.where(~link_key.str.fullmatch(POSTCODE_PATTERN + "[ABC]"), link_key.str[:-1])
    category = pd.Series("linked", index=large.index)
    for sentinel in LINK_SENTINELS:
        category[links.eq(sentinel)] = sentinel
    real = category.eq("linked")
    category[real & ~base.isin(small_keys)] = "target_not_in_file"
    report.observe(f"{label}.links", {**category.value_counts().to_dict(),
                                      "with_split_suffix": int((real & link_key.str.len().eq(base.str.len() + 1)).sum())})
    report.observe(f"{label}.profile", {
        "rows": len(d), "live": int(d["is_current"].sum()),
        "split_indicator_y": d.groupby("spd_user_type")["SplitIndicator"].apply(lambda s: int(s.eq("Y").sum())).to_dict(),
        "same_day": int(d["introduced_on"].eq(d["deleted_on"]).sum()),
        "key_lengths": d["pc_norm"].str.len().value_counts().to_dict(),
        "introduced_range": [str(d["introduced_on"].min().date()), str(d["introduced_on"].max().date())],
    })
    for vintage in sorted({int(e["dz_vintage"]) for e in registry.phs_editions}):
        col = f"DataZone{vintage}Code"
        report.add(f"{label}.dz{vintage}.present", col in d, f"required by the configured SIMD editions: {col}")
        report.require()
        report.equal(f"{label}.dz{vintage}.blanks", int(d[col].eq("").sum()), 0)
    return d[schema["single_record"] + DERIVED]
