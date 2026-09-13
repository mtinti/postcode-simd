"""The default SQL reads SSPL only: no history, B/C geography or own-LU fallback."""

import json

import duckdb
import pandas as pd
import pytest

from support import ROOT
from test_sql import EDITIONS, QUERIES, SQL, event, query, record


def sspl_record(*args, split=False, **kwargs):
    row = record(*args, **kwargs)
    row.pop("pc_base")
    row.pop("spd_release")
    row.update(sspl_release="fixture-sspl", SplitIndicator="Y" if split else "N")
    return row


@pytest.fixture
def con():
    with duckdb.connect() as connection:
        yield connection


def setup(con, rows):
    con.register("postcode_simd", pd.DataFrame(rows))
    con.execute((SQL / "create_latest_postcode_lookup.sql").read_text())


@pytest.mark.parametrize("name", QUERIES)
@pytest.mark.parametrize("rows,postcode,status,value,source", [
    ([sspl_record(q=4)], " ab1 1aa ", "matched", 4, "AB11AA"),
    ([sspl_record(live=False, q=2)], "AB1 1AA", "matched", 2, "AB11AA"),
    ([sspl_record(split=True, q=5)], "AB1 1AA", "a_part", 5, "AB11AA"),
    ([sspl_record(split=True)], "AB1 1AAA", "not_found", None, None),
    ([sspl_record()], None, "missing_postcode", None, None),
    ([sspl_record()], "  ", "missing_postcode", None, None),
    ([sspl_record(q=None)], "AB1 1AA", "missing_simd", None, "AB11AA"),
    ([sspl_record(user="large_user", link=" ab1 1ab ", q=1), sspl_record("AB11AB", q=5)],
     "AB1 1AA", "linked_small_user", 5, "AB11AB"),
    ([sspl_record(user="large_user", link="AB1 1ABA", q=1), sspl_record("AB11AB", split=True, q=4)],
     "AB1 1AA", "linked_small_user", 4, "AB11AB"),
    ([sspl_record(user="large_user", link="AB1 1ABA"), sspl_record("AB11AB", split=False)],
     "AB1 1AA", "linked_small_user_not_found", None, None),
    ([sspl_record(user="large_user", link="AB1 1ABB"), sspl_record("AB11AB", split=True)],
     "AB1 1AA", "linked_small_user_not_found", None, None),
    ([sspl_record(user="large_user", link="AB1 1ABC"), sspl_record("AB11AB", split=True)],
     "AB1 1AA", "linked_small_user_not_found", None, None),
    ([sspl_record(user="large_user", link="AB1 1AB"), sspl_record("AB11AB", user="large_user", link="AB1 1AC"), sspl_record("AB11AC")],
     "AB1 1AA", "linked_small_user_not_found", None, None),
    ([sspl_record(user="large_user", link="AB1 1AB")], "AB1 1AA", "linked_small_user_not_found", None, None),
])
def test_sspl_linkage_policy(con, name, rows, postcode, status, value, source):
    setup(con, rows)
    out = query(con, event(postcode), name).iloc[0]
    assert out.simd_status == status
    assert (out.simd_value == value) if value is not None else pd.isna(out.simd_value)
    assert (out.simd_source_pc_norm == source) if source else pd.isna(out.simd_source_pc_norm)
    if status not in ("not_found", "missing_postcode"):
        assert (out.index_source, out.index_release, out.allocation) == ("sspl", "fixture-sspl", "oa2022_centroid")
        assert out.matched_is_current == rows[0]["is_current"]


@pytest.mark.parametrize("link", [None, "", "  ", "NO LINKP", "no link"])
def test_no_link_large_users_receive_no_value(con, link):
    setup(con, [sspl_record(user="large_user", link=link, q=1)])
    out = query(con, event()).iloc[0]
    assert out.simd_status == "unlinked_large_user" and pd.isna(out.simd_value)


def test_deleted_target_and_duplicate_events_are_preserved(con):
    setup(con, [sspl_record(user="large_user", link="AB1 1ABA"), sspl_record("AB11AB", split=True, live=False, q=4)])
    events = pd.concat([event(), event(), event()], ignore_index=True)
    events["id"] = [None, 1, 1]
    out = query(con, events)
    assert len(out) == 3 and out.id.isna().sum() == 1
    assert out.simd_status.eq("linked_small_user").all() and out.simd_value.eq(4).all()
    assert not out.simd_source_is_current.any() and out.matched_is_current.all()
    assert out.requested_link_postcode.eq("AB1 1ABA").all()


@pytest.mark.parametrize("year,edition", [(1996, "2004"), (2003, "2004"), (2004, "2006"), (2006, "2006"),
    (2007, "2009v2"), (2009, "2009v2"), (2010, "2012"), (2013, "2012"), (2014, "2016"), (2016, "2016"),
    (2017, "2020v2"), (2026, "2020v2")])
def test_era_changes_edition_not_postcode_life(con, year, edition):
    row = sspl_record(intro="2026-01-01")
    values = dict(zip(EDITIONS, [1, 2, 3, 4, 5, 2]))
    row.update({f"simd{ed}_pw_scotland_quintile": q for ed, q in values.items()})
    setup(con, [row])
    out = query(con, event(date=f"{year}-01-01"), "link_by_era.sql").iloc[0]
    assert (out.simd_edition, out.simd_value) == (edition, values[edition])
    assert out.matched_introduced_on == pd.Timestamp("2026-01-01")


@pytest.mark.parametrize("date,status", [(None, "missing_date"), ("1995-12-31", "no_edition")])
def test_missing_edition_does_not_erase_postcode_provenance(con, date, status):
    setup(con, [sspl_record()])
    out = query(con, event(date=date), "link_by_era.sql").iloc[0]
    assert out.simd_status == status and pd.isna(out.simd_value)
    assert out.index_source == "sspl" and out.matched_pc_norm == "AB11AA"


def test_real_sspl_is_the_only_source(con):
    path = ROOT / "results/postcode_simd.parquet"
    if not path.exists():
        pytest.skip("no main table")
    con.read_parquet(str(path)).create_view("postcode_simd")
    con.execute((SQL / "create_latest_postcode_lookup.sql").read_text())
    total, unique = con.execute("SELECT COUNT(*), COUNT(DISTINCT postcode_key) FROM simd_postcode_latest").fetchone()
    assert total == unique == con.execute("SELECT COUNT(*) FROM postcode_simd").fetchone()[0]
    assert con.execute("""SELECT COUNT(*) FROM simd_postcode_latest
        WHERE postcode_status NOT IN ('matched','a_part','linked_small_user')
          AND (simd_source_pc_norm IS NOT NULL OR simd2020v2_pw_scotland_quintile IS NOT NULL)""").fetchone()[0] == 0
    assert con.execute("""SELECT COUNT(*) FROM simd_postcode_latest v
        JOIN postcode_simd p ON v.simd_source_pc_norm=p.pc_norm
        WHERE p.spd_user_type <> 'small_user'
           OR v.simd2020v2_pw_scotland_quintile <> p.simd2020v2_pw_scotland_quintile""").fetchone()[0] == 0
    manifest = json.loads((ROOT / "results/manifest.json").read_text())
    assert con.execute("SELECT DISTINCT index_source, index_release FROM simd_postcode_latest").fetchall() == [("sspl", manifest["sspl_release"])]
