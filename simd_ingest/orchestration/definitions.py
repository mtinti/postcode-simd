"""The Dagster code location.

Eighteen source assets, one per pinned file plus the decision log, each materialised by
the core fetch and versioned by its content hash. Four table assets calling the four core
builders. Checks are attached to the asset they guard: blocking ones fail the asset, the
population reconstruction is a warning. Importing this module reads configuration only;
no file is fetched or written until a run starts.

    export DAGSTER_HOME=$PWD/.dagster
    dagster dev -m simd_ingest.orchestration.definitions
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pandas as pd
from dagster import (AssetCheckResult, AssetCheckSeverity, AssetCheckSpec, AssetIn, AssetKey, AssetSelection,
                     DataVersion, Definitions, Failure, FilesystemIOManager, MaterializeResult, MetadataValue, Output,
                     asset, asset_check, define_asset_job)

from ..cli import OUTPUT_NAME, load_config
from ..core import output as out
from ..core.checks import Report
from ..core.crosscheck import cross_check
from ..core.fetch import ensure_file
from ..core.govscot import build_govscot_bands
from ..core.join import build_postcode_simd
from ..core.phs import build_phs_bands
from ..core.sources import load_registry, sha256
from ..core.spd import build_postcode_index

# The package's own files come from the package; everything else from the working directory,
# so this works both from a checkout and from an installed package.
CORE = Path(__file__).resolve().parents[1] / "core"
DEFAULT_CONFIG = Path("config/workflow.yaml")
DECISIONS_KEY = AssetKey(["source", "decisions"])


def code_version(*modules: str) -> str:
    """Hash of the core modules an asset runs, so a code change is visible as one."""
    h = hashlib.sha256()
    for m in ("checks", "sources", *modules):
        h.update((CORE / f"{m}.py").read_bytes())
    return h.hexdigest()[:16]


fingerprint = out.logical_fingerprint  # same rule for intermediate tables and the manifest


def md(**values) -> dict:
    return {k: MetadataValue.json(v) if isinstance(v, (dict, list)) else v for k, v in values.items()}


def check_result(name: str, report: Report, severity=AssetCheckSeverity.ERROR, diagnostic=False) -> AssetCheckResult:
    """One Dagster check summarising a report's blocking or diagnostic checks."""
    selected = [c for c in report.checks if (c.severity == "diagnostic") == diagnostic]
    failed = [c for c in selected if not c.passed]
    return AssetCheckResult(
        check_name=name, passed=not failed, severity=severity,
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
    baselines = __import__("yaml").safe_load(cfg["baselines"].read_text())
    schema = out.load_schema(cfg["output_schema"])

    # ---- source assets: one per pinned logical file ------------------------------------
    source_keys = {}
    source_assets = []
    for obj in registry.objects:
        for f in obj.files:
            key = AssetKey(["source", f.publisher, source_asset_name(f.path)])
            source_keys[f.path] = key

            def make(f=f, obj=obj, key=key):
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
                    yield MaterializeResult(data_version=DataVersion(actual),
                                            metadata=md(sha256=actual, source_mode=mode, root=str(root)))
                return _source
            source_assets.append(make())

    @asset(key=DECISIONS_KEY, group_name="sources", description="decisions.yaml: every judgement that shapes the data",
           metadata=md(path=str(cfg["decisions"])), code_version="decisions-v1")
    def decisions():
        raw = __import__("yaml").safe_load(cfg["decisions"].read_text())
        digest = sha256(cfg["decisions"])
        return MaterializeResult(data_version=DataVersion(digest),
                                 metadata=md(sha256=digest, count=len(raw["decisions"]),
                                             ids=[d["id"] for d in raw["decisions"]],
                                             statuses={d["id"]: d["status"] for d in raw["decisions"]}))

    def consumed(paths) -> list:
        return [{"path": p, "sha256": registry.file(p).sha256} for p in paths]

    phs_paths = [e["file"] for e in registry.phs_editions]
    gov_paths = [e["file"] for e in registry.govscot_editions]
    spd_paths = [e["file"] for e in registry.spd_files]

    # ---- table assets --------------------------------------------------------------------
    @asset(deps=[source_keys[p] for p in phs_paths] + [DECISIONS_KEY], group_name="tables",
           code_version=code_version("phs"), description="PHS SIMD by data zone, six editions, 1 = most deprived",
           check_specs=[AssetCheckSpec("blocking_checks", asset="phs_bands", blocking=True)])
    def phs_bands():
        report = Report()
        table = build_phs_bands(registry, root, report)
        yield check_result("blocking_checks", report)
        report.require()
        yield Output(table, data_version=DataVersion(fingerprint(table)),
                     metadata=md(rows=len(table), editions=[e["key"] for e in registry.phs_editions],
                                 inverted_editions=[e["key"] for e in registry.phs_editions if e["invert_bands"]],
                                 direction="1 = most deprived in every edition after canonicalisation",
                                 sources_consumed=consumed(phs_paths), checks_passed=report.summary()["blocking_passed"]))

    @asset(deps=[source_keys[p] for p in gov_paths] + [DECISIONS_KEY], group_name="tables",
           code_version=code_version("govscot"), description="Scottish Government unweighted bands and population by data zone",
           check_specs=[AssetCheckSpec("blocking_checks", asset="govscot_bands", blocking=True)])
    def govscot_bands():
        report = Report()
        table = build_govscot_bands(registry, root, report)
        yield check_result("blocking_checks", report)
        report.require()
        yield Output(table, data_version=DataVersion(fingerprint(table)),
                     metadata=md(rows=len(table), provenance={e["key"]: e["file"] for e in registry.govscot_editions},
                                 population_columns={e["key"]: e["columns"]["population"] for e in registry.govscot_editions},
                                 sources_consumed=consumed(gov_paths), checks_passed=report.summary()["blocking_passed"]))

    @asset_check(asset="govscot_bands", additional_ins={"phs_bands": AssetIn("phs_bands")}, blocking=True,
                 description="Same zones and identical ranks as PHS; pinned divergence fingerprints")
    def phs_agreement(govscot_bands, phs_bands):
        report = Report()
        cross_check(phs_bands, govscot_bands, baselines, report)
        return check_result("phs_agreement", report)

    @asset_check(asset="govscot_bands", additional_ins={"phs_bands": AssetIn("phs_bands")},
                 description="Diagnostic: midpoint rule on published population versus PHS bands and flags")
    def population_reconstruction(govscot_bands, phs_bands):
        report = Report()
        cross_check(phs_bands, govscot_bands, baselines, report)
        return check_result("population_reconstruction", report, severity=AssetCheckSeverity.WARN, diagnostic=True)

    @asset(deps=[source_keys[p] for p in spd_paths] + [DECISIONS_KEY], group_name="tables",
           code_version=code_version("spd"), description="Both directory files, original columns as text, seven derived fields",
           check_specs=[AssetCheckSpec("blocking_checks", asset="postcode_index", blocking=True)])
    def postcode_index():
        report = Report()
        table = build_postcode_index(registry, root, report, baselines)
        yield check_result("blocking_checks", report)
        report.require()
        yield Output(table, data_version=DataVersion(fingerprint(table)),
                     metadata=md(rows=len(table), columns=len(table.columns), spd_release=registry.spd_release,
                                 by_user_type=table["spd_user_type"].value_counts().to_dict(),
                                 current=int(table["is_current"].sum()), deleted=int((~table["is_current"]).sum()),
                                 ordinary_postcodes_current=value_of(report, "spd.live_base_keys"),
                                 ordinary_postcodes_with_multiple_current_records=value_of(report, "spd.multiple_candidate_bases"),
                                 of_which_differing_2011_data_zone=value_of(report, "spd.base_keys_with_differing_2011_zones"),
                                 sources_consumed=consumed(spd_paths), checks_passed=report.summary()["blocking_passed"]))

    @asset(ins={"postcode_index": AssetIn(), "phs_bands": AssetIn(), "govscot_bands": AssetIn()}, deps=[DECISIONS_KEY],
           group_name="tables", code_version=code_version("join", "output", "crosscheck"),
           description=f"The deliverable: results/{OUTPUT_NAME}, written, read back, then renamed into place",
           check_specs=[AssetCheckSpec("join_checks", asset="postcode_simd", blocking=True),
                        AssetCheckSpec("readback", asset="postcode_simd", blocking=True)])
    def postcode_simd(context, postcode_index, phs_bands, govscot_bands):
        report = Report()
        table = build_postcode_simd(postcode_index, phs_bands, govscot_bands, registry,
                                    [f["name"] for f in schema["fields"]], report)
        yield check_result("join_checks", report)
        report.require()
        results = cfg["results_root"]
        final, candidate = results / OUTPUT_NAME, results / (OUTPUT_NAME + ".candidate")
        decisions_sha = sha256(cfg["decisions"])
        out.write_table(table, schema, candidate, {
            "band_convention": out.BAND_CONVENTION, "schema_version": schema["version"],
            "spd_release": registry.spd_release, "decisions_sha256": decisions_sha,
            "sources": [{"key": o.key, "sha256": o.sha256} for o in registry.objects]})
        before = len(report.checks)
        info = out.readback(candidate, schema, postcode_index, phs_bands, govscot_bands, registry, report)
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

    build_job = define_asset_job("build_postcode_simd", selection=AssetSelection.all(),
                                 description="Fetch or verify every source, build the four tables, write the deliverable")
    # Intermediate tables go to a disposable work directory, not into the instance, so the
    # instance directory stays a small provenance record that can be backed up whole.
    io_manager = FilesystemIOManager(base_dir=str(cfg["work_root"]))
    return Definitions(assets=[*source_assets, decisions, phs_bands, govscot_bands, postcode_index, postcode_simd],
                       asset_checks=[phs_agreement, population_reconstruction], jobs=[build_job],
                       resources={"io_manager": io_manager})


defs = build_definitions(Path(os.environ.get("SIMD_WORKFLOW_CONFIG", DEFAULT_CONFIG)))
