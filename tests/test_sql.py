"""Execute the documented SQL; expectations are policy examples, not lookup.py output.

The Python helper intentionally uses a different, historical postcode policy.
These tests use DuckDB. They do not establish SQL Server runtime compatibility or
equivalence to a separately published PHS postcode lookup.
"""

from pathlib import Path
import json

import duckdb
import pandas as pd
import pytest

from support import known_snapshot

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "docs/sql"
EDITIONS = ("2004", "2006", "2009v2", "2012", "2016", "2020v2")
QUERIES = ("link_latest.sql", "link_by_era.sql")


def record(pc="AB11AA", *, base=None, intro="2010-01-01", live=True,
           user="small_user", link=None, q=3):
    """One directory life; linked and own SIMD can deliberately disagree."""
    return dict(
        pc_norm=pc, pc_base=base or pc, introduced_on=pd.Timestamp(intro),
        is_current=live, spd_user_type=user, LinkedSmallUserPostcode=link,
        spd_release="fixture", DataZone2001Code="old-zone", DataZone2011Code="new-zone",
        **{f"simd{edition}_pw_scotland_quintile": q for edition in EDITIONS},
    )


@pytest.fixture
def con():
    with duckdb.connect() as connection:
        yield connection


def setup(con, rows):
    con.register("postcode_simd", pd.DataFrame(rows))
    con.execute((SQL / "create_latest_postcode_lookup.sql").read_text())


def query(con, events, name="link_latest.sql", text=None):
    con.register("events", events)
    return con.execute(text or (SQL / name).read_text()).df()


def event(postcode="AB1 1AA", date="2020-01-01"):
    return pd.DataFrame({"id": [1], "postcode": [postcode],
                         "event_date": pd.to_datetime([date])})


@pytest.mark.parametrize("name", QUERIES)
def test_latest_life_not_event_date(con, name):
    setup(con, [record(intro="1990-01-01", live=False, q=1), record(q=4)])
    events = pd.concat([event(date="2004-01-01"), event(date="2020-01-01")])
    out = query(con, events, name)
    assert len(out) == 2  # same patient ID must not merge two events
    assert out.simd_value.tolist() == [4, 4]
    assert out.matched_introduced_on.eq(pd.Timestamp("2010-01-01")).all()
    assert out.simd_source_pc_norm.eq("AB11AA").all()
    assert out.spd_release.eq("fixture").all()


@pytest.mark.parametrize("date,edition,value", [
    ("1996-01-01", "2004", 1), ("2003-12-31", "2004", 1),
    ("2004-01-01", "2006", 2), ("2006-12-31", "2006", 2),
    ("2007-01-01", "2009v2", 3), ("2009-12-31", "2009v2", 3),
    ("2010-01-01", "2012", 4), ("2013-12-31", "2012", 4),
    ("2014-01-01", "2016", 5), ("2016-12-31", "2016", 5),
    ("2017-01-01", "2020v2", 2), ("2026-09-12", "2020v2", 2),
])
def test_table4_boundaries(con, date, edition, value):
    row = record()
    row.update({f"simd{e}_pw_scotland_quintile": q
                for e, q in zip(EDITIONS, [1, 2, 3, 4, 5, 2])})
    setup(con, [row])
    out = query(con, event(date=date), "link_by_era.sql").iloc[0]
    assert (out.simd_edition, out.simd_value, out.simd_status) == (edition, value, "matched")


def test_fixed_edition_has_two_explicit_edit_points_and_needs_no_date(con):
    row = record(q=5)
    row["simd2004_pw_scotland_quintile"] = 1
    setup(con, [row])
    sql = (SQL / "link_latest.sql").read_text()
    assert sql.count("-- EDIT EDITION") == 2
    # Exactly the two marked code lines; selecting an older edition is intentional.
    edited = "\n".join(line.replace("2020v2", "2004") if "-- EDIT EDITION" in line else line
                       for line in sql.splitlines())
    events = event().drop(columns="event_date")
    assert query(con, events).iloc[0].simd_value == 5
    out = query(con, events, text=edited).iloc[0]
    assert (out.simd_edition, out.simd_value) == ("2004", 1)
    assert out.simd_measure == "PHS population-weighted within-Scotland quintile; 1 = most deprived"


