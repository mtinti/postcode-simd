"""Build the postcode-SIMD table without Dagster.

    python -m simd_ingest.cli fetch   [--config config/workflow.yaml]
    python -m simd_ingest.cli build   [--config config/workflow.yaml] [--source-mode offline|download]
    python -m simd_ingest.cli audit   [--config config/workflow.yaml]

build: verify or download sources, build the three reference tables and the index, run every
check, write the table to a temporary file, reopen and verify it, rename it into place, then
write the manifest. A failed validation prevents replacement of the published table.
audit: rerun the readback on the existing table against freshly verified sources.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd
import yaml

from .core import output, report as build_report
from .core.checks import BuildStopped, Report
from .core.crosscheck import cross_check
from .core.fetch import ensure_sources
from .core.govscot import read_gov_edition
from .core.join import build_postcode_simd
from .core.phs import canonicalise_phs, read_phs_source
from .core.sources import load_registry, sha256
from .core.spd import read_index_file, union_index

OUTPUT_NAME = "postcode_simd.parquet"


def load_config(path: Path) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    root = Path(path).resolve().parent.parent
    cfg.setdefault("work_root", "data/work")
    for key in ("source_manifest", "baselines", "decisions", "output_schema", "cache_root", "work_root", "results_root"):
        cfg[key] = root / cfg[key]
    cfg["source_roots"] = {k: root / v for k, v in cfg["source_roots"].items()}
    # The environment can override the mode, so a container can run in download mode
    # without a different config file. The CLI flag still wins over both.
    cfg["source_mode"] = os.environ.get("SIMD_SOURCE_MODE", cfg["source_mode"])
    if cfg["source_mode"] not in ("offline", "download"):
        raise ValueError(f"source_mode must be offline or download, not {cfg['source_mode']!r}")
    # The decision log is hashed into every build; it must also be readable, or the record
    # points at a file nobody can load.
    try:
        decisions = yaml.safe_load(cfg["decisions"].read_text())
        if not isinstance(decisions.get("decisions"), list):
            raise ValueError("no 'decisions' list")
    except Exception as exc:
        raise ValueError(f"{cfg['decisions']} is not a valid decision log: {exc}") from exc
    return cfg


def print_report(report: Report) -> None:
    for c in report.checks:
        if not c.passed:
            tag = "FAIL" if c.severity == "blocking" else "WARN"
            print(f"  [{tag}] {c.name}: {c.detail}")
    s = report.summary()
    print(f"  {s['blocking_passed']} checks passed, {s['blocking_failed']} failed")


def prepare(cfg: dict, mode: str, report: Report):
    """Sources verified and the three reference tables built. Shared by build and audit."""
    registry = load_registry(cfg["source_manifest"])
    baselines = yaml.safe_load(cfg["baselines"].read_text())
    root = cfg["source_roots"][mode]
    print(f"Sources ({mode})")
    ensure_sources(registry, mode, root, cfg["cache_root"], report)
    report.require()
    print("Prepare: the index")
    parts = {spec["role"]: read_index_file(spec, registry, root, report, baselines) for spec in registry.spd_files}
    report.require()
    index = union_index(parts["small_user"], parts["large_user"], registry, report, baselines)
    report.require()
    print("Prepare: the editions")
    phs_tables = {ed["key"]: canonicalise_phs(ed, read_phs_source(ed, root, report), report) for ed in registry.phs_editions}
    gov_tables = {ed["key"]: read_gov_edition(ed, root, report) for ed in registry.govscot_editions}
    report.require()
    for key in phs_tables:
        cross_check(phs_tables[key], gov_tables[key], baselines, report)
    report.require()
    return registry, baselines, phs_tables, gov_tables, index


def cmd_fetch(cfg: dict, mode: str) -> int:
    report = Report()
    registry = load_registry(cfg["source_manifest"])
    ok = ensure_sources(registry, mode, cfg["source_roots"][mode], cfg["cache_root"], report)
    print_report(report)
    return 0 if ok else 1


def write_output(cfg: dict, registry, schema: dict, mode: str, table: pd.DataFrame, index: pd.DataFrame,
                 simd: pd.DataFrame, gov: pd.DataFrame, report: Report, extra: dict) -> dict:
    """Write the table to a temporary file, read it back against the reference tables, rename it
    into place, then write the manifest and the build report. Shared by the CLI and Dagster.
    Raises BuildStopped, leaving the previous output untouched, if the readback fails."""
    report.require()
    decisions_sha = sha256(cfg["decisions"])
    results = cfg["results_root"]
    final, candidate = results / OUTPUT_NAME, results / (OUTPUT_NAME + ".candidate")
    output.write_table(table, schema, candidate, output.table_metadata(registry, schema, decisions_sha))
    try:
        info = output.readback(candidate, schema, index, simd, gov, registry, report,
                               decisions_sha256=decisions_sha)
        report.require()
    except Exception:
        candidate.unlink(missing_ok=True)
        raise
    candidate.replace(final)
    info.update(path=str(final), decisions_sha256=decisions_sha, manifest=str(results / "manifest.json"),
                build_report=str(results / "BUILD_REPORT.md"))
    man = output.manifest(registry, schema, decisions_sha, sha256(cfg["baselines"]), mode, info, report, extra)
    (results / "manifest.json").write_text(json.dumps(man, indent=2))
    (results / "BUILD_REPORT.md").write_text(build_report.render(report, registry, table, info, mode, index, simd, gov))
    return info


def cmd_build(cfg: dict, mode: str) -> int:
    report = Report()
    registry, baselines, phs_tables, gov_tables, index = prepare(cfg, mode, report)
    schema = output.load_schema(cfg["output_schema"])
    print("Join: one edition at a time")
    table = build_postcode_simd(index, phs_tables, gov_tables, registry, [f["name"] for f in schema["fields"]], report)
    report.require()
    simd = pd.concat(phs_tables.values(), ignore_index=True)
    gov = pd.concat(gov_tables.values(), ignore_index=True)
    print("Write and read back")
    info = write_output(cfg, registry, schema, mode, table, index, simd, gov, report, {})
    print_report(report)
    print(f"Wrote {info['path']}  {info['rows']:,} rows x {info['columns']} columns  {info['sha256'][:16]}")
    print(f"Build report: {info['build_report']}")
    return 0


def cmd_audit(cfg: dict, mode: str) -> int:
    report = Report()
    registry, baselines, phs_tables, gov_tables, index = prepare(cfg, mode, report)
    simd = pd.concat(phs_tables.values(), ignore_index=True)
    gov = pd.concat(gov_tables.values(), ignore_index=True)
    schema = output.load_schema(cfg["output_schema"])
    final = cfg["results_root"] / OUTPUT_NAME
    if not final.is_file():
        print(f"no table at {final}")
        return 1
    print("Read back")
    info = output.readback(final, schema, index, simd, gov, registry, report,
                           decisions_sha256=sha256(cfg["decisions"]))
    man_path = cfg["results_root"] / "manifest.json"
    if man_path.is_file():
        recorded = json.loads(man_path.read_text())["output"]["sha256"]
        report.equal("audit.manifest_hash_matches_file", info["sha256"], recorded)
    else:
        report.add("audit.manifest_present", False, "manifest.json missing")
    print_report(report)
    return 0 if not report.blocking_failures else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["fetch", "build", "audit"])
    ap.add_argument("--config", default=os.environ.get("SIMD_WORKFLOW_CONFIG", "config/workflow.yaml"))
    ap.add_argument("--source-mode", choices=["offline", "download"], help="override the configured mode")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    mode = args.source_mode or cfg["source_mode"]
    try:
        return {"fetch": cmd_fetch, "build": cmd_build, "audit": cmd_audit}[args.command](cfg, mode)
    except BuildStopped as exc:
        print(f"\nStopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
