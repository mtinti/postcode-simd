# simd_ingest

The package behind the postcode-SIMD reference table. See the project README for how to build,
run and query it, and `docs/DATA_DICTIONARY.md` for the columns.

- `core/` holds every rule that touches data. It imports nothing from Dagster.
- `orchestration/` declares the Dagster assets and checks over those functions.
- `cli.py` is the same pipeline without Dagster.
- `sources.yaml`, `decisions.yaml`, `output_schema.yaml` and `acceptance_baselines.yaml` are the
  contract: what is read, why, what comes out, and what the checks expect.