@pytest.mark.parametrize("date,status", [(None, "missing_date"), ("1995-12-31", "no_edition")])
def test_unassigned_edition_keeps_postcode_provenance(con, date, status):
    setup(con, [record()])
    out = query(con, event(date=date), "link_by_era.sql").iloc[0]
    assert out.simd_status == status
    assert pd.isna(out.simd_edition) and pd.isna(out.simd_value)
    assert out.matched_pc_norm == out.simd_source_pc_norm == "AB11AA"


@pytest.mark.parametrize("name", QUERIES)
@pytest.mark.parametrize("postcode,status", [
    (None, "missing_postcode"), ("   ", "missing_postcode"), ("ZZ1 1ZZ", "not_found"),
    (" ab1 1aa ", "matched"),
])
def test_input_keys(con, name, postcode, status):
    setup(con, [record()])
    out = query(con, event(postcode), name).iloc[0]
    assert out.simd_status == status
    assert (out.simd_value == 3) if status == "matched" else pd.isna(out.simd_value)


@pytest.mark.parametrize("name", QUERIES)
def test_duplicate_and_null_ids_do_not_drop_or_multiply_events(con, name):
    setup(con, [record(), record("AB11ABA", base="AB11AB"),
                record("AB11ABB", base="AB11AB", q=1)])
    events = pd.concat([event(), event(), event("AB1 1AB"), event("ZZ1 1ZZ")], ignore_index=True)
    events["id"] = [1, 1, None, None]
    out = query(con, events, name)
    assert len(out) == len(events)
    assert out.simd_status.value_counts().to_dict() == {"matched": 2, "a_part": 1, "not_found": 1}
    assert out.id.isna().sum() == 2


@pytest.mark.parametrize("name", QUERIES)
@pytest.mark.parametrize("rows,status,value,source", [
    ([record(live=False, q=2)], "matched", 2, "AB11AA"),  # latest deleted is retained
    ([record("AB11AAA", base="AB11AA", q=5),
      record("AB11AAB", base="AB11AA", intro="2020-01-01", q=1)], "a_part", 5, "AB11AAA"),
    ([record("AB11AAB", base="AB11AA")], "split_a_missing", None, None),
    ([record(live=False), record("AB11AAB", base="AB11AA")], "split_a_missing", None, None),
    ([record("AB11AAA", base="AB11AA", live=False),
      record("AB11AAB", base="AB11AA")], "split_a_missing", None, None),
    ([record(), record("AB11AAA", base="AB11AA")], "ambiguous_postcode", None, None),
    ([record(q=None)], "missing_simd", None, "AB11AA"),
])
def test_representative_and_missing_value_policy(con, name, rows, status, value, source):
    setup(con, rows)
    out = query(con, event(), name).iloc[0]
    assert out.simd_status == status
    assert (out.simd_value == value) if value is not None else pd.isna(out.simd_value)
    assert (out.simd_source_pc_norm == source) if source else pd.isna(out.simd_source_pc_norm)
    if len(rows) == 1 and not rows[0]["is_current"]:
        assert not out.matched_is_current and not out.simd_source_is_current


def test_input_is_ordinary_postcode_not_full_nrs_key(con):
    setup(con, [record("AB11AAA", base="AB11AA"), record("AB11AAB", base="AB11AA")])
    out = query(con, event("AB1 1AAB")).iloc[0]
    assert out.simd_status == "not_found" and pd.isna(out.simd_value)


@pytest.mark.parametrize("name", QUERIES)
def test_large_user_uses_latest_named_small_user_even_when_link_is_b(con, name):
    setup(con, [record(user="large_user", link=" ab1 1abb ", q=1),
                record("AB11ABA", base="AB11AB", q=2),
                record("AB11ABB", base="AB11AB", intro="1990-01-01", live=False, q=3),
                record("AB11ABB", base="AB11AB", intro="2020-01-01", q=5)])
    out = query(con, event(), name).iloc[0]
    assert (out.simd_status, out.simd_value) == ("linked_small_user", 5)
    assert out.matched_pc_norm == "AB11AA" and out.matched_user_type == "large_user"
    assert out.simd_source_pc_norm == "AB11ABB"
    assert out.simd_source_introduced_on == pd.Timestamp("2020-01-01")


@pytest.mark.parametrize("link", [None, "", "  ", "NO LINKP", "no link"])
def test_unlinked_new_large_user_does_not_resurrect_old_small_user(con, link):
    setup(con, [record(intro="1990-01-01", live=False),
                record(user="large_user", link=link, q=1)])
    out = query(con, event()).iloc[0]
    assert out.simd_status == "unlinked_large_user"
    assert pd.isna(out.simd_value) and pd.isna(out.simd_source_pc_norm)
    assert out.matched_user_type == "large_user"


