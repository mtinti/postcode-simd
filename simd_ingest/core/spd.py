"""The postcode index in two visible steps.

read_index_file     one directory file: every original column kept as text, the key and the
                    dates derived, per-file checks against the published counts
union_index         the two files stacked in source column order, spd_user_type added as
                    provenance, and the checks that only make sense across both

The key is pc_norm with introduced_on. One row per directory record.
"""

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
    small-user record only. Malformed values raise rather than getting a different key.
    Role "sspl" is the lookup's whole-postcode file: a suffix on any record is an error."""
    if role not in ("small_user", "large_user", "sspl"):
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
    """Day-precision dates from D/M/YYYY text, with the directory's midnight time or, as in
    the lookup, without it. Never fabricates."""
    out = {}
    for column, target in (("DateOfIntroduction", "introduced_on"), ("DateOfDeletion", "deleted_on")):
        text = frame[column]
        nonblank = text.ne("")
        if not text[nonblank].str.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}( 00:00:00)?").all():
            raise ValueError(f"{column} is not a day-precision D/M/YYYY date")
        day = text.str.replace(" 00:00:00", "", regex=False)
        out[target] = pd.to_datetime(day.where(nonblank, None), format="%d/%m/%Y")
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


def read_index_file(spec: dict, registry: Registry, root: Path, report: Report, schema: dict) -> pd.DataFrame:
    """One directory file: validate the contract, then record this release's profile."""
    role, label = spec["role"], f"spd.{spec['role']}"
    d = pd.read_csv(Path(root) / spec["file"], dtype=str, keep_default_na=False, encoding="utf-8-sig")
    report.equal(f"{label}.schema", list(d.columns), schema[role])
    report.equal(f"{label}.rows", len(d), spec["rows"])
    report.equal(f"{label}.identical_duplicates", int(d.duplicated().sum()), 0)
    report.require()
    d = pd.concat([d, postcode_keys(d, role), parse_dates(d)], axis=1)
    d["spd_user_type"] = role
    d["spd_release"] = registry.spd_release
    d["is_current"] = d["deleted_on"].isna()
    report.equal(f"{label}.live", int(d["is_current"].sum()), spec["live"])
    counts = d["pc_norm"].value_counts()
    profile = {
        "rows": len(d), "live": int(d["is_current"].sum()),
        "same_day": int(d["introduced_on"].eq(d["deleted_on"]).sum()),
        "split_records": int(d["SplitIndicator"].eq("Y").sum()),
        "key_lengths": d["pc_norm"].str.len().value_counts().to_dict(),
        "repeated_keys": int(counts.gt(1).sum()),
        "max_repeats": int(counts.max()) if len(counts) else 0,
    }
    if "NeverDigitised" in d:
        profile["live_never_digitised"] = int((d["is_current"] & d["NeverDigitised"].eq("Y")).sum())
    report.observe(label, profile)
    return d


def union_index(small: pd.DataFrame, large: pd.DataFrame, registry: Registry, report: Report, schema: dict) -> pd.DataFrame:
    """Stack the files; retain raw blanks and distinguish columns absent from a role."""
    original = schema["small_user"] + [c for c in schema["large_user"] if c not in schema["small_user"]]
    d = pd.concat([small, large], ignore_index=True)[original + DERIVED]
    d = d.sort_values(["pc_norm", "introduced_on"], kind="mergesort").reset_index(drop=True)
    report.equal("spd.columns", len(d.columns), len(original) + len(DERIVED))
    report.equal("spd.primary_key_unique", int(d.duplicated(["pc_norm", "introduced_on"]).sum()), 0)
    report.equal("spd.primary_key_nonnull", int(d["pc_norm"].isna().sum() + d["introduced_on"].isna().sum()), 0)
    totals = registry.spd_published_totals
    report.equal("spd.total_all", len(d), totals["all"])
    report.equal("spd.total_live", int(d["is_current"].sum()), totals["live"])
    report.equal("spd.total_deleted", int((~d["is_current"]).sum()), totals["deleted"])
    intervals, _ = interval_summary(d)
    report.equal("spd.strict_overlaps", intervals["strict_overlaps"], 0)
    links = classify_links(large["LinkedSmallUserPostcode"], small["pc_norm"])
    report.equal("spd.unresolved_real_links", int(links.eq("unresolved").sum()), 0)
    current = d[d["is_current"]]
    report.equal("spd.current_unique_nrs", bool(current["pc_norm"].is_unique), True)
    counts = current["pc_base"].value_counts()
    multiple = counts[counts.gt(1)]
    report.observe("spd.intervals", intervals)
    report.observe("spd.links", links.value_counts().to_dict())
    report.observe("spd.current", {
        "base_keys": len(counts), "multiple_candidate_bases": len(multiple),
        "multiple_candidate_sizes": multiple.value_counts().to_dict(),
    })
    for vintage in sorted({int(e["dz_vintage"]) for e in registry.phs_editions}):
        col = f"DataZone{vintage}Code"
        report.add(f"spd.dz{vintage}.present", col in d, f"required by the configured SIMD editions: {col}")
        report.require()
        report.equal(f"spd.dz{vintage}.blanks", int(d[col].eq("").sum()), 0)
        report.observe(f"spd.dz{vintage}.ambiguous_bases", int(current.groupby("pc_base")[col].nunique().gt(1).sum()))
    return d


def build_postcode_index(registry: Registry, root: Path, report: Report, schema: dict) -> pd.DataFrame:
    frames = {spec["role"]: read_index_file(spec, registry, root, report, schema) for spec in registry.spd_files}
    report.require()
    return union_index(frames["small_user"], frames["large_user"], registry, report, schema)
