"""Default SQL: SSPL's own record, analysis year, both publishers, no geography override.

Execute the actual SQL on DuckDB. This tests policy and saved-data fidelity, not
SQL Server runtime compatibility or parity with an official PHS postcode lookup.
"""

import json
import duckdb
import pandas as pd
import pytest

from support import ROOT, known_snapshot

SQL = ROOT / "docs/sql"
EDITIONS = ("2004", "2006", "2009v2", "2012", "2016", "2020v2")
# An independent expected mapping, also used to compare ALL output values with saved rows.
FIELDS = {
    "simd_rank": "rank",
    "phs_pw_scotland_quintile": "pw_scotland_quintile",
    "phs_pw_scotland_decile": "pw_scotland_decile",
    "phs_pw_hb_quintile": "pw_hb_quintile",
    "phs_pw_hb_decile": "pw_hb_decile",
    "phs_pw_hscp_quintile": "pw_hscp_quintile",
    "phs_pw_hscp_decile": "pw_hscp_decile",
    "phs_pw_ca_quintile": "pw_ca_quintile",
    "phs_pw_ca_decile": "pw_ca_decile",
    "phs_pw_most15pc": "most15pc",
    "phs_pw_least15pc": "least15pc",
    "gov_uw_scotland_quintile": "uw_scotland_quintile",
    "gov_uw_scotland_decile": "uw_scotland_decile",
    "gov_uw_scotland_vigintile": "uw_scotland_vigintile",
}
DEMO_INPUT = "SELECT 1 AS id, CAST('AB24 2TY' AS varchar(32)) AS postcode, 2020 AS analysis_year"


def record(pc="AB11AA", *, user="small_user", link="", split="N", live=True, q=None):
    row = dict(
        Postcode=pc[:-3] + " " + pc[-3:], pc_norm=pc, spd_user_type=user,
        LinkedSmallUserPostcode=link, SplitIndicator=split, sspl_release="fixture",
        introduced_on=pd.Timestamp("2026-01-01"),
        deleted_on=pd.NaT if live else pd.Timestamp("2026-02-01"), is_current=live,
        DataZone2001Code="old-zone", DataZone2011Code="new-zone",
        OutputArea2022Code="oa2022", CouncilArea2019Code="nrs-council",
        HealthBoardArea2019Code="nrs-board", IntegrationAuthority2019Code="nrs-hscp",
        UrbanRural6Fold2022Code="6", UrbanRural8Fold2022Code="8",
    )
    for vintage in (2001, 2011):
        row.update({f"phs_dz{vintage}_{g}": f"phs-{g}-{vintage}" for g in ("hb", "hscp", "ca")})
    for n, edition in enumerate(EDITIONS):
        # Different scopes, publishers and editions have deliberately different values.
        values = [100 * n + 7, n % 5 + 1, n % 10 + 1,
                  (n + 1) % 5 + 1, (n + 1) % 10 + 1,
                  (n + 2) % 5 + 1, (n + 2) % 10 + 1,
                  (n + 3) % 5 + 1, (n + 3) % 10 + 1,
                  n % 2, (n + 1) % 2,
                  (n + 4) % 5 + 1, (n + 4) % 10 + 1, (n + 4) % 20 + 1]
        row.update({f"simd{edition}_{suffix}": value
                    for suffix, value in zip(FIELDS.values(), values)})
        if q is not None:
            row[f"simd{edition}_pw_scotland_quintile"] = q
    return row


def events(postcode="AB1 1AA", year=2020):
    return pd.DataFrame({"id": [1], "postcode": pd.Series([postcode], dtype="string"),
                         "analysis_year": pd.Series([year], dtype="Int64")})


@pytest.fixture
def con():
    with duckdb.connect() as connection:
        yield connection


def setup(con, rows):
    frame = pd.DataFrame(rows) if rows else pd.DataFrame([record()]).iloc[:0]
    con.register("postcode_simd", frame)
    con.execute((SQL / "create_latest_postcode_lookup.sql").read_text())


def cohort_sql():
    text = (SQL / "link_by_era.sql").read_text()
    assert text.count(DEMO_INPUT) == 1
    return text.replace(DEMO_INPUT, "SELECT id, postcode, analysis_year FROM events")


def query(con, inputs):
    con.register("events", inputs)
    return con.execute(cohort_sql()).fetchdf()


