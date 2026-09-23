"""Current/as-of record-level SIMD lookups, with explicit analyst choices.

This API uses current-only or date-valid records and own-record large-user geography.
The SQL sets in docs/sql use the latest postcode and follow large-user links instead;
see docs/LINKAGE_BY_ERA.md.
SSPL cannot answer date-valid or split-report questions.

The guidance's method: choose the edition for the years of your data, choose the category
and level, then match by postcode. This module does the matching and leaves the choices to
the analyst, who passes an edition and a measure explicitly.

    from simd_ingest import lookup
    t = lookup.load("results/postcode_simd.parquet")
    lookup.lookup(t, "G71 8BQ", edition="2020v2")                      # current only
    h = lookup.load("results/postcode_simd_history.parquet")
    lookup.lookup(h, "AB10 1BF", edition="2012", on="2012-06-01")      # at a date
    lookup.attach(cohort, h, "postcode", "event_date", edition="2020v2")  # a whole frame
    lookup.attach_rurality(cohort, h, "postcode", "event_date")          # urban-rural for the year

Split postcodes: NRS splits a postcode that straddles a boundary into A, B and C parts, each
its own record, and the A part is the one with more addresses. By default, as in NRS's own
Scottish Statistics Postcode Lookup, a lookup on the ordinary postcode resolves to the A part
and says so with status `a_part`. Pass `split="report"` to refuse instead: several valid parts
that agree give `split_consensus`, parts that disagree give `split_conflict` with a null value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from .core.spd import normalise_postcode, part_of

# PHS deprivation guidance for analysts v3.5, table 4: years of health data -> edition.
# A recommendation. Nothing in this module calls it for you.
GUIDANCE_TABLE_4 = [(1996, 2003, "2004"), (2004, 2006, "2006"), (2007, 2009, "2009v2"),
                    (2010, 2013, "2012"), (2014, 2016, "2016"), (2017, 9999, "2020v2")]

NOT_FOUND, UNIQUE, SPLIT_CONSENSUS, SPLIT_CONFLICT, DELETED = "not_found", "unique", "split_consensus", "split_conflict", "deleted"
BEFORE_FIRST_VERSION = "before_first_version"  # the event predates the first urban-rural version
A_PART = "a_part"          # several split parts valid; resolved to the A part, the NRS convention
NO_EDITION = "no_edition"  # the event predates SIMD; the guidance points to Carstairs
STATUSES = (NOT_FOUND, UNIQUE, A_PART, SPLIT_CONSENSUS, SPLIT_CONFLICT, DELETED, NO_EDITION)
SPLIT_RULES = ("a_part", "report")

_SCOPE = {"scotland": "within-Scotland", "hb": "within-NHS-Board", "hscp": "within-HSCP", "ca": "within-council-area"}
_WEIGHT = {"pw": "PHS population-weighted", "uw": "Scottish Government unweighted"}
# Large-user records whose link field carries one of these have no residential location: PO
# boxes and the like. PHS practice attaches no deprivation to them, so they are excluded by
# default from every lookup. The table itself keeps them, with the SIMD the directory assigns.
PO_BOX_SENTINELS = ("NO LINKP", "NO LINK")


def scope(table: pd.DataFrame, include_po_boxes: bool = False, include_large_users: bool = True) -> pd.DataFrame:
    """Python's scope: exclude no-link sentinels by default; keep own-record geography."""
    keep = pd.Series(True, index=table.index)
    if not include_large_users and "spd_user_type" in table:
        keep &= table["spd_user_type"] != "large_user"
    if not include_po_boxes and "LinkedSmallUserPostcode" in table:
        keep &= ~table["LinkedSmallUserPostcode"].isin(PO_BOX_SENTINELS)
    return table[keep]


def recommended_edition(year: int) -> str:
    """The edition the PHS guidance recommends for health data from a given year."""
    for first, last, edition in GUIDANCE_TABLE_4:
        if first <= year <= last:
            return edition
    raise ValueError(f"No SIMD edition is recommended for {year}; the guidance points to Carstairs before 1996")


