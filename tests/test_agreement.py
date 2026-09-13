"""The build's cross-table comparison reduces the history table with the same rule as the SPD
SQL set: latest life per NRS key, then live, whole or A part, newest introduction."""

from types import SimpleNamespace

import pandas as pd
import pytest

from simd_ingest.core.agreement import compare_tables, latest_per_postcode
from test_sql_sets import DEMO, SQL, record

STATUS_OF = {"resolved": ("matched", "a_part", "linked_small_user", "unlinked_large_user", "po_box", "linked_small_user_not_found"),
             "split_a_missing": ("split_a_missing",), "ambiguous_postcode": ("ambiguous_postcode",)}


def sql_representatives(history: pd.DataFrame) -> pd.DataFrame:
    import duckdb
    with duckdb.connect() as con:
        con.register("postcode_simd_history", history)
        con.register("cohort", pd.DataFrame({"id": history.pc_base.unique(), "postcode": history.pc_base.unique()}))
        sql = (SQL / "spd" / "link_latest.sql").read_text().replace(DEMO["link_latest"], "    SELECT id, postcode FROM cohort")
        return con.execute(sql).df().set_index("postcode_key").sort_index()


@pytest.mark.parametrize("rows,key,status", [
    ([dict(live=False), dict(pc="AB11AAA", base="AB11AA", split="Y")], "AB11AAA", "resolved"),
    ([dict(pc="AB11AAA", base="AB11AA", split="Y", intro="1973-08-01"),
      dict(pc="AB11AAC", base="AB11AA", split="Y", intro="1978-05-01", live=False)], "AB11AAA", "resolved"),
    ([dict(pc="AB11AAA", base="AB11AA", split="Y"), dict(pc="AB11AAB", base="AB11AA", split="Y", intro="2020-01-01")], "AB11AAA", "resolved"),
    ([dict(live=False), dict(pc="AB11AAB", base="AB11AA", split="Y")], "AB11AAB", "split_a_missing"),
    ([dict(), dict(pc="AB11AAA", base="AB11AA", split="Y")], "AB11AA", "ambiguous_postcode"),
    ([dict(live=False), dict(intro="2020-01-01", user="large_user", link="NO LINK")], "AB11AA", "resolved"),
])
def test_representative_selection_matches_the_spd_sql(rows, key, status):
    history = pd.DataFrame([record("spd", **r) for r in rows])
    actual = latest_per_postcode(history).iloc[0]
    assert actual.pc_norm == key and actual.comparison_status == status
    sql = sql_representatives(history).iloc[0]
    assert (actual.pc_norm, actual.is_current) == (sql.matched_pc_norm, sql.matched_is_current)
    assert sql.postcode_status in STATUS_OF[status]


def test_unresolved_representatives_are_counted_but_not_compared():
    main = pd.DataFrame([record("sspl", q=1)])
    history = pd.DataFrame([record("spd", pc="AB11AAB", base="AB11AA", split="Y", q=5)])
    result = compare_tables(main, history, SimpleNamespace(phs_editions=[]))
    assert result["shared"] == 1 and result["shared_resolved"] == 0
    assert result["unresolved_history_representatives"] == {"split_a_missing": 1}
    assert result["shared_and_current_in_both"] == 0


def test_real_representatives_match_the_spd_sql():
    import json
    from support import ROOT, known_snapshot
    path = ROOT / "results/postcode_simd_history.parquet"
    if not path.exists():
        pytest.skip("no saved history table")
    history = pd.read_parquet(path)
    actual = latest_per_postcode(history).sort_index()
    expected = sql_representatives(history)
    assert actual.index.tolist() == expected.index.tolist()
    assert actual.pc_norm.tolist() == expected.matched_pc_norm.tolist()
    assert actual.is_current.tolist() == expected.matched_is_current.tolist()
    if known_snapshot(json.loads((ROOT / "results/manifest.json").read_text())):
        assert actual.loc["G628LB", "pc_norm"] == "G628LBA"
        assert actual.loc["DD25EG", "pc_norm"] == "DD25EGA"
