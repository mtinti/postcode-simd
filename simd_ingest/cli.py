"""One entry point: fetch pinned sources, build a replacement snapshot, or audit it."""

import argparse
import os
import sys

import yaml

from .config import load_config
from .core.checks import BuildStopped, Report
from .core.fetch import FetchError, ensure_sources
from .core.sources import load_registry
from .pipeline import audit, build


def print_report(report: Report) -> None:
    for check in report.blocking_failures:
        print(f"  [FAIL] {check.name}: {check.detail}", file=sys.stderr)
    summary = report.summary()
    print(f"{summary['blocking_passed']} checks passed, {summary['blocking_failed']} failed")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=["fetch", "build", "audit"])
    ap.add_argument("--config", default=os.environ.get("SIMD_WORKFLOW_CONFIG", "config/workflow.yaml"))
    ap.add_argument("--source-mode", choices=["offline", "download"], help="source root/mode; audit never downloads")
    args = ap.parse_args(argv)
    report = Report()
    try:
        cfg = load_config(args.config)
        mode = args.source_mode or cfg["source_mode"]
        if args.command == "fetch":
            ensure_sources(load_registry(cfg["source_manifest"]), mode, cfg["source_roots"][mode], cfg["cache_root"], report)
            report.require()
        elif args.command == "audit":
            audit(cfg, mode, report)
        else:
            info = build(cfg, mode, report)
            print(f"Wrote {info['path']}: {info['rows']:,} rows x {info['columns']} columns")
            print(f"Review: {info['build_report']}")
    except (BuildStopped, FetchError, OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        print_report(report)
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1
    print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
