"""A human report must not turn missing evidence into a passing check."""

from simd_ingest.core.checks import Report
from simd_ingest.core.report import _passed


def test_missing_check_is_not_reported_as_passed():
    report = Report()
    assert _passed(report, "absent") == "NOT RECORDED"
    report.add("good", True)
    report.add("bad", False)
    assert _passed(report, "good") == "ok"
    assert _passed(report, "bad") == "FAILED"


def test_observations_are_not_acceptance_gates():
    report = Report()
    report.observe("changed_release_profile", {"split_records": 12345})
    report.require()
    assert report.summary()["checks"] == 0
    assert report.observations["changed_release_profile"]["split_records"] == 12345
