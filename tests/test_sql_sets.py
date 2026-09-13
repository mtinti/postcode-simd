"""Both SQL sets, executed on DuckDB: the SPD set on synthetic history rows, the SSPL set on
synthetic lookup rows, and both on the real tables where a build exists.

The expectations are the documented policy of each step. They do not establish SQL Server
compatibility or equivalence to PHS's own postcode-level lookup.
"""

import json

import duckdb
import pandas as pd
import pytest
import yaml

from simd_ingest.sql_examples import MEASURES, PRODUCTS, render, shared_block
from support import ROOT, known_snapshot

SQL = ROOT / "docs/sql"
EDITIONS = ("2004", "2006", "2009v2", "2012", "2016", "2020v2")
VINTAGE = {e: 2011 if e in ("2016", "2020v2") else 2001 for e in EDITIONS}
VARIANTS = ("link_by_era", "link_latest")
RAW = {name: [f["name"] for f in yaml.safe_load((ROOT / "simd_ingest" / spec["schema"]).read_text())["fields"]
              if f["source"] == spec["raw_source"]] for name, spec in PRODUCTS.items()}
DEMO = {"link_by_era": "    SELECT 1 AS id, CAST('AB24 2TY' AS varchar(32)) AS postcode, 2020 AS analysis_year",
        "link_latest": "    SELECT 1 AS id, CAST('AB24 2TY' AS varchar(32)) AS postcode"}
CONTRACT = ["id", "postcode", "analysis_year", "postcode_key", "postcode_status", "simd_status",
            "index_source", "index_release", "allocation", "simd_edition", "edition_policy", "data_zone_vintage",
            "matched_pc_norm", "matched_introduced_on", "matched_is_current", "matched_user_type",
            "requested_link_postcode", "simd_source_pc_norm", "simd_source_introduced_on", "simd_source_is_current",
            "data_zone_code", "phs_hb_code", "phs_hscp_code", "phs_ca_code",
            *[out for out, _ in MEASURES], "band_direction"]
OK = ("matched", "a_part", "linked_small_user")


def stored_values(seed: int) -> dict:
    """Every edition and measure gets its own value, so a wrong branch is visible."""
    return {f"simd{ed}_{suffix}": seed * 1000 + n * 20 + k + 1
            for n, ed in enumerate(EDITIONS) for k, (_, suffix) in enumerate(MEASURES)}


def record(name, pc="AB11AA", *, base=None, intro="2010-01-01", live=True, user="small_user",
           link="", split="N", seed=1, q=None) -> dict:
    row = {c: f"raw-{c}" for c in RAW[name]}
    row.update(Postcode=pc[:-3] + " " + pc[-3:], SplitIndicator=split, LinkedSmallUserPostcode=link,
               PostcodeType="L" if user == "large_user" else "S",
               DataZone2001Code=f"dz2001-{seed}", DataZone2011Code=f"dz2011-{seed}",
               pc_norm=pc, spd_user_type=user, introduced_on=pd.Timestamp(intro),
               deleted_on=pd.NaT if live else pd.Timestamp(intro) + pd.Timedelta(days=30), is_current=live)
    if name == "spd":
        row.update(pc_base=base or pc, spd_release="fixture-spd")
    else:
        row.update(sspl_release="fixture-sspl")
    for v in (2001, 2011):
        row.update({f"phs_dz{v}_{g}": f"phs-{g}-{v}-{seed}" for g in ("hb", "hscp", "ca")})
    row.update(stored_values(seed))
    if q is not None:
        row.update({f"simd{ed}_pw_scotland_quintile": q for ed in EDITIONS})
    return row


def inputs(postcode="AB1 1AA", year=2020) -> pd.DataFrame:
    return pd.DataFrame({"id": [1], "postcode": pd.Series([postcode], dtype="string"),
                         "analysis_year": pd.Series([year], dtype="Int64")})


@pytest.fixture
def con():
    with duckdb.connect() as connection:
        yield connection


