"""The single build path: verify -> prepare -> cross-check -> join -> readback -> publish.

Two tables come out of one run. The main table is the Scottish Statistics Postcode Lookup
with every edition attached, one row per whole postcode. The history table is the Scottish
Postcode Directory with every edition attached, one row per postcode life. Both go through
the same joins and the same readback; they differ in the index they start from and the key.

All work is local except explicit download mode. One writer per results directory.
No cached intermediate tables or orchestrator state are involved.
"""

import datetime as dt
import importlib.metadata
import json
import platform
import shutil
import tempfile
import uuid
from pathlib import Path

import pandas as pd
import yaml

from .core import output, report as build_report
from .core.agreement import compare_tables
from .core.changes import compare_snapshot
from .core.checks import Report
from .core.crosscheck import cross_check
from .core.fetch import ensure_sources
from .core.govscot import read_gov_edition
from .core.join import GEOGRAPHY, build_postcode_simd
from .core.phs import canonicalise_phs, read_phs_source
from .core.sources import load_registry, sha256, verify_root
from .core.spd import build_postcode_index
from .core.sspl import build_latest_index

# Table name -> which output schema describes it and which index it starts from. The history
# table is built first so that its unchanged fingerprint is confirmed before the main table.
TABLES = {
    "history": {"file": "postcode_simd_history.parquet", "schema": "output_schema_history", "index": "spd"},
    "main": {"file": "postcode_simd.parquet", "schema": "output_schema", "index": "sspl"},
}
CONTRACTS = ("source_manifest", "spd_schema", "sspl_schema", "output_schema", "output_schema_history", "decisions")


def prepare(cfg: dict, mode: str, report: Report, *, audit=False):
    """Build references from verified files; audit is always read-only and never downloads.
    Returns the registry, the PHS and Government edition tables, and both postcode indices."""
    registry = load_registry(cfg["source_manifest"])
    schemas = {}
    for name, key in (("spd", "spd_schema"), ("sspl", "sspl_schema")):
        schemas[name] = yaml.safe_load(cfg[key].read_text())
        if schemas[name].get("version") != 1:
            raise ValueError(f"Unsupported {name} header schema version")
    root = cfg["source_roots"][mode]
    if audit:
        verify_root(registry, root, report)
    else:
        ensure_sources(registry, mode, root, cfg["cache_root"], report)
    report.require()
    indices = {"spd": build_postcode_index(registry, root, report, schemas["spd"]),
               "sspl": build_latest_index(registry, root, report, schemas["sspl"])}
    report.require()
    phs = {e["key"]: canonicalise_phs(e, read_phs_source(e, root, report), report) for e in registry.phs_editions}
    gov = {e["key"]: read_gov_edition(e, root, report) for e in registry.govscot_editions}
    report.require()
    for key in phs:
        cross_check(phs[key], gov[key], report)
    # Geography is stored once per vintage, so agreement must be checked.
    first = {}
    for ed in registry.phs_editions:
        vintage = ed["dz_vintage"]
        geo = phs[ed["key"]].set_index("dz_code")[GEOGRAPHY].sort_index()
        if vintage in first:
            report.equal(f"phs.{ed['key']}.shared_geography", geo.equals(first[vintage]), True)
        else:
            first[vintage] = geo
    report.require()
    return registry, phs, gov, indices


def load_schemas(cfg: dict) -> dict:
    schemas = {name: output.load_schema(cfg[spec["schema"]]) for name, spec in TABLES.items()}
    for name, spec in TABLES.items():
        if schemas[name]["index_source"] != spec["index"]:
            raise ValueError(f"{cfg[spec['schema']]} must declare index_source {spec['index']!r}")
    return schemas


def start_record(cfg: dict, mode: str) -> tuple:
    """Keep small run records, not table copies or an orchestration database."""
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid.uuid4().hex[:8]
    run = cfg["results_root"] / "runs" / run_id
    run.mkdir(parents=True)
    package = Path(__file__).resolve().parent
    record = {
        "run_id": run_id, "run_record": str(run), "source_mode": mode,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "config": {k: ({a: str(b) for a, b in v.items()} if isinstance(v, dict) else str(v)) for k, v in cfg.items()},
        "python": platform.python_version(),
        "dependencies": {n: importlib.metadata.version(n) for n in ("pandas", "numpy", "pyarrow", "PyYAML", "dbfread", "requests")},
        "code_sha256": {str(p.relative_to(package)): sha256(p) for p in sorted(package.rglob("*.py"))},
    }
    (run / "run.json").write_text(json.dumps(record, indent=2))
    return run, record


