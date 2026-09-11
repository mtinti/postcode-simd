"""postcode_index: both directory files with every original column kept as text, plus seven
derived fields. One row per directory record. The key is pc_norm with introduced_on."""

from __future__ import annotations

import heapq
from collections import Counter
from pathlib import Path

import pandas as pd

from .checks import Report
from .sources import Registry

POSTCODE_PATTERN = r"[A-Z]{1,2}[0-9][A-Z0-9]?[0-9][A-Z]{2}"
DERIVED = ["pc_norm", "pc_base", "spd_user_type", "spd_release", "introduced_on", "deleted_on", "is_current"]
LINK_SENTINELS = ("NO LINKP", "NO LINK")


def normalise_postcode(series: pd.Series) -> pd.Series:
    """The single postcode key rule. Consumers must apply exactly this to join."""
    return series.str.upper().str.replace(" ", "", regex=False)


def postcode_keys(frame: pd.DataFrame, role: str) -> pd.DataFrame:
    """pc_norm keeps any NRS split suffix; pc_base drops a validated suffix from a flagged
    small-user record only. Malformed values raise rather than getting a different key."""
    if role not in ("small_user", "large_user"):
        raise ValueError(f"unknown role {role!r}")
    raw = frame["Postcode"]
    if not raw.str.fullmatch(r"[A-Za-z0-9]+ [A-Za-z0-9]+").all():
        raise ValueError("Postcodes must be ASCII letters and digits with one separating space")
    key = normalise_postcode(raw)
    if not frame["SplitIndicator"].isin(["Y", "N"]).all():
        raise ValueError("Unknown split indicator value")
    split = frame["SplitIndicator"].eq("Y") if role == "small_user" else pd.Series(False, index=frame.index)
    valid = key.str.fullmatch(POSTCODE_PATTERN).where(~split, key.str.fullmatch(POSTCODE_PATTERN + "[ABC]"))
    if not valid.all() or not key.str.len().between(5, 8).all():
        raise ValueError("Postcode shape or small-user split suffix is invalid")
    return pd.DataFrame({"pc_norm": key, "pc_base": key.where(~split, key.str[:-1])})


def parse_dates(frame: pd.DataFrame) -> pd.DataFrame:
    """Day-precision dates from the directory's D/M/YYYY midnight text. Never fabricates."""
    out = {}
    for column, target in (("DateOfIntroduction", "introduced_on"), ("DateOfDeletion", "deleted_on")):
        text = frame[column]
        nonblank = text.ne("")
        if not text[nonblank].str.fullmatch(r"\d{1,2}/\d{1,2}/\d{4} 00:00:00").all():
            raise ValueError(f"{column} is not a day-precision D/M/YYYY midnight date")
        out[target] = pd.to_datetime(text.where(nonblank, None), format="%d/%m/%Y %H:%M:%S")
    parsed = pd.DataFrame(out, index=frame.index)
    if parsed["introduced_on"].isna().any() or (parsed["deleted_on"] < parsed["introduced_on"]).any():
        raise ValueError("Missing introduction date, or deletion before introduction")
    return parsed


def active_on(frame: pd.DataFrame, when) -> pd.Series:
    """Half-open validity: introduced_on <= day < deleted_on. Same-day records never match."""
    day = pd.Timestamp(when)
    return frame["introduced_on"].le(day) & (frame["deleted_on"].isna() | frame["deleted_on"].gt(day))


def interval_summary(frame: pd.DataFrame) -> tuple:
    """Directed touching pairs, their user-type transitions, and strict overlaps per key."""
    d = frame[["pc_norm", "spd_user_type", "introduced_on", "deleted_on"]].reset_index(drop=True)
    d["record"] = d.index
    d = d[d["pc_norm"].duplicated(keep=False)]
    touching = d[d["deleted_on"].notna()].merge(d, left_on=["pc_norm", "deleted_on"], right_on=["pc_norm", "introduced_on"], suffixes=("_a", "_b"))
    touching = touching[touching["record_a"].ne(touching["record_b"])]
    transitions = Counter(touching["spd_user_type_a"] + ":" + touching["spd_user_type_b"])
    positive = d[d["deleted_on"].isna() | d["deleted_on"].gt(d["introduced_on"])].sort_values("introduced_on")
    overlaps = 0
    for _, group in positive.groupby("pc_norm"):
        ends = []
        for row in group.itertuples():
            while ends and ends[0] <= row.introduced_on:
                heapq.heappop(ends)
            overlaps += len(ends)
            heapq.heappush(ends, pd.Timestamp.max if pd.isna(row.deleted_on) else row.deleted_on)
    return {"touching_pairs": len(touching), "transitions": dict(transitions), "strict_overlaps": overlaps}, touching


def classify_links(links: pd.Series, small_keys) -> pd.Series:
    reason = pd.Series("linked", index=links.index)
    for sentinel in LINK_SENTINELS:
        reason.loc[links.eq(sentinel)] = sentinel
    real = reason.eq("linked")
    reason.loc[real & ~normalise_postcode(links).isin(set(small_keys))] = "unresolved"
    return reason


def current_candidates(current: pd.DataFrame, ordinary_postcode: str) -> dict:
    """All current records for an ordinary postcode. The caller decides what ambiguity means."""
    key = ordinary_postcode.upper().replace(" ", "")
    candidates = current[current["pc_base"].eq(key)]
    status = "not_found" if candidates.empty else "unique" if len(candidates) == 1 else "ambiguous"
    return {"selection_status": status, "candidate_count": len(candidates), "candidates": candidates}