def column(edition: str, measure: str) -> str:
    return f"simd{edition}_{measure}"


def label(col: str, split: str = "a_part") -> str:
    """The label the guidance's checklist requires, derived from the column name, plus how
    split postcodes were resolved."""
    return _measure_label(col) + (", split postcodes resolved to the A part" if split == "a_part" else ", split postcodes reported")


def _measure_label(col: str) -> str:
    m = re.fullmatch(r"simd(?P<ed>[0-9v]+)_(?:(?P<w>pw|uw)_(?P<scope>[a-z]+)_(?P<measure>[a-z]+)|(?P<other>rank|most15pc|least15pc))", col)
    if not m:
        raise ValueError(f"not a SIMD column: {col}")
    ed = f"SIMD {m['ed']}"
    if m["other"] == "rank":
        return f"{ed} rank, 1 = most deprived"
    if m["other"]:
        return f"{ed} PHS population-weighted {m['other'][:-4]}-deprived 15% flag, as published"
    return f"{ed}, {_WEIGHT[m['w']]}, {_SCOPE[m['scope']]} {m['measure']}, 1 = most deprived"


def load(path: str) -> pd.DataFrame:
    """The table with its two date columns as timestamps, ready for comparisons. The table's
    own metadata says which NRS product it came from; the date-based lookups need history."""
    import pyarrow.parquet as pq
    meta = pq.read_schema(path).metadata or {}
    t = pd.read_parquet(path)
    for c in ("introduced_on", "deleted_on"):
        t[c] = pd.to_datetime(t[c])
    t.attrs["index_source"] = meta.get(b"index_source", b"").decode() or None
    return t


def _prepare(table: pd.DataFrame, dated: bool, split: str = "a_part") -> pd.DataFrame:
    """Refuse a dated question against a latest-life table; give a whole-postcode table the
    pc_base column the resolution rules expect (every record is its own whole postcode)."""
    is_sspl = table.attrs.get("index_source") == "sspl" or "sspl_release" in table
    if dated and is_sspl:
        raise ValueError("This is the latest-postcode table (SSPL): it holds one life per postcode and cannot "
                         "answer a question about a date. Use the history table, postcode_simd_history.parquet.")
    if is_sspl and split == "report":
        raise ValueError("SSPL has no individual split parts to compare. Use the history table for split='report'.")
    if "pc_base" not in table:
        table = table.assign(pc_base=table["pc_norm"])
    return table


@dataclass
class Result:
    postcode: str
    key: str
    edition: str
    measure: str
    on: pd.Timestamp | None
    status: str
    value: object
    label: str
    candidates: pd.DataFrame

    def __str__(self) -> str:
        when = f"on {self.on.date()}" if self.on is not None else "currently"
        return f"{self.postcode} {when}: {self.status}, {self.label} = {self.value}"


def _check_split(split: str) -> None:
    if split not in SPLIT_RULES:
        raise ValueError(f"split must be one of {SPLIT_RULES}, not {split!r}")


def _resolve(valid: pd.DataFrame, col: str, split: str) -> tuple:
    if len(valid) == 1:
        return UNIQUE, valid[col].iloc[0]
    if split == "a_part":
        a = valid[part_of(valid) == "A"]
        if len(a) == 1:
            return A_PART, a[col].iloc[0]
    values = valid[col].unique()
    if len(values) == 1:
        return SPLIT_CONSENSUS, values[0]
    return SPLIT_CONFLICT, None


