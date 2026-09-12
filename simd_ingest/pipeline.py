"""The single build path: verify -> prepare -> cross-check -> join -> readback -> publish.

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
from .core.changes import compare_snapshot
from .core.checks import Report
from .core.crosscheck import cross_check
from .core.fetch import ensure_sources
from .core.govscot import read_gov_edition
from .core.join import GEOGRAPHY, build_postcode_simd
from .core.phs import canonicalise_phs, read_phs_source
from .core.sources import load_registry, sha256, verify_root
from .core.spd import build_postcode_index

OUTPUT_NAME = "postcode_simd.parquet"


def prepare(cfg: dict, mode: str, report: Report, *, audit=False):
    """Build references from verified files; audit is always read-only and never downloads."""
    registry = load_registry(cfg["source_manifest"])
    schema = yaml.safe_load(cfg["spd_schema"].read_text())
    if schema.get("version") != 1:
        raise ValueError("Unsupported postcode schema version")
    root = cfg["source_roots"][mode]
    if audit:
        verify_root(registry, root, report)
    else:
        ensure_sources(registry, mode, root, cfg["cache_root"], report)
    report.require()
    index = build_postcode_index(registry, root, report, schema)
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
    return registry, phs, gov, index


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


def write_output(cfg: dict, registry, schema: dict, mode: str, table: pd.DataFrame, index: pd.DataFrame,
                 simd: pd.DataFrame, gov: pd.DataFrame, report: Report, extra: dict) -> dict:
    """Validate the saved candidate and prepare evidence before replacing the current file."""
    report.require()
    results = cfg["results_root"]
    results.mkdir(parents=True, exist_ok=True)
    final = results / OUTPUT_NAME
    report.observe("snapshot_changes", compare_snapshot(table, final, results / "manifest.json"))
    decisions_sha = sha256(cfg["decisions"])
    with tempfile.TemporaryDirectory(prefix=".build-", dir=results) as temp:
        staging = Path(temp)
        candidate = staging / OUTPUT_NAME
        output.write_table(table, schema, candidate, output.table_metadata(registry, schema, decisions_sha))
        info = output.readback(candidate, schema, index, simd, gov, registry, report, decisions_sha256=decisions_sha)
        report.require()
        info.update(path=str(final), manifest=str(results / "manifest.json"), build_report=str(results / "BUILD_REPORT.md"))
        man = output.manifest(registry, schema, decisions_sha, sha256(cfg["spd_schema"]), mode, info, report, extra)
        narrative = build_report.render(report, registry, table, info, mode, index, simd, gov)
        (staging / "manifest.json").write_text(json.dumps(man, indent=2))
        (staging / "BUILD_REPORT.md").write_text(narrative)
        if "run_record" in extra:
            run = Path(extra["run_record"])
            shutil.copyfile(staging / "manifest.json", run / "manifest.json")
            shutil.copyfile(staging / "BUILD_REPORT.md", run / "BUILD_REPORT.md")
        candidate.replace(final)  # Atomic individually, not a three-file transaction.
        (staging / "manifest.json").replace(results / "manifest.json")
        (staging / "BUILD_REPORT.md").replace(results / "BUILD_REPORT.md")
    return info


def build(cfg: dict, mode: str, report: Report) -> dict:
    run, record = start_record(cfg, mode)
    print(f"Run record: {run}")
    try:
        for key in ("source_manifest", "spd_schema", "output_schema", "decisions"):
            shutil.copyfile(cfg[key], run / f"{key}.yaml")
        print("Verify sources and prepare postcode/PHS/Government tables")
        registry, phs, gov, index = prepare(cfg, mode, report)
        schema = output.load_schema(cfg["output_schema"])
        print("Join each edition")
        table = build_postcode_simd(index, phs, gov, registry, [f["name"] for f in schema["fields"]], report)
        print("Write, reopen, check and publish")
        info = write_output(cfg, registry, schema, mode, table, index, pd.concat(phs.values(), ignore_index=True),
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
    registry, phs, gov, index = prepare(cfg, mode, report, audit=True)
    schema = output.load_schema(cfg["output_schema"])
    final = cfg["results_root"] / OUTPUT_NAME
    info = output.readback(final, schema, index, pd.concat(phs.values(), ignore_index=True),
                           pd.concat(gov.values(), ignore_index=True), registry, report,
                           decisions_sha256=sha256(cfg["decisions"]))
    man = json.loads((cfg["results_root"] / "manifest.json").read_text())
    report.equal("audit.manifest_hash_matches_file", info["sha256"], man["output"]["sha256"])
    report.equal("audit.registry_matches", registry.sha256, man["registry_sha256"])
    report.equal("audit.schema_matches", schema["sha256"], man["schema_sha256"])
    report.equal("audit.spd_schema_matches", sha256(cfg["spd_schema"]), man["spd_schema_sha256"])
    report.equal("audit.decisions_match", sha256(cfg["decisions"]), man["decisions_sha256"])
    report.require()
