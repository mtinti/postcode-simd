"""Agreement uses the SPD SQL's representative selection, not newest split-part date."""

from types import SimpleNamespace

import pandas as pd
import pytest

from simd_ingest.core.agreement import compare_tables, latest_per_postcode
from test_sql import record, setup, SQL


@pytest.mark.parametrize("rows,key,status", [
    ([record(live=False), record("AB11AAA", base="AB11AA")], "AB11AAA", "resolved"),
    ([record("AB11AAA", base="AB11AA", intro="1973-08-01"),
      record("AB11AAC", base="AB11AA", intro="1978-05-01", live=False)], "AB11AAA", "resolved"),
    ([record("AB11AAA", base="AB11AA"),
      record("AB11AAB", base="AB11AA", intro="2020-01-01")], "AB11AAA", "resolved"),
    ([record(live=False), record("AB11AAB", base="AB11AA")], "AB11AAB", "split_a_missing"),
    ([record(), record("AB11AAA", base="AB11AA")], "AB11AA", "ambiguous_postcode"),
    ([record(live=False), record(intro="2020-01-01", user="large_user")], "AB11AA", "resolved"),
])
def test_representative_selection_matches_sql(rows, key, status):
    import duckdb
    history = pd.DataFrame(rows)
    actual = latest_per_postcode(history).iloc[0]
    assert actual.pc_norm == key and actual.comparison_status == status
    with duckdb.connect() as con:
        setup(con, rows)
        sql = con.execute("SELECT matched_pc_norm, matched_is_current, postcode_status FROM simd_postcode_latest").df().iloc[0]
    assert actual.pc_norm == sql.matched_pc_norm
    assert actual.is_current == sql.matched_is_current
    if status != "resolved":
        assert status == sql.postcode_status


def test_unresolved_representatives_are_counted_but_not_compared():
    main = pd.DataFrame([record(q=1)]).drop(columns="pc_base")
    history = pd.DataFrame([record("AB11AAB", base="AB11AA", q=5)])
    result = compare_tables(main, history, SimpleNamespace(phs_editions=[]))
    assert result["shared"] == 1 and result["shared_resolved"] == 0
    assert result["unresolved_history_representatives"] == {"split_a_missing": 1}
    assert result["shared_and_current_in_both"] == 0


def test_real_representatives_match_sql():
    import duckdb
    import json
    from support import ROOT, known_snapshot
    path = ROOT / "results/postcode_simd_history.parquet"
    if not path.exists():
        pytest.skip("no saved history table")
    history = pd.read_parquet(path)
    actual = latest_per_postcode(history).sort_index()
    with duckdb.connect() as con:
        con.register("postcode_simd_history", history)
        con.execute((SQL / "create_latest_postcode_lookup.sql").read_text())
        expected = con.execute("SELECT postcode_key, matched_pc_norm, matched_is_current FROM simd_postcode_latest").df().set_index("postcode_key").sort_index()
    assert actual.index.tolist() == expected.index.tolist()
    assert actual.pc_norm.tolist() == expected.matched_pc_norm.tolist()
    assert actual.is_current.tolist() == expected.matched_is_current.tolist()
    if known_snapshot(json.loads((ROOT / "results/manifest.json").read_text())):
        assert actual.loc["G628LB", "pc_norm"] == "G628LBA"
        assert actual.loc["DD25EG", "pc_norm"] == "DD25EGA"
