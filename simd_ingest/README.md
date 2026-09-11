# simd_ingest

The package behind the postcode-SIMD reference table. Start a review at
[How it is built](../docs/HOW_IT_IS_BUILT.md), then read the run's `results/BUILD_REPORT.md`.
See the [project README](../README.md) for commands and the
[data dictionary](../docs/DATA_DICTIONARY.md) for columns.

- `core/` holds every rule that touches data. It imports nothing from Dagster.
- `orchestration/` declares Dagster assets/checks and collects their actual current-run evidence.
- `cli.py` is the same pipeline without Dagster.
- `sources.yaml`, `decisions.yaml`, `output_schema.yaml` and `acceptance_baselines.yaml` are the
  contract: what is read, why, what comes out, and what the checks expect.
