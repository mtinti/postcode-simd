"""Parquet storage for intermediate tables, one file per asset under the work directory.

The ladder produces twelve wide intermediate tables per run. As pickles they would be about
two gigabytes; as Parquet they are a few hundred megabytes and can be opened by anything.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from dagster import ConfigurableIOManager, InputContext, OutputContext


class ParquetIOManager(ConfigurableIOManager):
    base_dir: str

    def _path(self, context) -> Path:
        return Path(self.base_dir).joinpath(*context.asset_key.path).with_suffix(".parquet")

    def handle_output(self, context: OutputContext, obj: pd.DataFrame) -> None:
        if obj is None:
            return
        path = self._path(context)
        path.parent.mkdir(parents=True, exist_ok=True)
        obj.to_parquet(path, index=False)
        context.add_output_metadata({"path": str(path), "rows": len(obj), "columns": len(obj.columns)})

    def load_input(self, context: InputContext) -> pd.DataFrame:
        return pd.read_parquet(self._path(context))
