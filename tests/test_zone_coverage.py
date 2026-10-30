"""Every data zone of the SIMD sources has a record: required of the history table, observed for the main one."""

from types import SimpleNamespace

import pandas as pd

from simd_ingest.core.checks import Report
from simd_ingest.core.join import zone_coverage

REGISTRY = SimpleNamespace(
    phs_editions=({"key": "a", "dz_vintage": 2001}, {"key": "b", "dz_vintage": 2011}),
    govscot_editions=({"key": "a", "dz_vintage": 2001}, {"key": "b", "dz_vintage": 2011}),
)
PHS = {"a": pd.DataFrame({"dz_code": ["S01000001", "S01000002"]}),
       "b": pd.DataFrame({"dz_code": ["S01006506", "S01006507"]})}
# A zone only the Government table has still belongs to the vintage's universe.
GOV = {"a": pd.DataFrame({"dz_code": ["S01000001", "S01000002", "S01000003"]}),
       "b": pd.DataFrame({"dz_code": ["S01006506", "S01006507"]})}


def index(dz2001, dz2011):
    return pd.DataFrame({"DataZone2001Code": dz2001, "DataZone2011Code": dz2011})


def run(idx, required):
    report = Report()
    zone_coverage(idx, PHS, GOV, REGISTRY, report, "join.t", required)
    return report


def test_complete_coverage_passes_and_is_observed():
    report = run(index(["S01000001", "S01000002", "S01000003", "S01000003"],
                       ["S01006506", "S01006507", "S01006507", "S01006506"]), required=True)
    assert not report.blocking_failures
    assert report.observations["join.t.dz2001.coverage"] == {"zones": 3, "with_a_record": 3, "missing": []}
    assert report.observations["join.t.dz2011.coverage"] == {"zones": 2, "with_a_record": 2, "missing": []}


def test_a_missing_zone_fails_when_required_and_is_named():
    report = run(index(["S01000001", "S01000002"], ["S01006506", "S01006507"]), required=True)
    failed = {c.name: c for c in report.blocking_failures}
    assert set(failed) == {"join.t.dz2001.coverage"}
    assert failed["join.t.dz2001.coverage"].actual == ["S01000003"]


def test_a_missing_zone_is_only_observed_when_not_required():
    report = run(index(["S01000001", "S01000002"], ["S01006506", None]), required=False)
    assert not report.blocking_failures
    assert report.observations["join.t.dz2001.coverage"]["missing"] == ["S01000003"]
    assert report.observations["join.t.dz2011.coverage"] == {"zones": 2, "with_a_record": 1, "missing": ["S01006507"]}


def test_records_never_add_zones_to_the_universe():
    report = run(index(["S01000001", "S01000002", "S01000003", "S01999999"],
                       ["S01006506", "S01006507", "S01006507", "S01006507"]), required=True)
    assert report.observations["join.t.dz2001.coverage"]["zones"] == 3
    assert not report.blocking_failures
