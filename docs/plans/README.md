# Planning record

These are historical design and review records, not the instructions for the current build.
Start with [How it is built](../HOW_IT_IS_BUILT.md) and the current run's `BUILD_REPORT.md`.
The [decision log](../../simd_ingest/decisions.yaml) is authoritative for current policy and
explicit supersessions; the implemented schema lives in `simd_ingest/output_schema.yaml`.

In particular, the population diagnostic was removed by `trust-the-sources` on 11 September
2026, and the default split lookup changed to the A part with an explicit report option.
Earlier policies below explain the history; they do not override those decisions.

On 12 September 2026, CLI-first replaced the orchestration delivery plan. The current
maintenance instructions are [Updating the sources](../UPDATING.md); no Dagster runtime
or intermediate-table cache is required.

| Document | Date | Status |
| --- | --- | --- |
| `Full_Implementation_Plan.md` | 9 September 2026 | The original scope: four published products, three database targets. Superseded. |
| `Plan_Gap_Closure.md` | 9 to 10 September | Evidence from profiling the downloaded sources; corrected the band formula and pinned the postcode contract. Still the reference for the source facts. |
| `Source_API_Options.md` | 10 September | Which publishers expose the data through an API, with every claim verified live. |
| `Snakemake_Implementation_Plan.md` | 10 September | A Snakemake delivery plan. Reviewed and set aside in favour of Dagster. |
| `Dagster_Implementation_Plan.md` | 10 September | Historical seven-step proposal. Consult the implemented schema and current decision log, not this plan, for today's contract. |
| `Dagster_First_Release_Plan.md` | 10 September | The three-step cut that produced v1.0, with the hardening backlog. |
| `v1_1_Plan.md` | 11 September | CSV output, the guidance-following lookup, and Docker. Steps 2 and 3 delivered; step 1 pending. |
| `GitHub_Plan.md` | 11 September | Publishing this repository. |
| `SSPL_Main_Table_Plan.md` | 12 September | Historical proposal; option A implemented, then corrected and refreshed to SSPL 2026/2. See its correction notice and the current runbook. |
| `SQL_Two_Products_Plan.md` | 13 September | Historical proposal, implemented in 2.1.0; review corrections clarify shared core versus raw context and guidance versus project interpretations. See the current SQL guide. |
| `Exports_Plan.md` | 16 September | The shared CSV rendering, coordinate-free SQL output and the database load check. Implemented in 2.2.0. |
| `Rurality_By_Version_Plan.md` | 21 September | Implemented on the feature branch, not yet released. A contemporary urban-rural class for every postcode life, by placing each life's grid reference in each of the nine published classification shapefiles, gated on reproducing the published 2022 codes. |
