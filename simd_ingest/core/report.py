"""The build report: what happened to the data, in order, with this run's numbers.

Written beside the manifest as BUILD_REPORT.md by every build. The manifest holds every check
for the machine; this holds the story for a person. Two tables come out of a build, so the
report says where each starts, what they share, and where they differ.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from .checks import Report
from .sources import Registry
from .spd import part_of


def _actual(report: Report, name: str, default=None):
    return next((c.actual for c in report.checks if c.name == name), default)


def _passed(report: Report, name: str) -> str:
    """Describe recorded evidence only. Absence is not evidence of a passing check."""
    c = next((c for c in report.checks if c.name == name), None)
    return "ok" if c is not None and c.passed else "FAILED" if c is not None else "NOT RECORDED"


def _detail(report: Report, name: str) -> str:
    return next((c.detail for c in report.checks if c.name == name), "")


def _snapshot_change(changes: dict, product: str) -> list:
    if changes.get("status") != "compared":
        return [f"Comparison unavailable: {changes.get('reason', 'not recorded')}.", ""]
    L = [f"Compared with hash-verified {product} release {changes['previous_release']}. "
         f"{changes['added_records']:,} records added, {changes['removed_records']:,} removed from the snapshot, "
         f"{changes['changed_records']:,} changed among {changes['common_records']:,} shared natural keys. "
         f"{changes['newly_deleted_records']:,} retained records became deleted. "
         "The release label alone is not counted as a record change.", "",
         f"Columns added: {', '.join(changes['added_columns']) or 'none'}. "
         f"Columns removed: {', '.join(changes['removed_columns']) or 'none'}.", ""]
    if changes["changed_fields"]:
        L += ["| Changed field | Shared records affected |", "| --- | ---: |"]
        L += [f"| {col} | {count:,} |" for col, count in changes["changed_fields"].items()]
    else:
        L += ["No shared field values changed."]
    return L + [""]


def render(report: Report, registry: Registry, tables: dict, info: dict, mode: str,
           indices: dict, phs: pd.DataFrame, gov: pd.DataFrame, example: str = "AB123GQ") -> str:
    """`tables` and `info` are keyed by table name (main, history); `indices` by index source."""
    s = report.summary()
    main, history = indices["sspl"], indices["spd"]
    changes = report.observations.get("snapshot_changes", {})
    L = [f"# Build report: postcode_simd and postcode_simd_history", "",
         f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M')}Z, source mode {mode}, "
         f"SSPL release {registry.sspl_release}, SPD release {registry.spd_release}. "
         f"{s['blocking_passed']} blocking checks passed, {s['blocking_failed']} failed.", "",
         "Two tables are built from the same SIMD sources. The **main table** starts from the Scottish Statistics "
         "Postcode Lookup: the latest life of every whole postcode, with each geography taken from the centroid of "
         "the postcode's 2022 output area. The **history table** starts from the Scottish Postcode Directory: "
         "every postcode life, with the geography containing the postcode's own grid reference. "
         "Same joins, same checks, different postcode grain and different data-zone allocation.", ""]

    # 1. sources
    verified = sum(1 for c in report.checks if c.name.startswith("source.hash.") and c.passed)
    L += ["## 1. Sources", "",
          f"{len(registry.objects)} remote objects, {len(registry.files)} pinned files. "
          f"{verified} of {len(registry.files)} files present with the pinned hash."
          + (" All match." if verified == len(registry.files) else " **Verification evidence is missing or failed.**"), ""]

    # 2. main index
    by_type = main["spd_user_type"].value_counts()
    current = int(main["is_current"].sum())
    links = report.observations.get("sspl.links", {})
    profile = report.observations.get("sspl.profile", {})
    L += ["## 2. Main table index: Scottish Statistics Postcode Lookup", "",
          f"{len(main):,} whole postcodes: {int(by_type.get('small_user', 0)):,} small user and "
          f"{int(by_type.get('large_user', 0)):,} large user, of which {current:,} current and {len(main) - current:,} "
          f"deleted (the latest life of a deleted postcode is kept). Totals are {registry.sspl_file.get('totals_basis', 'counted')} "
          "from the pinned file, since NRS publishes none. Every original column kept as text; `pc_norm` (uppercase, no "
          "spaces), `introduced_on`, `deleted_on`, `is_current`, `spd_user_type` and `sspl_release` added. "
          f"Key `pc_norm` unique: {_passed(report, 'sspl.primary_key_unique')}. No split suffix exists: NRS made split "
          f"postcodes whole on the A part ({profile.get('split_indicator_y', {}).get('small_user', 'NOT RECORDED')} small-user "
          "records carry `SplitIndicator` Y).",
          f"Large-user links: {links.get('linked', 0):,} to a small-user postcode in the file, "
          f"{links.get('NO LINKP', 0):,} PO boxes (`NO LINKP`), {links.get('NO LINK', 0):,} `NO LINK`, "
          f"{links.get('small_user_target_not_found', 0):,} without a small-user target in the file (absent or now large-user); "
          f"{links.get('with_split_suffix', 0):,} links retain an NRS split suffix.", "",
          "### Change from previous snapshot", "", *_snapshot_change(changes.get("main", {}), "SSPL")]

    # 3. history index
    by_type = history["spd_user_type"].value_counts()
    small, large = int(by_type.get("small_user", 0)), int(by_type.get("large_user", 0))
    current = int(history["is_current"].sum())
    from .spd import interval_summary
    intervals, _ = interval_summary(history)
    touching, overlaps = intervals["touching_pairs"], intervals["strict_overlaps"]
    multi = int(history.loc[history["is_current"], "pc_base"].value_counts().gt(1).sum())
    L += ["## 3. History table index: Scottish Postcode Directory", "",
          f"SmallUser {small:,} records + LargeUser {large:,} = {len(history):,}, "
          f"of which {current:,} current and {len(history) - current:,} deleted. "
          f"Every original column kept as text; `pc_norm` (uppercase, no spaces, NRS suffix kept), `pc_base`, "
          f"`introduced_on`, `deleted_on`, `is_current`, `spd_user_type` and `spd_release` added.",
          f"Key `pc_norm` + `introduced_on` unique: {_passed(report, 'spd.primary_key_unique')}. "
          f"{touching} touching record pairs, {overlaps} overlapping pairs. "
          f"Ordinary postcodes with more than one current record: {multi}.", ""]
    L += ["### Release profile (information, not acceptance gates)", "",
          "| File | Split records | Repeated keys | Same-day records |",
          "| --- | ---: | ---: | ---: |"]
    for role in ("small_user", "large_user"):
        p = report.observations.get(f"spd.{role}", {})
        values = [p.get(k, "NOT RECORDED") for k in ("split_records", "repeated_keys", "same_day")]
        L.append(f"| {role} | " + " | ".join(str(v) for v in values) + " |")
    L += ["", "Other profile details (key lengths, link categories and ambiguity by vintage) are in the manifest.", "",
          "### Change from previous snapshot", "", *_snapshot_change(changes.get("history", {}), "SPD")]

    # 4. agreement
    a = report.observations.get("table_agreement")
    L += ["## 4. Agreement between the two tables (information, not acceptance gates)", ""]
    if a:
        cut = a["record_differences"]
        L += [f"The history table reduced to latest full-key lives, then live, whole/A and newest introduction, has "
              f"{a['history_whole_postcodes']:,} postcodes; the main table has {a['main_rows']:,}; {a['shared']:,} are shared, "
              f"{a['only_in_main']:,} exist only in the main table and {a['only_in_history']:,} only in the history table. "
              f"Unresolved history representatives: {a['unresolved_history_representatives'] or 'none'}. "
              f"Comparisons below use {a['shared_resolved']:,} shared, resolved representatives. "
              f"The introduction date differs on {cut['introduced_on']:,}, the live/deleted state on "
              f"{cut['is_current']:,} and the user type on {cut['spd_user_type']:,}.", "",
              "These are observed differences between the pinned releases, not a causal decomposition. "
              "The products use different allocation methods (2022 output-area centroid versus postcode grid reference); "
              "release changes, reintroductions and source corrections can also affect geography. Even matching release "
              "labels do not prove the cause of an individual difference. Values below are each record's own attached "
              "SIMD, before consumer SQL follows any large-user link; they do not measure agreement with a PHS lookup.", "",
              "| Column | Shared postcodes that differ | Of which current in both |", "| --- | ---: | ---: |"]
        L += [f"| {col} | {v['all']:,} | {v['current']:,} |" for col, v in a["geography_differences"].items()]
        L += ["", f"Effect on the attached SIMD for the {a['shared_and_current_in_both']:,} postcodes current in both tables:", "",
              "| Edition | PHS Scotland quintile differs | PHS Scotland decile differs | Most-deprived 15% flag differs | Government quintile differs |",
              "| --- | ---: | ---: | ---: | ---: |"]
        L += [f"| {k} | {v['pw_scotland_quintile']:,} | {v['pw_scotland_decile']:,} | {v['most15pc']:,} | {v['uw_scotland_quintile']:,} |"
              for k, v in a["band_differences_among_current"].items()]
        L += [""]
    else:
        L += ["NOT RECORDED.", ""]

    # 5. PHS
    L += ["## 5. PHS population-weighted SIMD", "", "| Edition | Rows | Data zones | Bands | Rank 1 in band 1 |", "| --- | ---: | --- | --- | --- |"]
    for ed in registry.phs_editions:
        k = ed["key"]
        L.append(f"| {k} | {int((phs['edition'] == k).sum()):,} | {ed['dz_vintage']} | "
                 f"{'inverted: 11 - decile, 6 - quintile' if ed['invert_bands'] else 'as published'} | {_passed(report, f'phs.{k}.rank1_in_band1')} |")
    L += ["", "After this step 1 means most deprived in every edition. Ranks and the 15% flags are never changed.", ""]

    # 6. government
    L += ["## 6. Scottish Government unweighted SIMD", "", "| Edition | Rows | Same data zones as PHS | Rank identical to PHS |", "| --- | ---: | --- | --- |"]
    for ed in registry.govscot_editions:
        k = ed["key"]
        L.append(f"| {k} | {int((gov['edition'] == k).sum()):,} | {_passed(report, f'cross.{k}.same_zones')} | {_passed(report, f'cross.{k}.rank_identical')} |")
    L += ["", "Bands and population copied from the shapefile tables as published; nothing is calculated or compared "
          "beyond confirming that both sources describe the same zones with the same ranks.", ""]

    # 7. joins
    L += ["## 7. Joins, one edition at a time, for each table", "",
          "Each join looks up the record's data zone in one edition table and copies that edition's values on. "
          "The source registry declares the data-zone vintage for each edition. The order is fixed for reading; "
          "it does not affect the result.", ""]
    for name in tables:
        L += [f"### {name} table", "",
              "| Step | Key | Rows before and after | Columns added | Empty cells |", "| --- | --- | ---: | ---: | --- |"]
        n = 0
        for kind, editions in (("phs", registry.phs_editions), ("gov", registry.govscot_editions)):
            for ed in editions:
                n += 1
                k = ed["key"]
                rows = _actual(report, f"join.{name}.{kind}.{k}.rows_unchanged")
                rows_label = f"{rows:,}" if rows is not None else "NOT RECORDED"
                added = _detail(report, f"join.{name}.{kind}.{k}.every_record_matched").split(" ")[0]
                L.append(f"| {n}. {'PHS' if kind == 'phs' else 'Government'} {k} | DataZone{ed['dz_vintage']}Code | "
                         f"{rows_label} | {added or 'NOT RECORDED'} | {_passed(report, f'join.{name}.{kind}.{k}.every_record_matched')} |")
        L += [""]

    # 7b. rurality
    agreement = report.observations.get("rurality.agreement")
    if registry.rurality_versions and agreement is not None:
        gate = registry.rurality_published
        L += ["## 7b. Urban Rural Classification, history table only", "",
              f"Every life's own grid reference is placed in each of the {len(registry.rurality_versions)} published "
              "Scottish Government classification versions. A point in no polygon is null with `outside_polygons`, never "
              "the nearest polygon; a post-office box is null with `po_box` in every version because its grid reference "
              "is the sorting office. The main table keeps only the 2022 code the lookup publishes.", "",
              f"**The gate.** The {gate['version']} placement must reproduce the codes the directory publishes, before "
              f"boxes are withheld, with every life in the denominator and a point in no polygon counted wrong: "
              f"{gate['current_small_user']:.1%} for current small users and {gate['other_cohorts']:.0%} for every other "
              f"cohort of more than {gate['min_cohort']:,} lives. Thresholds fixed before the first comparison.", "",
              "| Cohort | Lives | Agreement | Gated | Result |", "| --- | ---: | ---: | --- | --- |"]
        for cohort, v in agreement.items():
            name = f"rurality.agreement.{cohort}"
            gated = any(c.name == name for c in report.checks)
            rate = "n/a" if v["agreement"] is None else f"{v['agreement']:.4%}"
            L.append(f"| {cohort.replace('_', ' ')} | {v['lives']:,} | {rate} | {'yes' if gated else 'no, too few'} | "
                     f"{_passed(report, name) if gated else 'reported'} |")
        L += ["", "| Version | Reference year | Outside every polygon, boxes included | Ambiguous | Geometries repaired |",
              "| --- | ---: | ---: | ---: | ---: |"]
        for v in registry.rurality_versions:
            k = f"rurality.{v['key']}"
            L.append(f"| {v['key']} | {v['reference_year']} | {report.observations.get(k + '.outside_polygons', 'NOT RECORDED')} | "
                     f"{report.observations.get(k + '.ambiguous_polygons', 'NOT RECORDED')} | "
                     f"{report.observations.get(k + '.invalid_geometries_repaired', 'NOT RECORDED')} |")
        boxes = report.observations.get("rurality.po_boxes_withheld")
        L += ["", f"Post-office boxes withheld in every version: {'NOT RECORDED' if boxes is None else f'{boxes:,}'}. "
              "Readback places every point again from the saved file's own grid references: "
              f"{_passed(report, 'readback.history.rurality_values')}.", ""]

    # 8. output
    L += ["## 8. Output", ""]
    for name, i in info.items():
        L += [f"**{name}**: `{i['table']}`, {i['rows']:,} rows by {i['columns']} columns, key {i['key']}, "
              f"index {i['index_source']} release {i['index_release']}, allocation {i['allocation']}. "
              f"Written to a temporary file, reopened, and every attached value re-looked-up from the reference tables "
              f"through the saved file's own data zone codes: {_passed(report, f'readback.{name}.attached_values')}. "
              f"Original columns compared with the index: {_passed(report, f'readback.{name}.index_columns')}. "
              f"Rows-only fingerprint `{i['logical_fingerprint']}`. File SHA256 `{i['sha256']}`.", ""]
    L += ["Null and source blank are distinct. Embedded convention, schema version, index source and release, allocation, "
          "key, source pins and decision hash are checked against the build inputs, not just for the presence of "
          "metadata keys. With the same pinned runtime, identical rows have the same fingerprint; the file hash also "
          "covers metadata.", ""]

    # example, from the main table, with the history table's answer beside it
    table = tables.get("main")
    if table is not None and len(table):
        ex = table[table["pc_norm"] == example]
        ex = (ex if len(ex) else table.iloc[:1]).iloc[0]
        hist = tables.get("history")
        hrow = None
        if hist is not None:
            cand = hist[hist["pc_base"].eq(ex["pc_norm"]) & hist["is_current"]]
            if len(cand):
                a_part = cand[part_of(cand) == "A"]
                hrow = (a_part if len(a_part) else cand).iloc[0]
        vintages = sorted({e["dz_vintage"] for e in registry.phs_editions})
        L += [f"## Example: {ex['Postcode']}", "",
              f"Main table: {ex['spd_user_type']}, introduced {pd.Timestamp(ex['introduced_on']).date()}, "
              f"{'current' if ex['is_current'] else 'deleted ' + str(pd.Timestamp(ex['deleted_on']).date())}. "
              "Zones: " + ", ".join(f"{v}: {ex[f'DataZone{v}Code']}" for v in vintages) + "."]
        if hrow is not None:
            L += [f"History table, current record `{hrow['pc_norm']}`: zones "
                  + ", ".join(f"{v}: {hrow[f'DataZone{v}Code']}" for v in vintages) + "."]
        L += ["", "| Edition | Main via | Rank | PHS Scotland quintile | Government quintile | History via | Rank | PHS Scotland quintile |",
              "| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |"]
        for ed in registry.phs_editions:
            k, v = ed["key"], ed["dz_vintage"]
            h = (f"{hrow[f'DataZone{v}Code']} | {hrow[f'simd{k}_rank']} | {hrow[f'simd{k}_pw_scotland_quintile']}"
                 if hrow is not None else "not current | | ")
            L.append(f"| {k} | {ex[f'DataZone{v}Code']} | {ex[f'simd{k}_rank']} | {ex[f'simd{k}_pw_scotland_quintile']} | "
                     f"{ex[f'simd{k}_uw_scotland_quintile']} | {h} |")
        L += ["", f"To see the source rows behind these numbers: `python -m simd_ingest.trace \"{ex['Postcode']}\"`.", ""]
    return "\n".join(L)
