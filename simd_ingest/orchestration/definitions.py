"""The Dagster code location: the ladder.

    sources   eighteen pinned files and the decision log, each verified against its hash
    prepare   index_small, index_large, postcode_index; phs_<ed>_source and phs_<ed> for six
              editions; gov_<ed> for six editions
    join      joined_phs_<ed> for six editions, then joined_gov_<ed>, ending in postcode_simd

Every asset carries a blocking check; a failed rung stops the ladder there and leaves the
rungs above it materialised for inspection. Importing this module reads configuration only.

    export DAGSTER_HOME=$PWD/.dagster
    dagster dev -m simd_ingest.orchestration.definitions
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
from pathlib import Path

import pandas as pd
import yaml
from dagster import (AssetCheckResult, AssetCheckSeverity, AssetCheckSpec, AssetIn, AssetKey, AssetSelection,
                     DataVersion, Definitions, Failure, MaterializeResult, MetadataValue, Output, asset, asset_check,
                     define_asset_job)

from ..cli import OUTPUT_NAME, load_config
from ..core import output as out
from ..core.checks import Report
from ..core.crosscheck import cross_check
from ..core.fetch import ensure_file
from ..core.govscot import read_gov_edition
from ..core.join import finish, join_edition
from ..core.phs import canonicalise_phs, read_phs_source
from ..core.sources import load_registry, sha256
from ..core.spd import read_index_file, union_index
from .io import ParquetIOManager

CORE = Path(__file__).resolve().parents[1] / "core"
DEFAULT_CONFIG = Path("config/workflow.yaml")
DECISIONS_KEY = AssetKey(["source", "decisions"])


def code_version(*modules: str) -> str:
    h = hashlib.sha256()
    for m in ("checks", "sources", *modules):
        h.update((CORE / f"{m}.py").read_bytes())
    return h.hexdigest()[:16]


fingerprint = out.logical_fingerprint


def md(**values) -> dict:
    return {k: MetadataValue.json(v) if isinstance(v, (dict, list)) else v for k, v in values.items()}


def check_result(name: str, report: Report, severity=AssetCheckSeverity.ERROR, diagnostic=False) -> AssetCheckResult:
    selected = [c for c in report.checks if (c.severity == "diagnostic") == diagnostic]
    failed = [c for c in selected if not c.passed]
    return AssetCheckResult(check_name=name, passed=not failed, severity=severity,
                            metadata=md(checks=len(selected), failed=len(failed),
                                        failures=[{"check": c.name, "detail": c.detail} for c in failed[:50]]))


def value_of(report: Report, name: str):
    return next((c.actual for c in report.checks if c.name == name), None)


def source_asset_name(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", Path(path).name)


def blocking(name: str):
    return [AssetCheckSpec("blocking_checks", asset=name, blocking=True)]


def build_definitions(config_path: Path = DEFAULT_CONFIG) -> Definitions:
    cfg = load_config(config_path)
    registry = load_registry(cfg["source_manifest"])
    mode = cfg["source_mode"]
    root, cache = cfg["source_roots"][mode], cfg["cache_root"]
    baselines = yaml.safe_load(cfg["baselines"].read_text())
    schema = out.load_schema(cfg["output_schema"])
    assets, checks = [], []

    # ---- sources ---------------------------------------------------------------------------
    source_keys = {}
    for obj in registry.objects:
        for f in obj.files:
            key = AssetKey(["source", f.publisher, source_asset_name(f.path)])
            source_keys[f.path] = key

            def make_source(f=f, obj=obj, key=key):
                @asset(key=key, group_name="sources", code_version=code_version("fetch"),
                       description=f"{f.path}, from {obj.url}",
                       metadata=md(path=f.path, pinned_sha256=f.sha256, url=obj.url, publisher=obj.publisher,
                                   role=f.role, licence=registry.licences.get(obj.publisher, "")),
                       check_specs=[AssetCheckSpec("pin_verified", asset=key, blocking=True)])
                def _source(context):
                    report = Report()
                    actual = ensure_file(registry, f.path, mode, root, cache, report, context.log.info)
                    yield check_result("pin_verified", report)
                    if report.blocking_failures:
                        raise Failure(f"{f.path}: {report.blocking_failures[0].detail}")
                    yield MaterializeResult(data_version=DataVersion(actual), metadata=md(sha256=actual, source_mode=mode))
                return _source
            assets.append(make_source())

    @asset(key=DECISIONS_KEY, group_name="sources", description="decisions.yaml: every judgement that shapes the data",
           metadata=md(path=str(cfg["decisions"])), code_version="decisions-v1")
    def decisions():
        raw = yaml.safe_load(cfg["decisions"].read_text())
        digest = sha256(cfg["decisions"])
        return MaterializeResult(data_version=DataVersion(digest),
                                 metadata=md(sha256=digest, count=len(raw["decisions"]), ids=[d["id"] for d in raw["decisions"]]))
    assets.append(decisions)

    def table_output(table: pd.DataFrame, report: Report, **extra) -> Output:
        return Output(table, data_version=DataVersion(fingerprint(table)),
                      metadata=md(rows=len(table), columns=len(table.columns), checks_passed=report.summary()["blocking_passed"], **extra))

    # ---- prepare: the index ------------------------------------------------------------------
    index_parts = {}
    for spec in registry.spd_files:
        name = f"index_{spec['role'].replace('_user', '')}"
        index_parts[spec["role"]] = name

        def make_index_part(spec=spec, name=name):
            @asset(name=name, deps=[source_keys[spec["file"]], DECISIONS_KEY], group_name="prepare",
                   code_version=code_version("spd"), check_specs=blocking(name),
                   description=f"{spec['file']}: every column as text, key and dates derived, counts checked")
            def _part():
                report = Report()
                table = read_index_file(spec, registry, root, report, baselines)
                yield check_result("blocking_checks", report)
                report.require()
                yield table_output(table, report, user_type=spec["role"], current=int(table["is_current"].sum()))
            return _part
        assets.append(make_index_part())

    @asset(ins={"index_small": AssetIn(), "index_large": AssetIn()}, group_name="prepare", code_version=code_version("spd"),
           check_specs=blocking("postcode_index"),
           description="Both files stacked in source column order, spd_user_type added as provenance")
    def postcode_index(index_small, index_large):
        report = Report()
        table = union_index(index_small, index_large, registry, report, baselines)
        yield check_result("blocking_checks", report)
        report.require()
        yield table_output(table, report, by_user_type=table["spd_user_type"].value_counts().to_dict(),
                           current=int(table["is_current"].sum()),
                           ordinary_postcodes_with_multiple_current_records=value_of(report, "spd.multiple_candidate_bases"))
    assets.append(postcode_index)

    # ---- prepare: the editions ---------------------------------------------------------------
    for ed in registry.phs_editions:
        key = ed["key"]
        src_name, canon_name = f"phs_{key}_source", f"phs_{key}"

        def make_phs(ed=ed, src_name=src_name, canon_name=canon_name):
            @asset(name=src_name, deps=[source_keys[ed["file"]]], group_name="prepare", code_version=code_version("phs"),
                   check_specs=blocking(src_name), description=f"{ed['file']} as published, typed and checked")
            def _src():
                report = Report()
                table = read_phs_source(ed, root, report)
                yield check_result("blocking_checks", report)
                report.require()
                yield table_output(table, report, edition=ed["key"], dz_vintage=int(ed["dz_vintage"]))

            @asset(name=canon_name, ins={"source": AssetIn(src_name)}, deps=[DECISIONS_KEY], group_name="prepare",
                   code_version=code_version("phs"), check_specs=blocking(canon_name),
                   description=("bands inverted so 1 = most deprived" if ed["invert_bands"] else "bands as published, 1 = most deprived already"))
            def _canon(source):
                report = Report()
                table = canonicalise_phs(ed, source, report)
                yield check_result("blocking_checks", report)
                report.require()
                yield table_output(table, report, edition=ed["key"], inverted=bool(ed["invert_bands"]),
                                   direction="1 = most deprived")
            return _src, _canon
        assets.extend(make_phs())

    for ed in registry.govscot_editions:
        key = ed["key"]
        gov_name = f"gov_{key}"

        def make_gov(ed=ed, gov_name=gov_name):
            @asset(name=gov_name, deps=[source_keys[ed["file"]], DECISIONS_KEY], group_name="prepare",
                   code_version=code_version("govscot"), check_specs=blocking(gov_name),
                   description=f"{ed['file']}: rank, unweighted bands and population by data zone")
            def _gov():
                report = Report()
                table = read_gov_edition(ed, root, report)
                yield check_result("blocking_checks", report)
                report.require()
                yield table_output(table, report, edition=ed["key"], population_column=ed["columns"]["population"])

            # An asset check receives its target through a parameter named after the asset.
            # The name varies per edition, so the function is given its signature explicitly.
            def with_target(fn):
                fn.__signature__ = inspect.Signature([inspect.Parameter(gov_name, inspect.Parameter.POSITIONAL_OR_KEYWORD),
                                                      inspect.Parameter("phs", inspect.Parameter.POSITIONAL_OR_KEYWORD)])
                return fn

            @asset_check(asset=gov_name, name="phs_agreement", additional_ins={"phs": AssetIn(f"phs_{key}")}, blocking=True,
                         description="Same zones and identical ranks as PHS; pinned divergence fingerprint")
            @with_target
            def _agree(**tables):
                report = Report()
                cross_check(tables["phs"], tables[gov_name], baselines, report)
                return check_result("phs_agreement", report)

            @asset_check(asset=gov_name, name="population_reconstruction", additional_ins={"phs": AssetIn(f"phs_{key}")},
                         description="Diagnostic: midpoint rule on published population versus PHS bands and flags")
            @with_target
            def _recon(**tables):
                report = Report()
                cross_check(tables["phs"], tables[gov_name], baselines, report)
                return check_result("population_reconstruction", report, severity=AssetCheckSeverity.WARN, diagnostic=True)
            return _gov, _agree, _recon
        g, a, r = make_gov()
        assets.append(g)
        checks.extend([a, r])

    # ---- join: the ladder --------------------------------------------------------------------
    rungs = [(ed, "phs", f"phs_{ed['key']}") for ed in registry.phs_editions] + \
            [(ed, "gov", f"gov_{ed['key']}") for ed in registry.govscot_editions]
    previous = "postcode_index"
    for i, (ed, kind, side) in enumerate(rungs):
        last = i == len(rungs) - 1
        name = "postcode_simd" if last else f"joined_{kind}_{ed['key']}"

        def make_rung(ed=ed, kind=kind, side=side, previous=previous, name=name, last=last):
            key_col = f"DataZone{ed['dz_vintage']}Code"
            if not last:
                @asset(name=name, ins={"previous": AssetIn(previous), "edition": AssetIn(side)}, deps=[DECISIONS_KEY],
                       group_name="join", code_version=code_version("join"), check_specs=[AssetCheckSpec("join_checks", asset=name, blocking=True)],
                       description=f"+ {side} on {key_col}")
                def _rung(previous, edition):
                    report = Report()
                    table = join_edition(previous, edition, ed, kind, registry, report)
                    yield check_result("join_checks", report)
                    report.require()
                    yield table_output(table, report, added=len(table.columns) - len(previous.columns), key=key_col)
                return _rung

            # The final rung joins the last edition, then writes the deliverable, reads it back
            # against every reference table, and writes the manifest.
            refs = {"postcode_index": AssetIn("postcode_index")}
            refs.update({f"phs_{e['key']}": AssetIn(f"phs_{e['key']}") for e in registry.phs_editions})
            refs.update({f"gov_{e['key']}": AssetIn(f"gov_{e['key']}") for e in registry.govscot_editions})

            @asset(name=name, ins={"previous": AssetIn(previous), **refs}, deps=[DECISIONS_KEY], group_name="join",
                   code_version=code_version("join", "output"),
                   check_specs=[AssetCheckSpec("join_checks", asset=name, blocking=True), AssetCheckSpec("readback", asset=name, blocking=True)],
                   description=f"+ {side} on {key_col}; then the deliverable results/{OUTPUT_NAME}, read back and manifested")
            def _final(context, previous, **tables):
                report = Report()
                table = join_edition(previous, tables[side], ed, kind, registry, report)
                table = finish(table, tables["postcode_index"], registry, [f["name"] for f in schema["fields"]], report)
                yield check_result("join_checks", report)
                report.require()
                results = cfg["results_root"]
                final, candidate = results / OUTPUT_NAME, results / (OUTPUT_NAME + ".candidate")
                decisions_sha = sha256(cfg["decisions"])
                out.write_table(table, schema, candidate, {
                    "band_convention": out.BAND_CONVENTION, "schema_version": schema["version"],
                    "spd_release": registry.spd_release, "decisions_sha256": decisions_sha,
                    "sources": [{"key": o.key, "sha256": o.sha256} for o in registry.objects]})
                simd = pd.concat([tables[f"phs_{e['key']}"] for e in registry.phs_editions], ignore_index=True)
                gov = pd.concat([tables[f"gov_{e['key']}"] for e in registry.govscot_editions], ignore_index=True)
                before = len(report.checks)
                info = out.readback(candidate, schema, tables["postcode_index"], simd, gov, registry, report)
                readback_report = Report(checks=report.checks[before:])
                yield check_result("readback", readback_report)
                if readback_report.blocking_failures:
                    candidate.unlink(missing_ok=True)
                    readback_report.require()
                candidate.replace(final)
                info["path"] = str(final)
                man = out.manifest(registry, schema, decisions_sha, sha256(cfg["baselines"]), mode, info, report,
                                   {"dagster_run_id": context.run_id})
                (results / "manifest.json").write_text(json.dumps(man, indent=2))
                context.log.info(f"wrote {final} {info['rows']:,} rows x {info['columns']} columns {info['sha256'][:16]}")
                yield MaterializeResult(data_version=DataVersion(info["sha256"]),
                                        metadata=md(path=str(final), manifest=str(results / "manifest.json"), rows=info["rows"],
                                                    columns=info["columns"], sha256=info["sha256"],
                                                    logical_fingerprint=info["logical_fingerprint"], schema_version=schema["version"],
                                                    band_convention=out.BAND_CONVENTION, decisions_sha256=decisions_sha,
                                                    checks=report.summary()))
            return _final
        assets.append(make_rung())
        previous = name

    build_job = define_asset_job("build_postcode_simd", selection=AssetSelection.all(),
                                 description="Verify every source, prepare the index and twelve edition tables, join them one rung at a time, write the deliverable")
    return Definitions(assets=assets, asset_checks=checks, jobs=[build_job],
                       resources={"io_manager": ParquetIOManager(base_dir=str(cfg["work_root"]))})


defs = build_definitions(Path(os.environ.get("SIMD_WORKFLOW_CONFIG", DEFAULT_CONFIG)))