def test_new_small_user_does_not_use_old_large_user_link(con):
    setup(con, [record(intro="1990-01-01", live=False, user="large_user", link="AB1 1AB", q=1),
                record(q=4), record("AB11AB", q=2)])
    out = query(con, event()).iloc[0]
    assert (out.simd_status, out.simd_value, out.simd_source_pc_norm) == ("matched", 4, "AB11AA")


@pytest.mark.parametrize("target", [[], [record("AB11AB", user="large_user")],
    [record("AB11AB", intro="1990-01-01", live=False), record("AB11AB", user="large_user")]])
def test_missing_or_wrong_role_link_has_no_own_or_older_life_fallback(con, target):
    setup(con, [record(user="large_user", link="AB1 1AB", q=1), *target])
    out = query(con, event()).iloc[0]
    assert out.simd_status == "linked_small_user_not_found"
    assert pd.isna(out.simd_value) and pd.isna(out.simd_source_pc_norm)


def test_deleted_link_target_is_visible(con):
    setup(con, [record(user="large_user", link="AB1 1AB", q=1), record("AB11AB", live=False, q=4)])
    out = query(con, event()).iloc[0]
    assert (out.simd_status, out.simd_value) == ("linked_small_user", 4)
    assert out.matched_is_current and not out.simd_source_is_current


@pytest.fixture
def real(con):
    path = ROOT / "results/postcode_simd_history.parquet"  # the view selects the latest life itself
    if not path.is_file():
        pytest.skip("no build output")
    con.read_parquet(str(path)).create_view("postcode_simd")
    con.execute((SQL / "create_latest_postcode_lookup.sql").read_text())
    return con


def test_real_snapshot_has_one_lookup_row_per_base_and_no_hidden_exclusion_values(real):
    total, unique = real.execute("SELECT COUNT(*), COUNT(DISTINCT pc_base) FROM simd_postcode_latest").fetchone()
    bases = real.execute("SELECT COUNT(DISTINCT pc_base) FROM postcode_simd").fetchone()[0]
    assert total == unique == bases
    assert real.execute("""SELECT COUNT(*) FROM simd_postcode_latest
        WHERE postcode_status NOT IN ('matched', 'a_part', 'linked_small_user')
          AND (simd_source_pc_norm IS NOT NULL OR simd2020v2_pw_scotland_quintile IS NOT NULL)""").fetchone()[0] == 0


def test_known_downloaded_large_user_disagreement_and_splits(real):
    manifest = json.loads((ROOT / "results/manifest.json").read_text())
    if known_snapshot(manifest) is None:
        pytest.skip("2026/2 examples do not apply to this snapshot")
    out = query(real, event("AB11 6GN")).iloc[0]
    assert (out.simd_status, out.simd_value, out.simd_source_pc_norm) == ("linked_small_user", 3, "AB116BE")
    own = real.execute("SELECT simd2020v2_pw_scotland_quintile FROM postcode_simd WHERE pc_norm = 'AB116GN' AND is_current").fetchone()[0]
    assert own == 2  # meaningful difference: the SQL must not reuse the LU's own value
    assert query(real, event("G71 8BQ")).iloc[0].simd_value == 5
    assert query(real, event("AB12 3GQ")).iloc[0].simd_value == 4
    assert real.execute("""SELECT COUNT(*) FROM simd_postcode_latest
        WHERE matched_is_current AND postcode_status = 'linked_small_user'""").fetchone()[0] == 3249
    assert real.execute("""SELECT COUNT(*) FROM simd_postcode_latest v
        JOIN postcode_simd p ON p.pc_norm = v.matched_pc_norm
                            AND p.introduced_on = v.matched_introduced_on
        WHERE v.matched_is_current AND v.postcode_status = 'linked_small_user'
          AND v.simd2020v2_pw_scotland_quintile <> p.simd2020v2_pw_scotland_quintile""").fetchone()[0] == 96
    # The named key was small-user but its newest life is large-user: no chain/fallback.
    old = query(real, event("EH3 9RW")).iloc[0]
    assert old.simd_status == "linked_small_user_not_found"
    assert not old.matched_is_current and pd.isna(old.simd_value)
