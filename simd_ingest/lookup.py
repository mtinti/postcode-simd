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
# No record was valid on the date, but the postcode had a life that ended before it: that life
# was used (project choice). Usually a Royal Mail recoding the record never caught up with.
PREVIOUS_LIFE = "previous_life"
MISSING_DATE = "missing_date"  # a dated question asked without a date
STATUSES = (NOT_FOUND, UNIQUE, A_PART, SPLIT_CONSENSUS, SPLIT_CONFLICT, DELETED, NO_EDITION, PREVIOUS_LIFE, MISSING_DATE)
_RESOLVED = (UNIQUE, A_PART, SPLIT_CONSENSUS)
SPLIT_RULES = ("a_part", "report")

_SCOPE = {"scotland": "within-Scotland", "hb": "within-NHS-Board", "hscp": "within-HSCP", "ca": "within-council-area"}
_WEIGHT = {"pw": "PHS population-weighted", "uw": "Scottish Government unweighted"}
# Large-user records whose link field carries one of these have no residential location: PO
# boxes and the like. PHS practice attaches no deprivation to them, so they are excluded by
# default from every lookup. The table itself keeps them, with the SIMD the directory assigns.
PO_BOX_SENTINELS = ("NO LINKP", "NO LINK")


def _excluded(table: pd.DataFrame, include_po_boxes: bool, include_large_users: bool) -> pd.Series:
    out = pd.Series(False, index=table.index)
    if not include_large_users and "spd_user_type" in table:
        out |= table["spd_user_type"] == "large_user"
    if not include_po_boxes and "LinkedSmallUserPostcode" in table:
        out |= table["LinkedSmallUserPostcode"].isin(PO_BOX_SENTINELS)
    return out.fillna(False).astype(bool)


def scope(table: pd.DataFrame, include_po_boxes: bool = False, include_large_users: bool = True) -> pd.DataFrame:
    """Python's scope: exclude no-link sentinels by default; keep own-record geography.
    The lookups apply it to the record they choose, never before choosing: removing a PO-box
    life first would let an earlier life answer for a date the PO box covers."""
    return table[~_excluded(table, include_po_boxes, include_large_users)]


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
    table = _prepare(table, on is not None, split)
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
    previous = False
    if valid.empty and when is not None:
        # The previous life: the last real life that ended before the date, never a later one.
        ended = cand[cand["deleted_on"].notna() & (cand["deleted_on"] <= when) & (cand["introduced_on"] < cand["deleted_on"])]
        if len(ended):
            valid, previous = ended[ended["deleted_on"] == ended["deleted_on"].max()], True
    if valid.empty:
        return Result(postcode, key, edition, measure, when, DELETED, None, label(col, split), cand)
    # The exclusions judge the record that answers the question, after it has been chosen.
    kept = valid[~_excluded(valid, include_po_boxes, include_large_users)]
    if kept.empty:
        return Result(postcode, key, edition, measure, when, NOT_FOUND, None, label(col, split), valid)
    status, value = _resolve(kept, col, split)
    if previous and status in _RESOLVED:
        status = PREVIOUS_LIFE
    return Result(postcode, key, edition, measure, when, status, value, label(col, split), kept)


def attach(events: pd.DataFrame, table: pd.DataFrame, postcode_col: str, date_col: str | None,
           edition: str, measure: str = "pw_scotland_quintile", prefix: str = "simd",
           include_po_boxes: bool = False, include_large_users: bool = True, split: str = "a_part") -> pd.DataFrame:
    """One result per event row: status, value and the matched NRS key where resolved.

    Rows are never dropped or duplicated. With `date_col` the record valid on the event's
    date is used; without it, the current record. PO boxes are excluded unless asked for.
    Split postcodes resolve to the A part unless split="report".
    """
    _check_split(split)
    table = _prepare(table, date_col is not None, split)
    col = column(edition, measure)
    out = _attach_column(events, table, postcode_col, date_col, [col], prefix, split, include_po_boxes, include_large_users)
    out[f"{prefix}_value"] = out[f"{prefix}_value"].astype("Int64")
    out.attrs[f"{prefix}_label"] = label(col, split)
    return out


