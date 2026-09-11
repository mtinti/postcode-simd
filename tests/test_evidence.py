"""Report evidence must be present, explicit and from the current run."""

from types import SimpleNamespace
from unittest.mock import Mock

from dagster import AssetKey, DagsterEventType, Failure, MetadataValue
import pytest

from simd_ingest.core.checks import Report
from simd_ingest.core.report import _passed
from simd_ingest.orchestration.evidence import upstream_report

KEY = AssetKey("phs_bands")
REQUIRED = {(KEY, "blocking_checks")}


def event(report, passed=True, include_records=True):
    metadata = {"check_records": MetadataValue.json(report.to_records())} if include_records else {}
    evaluation = SimpleNamespace(asset_key=KEY, check_name="blocking_checks", passed=passed, metadata=metadata)
    return SimpleNamespace(event_log_entry=SimpleNamespace(dagster_event=SimpleNamespace(event_specific_data=evaluation)))


def test_missing_check_is_not_reported_as_passed():
    report = Report()
    assert _passed(report, "absent") == "NOT RECORDED"
    report.add("good", True)
    report.add("bad", False)
    assert _passed(report, "good") == "ok"
    assert _passed(report, "bad") == "FAILED"


def test_only_current_run_is_read_and_pages_are_combined():
    report = Report()
    report.equal("phs.rows", 6505, 6505)
    instance = Mock()
    instance.get_records_for_run.side_effect = [
        SimpleNamespace(records=[], has_more=True, cursor="next-page"),
        SimpleNamespace(records=[event(report)], has_more=False, cursor="end"),
    ]
    collected = upstream_report(instance, "this-run", REQUIRED)
    assert collected.to_records() == report.to_records()
    assert [call.args for call in instance.get_records_for_run.call_args_list] == [("this-run",), ("this-run",)]
    assert instance.get_records_for_run.call_args_list[1].kwargs == {
        "cursor": "next-page", "of_type": DagsterEventType.ASSET_CHECK_EVALUATION}


def test_missing_current_run_evidence_does_not_fall_back_to_previous_success():
    instance = Mock()
    instance.get_records_for_run.return_value = SimpleNamespace(records=[], has_more=False)
    with pytest.raises(Failure, match="Missing upstream check evidence"):
        upstream_report(instance, "new-run", REQUIRED)
    instance.get_latest_materialization_event.assert_not_called()


@pytest.mark.parametrize("passed,include_records,empty", [(False, True, False), (True, False, False), (True, True, True)])
def test_failed_or_absent_check_records_cannot_be_published(passed, include_records, empty):
    report = Report()
    if not empty:
        report.add("phs.rows", True)
    instance = Mock()
    instance.get_records_for_run.return_value = SimpleNamespace(
        records=[event(report, passed, include_records)], has_more=False)
    with pytest.raises(Failure, match="Failed or empty upstream check evidence"):
        upstream_report(instance, "this-run", REQUIRED)


def test_empty_dagster_check_cannot_claim_success():
    from simd_ingest.orchestration.definitions import check_result
    assert not check_result("readback", Report()).passed