def setup(con, name, rows):
    frame = pd.DataFrame(rows) if rows else pd.DataFrame([record(name)]).iloc[:0]
    con.register(PRODUCTS[name]["table"], frame)


def run(con, name, variant, cohort, text=None) -> pd.DataFrame:
    sql = text or (SQL / name / f"{variant}.sql").read_text()
    assert sql.count(DEMO[variant]) == 1
    columns = "id, postcode, analysis_year" if variant == "link_by_era" else "id, postcode"
    con.register("cohort", cohort)
    return con.execute(sql.replace(DEMO[variant], f"    SELECT {columns} FROM cohort")).df()


def expect_edition(out, row, edition):
    for output, suffix in MEASURES:
        assert out[output] == row[f"simd{edition}_{suffix}"], output
    v = VINTAGE[edition]
    assert out.simd_edition == edition and out.data_zone_vintage == v
    assert out.data_zone_code == row[f"DataZone{v}Code"]
    for g in ("hb", "hscp", "ca"):
        assert out[f"phs_{g}_code"] == row[f"phs_dz{v}_{g}"]
    assert out.band_direction == "1 = most deprived"


# --- the files themselves --------------------------------------------------------------

@pytest.mark.parametrize("name", PRODUCTS)
@pytest.mark.parametrize("variant", VARIANTS)
def test_committed_file_matches_generator(name, variant):
    assert (SQL / name / f"{variant}.sql").read_text() == render(name, "era" if variant == "link_by_era" else "latest")


@pytest.mark.parametrize("name", PRODUCTS)
def test_shared_steps_are_identical_within_a_set(name):
    era, latest = ((SQL / name / f"{v}.sql").read_text() for v in VARIANTS)
    assert shared_block(era) == shared_block(latest)
    assert latest.count("-- EDIT EDITION") == 1 and era.count("-- EDIT EDITION") == 0


@pytest.mark.parametrize("name", PRODUCTS)
@pytest.mark.parametrize("variant", VARIANTS)
def test_output_contract_is_the_same_in_both_sets(con, name, variant):
    setup(con, name, [record(name)])
    out = run(con, name, variant, inputs())
    assert list(out.columns[:len(CONTRACT)]) == CONTRACT
    assert out.columns.str.lower().is_unique
    assert set(RAW[name]) - {"Postcode"} <= set(out.columns) and "matched_postcode" in out.columns


# --- steps 1 to 3: input, key, edition ---------------------------------------------------

@pytest.mark.parametrize("name", PRODUCTS)
@pytest.mark.parametrize("year,edition", [
    (1996, "2004"), (2003, "2004"), (2004, "2006"), (2006, "2006"), (2007, "2009v2"), (2009, "2009v2"),
    (2010, "2012"), (2013, "2012"), (2014, "2016"), (2016, "2016"), (2017, "2020v2"), (2026, "2020v2"), (9999, "2020v2")])
def test_year_selects_every_stored_measure_of_the_edition(con, name, year, edition):
    row = record(name)
    setup(con, name, [row])
    out = run(con, name, "link_by_era", inputs(year=year)).iloc[0]
    assert (out.postcode_status, out.simd_status) == ("matched", "matched")
    expect_edition(out, row, edition)
    assert (out.index_source, out.allocation) == (PRODUCTS[name]["index_source"], PRODUCTS[name]["allocation"])
    assert out.index_release == f"fixture-{name}"
    assert out.matched_pc_norm == out.simd_source_pc_norm == "AB11AA"


@pytest.mark.parametrize("name", PRODUCTS)
def test_one_edition_throughout_is_edited_on_one_line(con, name):
    row = record(name)
    setup(con, name, [row])
    text = (SQL / name / "link_latest.sql").read_text()
    assert run(con, name, "link_latest", inputs(), text).iloc[0].simd_edition == "2020v2"
    edited = "\n".join(line.replace("2020v2", "2004") if "-- EDIT EDITION" in line else line for line in text.splitlines())
    out = run(con, name, "link_latest", inputs(), edited).iloc[0]
    expect_edition(out, row, "2004")
    assert pd.isna(out.analysis_year) and out.edition_policy.startswith("PHS v3.5 section 3.2.1.2")
    unknown = "\n".join(line.replace("2020v2", "2099") if "-- EDIT EDITION" in line else line for line in text.splitlines())
    out = run(con, name, "link_latest", inputs(), unknown).iloc[0]
    assert out.simd_status == "unknown_edition" and pd.isna(out.simd_edition) and pd.isna(out.simd_rank)