def _attach_column(events: pd.DataFrame, table: pd.DataFrame, postcode_col: str, date_col: str | None,
                   value_cols: list, prefix: str, split: str, include_po_boxes: bool = False,
                   include_large_users: bool = True) -> pd.DataFrame:
    """attach()'s record resolution: one row per event, in order, never dropped or duplicated.

    The record is chosen first, on the whole table: the record valid on the date, or the
    previous life, or the current one. The exclusions are then applied to that record, so an
    excluded PO box answers not_found rather than letting an older life answer for it.
    value_cols are resolved together as one tuple taken from one record, nulls included:
    parts that agree must agree on every column, and a null is a value like any other.
    Returns {prefix}_status, {prefix}_value (the first column), {prefix}_pc_norm, and for any
    further column a companion {prefix}__<column>.
    """
    ev = pd.DataFrame({"_row": range(len(events)),
                       "_key": normalise_postcode(events[postcode_col].astype("string").fillna("")).replace("", pd.NA).to_numpy()})
    if date_col is not None:
        ev["_on"] = pd.to_datetime(events[date_col]).to_numpy()
    extra = [c for c in ("spd_user_type", "LinkedSmallUserPostcode") if c in table]
    cols = list(dict.fromkeys(["pc_norm", "pc_base", "introduced_on", "deleted_on", "is_current", *value_cols, *extra]))
    # Two routes, as in lookup(): an ordinary postcode matches on pc_base; a full NRS key
    # with a suffix matches its own split part on pc_norm and then takes precedence.
    by_base = ev.merge(table[cols], left_on="_key", right_on="pc_base", how="left")
    parts = table.loc[table["pc_norm"] != table["pc_base"], cols]
    by_part = ev.merge(parts, left_on="_key", right_on="pc_norm", how="inner")
    exact_rows = set(by_part["_row"])
    m = pd.concat([by_base[~by_base["_row"].isin(exact_rows)], by_part], ignore_index=True)
    known = m["pc_norm"].notna()
    rows = range(len(events))
    previous_rows, missing_rows = set(), set()
    if date_col is not None:
        dated = m["_on"].notna()
        missing_rows = set(m.loc[known & ~dated, "_row"])
        valid = known & dated & (m["introduced_on"] <= m["_on"]) & (m["deleted_on"].isna() | (m["deleted_on"] > m["_on"]))
        # Where no record is valid on the date, the last real life that ended before it.
        ended = (known & dated & ~m["_row"].isin(set(m.loc[valid, "_row"])) & m["deleted_on"].notna()
                 & (m["deleted_on"] <= m["_on"]) & (m["introduced_on"] < m["deleted_on"]))
        last = m.loc[ended].groupby("_row")["deleted_on"].transform("max")
        fallback = pd.Series(False, index=m.index)
        fallback[ended] = m.loc[ended, "deleted_on"] == last
        valid = valid | fallback
        previous_rows = set(m.loc[fallback, "_row"])
    else:
        valid = known & m["is_current"].fillna(False).astype(bool)
    kept = valid & ~_excluded(m, include_po_boxes, include_large_users)
    v = m[kept].copy()
    # One signature per record over every value column, a null marked rather than skipped.
    v["_sig"] = v[value_cols].astype("string").fillna("\x00").agg("\x1f".join, axis=1) if len(v) else pd.Series(dtype="string")
    a = v[part_of(v) == "A"] if len(v) else v
    first = v.groupby("_row").head(1).set_index("_row")          # the first record, nulls and all
    first_a = a.groupby("_row").head(1).set_index("_row")
    n_valid = m[valid].groupby("_row").size().reindex(rows, fill_value=0)
    n_kept = v.groupby("_row").size().reindex(rows, fill_value=0)
    n_values = v.groupby("_row")["_sig"].nunique().reindex(rows, fill_value=0)
    n_a = a.groupby("_row").size().reindex(rows, fill_value=0)
    n_known = known.groupby(m["_row"]).sum().reindex(rows, fill_value=0)

    status = pd.Series(NOT_FOUND, index=rows, dtype="object")
    status[(n_known > 0) & (n_valid == 0)] = DELETED
    status[(n_valid > 0) & (n_kept == 0)] = NOT_FOUND             # the chosen record is excluded
    status[n_kept == 1] = UNIQUE
    status[(n_kept > 1) & (n_values == 1)] = SPLIT_CONSENSUS
    status[(n_kept > 1) & (n_values > 1)] = SPLIT_CONFLICT
    if split == "a_part":
        status[(n_kept > 1) & (n_a == 1)] = A_PART
    status[status.index.isin(missing_rows)] = MISSING_DATE
    source = pd.Series(pd.NA, index=rows, dtype="object")       # which table the answering record is in
    use_first = status.isin([UNIQUE, SPLIT_CONSENSUS])
    use_a = status == A_PART
    out = events.copy()
    out[f"{prefix}_status"] = pd.Series(status).where(~(status.index.isin(previous_rows) & status.isin(_RESOLVED)), PREVIOUS_LIFE).to_numpy()
    for i, c in enumerate(value_cols + ["pc_norm"]):
        values = pd.Series(pd.NA, index=rows, dtype="object")
        if len(first):
            picked = first[c].reindex(rows)
            values[use_first] = picked[use_first]
        if len(first_a):
            picked_a = first_a[c].reindex(rows)
            values[use_a] = picked_a[use_a]
        if c == "pc_norm" and len(first):
            values[status == SPLIT_CONSENSUS] = pd.NA                # consensus is not one record
        name = f"{prefix}_value" if i == 0 else f"{prefix}_pc_norm" if c == "pc_norm" else f"{prefix}__{c}"
        out[name] = values.to_numpy()
    assert len(out) == len(events)
    return out