@pytest.mark.parametrize("year,edition", [
    (1996, "2004"), (2003, "2004"), (2004, "2006"), (2006, "2006"),
    (2007, "2009v2"), (2009, "2009v2"), (2010, "2012"), (2013, "2012"),
    (2014, "2016"), (2016, "2016"), (2017, "2020v2"), (2026, "2020v2"),
    (9999, "2020v2"),
])
def test_year_selects_all_fields_of_both_publishers(con, year, edition):
    row = record()
    setup(con, [row])
    out = query(con, events(year=year)).iloc[0]
    assert out.simd_edition == edition and out.simd_status == "matched"
    for output, suffix in FIELDS.items():
        assert out[output] == row[f"simd{edition}_{suffix}"], output
    vintage = 2011 if edition in ("2016", "2020v2") else 2001
    assert out.data_zone_vintage == vintage
    assert out.data_zone_code == row[f"DataZone{vintage}Code"]
    for geo in ("hb", "hscp", "ca"):
        assert out[f"phs_{geo}_code"] == row[f"phs_dz{vintage}_{geo}"]
    assert out.phs_hb_code != out.nrs_health_board_2019
    assert out.band_direction == "1 = most deprived"
    assert out.introduced_on == pd.Timestamp("2026-01-01")  # NOT an as-of lookup
    assert out.nrs_output_area_2022 == "oa2022"
    assert out.nrs_urban_rural_8fold_2022 == "8"


@pytest.mark.parametrize("postcode,status", [
    (" ab1 1aa ", "matched"), (None, "missing_postcode"), ("   ", "missing_postcode"),
    ("ZZ1 1ZZ", "not_found"), ("AB1 1AAA", "not_found"), ("AB1\t1AA", "not_found"),
])
def test_normalisation_does_not_repair_or_strip_split_suffixes(con, postcode, status):
    setup(con, [record()])
    out = query(con, events(postcode)).iloc[0]
    assert out.postcode_status == out.simd_status == status
    assert out.simd_edition == "2020v2"
    assert pd.isna(out.address_warning)
    if status != "matched":
        assert out[list(FIELDS)].isna().all()
        assert pd.isna(out.matched_pc_norm)


@pytest.mark.parametrize("link,warning", [
    (None, "unlinked_large_user"), ("", "unlinked_large_user"), ("  ", "unlinked_large_user"),
    ("NO LINKP", "po_box"), (" no linkp ", "po_box"), ("NO LINK", "unlinked_large_user"),
    ("AB1 1AB", "large_user"), ("AB1 1ABA", "large_user"),
    ("AB1 1ABB", "large_user"), ("AB1 1ABC", "large_user"), ("ZZ1 1ZZ", "large_user"),
])
def test_large_user_keeps_own_sspl_values_regardless_of_link(con, link, warning):
    own = record(user="large_user", link=link, q=5)
    target = record("AB11AB", split="Y", q=1)
    setup(con, [own, target])
    out = query(con, events()).iloc[0]
    assert out.postcode_status == out.simd_status == "matched"
    assert out.matched_pc_norm == "AB11AA" and out.phs_pw_scotland_quintile == 5
    assert out.address_warning == warning
    for output, suffix in FIELDS.items():
        assert out[output] == own[f"simd2020v2_{suffix}"]


@pytest.mark.parametrize("live,split", [(True, "N"), (False, "N"), (True, "Y"), (False, "Y")])
def test_deleted_and_already_whole_split_records_are_not_reselected(con, live, split):
    setup(con, [record(live=live, split=split, q=4)])
    out = query(con, events(year=2000)).iloc[0]
    assert out.postcode_status == out.simd_status == "matched"
    assert out.phs_pw_scotland_quintile == 4
    assert out.is_current == live and out.split_indicator == split
    assert out.matched_pc_norm == "AB11AA"


@pytest.mark.parametrize("year,status", [
    (None, "missing_year"), (1995, "no_edition"), (1, "no_edition"),
    (0, "invalid_year"), (-1, "invalid_year"), (10000, "invalid_year"),
])
def test_invalid_or_unsupported_year_retains_postcode_but_no_simd(con, year, status):
    setup(con, [record()])
    out = query(con, events(year=year)).iloc[0]
    assert out.simd_status == status and out.postcode_status == "matched"
    assert out.matched_pc_norm == "AB11AA" and out.sspl_release == "fixture"
    assert pd.isna(out.simd_edition) and out[list(FIELDS)].isna().all()
    assert pd.isna(out.data_zone_code) and pd.isna(out.phs_hb_code)


def test_postcode_and_year_problems_are_both_visible(con):
    setup(con, [])
    out = query(con, events(None, None)).iloc[0]
    assert out.postcode_status == "missing_postcode" and out.simd_status == "missing_year"


@pytest.mark.parametrize("field", list(FIELDS.values()))
def test_partial_missing_measure_is_reported_without_discarding_other_publisher(con, field):
    row = record()
    row[f"simd2020v2_{field}"] = None
    setup(con, [row])
    out = query(con, events()).iloc[0]
    assert out.simd_status == "missing_simd" and out.postcode_status == "matched"
    assert out[list(FIELDS)].notna().sum() == len(FIELDS) - 1