def lookup(table: pd.DataFrame, postcode: str, edition: str, measure: str = "pw_scotland_quintile", on=None,
           include_po_boxes: bool = False, include_large_users: bool = True, split: str = "a_part") -> Result:
    """SIMD for one postcode, current or valid on a day. The postcode may be an ordinary
    postcode or a full NRS key with its split suffix. PO boxes are excluded unless asked for.
    Split postcodes resolve to the A part unless split="report"."""
    _check_split(split)
    table = scope(_prepare(table, on is not None, split), include_po_boxes, include_large_users)
    col = column(edition, measure)
    key = normalise_postcode(pd.Series([postcode])).iloc[0]
    when = None if on is None else pd.Timestamp(on)
    # An ordinary postcode matches every record whose base it is: the unsplit record of any
    # earlier life and the current split parts. A full NRS key with a suffix selects its own
    # part only. A base that also exists as an old unsplit record is still an ordinary key.
    by_base = table["pc_base"] == key
    by_part = (table["pc_norm"] == key) & (table["pc_norm"] != table["pc_base"])
    cand = table[by_part] if by_part.any() else table[by_base]
    if cand.empty:
        return Result(postcode, key, edition, measure, when, NOT_FOUND, None, label(col, split), cand)
    if when is None:
        valid = cand[cand["is_current"]]
    else:
        valid = cand[(cand["introduced_on"] <= when) & (cand["deleted_on"].isna() | (cand["deleted_on"] > when))]
    if valid.empty:
        return Result(postcode, key, edition, measure, when, DELETED, None, label(col, split), cand)
    status, value = _resolve(valid, col, split)
    return Result(postcode, key, edition, measure, when, status, value, label(col, split), valid)


def attach(events: pd.DataFrame, table: pd.DataFrame, postcode_col: str, date_col: str | None,
           edition: str, measure: str = "pw_scotland_quintile", prefix: str = "simd",
           include_po_boxes: bool = False, include_large_users: bool = True, split: str = "a_part") -> pd.DataFrame:
    """One result per event row: status, value and the matched NRS key where resolved.

    Rows are never dropped or duplicated. With `date_col` the record valid on the event's
    date is used; without it, the current record. PO boxes are excluded unless asked for.
    Split postcodes resolve to the A part unless split="report".
    """
    _check_split(split)
    table = scope(_prepare(table, date_col is not None, split), include_po_boxes, include_large_users)
    col = column(edition, measure)
    out = _attach_column(events, table, postcode_col, date_col, col, prefix, split)
    out[f"{prefix}_value"] = out[f"{prefix}_value"].astype("Int64")
    out.attrs[f"{prefix}_label"] = label(col, split)
    return out


def _attach_column(events: pd.DataFrame, table: pd.DataFrame, postcode_col: str, date_col: str | None,
                   col: str, prefix: str, split: str) -> pd.DataFrame:
    """attach()'s record resolution for any one column of an already scoped table: status,
    value and matched key, one row per event, never dropped or duplicated."""
    ev = pd.DataFrame({"_row": range(len(events)),
                       "_key": normalise_postcode(events[postcode_col].astype("string").fillna("")).replace("", pd.NA)},
                      index=events.index)
    if date_col is not None:
        ev["_on"] = pd.to_datetime(events[date_col])
    cols = ["pc_norm", "pc_base", "introduced_on", "deleted_on", "is_current", col]
    # Two routes, as in lookup(): an ordinary postcode matches on pc_base; a full NRS key
    # with a suffix matches its own split part on pc_norm and then takes precedence.
    by_base = ev.merge(table[cols], left_on="_key", right_on="pc_base", how="left")
    parts = table.loc[table["pc_norm"] != table["pc_base"], cols]
    by_part = ev.merge(parts, left_on="_key", right_on="pc_norm", how="inner")
    exact_rows = set(by_part["_row"])
    m = pd.concat([by_base[~by_base["_row"].isin(exact_rows)], by_part], ignore_index=True)
    known = m["pc_norm"].notna()
    if date_col is not None:
        valid = known & (m["introduced_on"] <= m["_on"]) & (m["deleted_on"].isna() | (m["deleted_on"] > m["_on"]))
    else:
        valid = known & m["is_current"].fillna(False).astype(bool)
    v = m[valid]
    a = v[part_of(v) == "A"]
    rows = range(len(events))
    summary = pd.DataFrame({"n_known": known.groupby(m["_row"]).sum(),
                            "n_valid": v.groupby("_row").size().reindex(rows, fill_value=0),
                            "n_values": v.groupby("_row")[col].nunique().reindex(rows, fill_value=0),
                            "value": v.groupby("_row")[col].first().reindex(rows),
                            "pc_norm": v.groupby("_row")["pc_norm"].first().reindex(rows),
                            "n_a": a.groupby("_row").size().reindex(rows, fill_value=0),
                            "a_value": a.groupby("_row")[col].first().reindex(rows),
                            "a_pc_norm": a.groupby("_row")["pc_norm"].first().reindex(rows)})
    status = pd.Series(NOT_FOUND, index=summary.index)
    status[(summary["n_known"] > 0) & (summary["n_valid"] == 0)] = DELETED
    status[summary["n_valid"] == 1] = UNIQUE
    status[(summary["n_valid"] > 1) & (summary["n_values"] == 1)] = SPLIT_CONSENSUS
    status[(summary["n_valid"] > 1) & (summary["n_values"] > 1)] = SPLIT_CONFLICT
    if split == "a_part":
        status[(summary["n_valid"] > 1) & (summary["n_a"] == 1)] = A_PART
    value = summary["value"].where(status.isin([UNIQUE, SPLIT_CONSENSUS]))
    value[status == A_PART] = summary["a_value"][status == A_PART]
    pc_norm = summary["pc_norm"].where(status == UNIQUE)
    pc_norm[status == A_PART] = summary["a_pc_norm"][status == A_PART]
    out = events.copy()
    out[f"{prefix}_status"] = status.values
    out[f"{prefix}_value"] = value.values
    out[f"{prefix}_pc_norm"] = pc_norm.values
    assert len(out) == len(events)
    return out