def _by_group(events: pd.DataFrame, groups: pd.Series, resolve, prefix: str, columns: dict) -> pd.DataFrame:
    """Resolve each group of rows separately and reassemble them in the original order.

    Rows are identified by position, never by index label, so a cohort whose index repeats a
    label, or is empty, comes back unchanged in shape. `groups` holds a group key per row, or
    null for rows no group applies to; `columns` gives the value those rows take per column.
    """
    ev = events.reset_index(drop=True)
    keys = pd.Series(groups.to_numpy(), index=ev.index)
    out = ev.copy()
    for name, value in columns.items():
        out[f"{prefix}_{name}"] = pd.Series([value] * len(ev), index=ev.index, dtype="object")
    for key in keys.dropna().unique():
        at = keys.index[keys == key]
        part = resolve(ev.loc[at], key)
        for name in columns:
            out.loc[at, f"{prefix}_{name}"] = part[f"{prefix}_{name}"].to_numpy()
    out.index = events.index
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
    Events with no date get `missing_date`: they are not before 1996, they are unknown.
    """
    _prepare(table, True, split)  # Refuse SSPL even when no event has a recommended edition.
    dates = pd.to_datetime(events[date_col])
    edition = edition_for(dates)

    def resolve(rows, ed):
        part = attach(rows, table, postcode_col, date_col, edition=ed, measure=measure, prefix=prefix,
                      include_po_boxes=include_po_boxes, include_large_users=include_large_users, split=split)
        part[f"{prefix}_edition"] = ed
        part[f"{prefix}_label"] = label(column(ed, measure), split)
        return part

    out = _by_group(events, edition, resolve, prefix,
                    {"status": NO_EDITION, "value": pd.NA, "pc_norm": None, "edition": None, "label": None})
    out.loc[dates.isna().to_numpy(), f"{prefix}_status"] = MISSING_DATE
    out[f"{prefix}_value"] = pd.array(out[f"{prefix}_value"], dtype="Int64")
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

    The class and its stored reason are resolved together, from one record: where the chosen
    record has no code in that version the status is the reason, `outside_polygons`,
    `ambiguous_polygons` or `po_box`. Split parts agree only if they agree on both, a missing
    code included. Events before the first version get `before_first_version`, and events with
    no date `missing_date`. Like attach(), the class is the matched record's own, and PO boxes
    are excluded unless asked for, in which case they come back with no code and `po_box`.
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
    dates = pd.to_datetime(events[date_col]) if date_col is not None else None
    chosen = (pd.Series(version, index=events.index, dtype="object") if version is not None
              else rurality_version_for(dates).astype("object"))

    def resolve(rows, v):
        code, reason = f"{stem(v)}_{fold}fold", f"{stem(v)}_status"
        part = _attach_column(rows, table, postcode_col, date_col, [code, reason], prefix, split,
                              include_po_boxes, include_large_users)
        stored = part.pop(f"{prefix}__{reason}")
        resolved = part[f"{prefix}_status"].isin(_RESOLVED + (PREVIOUS_LIFE,))
        part[f"{prefix}_status"] = stored.where(resolved & stored.notna(), part[f"{prefix}_status"]).to_numpy()
        part[f"{prefix}_version"] = v
        part[f"{prefix}_label"] = rurality_label(v, fold)
        return part

    out = _by_group(events, chosen, resolve, prefix,
                    {"status": BEFORE_FIRST_VERSION, "value": pd.NA, "pc_norm": None, "version": None, "label": None})
    if dates is not None:
        out.loc[dates.isna().to_numpy(), f"{prefix}_status"] = MISSING_DATE
    out[f"{prefix}_value"] = pd.array(out[f"{prefix}_value"], dtype="Int8")
    return out