@pytest.mark.parametrize("name", PRODUCTS)
@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("postcode,status", [
    (None, "missing_postcode"), ("   ", "missing_postcode"), ("ZZ1 1ZZ", "not_found"),
    (" ab1 1aa ", "matched"), ("AB1 1AAA", "not_found"), ("AB1\t1AA", "not_found")])
def test_key_normalisation_neither_repairs_nor_strips_a_suffix(con, name, variant, postcode, status):
    setup(con, name, [record(name)])
    out = run(con, name, variant, inputs(postcode)).iloc[0]
    assert out.postcode_status == out.simd_status == status
    if status != "matched":
        assert pd.isna(out.matched_pc_norm) and out[[m for m, _ in MEASURES]].isna().all()
    assert out.simd_edition == "2020v2"  # the edition is resolved independently of the postcode


@pytest.mark.parametrize("name", PRODUCTS)
@pytest.mark.parametrize("year,status", [(None, "missing_year"), (0, "invalid_year"), (10000, "invalid_year"), (1995, "no_edition")])
def test_year_problems_keep_the_postcode_but_no_simd(con, name, year, status):
    setup(con, name, [record(name)])
    out = run(con, name, "link_by_era", inputs(year=year)).iloc[0]
    assert (out.simd_status, out.postcode_status) == (status, "matched")
    assert out.matched_pc_norm == "AB11AA" and out.index_release == f"fixture-{name}"
    assert pd.isna(out.simd_edition) and pd.isna(out.data_zone_code) and out[[m for m, _ in MEASURES]].isna().all()


# --- steps 4 and 5: the SPD set selects a life and a part ------------------------------------

def test_spd_uses_the_latest_life_not_the_event_year(con):
    setup(con, "spd", [record("spd", intro="1990-01-01", live=False, seed=1), record("spd", intro="2010-01-01", seed=2)])
    out = run(con, "spd", "link_by_era", pd.concat([inputs(year=1996), inputs(year=2020)]))
    assert len(out) == 2 and out.matched_introduced_on.eq(pd.Timestamp("2010-01-01")).all()
    assert out.simd_edition.tolist() == ["2004", "2020v2"]
    assert out.simd_rank.tolist() == [stored_values(2)["simd2004_rank"], stored_values(2)["simd2020v2_rank"]]


@pytest.mark.parametrize("rows,key,status,has_simd", [
    ([dict(live=False), dict(pc="AB11AAA", base="AB11AA", split="Y")], "AB11AAA", "a_part", True),
    ([dict(pc="AB11AAA", base="AB11AA", split="Y", intro="1973-08-01"),
      dict(pc="AB11AAC", base="AB11AA", split="Y", intro="1978-05-01", live=False)], "AB11AAA", "a_part", True),
    ([dict(pc="AB11AAA", base="AB11AA", split="Y"), dict(pc="AB11AAB", base="AB11AA", split="Y", intro="2020-01-01")], "AB11AAA", "a_part", True),
    ([dict(live=False), dict(pc="AB11AAB", base="AB11AA", split="Y")], "AB11AAB", "split_a_missing", False),
    ([dict(), dict(pc="AB11AAA", base="AB11AA", split="Y")], "AB11AA", "ambiguous_postcode", False),
    ([dict(live=False), dict(intro="2020-01-01", user="large_user", link="NO LINK")], "AB11AA", "unlinked_large_user", False),
])
def test_spd_representative_rule(con, rows, key, status, has_simd):
    setup(con, "spd", [record("spd", **r) for r in rows])
    out = run(con, "spd", "link_latest", inputs()).iloc[0]
    assert (out.matched_pc_norm, out.postcode_status) == (key, status)
    assert out.simd_status == ("matched" if has_simd else status)
    assert out.simd_rank == (out.simd_rank if has_simd else out.simd_rank) if has_simd else pd.isna(out.simd_rank)


