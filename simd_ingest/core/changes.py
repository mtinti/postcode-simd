"""Non-gating comparison with the previous, hash-verified snapshot."""

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .output import same_values
from .sources import sha256

KEY = ["pc_norm", "introduced_on"]


def compare_snapshot(table: pd.DataFrame, path: Path, manifest_path: Path) -> dict:
    if not path.exists():
        return {"status": "unavailable", "reason": "No previous snapshot"}
    try:
        manifest = json.loads(manifest_path.read_text())
        digest = sha256(path)
        if digest != manifest["output"]["sha256"]:
            raise ValueError("Previous snapshot does not match its manifest hash")
        previous = pq.read_table(path).to_pandas(date_as_object=False)
        before, after = previous.copy(), table.copy()
        for frame in (before, after):
            for col in ("introduced_on", "deleted_on"):
                frame[col] = pd.to_datetime(frame[col])
            if frame.duplicated(KEY).any():
                raise ValueError("Duplicate natural key in snapshot comparison")
        before, after = before.set_index(KEY), after.set_index(KEY)
        common = before.index.intersection(after.index)
        old, new = before.loc[common], after.loc[common]
        changed = pd.Series(False, index=common)
        fields = {}
        for col in after.columns.intersection(before.columns):
            if col == "spd_release":
                continue
            differs = ~same_values(old[col], new[col])
            if differs.any():
                fields[col] = int(differs.sum())
                changed |= differs
        return {
            "status": "compared", "previous_release": manifest["spd_release"],
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