def build_postcode_index(registry: Registry, root: Path, report: Report, baselines: dict) -> pd.DataFrame:
    base = baselines["postcode"]
    frames = {}
    for spec in registry.spd_files:
        role, label = spec["role"], f"spd.{spec['role']}"
        d = pd.read_csv(Path(root) / spec["file"], dtype=str, keep_default_na=False, encoding="utf-8-sig")
        report.equal(f"{label}.schema", list(d.columns), baselines["schemas"][role])
        report.equal(f"{label}.rows", len(d), spec["rows"])
        report.equal(f"{label}.identical_duplicates", int(d.duplicated().sum()), 0)
        keys = postcode_keys(d, role)
        dates = parse_dates(d)
        d = pd.concat([d, keys, dates], axis=1)
        d["spd_user_type"] = role
        d["spd_release"] = registry.spd_release
        d["is_current"] = d["deleted_on"].isna()
        report.equal(f"{label}.live", int(d["is_current"].sum()), spec["live"])
        report.equal(f"{label}.same_day", int(d["introduced_on"].eq(d["deleted_on"]).sum()), base["same_day_records"][role])
        report.equal(f"{label}.split_records", int(d["SplitIndicator"].eq("Y").sum()), base["split_records"][role])
        report.equal(f"{label}.key_lengths", d["pc_norm"].str.len().value_counts().to_dict(), base["normalised_length_counts"][role])
        counts = d["pc_norm"].value_counts()
        report.equal(f"{label}.repeated_keys", int(counts.gt(1).sum()), base["repeated_keys"][role])
        report.equal(f"{label}.max_repeats", int(counts.max()), base["max_records_per_key"])
        if role == "small_user":
            report.equal(f"{label}.all_splits_suffixed", int(d["pc_norm"].ne(d["pc_base"]).sum()), base["split_records"][role])
            report.equal(f"{label}.live_never_digitised", int((d["is_current"] & d["NeverDigitised"].eq("Y")).sum()), base["live_never_digitised_small_user"])
        frames[role] = d

    # Union of columns in source order: the small-user header, then the large-user-only field.
    original = baselines["schemas"]["small_user"] + [c for c in baselines["schemas"]["large_user"] if c not in baselines["schemas"]["small_user"]]
    d = pd.concat([frames["small_user"], frames["large_user"]], ignore_index=True)[original + DERIVED]
    d = d.sort_values(["pc_norm", "introduced_on"], kind="mergesort").reset_index(drop=True)

    report.equal("spd.columns", len(d.columns), len(original) + len(DERIVED))
    report.equal("spd.primary_key_unique", int(d.duplicated(["pc_norm", "introduced_on"]).sum()), 0)
    report.equal("spd.primary_key_nonnull", int(d["pc_norm"].isna().sum() + d["introduced_on"].isna().sum()), 0)
    totals = registry.spd_published_totals
    report.equal("spd.total_all", len(d), totals["all"])
    report.equal("spd.total_live", int(d["is_current"].sum()), totals["live"])
    report.equal("spd.total_deleted", int((~d["is_current"]).sum()), totals["deleted"])
    intervals, pairs = interval_summary(d)
    report.equal("spd.touching_pairs", intervals["touching_pairs"], base["touching_pairs"])
    report.equal("spd.touching_transitions", intervals["transitions"], base["touching_transitions"])
    report.equal("spd.strict_overlaps", intervals["strict_overlaps"], 0)
    february = pairs[pairs["deleted_on_a"].eq(pd.Timestamp(base["february_correction_date"])) & pairs["spd_user_type_a"].eq("small_user") & pairs["spd_user_type_b"].eq("small_user")]
    report.equal("spd.february_corrections", sorted(february["pc_norm"]), base["february_correction_keys"])
    links = classify_links(frames["large_user"]["LinkedSmallUserPostcode"], frames["small_user"]["pc_norm"])
    report.equal("spd.link_categories", links.value_counts().to_dict(), {**base["link_sentinels"], "linked": base["real_links"]})
    report.equal("spd.unresolved_real_links", int(links.eq("unresolved").sum()), base["unresolved_real_links"])
    current = d[d["is_current"]]
    report.equal("spd.current_unique_nrs", bool(current["pc_norm"].is_unique), True)
    counts = current["pc_base"].value_counts()
    multiple = counts[counts.gt(1)]
    report.equal("spd.live_base_keys", len(counts), base["live_base_keys"])
    report.equal("spd.multiple_candidate_bases", len(multiple), base["base_keys_with_multiple_candidates"])
    report.equal("spd.multiple_candidate_sizes", multiple.value_counts().to_dict(), base["multiple_candidate_group_sizes"])
    report.equal("spd.base_keys_with_differing_2011_zones", int(current.groupby("pc_base")["DataZone2011Code"].nunique().gt(1).sum()), base["base_keys_with_differing_2011_zones"])
    example = current_candidates(current, base["current_example"]["base"])
    report.equal("spd.example_selection", example["selection_status"], "ambiguous")
    report.equal("spd.example_candidates", dict(zip(example["candidates"]["pc_norm"], example["candidates"]["ScottishIndexOfMultipleDeprivation2020Rank"].astype(int))), base["current_example"]["candidates"])
    for vintage in (2001, 2011, 2022):
        report.equal(f"spd.dz{vintage}.blanks", int(d[f"DataZone{vintage}Code"].eq("").sum()), 0)
    return d
