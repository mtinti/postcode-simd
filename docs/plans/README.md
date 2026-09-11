# Planning record

The documents that shaped the pipeline, kept as written. Later ones supersede earlier ones;
the decision log in `simd_ingest/decisions.yaml` is the authoritative summary of what was
decided.

| Document | Date | Status |
| --- | --- | --- |
| `Full_Implementation_Plan.md` | 9 September 2026 | The original scope: four published products, three database targets. Superseded. |
| `Plan_Gap_Closure.md` | 9 to 10 September | Evidence from profiling the downloaded sources; corrected the band formula and pinned the postcode contract. Still the reference for the source facts. |
| `Source_API_Options.md` | 10 September | Which publishers expose the data through an API, with every claim verified live. |
| `Snakemake_Implementation_Plan.md` | 10 September | A Snakemake delivery plan. Reviewed and set aside in favour of Dagster. |
| `Dagster_Implementation_Plan.md` | 10 September | The seven-step Dagster plan with the frozen output contract and the validation decision. Those two sections remain in force. |
| `Dagster_First_Release_Plan.md` | 10 September | The three-step cut that produced v1.0, with the hardening backlog. |
| `v1_1_Plan.md` | 11 September | CSV output, the guidance-following lookup, and Docker. Steps 2 and 3 delivered; step 1 pending. |
| `GitHub_Plan.md` | 11 September | Publishing this repository. |