@pytest.mark.parametrize("live,split", [(True, "N"), (False, "N"), (True, "Y"), (False, "Y")])
def test_sspl_matches_its_one_row_as_published(con, live, split):
    row = record("sspl", live=live, split=split)
    setup(con, "sspl", [row])
    out = run(con, "sspl", "link_by_era", inputs(year=2000)).iloc[0]
    assert out.postcode_status == ("a_part" if split == "Y" else "matched") and out.simd_status == "matched"
    assert out.matched_is_current == live and out.SplitIndicator == split
    expect_edition(out, row, "2004")


# --- step 6: large users through their link, in both products --------------------------------

SPD_TARGETS = [dict(pc="AB11AC", seed=3), dict(pc="AB11ABA", base="AB11AB", split="Y", seed=4),
               dict(pc="AB11ABB", base="AB11AB", split="Y", seed=5), dict(pc="AB11AD", user="large_user", link="AB1 1AC", seed=6)]
SSPL_TARGETS = [dict(pc="AB11AC", seed=3), dict(pc="AB11AB", split="Y", seed=4), dict(pc="AB11AD", user="large_user", link="AB1 1AC", seed=6)]


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("name,link,status,source", [
    ("spd", "AB1 1AC", "linked_small_user", "AB11AC"), ("spd", " ab1 1ac ", "linked_small_user", "AB11AC"),
    ("spd", "AB1 1ABA", "linked_small_user", "AB11ABA"), ("spd", "AB1 1ABB", "linked_small_user", "AB11ABB"),
    ("spd", "AB1 1AB", "linked_small_user_not_found", None), ("spd", "AB1 1AD", "linked_small_user_not_found", None),
    ("spd", "ZZ1 1ZZ", "linked_small_user_not_found", None),
    ("spd", "NO LINKP", "po_box", None), ("spd", "NO LINK", "unlinked_large_user", None),
    ("spd", "", "unlinked_large_user", None), ("spd", None, "unlinked_large_user", None),
    ("sspl", "AB1 1AC", "linked_small_user", "AB11AC"), ("sspl", " ab1 1ac ", "linked_small_user", "AB11AC"),
    ("sspl", "AB1 1AB", "linked_small_user", "AB11AB"), ("sspl", "AB1 1ABA", "linked_small_user", "AB11AB"),
    ("sspl", "AB1 1ABB", "linked_small_user_not_found", None), ("sspl", "AB1 1ABC", "linked_small_user_not_found", None),
    ("sspl", "AB1 1ACA", "linked_small_user_not_found", None), ("sspl", "AB1 1AD", "linked_small_user_not_found", None),
    ("sspl", "ZZ1 1ZZ", "linked_small_user_not_found", None),
    ("sspl", "NO LINKP", "po_box", None), ("sspl", "NO LINK", "unlinked_large_user", None),
    ("sspl", "", "unlinked_large_user", None), ("sspl", None, "unlinked_large_user", None),
])
def test_large_user_geography_comes_from_the_linked_small_user(con, variant, name, link, status, source):
    targets = SPD_TARGETS if name == "spd" else SSPL_TARGETS
    rows = [record(name, user="large_user", link=link, seed=9)] + [record(name, **t) for t in targets]
    setup(con, name, rows)
    out = run(con, name, variant, inputs()).iloc[0]
    assert (out.matched_pc_norm, out.matched_user_type, out.postcode_status) == ("AB11AA", "large_user", status)
    assert out.requested_link_postcode == link if link is not None else pd.isna(out.requested_link_postcode)
    assert out.DataZone2011Code == "dz2011-9"  # the large user's own zone stays visible as context
    if source is None:
        assert out.simd_status == status and pd.isna(out.simd_source_pc_norm) and pd.isna(out.simd_rank)
    else:
        assert out.simd_status == "matched" and out.simd_source_pc_norm == source
        seed = next(t["seed"] for t in targets if t["pc"] == source)
        expect_edition(out, record(name, seed=seed), "2020v2")


