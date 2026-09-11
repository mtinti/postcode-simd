"""Look up SIMD for a postcode the way the PHS deprivation guidance describes.

The guidance's method: choose the edition for the years of your data, choose the category
and level, then match by postcode. This module does the matching and leaves the choices to
the analyst, who passes an edition and a measure explicitly.

    from simd_ingest import lookup
    t = lookup.load("results/postcode_simd.parquet")
    lookup.lookup(t, "G71 8BQ", edition="2020v2")                      # most recent
    lookup.lookup(t, "AB10 1BF", edition="2012", on="2012-06-01")      # at a date
    lookup.attach(cohort, t, "postcode", "event_date", edition="2020v2")  # a whole frame

Statuses, and the rule behind them: several records can be valid for one ordinary postcode
because NRS splits postcodes that straddle a boundary into A, B and C parts. If every valid
record agrees on the requested measure the answer is `split_consensus`; if they disagree it
is `split_conflict` and the value is null. The module never picks A, averages, or votes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from .core.spd import normalise_postcode

# PHS deprivation guidance for analysts v3.5, table 4: years of health data -> edition.
# A recommendation. Nothing in this module calls it for you.
GUIDANCE_TABLE_4 = [(1996, 2003, "2004"), (2004, 2006, "2006"), (2007, 2009, "2009v2"),
                    (2010, 2013, "2012"), (2014, 2016, "2016"), (2017, 9999, "2020v2")]

NOT_FOUND, UNIQUE, SPLIT_CONSENSUS, SPLIT_CONFLICT, DELETED = "not_found", "unique", "split_consensus", "split_conflict", "deleted"
NO_EDITION = "no_edition"  # the event predates SIMD; the guidance points to Carstairs
STATUSES = (NOT_FOUND, UNIQUE, SPLIT_CONSENSUS, SPLIT_CONFLICT, DELETED, NO_EDITION)

_SCOPE = {"scotland": "within-Scotland", "hb": "within-NHS-Board", "hscp": "within-HSCP", "ca": "within-council-area"}
_WEIGHT = {"pw": "PHS population-weighted", "uw": "Scottish Government unweighted"}
# Large-user records whose link field carries one of these have no residential location: PO
# boxes and the like. PHS practice attaches no deprivation to them, so they are excluded by
# default from every lookup. The table itself keeps them, with the SIMD the directory assigns.
PO_BOX_SENTINELS = ("NO LINKP", "NO LINK")


def scope(table: pd.DataFrame, include_po_boxes: bool = False, include_large_users: bool = True) -> pd.DataFrame:
    """The records a lookup may match. Defaults follow the PHS guidance, Appendix A."""
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


def label(col: str) -> str:
    """The label the guidance's checklist requires, derived from the column name."""
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
    """The table with its two date columns as timestamps, ready for comparisons."""
    t = pd.read_parquet(path)
    for c in ("introduced_on", "deleted_on"):
        t[c] = pd.to_datetime(t[c])
    return t


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


def _resolve(valid: pd.DataFrame, col: str) -> tuple:
    if len(valid) == 1:
        return UNIQUE, valid[col].iloc[0]
    values = valid[col].unique()
    if len(values) == 1:
        return SPLIT_CONSENSUS, values[0]
    return SPLIT_CONFLICT, None


def lookup(table: pd.DataFrame, postcode: str, edition: str, measure: str = "pw_scotland_quintile", on=None,
           include_po_boxes: bool = False, include_large_users: bool = True) -> Result:
    """SIMD for one postcode, current or valid on a day. The postcode may be an ordinary
    postcode or a full NRS key with its split suffix. PO boxes are excluded unless asked for."""
    table = scope(table, include_po_boxes, include_large_users)
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
        return Result(postcode, key, edition, measure, when, NOT_FOUND, None, label(col), cand)
    if when is None:
        valid = cand[cand["is_current"]]
    else:
        valid = cand[(cand["introduced_on"] <= when) & (cand["deleted_on"].isna() | (cand["deleted_on"] > when))]
    if valid.empty:
        return Result(postcode, key, edition, measure, when, DELETED, None, label(col), cand)
    status, value = _resolve(valid, col)
    return Result(postcode, key, edition, measure, when, status, value, label(col), valid)


def attach(events: pd.DataFrame, table: pd.DataFrame, postcode_col: str, date_col: str | None,
           edition: str, measure: str = "pw_scotland_quintile", prefix: str = "simd",
           include_po_boxes: bool = False, include_large_users: bool = True) -> pd.DataFrame:
    """One result per event row: status, value and the matched NRS key where unique.

    Rows are never dropped or duplicated. With `date_col` the record valid on the event's
    date is used; without it, the current record. PO boxes are excluded unless asked for.
    """
    table = scope(table, include_po_boxes, include_large_users)
    col = column(edition, measure)
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
    summary = pd.DataFrame({"n_known": known.groupby(m["_row"]).sum(),
                            "n_valid": v.groupby("_row").size().reindex(range(len(events)), fill_value=0),
                            "n_values": v.groupby("_row")[col].nunique().reindex(range(len(events)), fill_value=0),
                            "value": v.groupby("_row")[col].first().reindex(range(len(events))),
                            "pc_norm": v.groupby("_row")["pc_norm"].first().reindex(range(len(events)))})
    status = pd.Series(NOT_FOUND, index=summary.index)
    status[(summary["n_known"] > 0) & (summary["n_valid"] == 0)] = DELETED
    status[summary["n_valid"] == 1] = UNIQUE
    status[(summary["n_valid"] > 1) & (summary["n_values"] == 1)] = SPLIT_CONSENSUS
    status[(summary["n_valid"] > 1) & (summary["n_values"] > 1)] = SPLIT_CONFLICT
    resolved = status.isin([UNIQUE, SPLIT_CONSENSUS])
    out = events.copy()
    out[f"{prefix}_status"] = status.values
    out[f"{prefix}_value"] = summary["value"].where(resolved).astype("Int64").values
    out[f"{prefix}_pc_norm"] = summary["pc_norm"].where(status == UNIQUE).values
    out.attrs[f"{prefix}_label"] = label(col)
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
                  include_po_boxes: bool = False, include_large_users: bool = True) -> pd.DataFrame:
    """The guidance's first approach: each event takes the edition recommended for its year,
    and the record valid on its date. Adds an edition column and a per-row label.

    Events before 1996 get status `no_edition`; the guidance points to Carstairs for them.
    """
    edition = edition_for(events[date_col])
    parts = []
    for ed in edition.dropna().unique():
        rows = events[edition == ed]
        part = attach(rows, table, postcode_col, date_col, edition=ed, measure=measure, prefix=prefix,
                      include_po_boxes=include_po_boxes, include_large_users=include_large_users)
        part[f"{prefix}_edition"] = ed
        part[f"{prefix}_label"] = label(column(ed, measure))
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
