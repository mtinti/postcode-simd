"""Collect the actual upstream check records from this Dagster run for the final report.

The CLI keeps one Report in memory. Dagster runs stages separately, so their check events
carry the same records. Only the current run is read; missing evidence is never a pass.
"""

from dagster import DagsterEventType, Failure

from ..core.checks import Check, Report


def upstream_report(instance, run_id: str, required: set) -> Report:
    """Require each (asset key, check name), then combine its recorded core checks."""
    evaluations = {}
    cursor = None
    while True:
        page = instance.get_records_for_run(run_id, cursor=cursor,
                                            of_type=DagsterEventType.ASSET_CHECK_EVALUATION)
        for record in page.records:
            evaluation = record.event_log_entry.dagster_event.event_specific_data
            key = (evaluation.asset_key, evaluation.check_name)
            if key in required:
                evaluations[key] = evaluation  # Latest attempt in this run, after any retry.
        if not page.has_more:
            break
        cursor = page.cursor

    missing = required - evaluations.keys()
    if missing:
        names = sorted(f"{asset.to_user_string()}/{check}" for asset, check in missing)
        raise Failure(f"Missing upstream check evidence in this run: {names}")

    report = Report()
    for key in sorted(evaluations, key=lambda k: (k[0].to_user_string(), k[1])):
        evaluation = evaluations[key]
        evidence = evaluation.metadata.get("check_records")
        if not evaluation.passed or evidence is None or not evidence.value:
            raise Failure(f"Failed or empty upstream check evidence: {key}")
        report.checks.extend(Check(**record) for record in evidence.value)
    report.require()
    return report