@pytest.mark.parametrize("name", PRODUCTS)
def test_deleted_link_target_still_supplies_geography_and_says_so(con, name):
    setup(con, name, [record(name, user="large_user", link="AB1 1AB"), record(name, pc="AB11AB", live=False, seed=2)])
    out = run(con, name, "link_latest", inputs()).iloc[0]
    assert (out.postcode_status, out.simd_status) == ("linked_small_user", "matched")
    assert out.matched_is_current and not out.simd_source_is_current
    assert out.simd_rank == stored_values(2)["simd2020v2_rank"]


# --- steps 7 and 8: values and report ---------------------------------------------------------

@pytest.mark.parametrize("name", PRODUCTS)
@pytest.mark.parametrize("field", [suffix for _, suffix in MEASURES] + ["DataZone2011Code", "phs_dz2011_hb", "phs_dz2011_hscp", "phs_dz2011_ca"])
def test_a_missing_stored_value_is_reported_not_hidden(con, name, field):
    row = record(name)
    row["simd2020v2_" + field if field in dict(MEASURES).values() else field] = None
    setup(con, name, [row])
    out = run(con, name, "link_by_era", inputs()).iloc[0]
    assert (out.simd_status, out.postcode_status) == ("missing_simd", "matched")
    present = out[[m for m, _ in MEASURES]].notna().sum()
    assert present == (len(MEASURES) - 1 if field in dict(MEASURES).values() else len(MEASURES))


@pytest.mark.parametrize("name", PRODUCTS)
@pytest.mark.parametrize("variant", VARIANTS)
def test_every_input_row_comes_back_once_including_duplicates_and_nulls(con, name, variant):
    setup(con, name, [record(name)])
    cohort = pd.concat([inputs(), inputs(), inputs(year=2000), inputs("ZZ1 1ZZ")], ignore_index=True)
    cohort["id"] = [1, 1, None, None]
    out = run(con, name, variant, cohort)
    assert len(out) == 4 and out.id.isna().sum() == 2
    assert out.simd_status.value_counts().to_dict() == {"matched": 3, "not_found": 1}
    assert run(con, name, variant, cohort.iloc[:0]).empty


@pytest.mark.parametrize("name", PRODUCTS)
@pytest.mark.parametrize("variant", VARIANTS)
def test_worked_example_runs_as_committed(con, name, variant):
    rows = [record(name, "AB242TY", user="large_user", link="AB24 2TN", q=5), record(name, "AB242TN", q=1, seed=2)]
    setup(con, name, rows)
    out = con.execute((SQL / name / f"{variant}.sql").read_text()).df()
    assert len(out) == 1 and out.iloc[0].postcode_status == "linked_small_user"
    assert out.iloc[0].phs_pw_scotland_quintile == 1 and out.iloc[0].matched_pc_norm == "AB242TY"


# --- the real tables --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real():
    paths = {name: ROOT / spec["parquet"] for name, spec in PRODUCTS.items()}
    if not all(p.is_file() for p in paths.values()):
        pytest.skip("no build output")
    con = duckdb.connect()
    for name, spec in PRODUCTS.items():
        con.execute(f"CREATE TABLE {spec['table']} AS SELECT * FROM read_parquet('{paths[name]}')")
    yield con
    con.close()


