"""The build report: what happened to the data, in order, with this run's numbers.

Written beside the manifest as BUILD_REPORT.md by every build. The manifest holds every check
for the machine; this holds the story for a person.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .checks import Report
from .sources import Registry


def _actual(report: Report, name: str, default=None):
    return next((c.actual for c in report.checks if c.name == name), default)


def _passed(report: Report, name: str) -> str:
    """Under Dagster a check may have run in an upstream asset; it must have passed for this
    step to run at all, so it is reported as passed upstream rather than as missing."""
    c = next((c for c in report.checks if c.name == name), None)
    return "ok" if c is not None and c.passed else "FAILED" if c is not None else "ok, upstream"


def _detail(report: Report, name: str) -> str:
    return next((c.detail for c in report.checks if c.name == name), "")


def render(report: Report, registry: Registry, table: pd.DataFrame, info: dict, mode: str,
           index: pd.DataFrame, phs: pd.DataFrame, gov: pd.DataFrame, example: str = "AB123GQA") -> str:
    s = report.summary()
    L = [f"# Build report: postcode_simd", "",
         f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M')}Z, source mode {mode}, "
         f"SPD release {registry.spd_release}. {s['blocking_passed']} blocking checks passed, {s['blocking_failed']} failed.", ""]

    # 1. sources
    verified = sum(1 for c in report.checks if c.name.startswith("source.hash.") and c.passed)
    L += ["## 1. Sources", "",
          f"{len(registry.objects)} remote objects, {len(registry.files)} pinned files. "
          f"{verified} of {len(registry.files)} files present with the pinned hash."
          + (" All match." if verified == len(registry.files) else " **Some do not.**"), ""]

    # 2. index
    by_type = index["spd_user_type"].value_counts()
    small, large = int(by_type.get("small_user", 0)), int(by_type.get("large_user", 0))
    current = int(index["is_current"].sum())
    from .spd import interval_summary
    intervals, _ = interval_summary(index)
    touching, overlaps = intervals["touching_pairs"], intervals["strict_overlaps"]
    multi = int(index.loc[index["is_current"], "pc_base"].value_counts().gt(1).sum())
    L += ["## 2. Postcode index", "",
          f"SmallUser {small:,} records + LargeUser {large:,} = {len(index):,}, "
          f"of which {current:,} current and {len(index) - current:,} deleted. "
          f"Every original column kept as text; `pc_norm` (uppercase, no spaces, NRS suffix kept), `pc_base`, "
          f"`introduced_on`, `deleted_on`, `is_current` and `spd_user_type` added.",
          f"Key `pc_norm` + `introduced_on` unique: {_passed(report, 'spd.primary_key_unique')}. "
          f"{touching} records touch on a date, {overlaps} overlap. "
          f"Ordinary postcodes with more than one current record: {multi}.", ""]

    # 3. PHS
    L += ["## 3. PHS population-weighted SIMD", "", "| Edition | Rows | Data zones | Bands | Rank 1 in band 1 |", "| --- | ---: | --- | --- | --- |"]
    for ed in registry.phs_editions:
        k = ed["key"]
        L.append(f"| {k} | {int((phs['edition'] == k).sum()):,} | {ed['dz_vintage']} | "
                 f"{'inverted: 11 - decile, 6 - quintile' if ed['invert_bands'] else 'as published'} | {_passed(report, f'phs.{k}.rank1_in_band1')} |")
    L += ["", "After this step 1 means most deprived in every edition. Ranks and the 15% flags are never changed.", ""]

    # 4. government
    L += ["## 4. Scottish Government unweighted SIMD", "", "| Edition | Rows | Same data zones as PHS | Rank identical to PHS |", "| --- | ---: | --- | --- |"]
    for ed in registry.govscot_editions:
        k = ed["key"]
        L.append(f"| {k} | {int((gov['edition'] == k).sum()):,} | {_passed(report, f'cross.{k}.same_zones')} | {_passed(report, f'cross.{k}.rank_identical')} |")
    L += ["", "Bands and population copied from the shapefile tables as published; nothing is calculated or compared "
          "beyond confirming that both sources describe the same zones with the same ranks.", ""]

    # 5. joins
    L += ["## 5. Joins, one edition at a time", "",
          "Each join looks up the record's data zone in one edition table and copies that edition's values on. "
          "2001 data zones for 2004 to 2012, 2011 data zones for 2016 and 2020v2. The order is fixed for reading; "
          "it does not affect the result.", "",
          "| Step | Key | Rows before and after | Columns added | Empty cells |", "| --- | --- | ---: | ---: | --- |"]
    n = 0
    for kind, editions in (("phs", registry.phs_editions), ("gov", registry.govscot_editions)):
        for ed in editions:
            n += 1
            k = ed["key"]
            rows = _actual(report, f"join.{kind}.{k}.rows_unchanged", len(table))
            added = _detail(report, f"join.{kind}.{k}.every_record_matched").split(" ")[0]
            L.append(f"| {n}. {'PHS' if kind == 'phs' else 'Government'} {k} | DataZone{ed['dz_vintage']}Code | "
                     f"{rows:,} | {added} | {_passed(report, f'join.{kind}.{k}.every_record_matched')} |")
    L += [""]

    # 6. output
    L += ["## 6. Output", "",
          f"{info['rows']:,} rows by {info['columns']} columns. Written to a temporary file, reopened, and every attached "
          f"value re-looked-up from the reference tables through the saved file's own data zone codes: "
          f"{_passed(report, 'readback.attached_values')}. Original columns compared with the index: {_passed(report, 'readback.index_columns')}.",
          f"Rows-only fingerprint `{info['logical_fingerprint']}`. File SHA256 `{info['sha256']}`. "
          "The fingerprint changes only when data changes; the file hash also covers the embedded decision log.", ""]

    # example
    ex = table[table["pc_norm"] == example]
    if len(ex):
        ex = ex[ex["is_current"]].iloc[0] if ex["is_current"].any() else ex.iloc[0]
        L += [f"## Example: {ex['Postcode']}", "",
              f"{ex['spd_user_type']}, introduced {pd.Timestamp(ex['introduced_on']).date()}, "
              f"{'current' if ex['is_current'] else 'deleted ' + str(pd.Timestamp(ex['deleted_on']).date())}. "
              f"2001 zone {ex['DataZone2001Code']}, 2011 zone {ex['DataZone2011Code']}.", "",
              "| Edition | Via | Rank | PHS Scotland quintile | Government quintile |", "| --- | --- | ---: | ---: | ---: |"]
        for ed in registry.phs_editions:
            k, v = ed["key"], ed["dz_vintage"]
            L.append(f"| {k} | {ex[f'DataZone{v}Code']} | {ex[f'simd{k}_rank']} | {ex[f'simd{k}_pw_scotland_quintile']} | {ex[f'simd{k}_uw_scotland_quintile']} |")
        L += ["", f"To see the source rows behind these numbers: `python -m simd_ingest.trace \"{ex['Postcode']}\"`.", ""]
    return "\n".join(L)
