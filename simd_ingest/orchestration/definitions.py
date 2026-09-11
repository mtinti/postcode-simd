"""The Dagster code location.

Five things a person can hold in their head: the pinned sources, three prepared tables,
one output.

    sources          eighteen pinned files and the decision log, each verified against its hash
    postcode_index   both directory files, keys and dates derived
    phs_bands        six PHS editions, bands turned so 1 = most deprived
    govscot_bands    six government editions from the shapefile tables
    postcode_simd    twelve joins on the data zone, one edition at a time, then the file,
                     its readback, the manifest and the build report

The twelve joins run in a fixed order inside postcode_simd and appear as twelve rows in
results/BUILD_REPORT.md, not as twelve nodes here. Importing this module reads configuration
only.

    export DAGSTER_HOME=$PWD/.dagster
    dagster dev -m simd_ingest.orchestration.definitions
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pandas as pd
import yaml
from dagster import (AssetCheckResult, AssetCheckSeverity, AssetCheckSpec, AssetIn, AssetKey, AssetSelection,
                     DataVersion, Definitions, Failure, MaterializeResult, MetadataValue, Output, asset, asset_check,
                     define_asset_job)

from ..cli import OUTPUT_NAME, load_config, write_output
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


def build_definitions(config_path: Path = DEFAULT_CONFIG) -> Definitions:
    cfg = load_config(config_path)
    registry = load_registry(cfg["source_manifest"])
    mode = cfg["source_mode"]
    root, cache = cfg["source_roots"][mode], cfg["cache_root"]
    baselines = yaml.safe_load(cfg["baselines"].read_text())
    schema = out.load_schema(cfg["output_schema"])

    # ---- sources ---------------------------------------------------------------------------
    source_keys, source_assets = {}, []
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
            source_assets.append(make_source())

    @asset(key=DECISIONS_KEY, group_name="sources", description="decisions.yaml: every judgement that shapes the data",
           metadata=md(path=str(cfg["decisions"])), code_version="decisions-v1")
    def decisions():
        raw = yaml.safe_load(cfg["decisions"].read_text())
        digest = sha256(cfg["decisions"])
        return MaterializeResult(data_version=DataVersion(digest),
                                 metadata=md(sha256=digest, count=len(raw["decisions"]), ids=[d["id"] for d in raw["decisions"]]))

    def consumed(paths) -> list:
        return [{"path": p, "sha256": registry.file(p).sha256} for p in paths]

    phs_paths = [e["file"] for e in registry.phs_editions]
    gov_paths = [e["file"] for e in registry.govscot_editions]
    spd_paths = [e["file"] for e in registry.spd_files]

    def blocking(name):
        return [AssetCheckSpec("blocking_checks", asset=name, blocking=True)]

    # ---- three prepared tables ------------------------------------------------------------
    @asset(deps=[source_keys[p] for p in spd_paths] + [DECISIONS_KEY], group_name="tables", code_version=code_version("spd"),
           check_specs=blocking("postcode_index"),
           description="Both directory files, every column as text, key and dates derived, spd_user_type as provenance")
    def postcode_index():
        report = Report()
        parts = {spec["role"]: read_index_file(spec, registry, root, report, baselines) for spec in registry.spd_files}
        report.require()
        table = union_index(parts["small_user"], parts["large_user"], registry, report, baselines)
        yield check_result("blocking_checks", report)
        report.require()
        yield Output(table, data_version=DataVersion(fingerprint(table)),
                     metadata=md(rows=len(table), columns=len(table.columns), spd_release=registry.spd_release,
                                 by_user_type=table["spd_user_type"].value_counts().to_dict(), current=int(table["is_current"].sum()),
                                 ordinary_postcodes_with_multiple_current_records=value_of(report, "spd.multiple_candidate_bases"),
                                 sources_consumed=consumed(spd_paths), checks_passed=report.summary()["blocking_passed"]))

    @asset(deps=[source_keys[p] for p in phs_paths] + [DECISIONS_KEY], group_name="tables", code_version=code_version("phs"),
           check_specs=blocking("phs_bands"),
           description="Six PHS editions by data zone; 2004 and 2006 bands turned so 1 = most deprived everywhere")
    def phs_bands():
        report = Report()
        frames = [canonicalise_phs(ed, read_phs_source(ed, root, report), report) for ed in registry.phs_editions]
        table = pd.concat(frames, ignore_index=True)
        yield check_result("blocking_checks", report)
        report.require()
        yield Output(table, data_version=DataVersion(fingerprint(table)),
                     metadata=md(rows=len(table), editions=[e["key"] for e in registry.phs_editions],
                                 inverted_editions=[e["key"] for e in registry.phs_editions if e["invert_bands"]],
                                 direction="1 = most deprived in every edition after canonicalisation",
                                 sources_consumed=consumed(phs_paths), checks_passed=report.summary()["blocking_passed"]))

    @asset(deps=[source_keys[p] for p in gov_paths] + [DECISIONS_KEY], group_name="tables", code_version=code_version("govscot"),
           check_specs=blocking("govscot_bands"),
           description="Six Scottish Government editions from the shapefile tables: rank, unweighted bands, population")
    def govscot_bands():
        report = Report()
        table = pd.concat([read_gov_edition(ed, root, report) for ed in registry.govscot_editions], ignore_index=True)
        yield check_result("blocking_checks", report)
        report.require()
        yield Output(table, data_version=DataVersion(fingerprint(table)),
                     metadata=md(rows=len(table), provenance={e["key"]: e["file"] for e in registry.govscot_editions},
                                 population_columns={e["key"]: e["columns"]["population"] for e in registry.govscot_editions},
                                 sources_consumed=consumed(gov_paths), checks_passed=report.summary()["blocking_passed"]))

    @asset_check(asset="govscot_bands", additional_ins={"phs_bands": AssetIn("phs_bands")}, blocking=True,
                 description="Same data zones and identical ranks as PHS in every edition")
    def phs_agreement(govscot_bands, phs_bands):
        report = Report()
        cross_check(phs_bands, govscot_bands, baselines, report)
        return check_result("phs_agreement", report)

    # ---- the output ----------------------------------------------------------------------
    @asset(ins={"postcode_index": AssetIn(), "phs_bands": AssetIn(), "govscot_bands": AssetIn()}, deps=[DECISIONS_KEY],
           group_name="tables", code_version=code_version("join", "output", "report"),
           description=f"Twelve joins on the data zone, one edition at a time; then results/{OUTPUT_NAME}, read back, manifest and build report",
           check_specs=[AssetCheckSpec("join_checks", asset="postcode_simd", blocking=True),
                        AssetCheckSpec("readback", asset="postcode_simd", blocking=True)])
    def postcode_simd(context, postcode_index, phs_bands, govscot_bands):
        report = Report()
        table = postcode_index
        for ed in registry.phs_editions:
            table = join_edition(table, phs_bands[phs_bands["edition"] == ed["key"]], ed, "phs", registry, report)
        for ed in registry.govscot_editions:
            table = join_edition(table, govscot_bands[govscot_bands["edition"] == ed["key"]], ed, "gov", registry, report)
        table = finish(table, postcode_index, registry, [f["name"] for f in schema["fields"]], report)
        yield check_result("join_checks", report)
        report.require()
        before = len(report.checks)
        try:
            info = write_output(cfg, registry, schema, mode, table, postcode_index, phs_bands, govscot_bands, report,
                                {"dagster_run_id": context.run_id})
        finally:
            yield check_result("readback", Report(checks=report.checks[before:]))
        context.log.info(f"wrote {info['path']} {info['rows']:,} rows x {info['columns']} columns {info['sha256'][:16]}")
        yield MaterializeResult(data_version=DataVersion(info["sha256"]),
                                metadata=md(path=info["path"], manifest=info["manifest"], build_report=info["build_report"],
                                            rows=info["rows"], columns=info["columns"], sha256=info["sha256"],
                                            logical_fingerprint=info["logical_fingerprint"], schema_version=schema["version"],
                                            decisions_sha256=info["decisions_sha256"], checks=report.summary()))

    build_job = define_asset_job("build_postcode_simd", selection=AssetSelection.all(),
                                 description="Verify every source, prepare three tables, join one edition at a time, write the deliverable")
    return Definitions(assets=[*source_assets, decisions, postcode_index, phs_bands, govscot_bands, postcode_simd],
                       asset_checks=[phs_agreement], jobs=[build_job],
                       resources={"io_manager": ParquetIOManager(base_dir=str(cfg["work_root"]))})


defs = build_definitions(Path(os.environ.get("SIMD_WORKFLOW_CONFIG", DEFAULT_CONFIG)))
