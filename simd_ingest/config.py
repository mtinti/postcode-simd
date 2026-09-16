"""Resolve the small set of build inputs. Relative paths are project-relative."""

import os
from pathlib import Path

import yaml


def load_config(path: Path) -> dict:
    path = Path(path).resolve()
    cfg = yaml.safe_load(path.read_text())
    root = path.parent.parent
    for key in ("source_manifest", "spd_schema", "sspl_schema", "export_contract", "decisions",
                "output_schema", "output_schema_history", "cache_root", "results_root"):
        cfg[key] = root / cfg[key]
    cfg["source_roots"] = {k: root / v for k, v in cfg["source_roots"].items()}
    cfg["source_mode"] = os.environ.get("SIMD_SOURCE_MODE", cfg["source_mode"])
    if cfg["source_mode"] not in ("offline", "download"):
        raise ValueError("source_mode must be offline or download")
    if not isinstance(yaml.safe_load(cfg["decisions"].read_text()).get("decisions"), list):
        raise ValueError("The decision log must contain a decisions list")
    return cfg
