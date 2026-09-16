"""Shared helpers for the integration tests: where the pinned sources are, and temp configs."""

from __future__ import annotations

from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent.parent


def known_snapshot(manifest: dict, table: str = "history") -> dict | None:
    """Each regression applies to its own source pins and schema.

    Refreshing SSPL must not disable the unchanged SPD history regression.
    """
    known = json.loads((ROOT / "tests/known_snapshot.json").read_text())
    expected = known["remote_object_sha256"]
    sources = manifest["sources"]
    schema_key = "main_schema_sha256" if table == "main" else "schema_sha256"
    if table == "history":
        sources = [o for o in sources if not o["key"].startswith("nrs_sspl_")]
        expected = [s for s in expected if s != known["sspl_object_sha256"]]
    if (sorted(o["sha256"] for o in sources) == sorted(expected)
            and manifest["tables"][table]["schema_sha256"] == known[schema_key]):
        return known
    return None


def source_root() -> Path | None:
    """Choose a complete current release, not an old manual_data directory by one probe."""
    from simd_ingest.core.sources import load_registry, sha256
    registry = load_registry(ROOT / "simd_ingest/sources.yaml")
    for candidate in (ROOT / "manual_data", ROOT / "data" / "sources"):
        if all((candidate / f.path).is_file() and sha256(candidate / f.path) == f.sha256 for f in registry.files):
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
spd_schema: {ROOT / 'simd_ingest' / 'spd_schema.yaml'}
sspl_schema: {ROOT / 'simd_ingest' / 'sspl_schema.yaml'}
export_contract: {ROOT / 'simd_ingest' / 'export_contract.yaml'}
decisions: {decisions}
output_schema: {ROOT / 'simd_ingest' / 'output_schema.yaml'}
output_schema_history: {ROOT / 'simd_ingest' / 'output_schema_history.yaml'}
source_mode: offline
source_roots: {{offline: {source}, download: {temp / 'dl'}}}
cache_root: {temp / 'cache'}
results_root: {temp / 'results'}
""")
    return cfg