def write_output(cfg: dict, registry, schemas: dict, mode: str, tables: dict, indices: dict,
                 simd: pd.DataFrame, gov: pd.DataFrame, report: Report, extra: dict) -> dict:
    """Validate every saved candidate and prepare the evidence before replacing any current file.

    `tables` maps a table name to its built frame; `indices` maps an index source to its frame.
    Returns the readback result of each table.
    """
    report.require()
    results = cfg["results_root"]
    results.mkdir(parents=True, exist_ok=True)
    manifest_path = results / "manifest.json"
    decisions_sha = sha256(cfg["decisions"])
    report.observe("snapshot_changes", {
        name: compare_snapshot(tables[name], results / TABLES[name]["file"], manifest_path, name, schemas[name]["key"])
        for name in TABLES})
    info = {}
    with tempfile.TemporaryDirectory(prefix=".build-", dir=results) as temp:
        staging = Path(temp)
        for name, spec in TABLES.items():
            candidate = staging / spec["file"]
            schema = schemas[name]
            output.write_table(tables[name], schema, candidate, output.table_metadata(registry, schema, decisions_sha))
            info[name] = output.readback(candidate, schema, indices[spec["index"]], simd, gov, registry, report,
                                         decisions_sha256=decisions_sha, label=f"readback.{name}")
            info[name]["path"] = str(results / spec["file"])
        report.require()
        contracts = {f"{key}_sha256": sha256(cfg[key]) for key in ("spd_schema", "sspl_schema")}
        man = output.manifest(registry, decisions_sha, contracts, mode, info, report, extra)
        narrative = build_report.render(report, registry, tables, info, mode, indices, simd, gov)
        (staging / "manifest.json").write_text(json.dumps(man, indent=2))
        (staging / "BUILD_REPORT.md").write_text(narrative)
        if "run_record" in extra:
            run = Path(extra["run_record"])
            shutil.copyfile(staging / "manifest.json", run / "manifest.json")
            shutil.copyfile(staging / "BUILD_REPORT.md", run / "BUILD_REPORT.md")
        # Each replacement is atomic on its own; the set is not one transaction.
        for spec in TABLES.values():
            (staging / spec["file"]).replace(results / spec["file"])
        (staging / "manifest.json").replace(manifest_path)
        (staging / "BUILD_REPORT.md").replace(results / "BUILD_REPORT.md")
    for name in info:
        info[name].update(manifest=str(manifest_path), build_report=str(results / "BUILD_REPORT.md"))
    return info


def build(cfg: dict, mode: str, report: Report) -> dict:
    run, record = start_record(cfg, mode)
    print(f"Run record: {run}")
    try:
        for key in CONTRACTS:
            shutil.copyfile(cfg[key], run / f"{key}.yaml")
        print("Verify sources and prepare postcode/PHS/Government tables")
        registry, phs, gov, indices = prepare(cfg, mode, report)
        schemas = load_schemas(cfg)
        tables = {}
        for name, spec in TABLES.items():
            print(f"Join each edition onto the {name} table")
            tables[name] = build_postcode_simd(indices[spec["index"]], phs, gov, registry, schemas[name], report,
                                               label=f"join.{name}")
        report.require()
        report.observe("table_agreement", compare_tables(tables["main"], tables["history"], registry))
        print("Write, reopen, check and publish")
        info = write_output(cfg, registry, schemas, mode, tables, indices, pd.concat(phs.values(), ignore_index=True),
                            pd.concat(gov.values(), ignore_index=True), report, record)
    except Exception as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        (run / "BUILD_REPORT.md").write_text(f"# Build failed\n\n{record['error']}\n\nSee run.json for checks.\n")
        raise
    else:
        record.update(status="published", output=info)
        return info
    finally:
        record.update(summary=report.summary(), checks=report.to_records(), observations=report.observations)
        (run / "run.json").write_text(json.dumps(record, indent=2))


def audit(cfg: dict, mode: str, report: Report) -> None:
    registry, phs, gov, indices = prepare(cfg, mode, report, audit=True)
    schemas = load_schemas(cfg)
    man = json.loads((cfg["results_root"] / "manifest.json").read_text())
    simd, gov_all = pd.concat(phs.values(), ignore_index=True), pd.concat(gov.values(), ignore_index=True)
    for name, spec in TABLES.items():
        info = output.readback(cfg["results_root"] / spec["file"], schemas[name], indices[spec["index"]], simd, gov_all,
                               registry, report, decisions_sha256=sha256(cfg["decisions"]), label=f"readback.{name}")
        report.equal(f"audit.{name}.manifest_hash_matches_file", info["sha256"], man["tables"][name]["sha256"])
        report.equal(f"audit.{name}.schema_matches", schemas[name]["sha256"], man["tables"][name]["schema_sha256"])
    report.equal("audit.registry_matches", registry.sha256, man["registry_sha256"])
    for key in ("spd_schema", "sspl_schema"):
        report.equal(f"audit.{key}_matches", sha256(cfg[key]), man[f"{key}_sha256"])
    report.equal("audit.decisions_match", sha256(cfg["decisions"]), man["decisions_sha256"])
    report.require()
