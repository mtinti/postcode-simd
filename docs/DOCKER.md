# Run the CLI in Docker

Docker is optional packaging for the same CLI, not a second workflow.

```bash
docker compose build
docker compose run --rm build
docker compose run --rm test
docker compose run --rm build audit
```

The default container mode is download. The pinned remote objects are cached in
`data/cache`, their selected files are placed in `data/sources`, and both tables, the report,
the manifest and retained run records go under `results` on the host. No data is baked into
the image.

For already supplied files, keep the relative paths listed in `simd_ingest/sources.yaml`
under `manual_data`:

```bash
SIMD_SOURCE_MODE=offline docker compose run --rm build
SIMD_SOURCE_MODE=offline docker compose run --rm build audit
```

Audit always verifies existing files without fetching or repairing them. Download builds
reuse only hash-valid cached objects. Rebuild the image after changing code or configuration:
the image contains the source registry, schemas and operational settings.

Review `results/BUILD_REPORT.md`, then `manifest.json`; keep `results/runs` with the source
archives and code for lineage. A container exit code of zero means checks passed, not that a
human has approved a new release. Run one writer per results directory. On Linux, use the
appropriate user/volume permissions for your deployment; container-written files may belong
to root.

There is no web UI or instance directory. Legacy local orchestration history is not deleted
by this change, but the CLI does not read or update it.
