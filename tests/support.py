"""Shared helpers for the integration tests: where the pinned sources are, and temp configs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = "PHS/simd2004_02042020.csv"


def source_root() -> Path | None:
    """The first root that holds the pinned files: manual_data, else what a download fetched."""
    for candidate in (ROOT / "manual_data", ROOT / "data" / "sources"):
        if (candidate / PROBE).is_file():
            return candidate
    return None


def write_config(temp: Path, source: Path, decisions: Path) -> Path:
    """A config with absolute paths, offline over `source`, writing under `temp`.

    The environment may carry SIMD_SOURCE_MODE, as it does inside the Docker image, which
    would override the offline mode this config relies on. Tests always use the config's mode.
    """
    import os
    os.environ.pop("SIMD_SOURCE_MODE", None)
    cfg = temp / "config" / "workflow.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(f"""
source_manifest: {ROOT / 'simd_ingest' / 'sources.yaml'}
baselines: {ROOT / 'simd_ingest' / 'acceptance_baselines.yaml'}
decisions: {decisions}
output_schema: {ROOT / 'simd_ingest' / 'output_schema.yaml'}
source_mode: offline
source_roots: {{offline: {source}, download: {temp / 'dl'}}}
cache_root: {temp / 'cache'}
work_root: {temp / 'work'}
results_root: {temp / 'results'}
""")
    return cfg