def edition_for(dates: pd.Series) -> pd.Series:
    """The guidance's recommended edition for each event date; null before 1996."""
    years = pd.to_datetime(dates).dt.year
    out = pd.Series(pd.NA, index=dates.index, dtype="string")
    for first, last, edition in GUIDANCE_TABLE_4:
        out[years.between(first, last)] = edition
    return out


def attach_by_era(events: pd.DataFrame, table: pd.DataFrame, postcode_col: str, date_col: str,
                  measure: str = "pw_scotland_quintile", prefix: str = "simd",
                  include_po_boxes: bool = False, include_large_users: bool = True, split: str = "a_part") -> pd.DataFrame:
    """Table 4 edition per event year, plus this API's historical postcode policy.
    Takes the record valid on the event date; adds an edition and per-row label.
    This is not the latest-postcode policy of the docs/sql sets.

    Events before 1996 get status `no_edition`; the guidance points to Carstairs for them.
    """
    _prepare(table, True, split)  # Refuse SSPL even when no event has a recommended edition.
    edition = edition_for(events[date_col])
    parts = []
    for ed in edition.dropna().unique():
        rows = events[edition == ed]
        part = attach(rows, table, postcode_col, date_col, edition=ed, measure=measure, prefix=prefix,
                      include_po_boxes=include_po_boxes, include_large_users=include_large_users, split=split)
        part[f"{prefix}_edition"] = ed
        part[f"{prefix}_label"] = label(column(ed, measure), split)
        parts.append(part)
    none = events[edition.isna()].copy()
    if len(none):
        none[f"{prefix}_status"] = NO_EDITION
        none[f"{prefix}_value"] = pd.Series(pd.NA, index=none.index, dtype="Int64")
        none[f"{prefix}_pc_norm"] = None
        none[f"{prefix}_edition"] = None
        none[f"{prefix}_label"] = None
        parts.append(none)
    out = pd.concat(parts).loc[events.index]
    out[f"{prefix}_value"] = out[f"{prefix}_value"].astype("Int64")
    assert len(out) == len(events)
    return out


# --- Urban Rural Classification, history table only --------------------------------------------
# The history table carries every published Scottish Government version, placed from each life's
# own grid reference. Which version suits a year is a PROJECT CHOICE, as in the SPD SQL: by
# reference year, the year a version describes, until the next version's year; not by
# publication date (the 2022 version appeared in December 2024).

