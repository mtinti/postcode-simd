# simd_ingest

Start at [How it is built](../docs/HOW_IT_IS_BUILT.md), then read the run's
`results/BUILD_REPORT.md`. Commands are in the [project README](../README.md);
routine changes are in [Updating the sources](../docs/UPDATING.md).

- `cli.py`: argument parsing and exit status.
- `pipeline.py`: one sequential build, retained evidence and publication; read this first.
- `core/`: source verification, parsers, joins, saved-file checks and reporting.
- `sources.yaml`: pinned sources, published counts and edition mappings.
- `spd_schema.yaml`: accepted directory headers, without fixed release-profile counts.
- `output_schema.yaml`: explicit saved-column contract.
- `decisions.yaml`: choices and their supersessions.
- `lookup.py`: separate consumer policies; not called by ingestion.
