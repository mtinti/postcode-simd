"""Non-gating comparison with the previous, hash-verified snapshot."""

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .output import same_values
from .sources import sha256

RELEASE_LABELS = ("spd_release", "sspl_release")


def compare_snapshot(table: pd.DataFrame, path: Path, manifest_path: Path, name: str = "history",
                     key: list = ("pc_norm", "introduced_on")) -> dict:
    """`name` is the table's entry in the manifest; `key` its natural key."""
    key = list(key)
    if not path.exists():
        return {"status": "unavailable", "reason": "No previous snapshot"}
    try:
        manifest = json.loads(manifest_path.read_text())
        previous_info = manifest["tables"][name]
        digest = sha256(path)
        if digest != previous_info["sha256"]:
            raise ValueError("Previous snapshot does not match its manifest hash")
        previous = pq.read_table(path).to_pandas(date_as_object=False)
        before, after = previous.copy(), table.copy()
        for frame in (before, after):
            for col in ("introduced_on", "deleted_on"):
                frame[col] = pd.to_datetime(frame[col])
            if frame.duplicated(key).any():
                raise ValueError("Duplicate natural key in snapshot comparison")
        before, after = before.set_index(key), after.set_index(key)
        common = before.index.intersection(after.index)
        old, new = before.loc[common], after.loc[common]
        changed = pd.Series(False, index=common)
        fields = {}
        for col in after.columns.intersection(before.columns):
            if col in RELEASE_LABELS:
                continue
            differs = ~same_values(old[col], new[col])
            if differs.any():
                fields[col] = int(differs.sum())
                changed |= differs
        return {
            "status": "compared", "previous_release": previous_info["index_release"],
            "previous_sha256": digest, "added_records": len(after.index.difference(before.index)),
            "removed_records": len(before.index.difference(after.index)),
            "common_records": len(common), "changed_records": int(changed.sum()),
            "newly_deleted_records": int((old["is_current"] & ~new["is_current"]).sum()),
            "changed_fields": fields,
            "added_columns": list(after.columns.difference(before.columns)),
            "removed_columns": list(before.columns.difference(after.columns)),
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "unavailable", "reason": str(exc)}