def rurality_versions() -> list:
    """(first year, last year, version) by reference year, read from the source registry so the
    windows cannot drift from the versions the table was built with."""
    from pathlib import Path
    from .core.sources import load_registry
    versions = list(load_registry(Path(__file__).resolve().parent / "sources.yaml").rurality_versions)
    return [(v["reference_year"], versions[i + 1]["reference_year"] - 1 if i + 1 < len(versions) else 9999, v["key"])
            for i, v in enumerate(versions)]


def rurality_version_for(dates: pd.Series) -> pd.Series:
    """The classification version for each event date's year; null before the first version."""
    years = pd.to_datetime(dates).dt.year
    out = pd.Series(pd.NA, index=dates.index, dtype="string")
    for first, last, version in rurality_versions():
        out[years.between(first, last)] = version
    return out


def rurality_label(version: str, fold: int) -> str:
    return (f"Scottish Government Urban Rural Classification {version}, {fold}-fold, placed from the record's own "
            "grid reference; version by reference year (project choice)")


def attach_rurality(events: pd.DataFrame, table: pd.DataFrame, postcode_col: str, date_col: str | None,
                    fold: int = 6, version: str | None = None, prefix: str = "rurality",
                    include_po_boxes: bool = False, include_large_users: bool = True, split: str = "a_part") -> pd.DataFrame:
    """The urban-rural class of the record attach() would choose, in the version for each event's
    year, or in one `version` throughout. With `date_col` the record valid on the event date is
    used; with `date_col=None` and a `version`, the current record.

    The status is attach()'s, except where the chosen record has no code in that version: then
    it is the reason stored with the record, `outside_polygons`, `ambiguous_polygons` or
    `po_box`. Events before the first version get `before_first_version`. Like attach(), the
    class is the matched record's own, and PO boxes are excluded unless asked for, in which case
    they come back with no code and status `po_box`.
    """
    if fold not in (6, 8):
        raise ValueError("fold must be 6 or 8")
    table = _prepare(table, date_col is not None, split)
    stem = lambda v: "urbanrural" + v.replace("-", "_")
    if not any(c.startswith("urbanrural") for c in table.columns):
        raise ValueError("This table carries no urban-rural versions. Use the history table, postcode_simd_history.parquet.")
    if version is None and date_col is None:
        raise ValueError("Give a date column to choose the version by year, or name one version to use throughout")
    known = [v for _, _, v in rurality_versions()]
    if version is not None and version not in known:
        raise ValueError(f"version must be one of {known}, not {version!r}")
    _check_split(split)
    table = scope(table, include_po_boxes, include_large_users)
    chosen = (pd.Series(version, index=events.index, dtype="string") if version is not None
              else rurality_version_for(events[date_col]))
    parts = []
    for v in chosen.dropna().unique():
        rows = events[chosen == v]
        code = _attach_column(rows, table, postcode_col, date_col, f"{stem(v)}_{fold}fold", prefix, split)
        stored = _attach_column(rows, table, postcode_col, date_col, f"{stem(v)}_status", "_stored", split)
        reason = stored["_stored_value"].where(code[f"{prefix}_status"].isin([UNIQUE, A_PART, SPLIT_CONSENSUS]))
        code[f"{prefix}_status"] = reason.fillna(code[f"{prefix}_status"]).values
        code[f"{prefix}_version"] = v
        code[f"{prefix}_label"] = rurality_label(v, fold)
        parts.append(code)
    none = events[chosen.isna()].copy()
    if len(none):
        none[f"{prefix}_status"] = BEFORE_FIRST_VERSION
        none[f"{prefix}_value"] = pd.NA
        none[f"{prefix}_pc_norm"] = None
        none[f"{prefix}_version"] = None
        none[f"{prefix}_label"] = None
        parts.append(none)
    out = pd.concat(parts).loc[events.index]
    out[f"{prefix}_value"] = out[f"{prefix}_value"].astype("Int8")
    assert len(out) == len(events)
    return out