@pytest.mark.parametrize("name", PRODUCTS)
def test_real_table_every_postcode_once_and_every_value_traceable(real, name):
    table = PRODUCTS[name]["table"]
    key = "pc_base" if name == "spd" else "pc_norm"
    real.execute(f"CREATE OR REPLACE VIEW cohort AS SELECT DISTINCT {key} AS id, {key} AS postcode, 2020 AS analysis_year FROM {table}")
    sql = (SQL / name / "link_by_era.sql").read_text().replace(DEMO["link_by_era"], "    SELECT id, postcode, analysis_year FROM cohort")
    real.execute("CREATE OR REPLACE TABLE result AS " + sql)
    total = real.execute("SELECT COUNT(*) FROM cohort").fetchone()[0]
    assert real.execute("SELECT COUNT(*), COUNT(DISTINCT id) FROM result").fetchone() == (total, total)
    statuses = dict(real.execute("SELECT postcode_status, COUNT(*) FROM result GROUP BY 1").fetchall())
    assert set(statuses) <= {"matched", "a_part", "linked_small_user", "linked_small_user_not_found",
                             "unlinked_large_user", "po_box", "split_a_missing", "ambiguous_postcode"}
    assert real.execute("SELECT COUNT(*) FROM result WHERE simd_status = 'matched' AND postcode_status NOT IN ('matched','a_part','linked_small_user')").fetchone()[0] == 0
    assert real.execute("SELECT COUNT(*) FROM result WHERE simd_status <> 'matched' AND simd_rank IS NOT NULL").fetchone()[0] == 0
    # Every value on a matched row is the stored 2020v2 value of the record that supplied it.
    join = "p.pc_norm = r.simd_source_pc_norm" + (" AND p.introduced_on = r.simd_source_introduced_on" if name == "spd" else "")
    differences = " OR ".join([f"r.{out} IS DISTINCT FROM p.simd2020v2_{suffix}" for out, suffix in MEASURES]
                              + ["r.data_zone_code IS DISTINCT FROM p.DataZone2011Code"]
                              + [f"r.phs_{g}_code IS DISTINCT FROM p.phs_dz2011_{g}" for g in ("hb", "hscp", "ca")])
    assert real.execute(f"SELECT COUNT(*) FROM result r JOIN {table} p ON {join} WHERE r.simd_status = 'matched' AND ({differences})").fetchone()[0] == 0
    assert real.execute(f"SELECT COUNT(*) FROM result r JOIN {table} p ON {join} WHERE p.spd_user_type <> 'small_user'").fetchone()[0] == 0
    ex = real.execute("SELECT * FROM result WHERE id = 'AB242TY'").df().iloc[0]
    assert (ex.postcode_status, ex.phs_pw_scotland_quintile, ex.simd_source_pc_norm, ex.DataZone2011Code) == ("linked_small_user", 1, "AB242TN", "S01006671")
    manifest = json.loads((ROOT / "results/manifest.json").read_text())
    if known_snapshot(manifest, "history") and name == "spd":
        assert real.execute("SELECT COUNT(*) FROM result WHERE postcode_status = 'linked_small_user' AND matched_is_current").fetchone()[0] == 3249


def test_real_tables_agree_on_the_worked_example_and_differ_only_by_allocation(real):
    """Where both products supply a value for the same postcode from the same small-user
    postcode, any difference is the two products' data-zone allocation, never the SQL."""
    outs = {}
    for name, spec in PRODUCTS.items():
        key = "pc_base" if name == "spd" else "pc_norm"
        real.execute(f"CREATE OR REPLACE VIEW cohort AS SELECT DISTINCT {key} AS id, {key} AS postcode, 2020 AS analysis_year FROM {spec['table']}")
        sql = (SQL / name / "link_by_era.sql").read_text().replace(DEMO["link_by_era"], "    SELECT id, postcode, analysis_year FROM cohort")
        real.execute("CREATE OR REPLACE TABLE result AS " + sql)
        outs[name] = real.execute("SELECT id, simd_source_pc_norm, data_zone_code, phs_pw_scotland_quintile FROM result").df().set_index("id")
    both = outs["spd"].join(outs["sspl"], how="inner", lsuffix="_spd", rsuffix="_sspl").dropna()
    assert len(both) > 200_000
    same_zone = both.data_zone_code_spd.eq(both.data_zone_code_sspl)
    assert both[same_zone].phs_pw_scotland_quintile_spd.eq(both[same_zone].phs_pw_scotland_quintile_sspl).all()
    assert 0 < (~same_zone).sum() < len(both) * 0.1
