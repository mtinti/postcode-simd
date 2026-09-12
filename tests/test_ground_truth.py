"""Ground-truth cases: data zones at every Scotland-level quintile and decile boundary of every
edition and publisher, each with one real postcode, taken from the source files by
simd_ingest.ground_truth. The history table must reproduce every case exactly. The main table
follows the SSPL's own data-zone allocation, so a case may legitimately differ there, but
only when the main table places the postcode in a different data zone; the attached value
must always be the one belonging to the zone the table records."""

from pathlib import Path

import pandas as pd
import pytest

from support import ROOT, known_snapshot

CASES = ROOT / "tests/ground_truth.csv"


@pytest.fixture(scope="module")
def cases():
    import json
    manifest = ROOT / "results/manifest.json"
    if not manifest.is_file() or known_snapshot(json.loads(manifest.read_text())) is None:
        pytest.skip("ground-truth cases apply to the SPD 2026/2 and SSPL 2026/1 pins only")
    return pd.read_csv(CASES, dtype={"pc_norm": str, "dz_code": str})


def _column(case) -> str:
    return f"simd{case.edition}_{'pw' if case.publisher == 'phs' else 'uw'}_scotland_{case.band}"


def test_cases_cover_every_boundary_of_every_edition(cases):
    assert len(cases) == 360
    assert set(cases.publisher) == {"phs", "govscot"} and set(cases.band) == {"quintile", "decile"}
    for (_, _, band), group in cases.groupby(["publisher", "edition", "band"]):
        width = 5 if band == "quintile" else 10
        assert sorted(group.value.unique()) == list(range(1, width + 1))
        first = group[group.edge == "first"].set_index("value")["rank"]
        last = group[group.edge == "last"].set_index("value")["rank"]
        assert first[1] == 1
        assert all(last[v] + 1 == first[v + 1] for v in range(1, width))


def test_history_table_reproduces_every_case(cases):
    t = pd.read_parquet(ROOT / "results/postcode_simd_history.parquet")
    t["introduced_on"] = pd.to_datetime(t["introduced_on"]).dt.strftime("%Y-%m-%d")
    t = t.set_index(["pc_norm", "introduced_on"])
    for case in cases.itertuples():
        row = t.loc[(case.pc_norm, case.introduced_on)]
        assert row["is_current"]
        assert row[f"DataZone{case.dz_vintage}Code"] == case.dz_code
        assert int(row[f"simd{case.edition}_rank"]) == case.rank
        assert int(row[_column(case)]) == case.expected_value


def test_main_table_differs_only_where_its_data_zone_differs(cases):
    t = pd.read_parquet(ROOT / "results/postcode_simd.parquet").set_index("pc_norm")
    reference = {}
    for vintage in (2001, 2011):
        reference[vintage] = t.drop_duplicates(f"DataZone{vintage}Code").set_index(f"DataZone{vintage}Code")
    latest_introduction = pd.to_datetime(t["introduced_on"]).max()
    differing, missing = [], []
    for case in cases.itertuples():
        if case.pc_norm not in t.index:
            # The two NRS products are different cuts: a postcode introduced after the
            # lookup's cut is absent from it. Any other absence is an error.
            assert pd.Timestamp(case.introduced_on) > latest_introduction, case.pc_norm
            missing.append(case.pc_norm)
            continue
        row = t.loc[case.pc_norm]
        zone = row[f"DataZone{case.dz_vintage}Code"]
        if zone == case.dz_code:
            assert int(row[f"simd{case.edition}_rank"]) == case.rank
            assert int(row[_column(case)]) == case.expected_value
        else:
            # A different zone by allocation: the value must be that zone's, not the case's.
            expected = reference[case.dz_vintage].loc[zone]
            assert int(row[_column(case)]) == int(expected[_column(case)])
            differing.append((case.pc_norm, case.dz_code, zone))
    assert len(missing) <= 5, missing
    # The allocation difference affects a few percent of postcodes; a wholesale disagreement
    # would mean the wrong file or the wrong join, not the SSPL's method.
    assert len(differing) < len(cases) * 0.1, differing
