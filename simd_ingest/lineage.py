"""Column lineage: for every column of each table, where its value comes from and how.

One record per (table, column), derived from the registry, the header schemas and the readers'
own constants, never typed by hand (docs/plans/Column_Provenance_Site_Plan.md). A record holds:

- inputs: each a reference (a pinned published file, a versioned repository file, or a registry
  entry), the field read, any condition, and the join key by which it reaches the row;
- scope: the row itself, or the wider universe a value is computed over;
- transformation: its kind, the rule in words, and the code that applies it;
- checks: the names of the build checks that guard it (definitions; whether a build passed them is
  in that build's manifest.json["checks"]);
- decisions: ids from decisions.yaml.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

from .core import rurality
from .core.govscot import PUBLISHED_DOMAINS
from .core.join import first_edition_of_vintage
from .core.phs import BANDS, FLAGS
from .core.sources import DOMAIN_BANDS, banded_domains, declared_domains, load_registry, status_domains
from .core.weighted import WEIGHTED_BANDS

PACKAGE = Path(__file__).resolve().parent
TABLES = {"history": "output_schema_history.yaml", "main": "output_schema.yaml"}
INDEX = {"history": "spd", "main": "sspl"}


@functools.lru_cache(maxsize=None)
def _context() -> dict:
    registry = load_registry(PACKAGE / "sources.yaml")
    by_path = {f.path: (f, o) for o in registry.objects for f in o.files}
    return {"registry": registry, "by_path": by_path,
            "spd": yaml.safe_load((PACKAGE / "spd_schema.yaml").read_text()),
            "sspl": yaml.safe_load((PACKAGE / "sspl_schema.yaml").read_text()),
            "schemas": {t: yaml.safe_load((PACKAGE / f).read_text()) for t, f in TABLES.items()}}


def _pinned(path: str, field: str, condition: str | None = None, join: str | None = None) -> dict:
    f, o = _context()["by_path"][path]
    return {"kind": "pinned_file", "path": path, "sha256": f.sha256, "object": o.key, "publisher": o.publisher,
            "url": o.url, "field": field, "condition": condition, "join": join}


def _repository(path: str, field: str, condition: str | None = None, join: str | None = None) -> dict:
    return {"kind": "repository_file", "path": path, "field": field, "condition": condition, "join": join}


def _registry(entry: str, field: str) -> dict:
    return {"kind": "registry", "path": "simd_ingest/sources.yaml", "entry": entry, "field": field,
            "condition": None, "join": None}


def _record(table, column, category, inputs, transformation, rule, code, checks, decisions, scope="the row itself"):
    return {"table": table, "column": column, "category": category, "inputs": inputs, "scope": scope,
            "transformation": {"kind": transformation, "rule": rule, "code": code},
            "checks": checks, "decisions": decisions}


# --- by category ---------------------------------------------------------------------------------

def _spd_field(column: str) -> dict:
    ctx = _context()
    files = {s["role"]: s["file"] for s in ctx["registry"].spd_files}
    small, large = column in ctx["spd"]["small_user"], column in ctx["spd"]["large_user"]
    inputs = []
    for role, present in (("small_user", small), ("large_user", large)):
        if present:
            only = "" if small and large else f"; only the {role.replace('_', '-')} file has it, so it is null for the other's records"
            inputs.append(_pinned(files[role], column, f"records of the {role.replace('_', '-')} file{only}"))
    return _record("history", column, "directory", inputs, "copied",
                   "Copied as text from the NRS Scottish Postcode Directory, unchanged; the two files are stacked.",
                   "simd_ingest/core/spd.py: read_index_file, union_index",
                   ["spd.small_user.schema", "spd.large_user.schema", "spd.columns", "readback.history.index_columns"],
                   ["spd-cut-edition", "single-combined-output", "record-key"])


def _sspl_field(column: str) -> dict:
    ctx = _context()
    return _record("main", column, "lookup", [_pinned(ctx["registry"].sspl_file["file"], column)], "copied",
                   "Copied as text from the NRS Scottish Statistics Postcode Lookup, unchanged.",
                   "simd_ingest/core/sspl.py: build_latest_index",
                   ["sspl.schema", "readback.main.index_columns"],
                   ["sspl-main-table", "sspl-allocation-is-part-of-the-contract", "two-nrs-cuts"])


def _derived(table: str, column: str) -> dict:
    ctx = _context()
    if table == "history":
        files = {s["role"]: s["file"] for s in ctx["registry"].spd_files}
        both = lambda field, cond=None: [_pinned(files["small_user"], field, cond), _pinned(files["large_user"], field, cond)]
        code = "simd_ingest/core/spd.py"
        rules = {
            "pc_norm": (both("Postcode"), "normalised", "Postcode uppercased with ASCII spaces removed, keeping any NRS split suffix (A, B, C).", ["postcode-normalisation", "record-key"]),
            "pc_base": (both("Postcode") + [_pinned(files["small_user"], "SplitIndicator", "Y marks a split part, whose A, B or C suffix is validated and removed; large users are never split")],
                        "normalised", "The ordinary postcode: pc_norm with the split suffix removed where SplitIndicator is Y on a small-user record.", ["split-suffix-derived-from-key"]),
            "spd_user_type": ([_pinned(files["small_user"], "(which file the record is in)", "small_user for every record of this file"),
                               _pinned(files["large_user"], "(which file the record is in)", "large_user for every record of this file")],
                              "classified", "Which of the two SPD files the record comes from.", ["single-combined-output"]),
            "spd_release": ([_registry("spd_release", "spd_release")], "registry", "The SPD release the registry pins, the same on every row.", ["two-nrs-cuts"]),
            "introduced_on": (both("DateOfIntroduction"), "parsed", "DateOfIntroduction parsed as a date; part of the primary key.", ["record-key", "half-open-intervals"]),
            "deleted_on": (both("DateOfDeletion"), "parsed", "DateOfDeletion parsed as a date; null while the record is current.", ["half-open-intervals"]),
            "is_current": (both("DateOfDeletion"), "derived", "True when the record has no deletion date.", ["half-open-intervals"]),
        }
        checks = ["spd.primary_key_unique", "spd.primary_key_nonnull", "readback.history.index_columns"]
    else:
        path = ctx["registry"].sspl_file["file"]
        code = "simd_ingest/core/sspl.py"
        rules = {
            "pc_norm": ([_pinned(path, "Postcode")], "normalised", "Postcode uppercased with ASCII spaces removed.", ["postcode-normalisation", "sspl-main-table"]),
            "spd_user_type": ([_pinned(path, "PostcodeType")], "classified", "PostcodeType S is small_user, L is large_user.", ["sspl-main-table"]),
            "sspl_release": ([_registry("sspl_release", "sspl_release")], "registry", "The SSPL release the registry pins, the same on every row.", ["two-nrs-cuts"]),
            "introduced_on": ([_pinned(path, "DateOfIntroduction")], "parsed", "DateOfIntroduction parsed as a date.", ["sspl-main-table"]),
            "deleted_on": ([_pinned(path, "DateOfDeletion")], "parsed", "DateOfDeletion parsed as a date; null while the postcode is current.", ["sspl-main-table"]),
            "is_current": ([_pinned(path, "DateOfDeletion")], "derived", "True when the postcode has no deletion date.", ["sspl-main-table"]),
        }
        checks = ["sspl.primary_key_unique", "sspl.postcode_type", "readback.main.index_columns"]
    inputs, kind, rule, decisions = rules[column]
    return _record(table, column, "derived", inputs, kind, rule, code, checks, decisions)


def _phs(table: str, column: str) -> dict:
    registry = _context()["registry"]
    for ed in registry.phs_editions:
        key, vintage = ed["key"], int(ed["dz_vintage"])
        join = f"DataZone{vintage}Code = DataZone"
        common = [f"source.hash.{ed['file']}", f"phs.{key}.source.schema", f"phs.{key}.source.key_unique",
                  f"cross.{key}.same_zones", f"join.{table}.phs.{key}.every_record_matched", f"readback.{table}.attached_values"]
        if column == f"simd{key}_rank":
            return _record(table, column, "phs", [_pinned(ed["file"], f"{ed['prefix']}Rank", join=join)], "copied",
                           "The SIMD rank as published, 1 most deprived.", "simd_ingest/core/phs.py: canonicalise_phs",
                           common + [f"phs.{key}.source.rank_dense", f"cross.{key}.rank_identical"],
                           ["rank-direction-confirmed", "trust-the-sources"])
        for src, canon in list(BANDS.items()) + list(FLAGS.items()):
            if column == f"simd{key}_{canon}":
                band = canon in BANDS.values()
                inverted = band and ed["invert_bands"]
                k = 10 if canon.endswith("decile") else 5
                rule = (f"Published with 1 least deprived, so turned round as {k + 1} - value; 1 is most deprived."
                        if inverted else "Copied as published, 1 most deprived." if band else "Copied as published, 1 or 0.")
                checks = common + ([f"phs.{key}.source.{src}.range", f"phs.{key}.{canon}.monotone", f"phs.{key}.rank1_in_band1",
                                    f"join.{table}.{column}.range"] if band else
                                   [f"phs.{key}.source.{src}.binary", f"phs.{key}.flag_anchors", f"join.{table}.{column}.binary"])
                decisions = ["bands-are-looked-up", "band-column-names-state-weighting"] + (["invert-2004-2006-phs-bands"] if inverted else [])
                return _record(table, column, "phs", [_pinned(ed["file"], f"{ed['prefix']}{src}", join=join)],
                               "inverted" if inverted else "copied", rule, "simd_ingest/core/phs.py: canonicalise_phs", checks, decisions)
    for vintage in sorted({int(e["dz_vintage"]) for e in registry.phs_editions}):
        for g, src in (("hb", "HB"), ("hscp", "HSCP"), ("ca", "CA")):
            if column == f"phs_dz{vintage}_{g}":
                first = first_edition_of_vintage(registry, vintage)
                ed = next(e for e in registry.phs_editions if e["key"] == first)
                return _record(table, column, "phs", [_pinned(ed["file"], src, join=f"DataZone{vintage}Code = DataZone")], "copied",
                               f"The code PHS assigned to the {vintage} data zone, from the first PHS edition of that vintage ({first}); identical across the vintage's editions.",
                               "simd_ingest/core/join.py: join_edition",
                               [f"phs.{e['key']}.shared_geography" for e in registry.phs_editions if int(e["dz_vintage"]) == vintage and e["key"] != first]
                               + [f"join.{table}.geography_nonnull", f"readback.{table}.attached_values"],
                               ["phs-geography-columns"])
    raise KeyError(column)


def _govscot(table: str, column: str) -> dict:
    registry = _context()["registry"]
    for ed in registry.govscot_editions:
        key, join = ed["key"], f"DataZone{ed['dz_vintage']}Code = {ed['columns']['datazone']}"
        common = [f"source.hash.{ed['file']}", f"govscot.{key}.columns_present", f"govscot.{key}.key_unique",
                  f"join.{table}.gov.{key}.every_record_matched", f"readback.{table}.attached_values"]
        for band in DOMAIN_BANDS:
            if column == f"simd{key}_uw_scotland_{band}":
                return _record(table, column, "govscot", [_pinned(ed["file"], ed["columns"][band], join=join)], "copied",
                               "The Scottish Government's unweighted band, copied as published, 1 most deprived.",
                               "simd_ingest/core/govscot.py: read_gov_edition",
                               common + [f"govscot.{key}.uw_scotland_{band}.range", f"govscot.{key}.uw_scotland_{band}.monotone", f"join.{table}.{column}.range"],
                               ["government-bands-from-shapefile-tables", "bands-are-looked-up", "band-column-names-state-weighting"])
        for d in declared_domains(ed):
            if column == f"simd{key}_{d}_domain_rank":
                return _record(table, column, "govscot", [_pinned(ed["file"], ed["domains"][d], join=join)], "copied",
                               "The domain rank copied exactly as published; it may end in .5 where zones tie.",
                               "simd_ingest/core/govscot.py: read_gov_edition",
                               common + [f"govscot.{key}.{d}_domain.{c}" for c in ("present", "complete", "half_units", "range")]
                               + [f"join.{table}.domain_ranks_half_units"],
                               ["simd-domain-ranks"])
        if column == f"simd{key}_population":
            return _record(table, column, "govscot", [_pinned(ed["file"], ed["columns"]["population"], join=join)], "copied",
                           "The data zone's population in this edition's shapefile, the weight behind the computed bands; the zone's figure on every postcode in it.",
                           "simd_ingest/core/govscot.py: read_gov_edition",
                           common + [f"govscot.{key}.population.integral", f"govscot.{key}.population_nonnegative"],
                           ["computed-weighted-domain-bands"])
    raise KeyError(column)


def _bands(table: str, column: str) -> dict:
    registry = _context()["registry"]
    name = {v: k for k, v in PUBLISHED_DOMAINS.items()}
    for ed in registry.govscot_editions:
        key, bands = ed["key"], ed.get("bands") or {}
        join = f"DataZone{ed['dz_vintage']}Code = {ed['columns']['datazone']}"
        published_join = f"DataZone{ed['dz_vintage']}Code = FeatureCode"
        for d in banded_domains(ed):
            gate = _pinned(ed["file"], ed["domains"][d], "the rank the published rank must equal, or differ from as declared", join)
            checks = [f"source.hash.{bands['file']}", f"govscot.{key}.bands.years", f"govscot.{key}.bands.{d}.zones",
                      f"govscot.{key}.bands.{d}.ranks_agree", f"join.{table}.gov.{key}.every_record_matched",
                      f"readback.{table}.attached_values"]
            listed = (bands.get("rank_disagreements") or {}).get(d)
            for band in DOMAIN_BANDS:
                if column == f"simd{key}_{d}_domain_{band}":
                    src = _pinned(bands["file"], "Value",
                                  f"SIMD Domain = {name[d]}, Measurement = {band.capitalize()}, DateCode = {bands['date_code']}",
                                  published_join)
                    rule = ("The Scottish Government's published band, copied, never derived; admitted only where the "
                            "published rank is the shapefile's" + (", a half the dataset rounds up allowed" if bands["half_ranks"] == "rounded_up" else "")
                            + (", or the zone is one of those listed, with both ranks, in the committed disagreement list: "
                               "there the two publications give different ranks, the band is the published one, and the "
                               "status column says so" if listed else "") + ".")
                    inputs = [src, gate] + ([_repository(f"simd_ingest/{Path(listed).name}", "data_zone, shapefile_rank, published_rank",
                                                         "zones whose two ranks may differ, exactly as listed", f"DataZone{ed['dz_vintage']}Code = data_zone")]
                                            if listed else [])
                    return _record(table, column, "govscot_bands", inputs, "copied (gated)", rule,
                                   "simd_ingest/core/govscot.py: read_published_bands",
                                   checks + ([f"govscot.{key}.bands.{d}.rank_disagreements_as_pinned"] if listed else [])
                                   + [f"govscot.{key}.bands.{d}.{band}.{c}" for c in ("whole", "range", "monotone")] + [f"join.{table}.{column}.range"],
                                   ["simd-domain-bands", "bands-are-looked-up"])
        for d in status_domains(ed):
            if column == f"simd{key}_{d}_domain_rank_source_status":
                listed = Path(bands["rank_disagreements"][d])
                return _record(table, column, "govscot_bands",
                               [_repository(f"simd_ingest/{listed.name}", "data_zone", "the zones listed, with both ranks", f"DataZone{ed['dz_vintage']}Code = data_zone"),
                                _pinned(bands["file"], "Value", f"SIMD Domain = {name[d]}, Measurement = Rank, DateCode = {bands['date_code']}", published_join),
                                _pinned(ed["file"], ed["domains"][d], "the shapefile rank", join)],
                               "flagged", "rank_sources_disagree where the published rank and the shapefile rank differ, as pinned zone by zone in the committed list; null otherwise. It describes the rank, not the band.",
                               "simd_ingest/core/govscot.py: read_published_bands",
                               [f"govscot.{key}.bands.{d}.rank_disagreements_as_pinned", f"join.{table}.{column}.values", f"readback.{table}.attached_values"],
                               ["simd-domain-bands"])
    raise KeyError(column)


def _computed(table: str, column: str) -> dict:
    registry = _context()["registry"]
    for ed in registry.govscot_editions:
        key = ed["key"]
        for d in declared_domains(ed):
            for band in WEIGHTED_BANDS:
                if column == f"simd{key}_{d}_domain_pw_scotland_{band}":
                    k = WEIGHTED_BANDS[band]
                    return _record(table, column, "computed",
                                   [_pinned(ed["file"], ed["domains"][d], "every data zone of the edition", f"DataZone{ed['dz_vintage']}Code = {ed['columns']['datazone']}"),
                                    _pinned(ed["file"], ed["columns"]["population"], "every data zone of the edition", f"DataZone{ed['dz_vintage']}Code = {ed['columns']['datazone']}")],
                                   "computed",
                                   f"Zones ordered by the domain rank, equal ranks one block; band = max(1, min({k}, ceil(midpoint x {k} / total))), "
                                   "where midpoint is the cumulative population through the block minus half the block's. Computed, not published.",
                                   "simd_ingest/core/weighted.py: population_bands",
                                   [f"weighted.{key}.zones", f"weighted.{key}.reproduces_phs_scotland_{band}",
                                    f"join.{table}.{column}.range", f"readback.{table}.attached_values"],
                                   ["computed-weighted-domain-bands"],
                                   scope=f"every data zone of SIMD {key}, once, with its population; never the table's rows")
    raise KeyError(column)


def _rurality(table: str, column: str) -> dict:
    registry = _context()["registry"]
    files = {s["role"]: s["file"] for s in registry.spd_files}
    for v in registry.rurality_versions:
        six, eight = rurality.column_names(v["key"])
        status = rurality.status_name(v["key"])
        if column not in (six, eight, status):
            continue
        point = [_pinned(files[r], "GridReferenceEasting, GridReferenceNorthing", "the life's own grid reference") for r in ("small_user", "large_user")]
        point += [{"kind": "derived_column", "path": "postcode_simd_history", "field": "spd_user_type",
                   "condition": "with LinkedSmallUserPostcode, identifies a PO box", "join": None},
                  _pinned(files["large_user"], "LinkedSmallUserPostcode",
                          "NO LINKP marks a PO box, whose grid reference is the sorting office: its codes are cleared and its status is po_box")]
        shape = _pinned(v["file"], v["columns"]["sixfold" if column == six else "eightfold"] if column != status else "geometry")
        early = v["reference_year"] < 2011
        checks = [f"rurality.{v['key']}.{c}" for c in ("columns_present", "polygons", "reference_system", "folds_nest")]
        checks += ["rurality.points_present", f"readback.{table}.rurality_values"]
        if v["key"] == registry.rurality_published["version"]:
            checks += ["rurality.agreement.current_small_user", "rurality.agreement.current_large_user"]
        decisions = ["rurality-by-version", "nullable-integers-and-never-blank-text"] + (["rurality-early-versions-confirmed"] if early else [])
        if column == status:
            rule = ("Why the version has no code: outside_polygons (the point is in no polygon), ambiguous_polygons "
                    "(on an edge between two classes) or po_box (a large user linked NO LINKP); null when it has one.")
        else:
            rule = ("The class of the polygon containing the life's grid reference, by point in polygon; cleared for a "
                    "PO box (a large user whose LinkedSmallUserPostcode is NO LINKP). "
                    + ("Compared directly with the codes NRS publishes for this version." if v["key"] == registry.rurality_published["version"]
                       else "Shares the placement algorithm and its gate; there is no direct comparison with NRS codes for this version."))
        return _record(table, column, "rurality", point + [shape], "placed", rule,
                       "simd_ingest/core/rurality.py: classify, place, attach_rurality, is_po_box",
                       checks, decisions)
    raise KeyError(column)


# --- the map --------------------------------------------------------------------------------------

def record(table: str, column: str) -> dict:
    """The lineage of one column of one table."""
    ctx = _context()
    field = next(f for f in ctx["schemas"][table]["fields"] if f["name"] == column)
    source = field["source"]
    if source == "directory":
        return _spd_field(column)
    if source == "lookup":
        return _sspl_field(column)
    if source == "derived":
        return _derived(table, column)
    if source == "phs":
        return _phs(table, column)
    if source == "govscot":
        return _govscot(table, column)
    if source == "govscot_bands":
        return _bands(table, column)
    if source == "computed":
        return _computed(table, column)
    if source == rurality.SOURCE:
        return _rurality(table, column)
    raise KeyError(f"{table}.{column}: no lineage rule for source {source!r}")


def lineage() -> dict:
    """Every (table, column) of both schemas, in schema order."""
    ctx = _context()
    return {(t, f["name"]): record(t, f["name"]) for t in TABLES for f in ctx["schemas"][t]["fields"]}