def test_duplicate_events_and_null_ids_are_preserved(con):
    setup(con, [record()])
    inputs = pd.concat([events(), events(), events(year=2000), events("ZZ1 1ZZ")], ignore_index=True)
    inputs["id"] = [1, 1, None, None]
    out = query(con, inputs)
    assert len(out) == 4 and out.id.isna().sum() == 2
    assert out.simd_status.value_counts().to_dict() == {"matched": 3, "not_found": 1}
    assert out.simd_edition.value_counts().to_dict() == {"2020v2": 3, "2004": 1}
    assert out.phs_pw_scotland_quintile.notna().sum() == 3


@pytest.mark.parametrize("field", ["DataZone2011Code", "phs_dz2011_hb", "phs_dz2011_hscp", "phs_dz2011_ca"])
def test_missing_selected_geography_is_not_a_complete_simd_match(con, field):
    row = record()
    row[field] = None
    setup(con, [row])
    out = query(con, events()).iloc[0]
    assert out.simd_status == "missing_simd" and out.postcode_status == "matched"
    assert out[list(FIELDS)].notna().all()


def test_single_postcode_example_runs_without_an_events_table(con):
    setup(con, [record("AB242TY", user="large_user", link="AB24 2TN", q=5),
                record("AB242TN", q=1)])
    out = con.execute((SQL / "link_by_era.sql").read_text()).fetchdf()
    assert len(out) == 1
    assert out.iloc[0].matched_pc_norm == "AB242TY"
    assert out.iloc[0].phs_pw_scotland_quintile == 5


@pytest.fixture
def real(con):
    path = ROOT / "results/postcode_simd.parquet"
    if not path.exists():
        pytest.skip("no SSPL build")
    con.read_parquet(str(path)).create_view("postcode_simd")
    con.execute((SQL / "create_latest_postcode_lookup.sql").read_text())
    return con


def test_all_saved_values_and_geographies_survive_sql_reshaping(real):
    total = real.sql("SELECT COUNT(*) FROM postcode_simd").fetchone()[0]
    assert real.sql("SELECT COUNT(*) FROM simd_postcode_by_edition").fetchone()[0] == 6 * total
    assert real.sql("""SELECT COUNT(*) FROM (
        SELECT pc_norm, simd_edition FROM simd_postcode_by_edition
        GROUP BY pc_norm, simd_edition HAVING COUNT(*) <> 1)""").fetchone()[0] == 0
    for edition in EDITIONS:
        vintage = 2011 if edition in ("2016", "2020v2") else 2001
        comparisons = [f"s.{out} IS DISTINCT FROM p.simd{edition}_{src}" for out, src in FIELDS.items()]
        comparisons += [f"s.data_zone_code IS DISTINCT FROM p.DataZone{vintage}Code",
                        f"s.data_zone_vintage <> {vintage}"]
        comparisons += [f"s.phs_{geo}_code IS DISTINCT FROM p.phs_dz{vintage}_{geo}"
                        for geo in ("hb", "hscp", "ca")]
        count = real.sql(f"""SELECT COUNT(*) FROM simd_postcode_by_edition s
            JOIN postcode_simd p ON p.pc_norm=s.pc_norm
            WHERE s.simd_edition='{edition}' AND ({" OR ".join(comparisons)})""").fetchone()[0]
        assert count == 0, edition


def test_default_query_preserves_whole_saved_cohort(real):
    real.sql("""CREATE VIEW events AS
        SELECT pc_norm AS id, Postcode AS postcode, 2020 AS analysis_year FROM postcode_simd""")
    real.execute("CREATE TEMP VIEW result AS " + cohort_sql())
    assert real.sql("SELECT COUNT(*), COUNT(DISTINCT id) FROM result").fetchone() == (
        real.sql("SELECT COUNT(*) FROM postcode_simd").fetchone()[0],) * 2
    assert real.sql("SELECT COUNT(*) FROM result WHERE simd_status <> 'matched'").fetchone()[0] == 0
    assert real.sql("""SELECT COUNT(*) FROM result r JOIN postcode_simd p ON r.id=p.pc_norm
        WHERE r.phs_pw_scotland_quintile IS DISTINCT FROM p.simd2020v2_pw_scotland_quintile
           OR r.gov_uw_scotland_quintile IS DISTINCT FROM p.simd2020v2_uw_scotland_quintile""").fetchone()[0] == 0


def test_reviewed_live_large_user_no_longer_changes_quintile(real):
    manifest = json.loads((ROOT / "results/manifest.json").read_text())
    if known_snapshot(manifest, table="main") is None:
        pytest.skip("examples require reviewed SSPL snapshot")
    out = query(real, events("AB24 2TY")).iloc[0]
    assert out.phs_pw_scotland_quintile == 5 and out.matched_pc_norm == "AB242TY"
    assert out.address_warning == "large_user"
    assert real.sql("""SELECT simd2020v2_pw_scotland_quintile FROM postcode_simd
        WHERE pc_norm='AB242TN'""").fetchone()[0] == 1
