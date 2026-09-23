"""Both SQL sets, executed on DuckDB: the SPD set on synthetic history rows, the SSPL set on
synthetic lookup rows, and both on the real tables where a build exists.

The expectations are the documented policy of each step. They do not establish SQL Server
compatibility or equivalence to PHS's own postcode-level lookup.
"""

import json
import re

import duckdb
import pandas as pd
import pytest
import yaml

from simd_ingest import sql_examples
from simd_ingest.sql_examples import FILES, PRODUCTS, VARIANTS as FILE_OF, render, shared_block
from support import ROOT, known_snapshot

SQL = ROOT / "docs/sql"
EDITIONS = ("2004", "2006", "2009v2", "2012", "2016", "2020v2")
# Independent output-to-source expectations: never import the generator's mapping here.
# Distinct fixture values below expose swapped columns even if the generator stays consistent.
MEASURES = [
    ("simd_rank", "rank"),
    ("phs_pw_scotland_quintile", "pw_scotland_quintile"),
    ("phs_pw_scotland_decile", "pw_scotland_decile"),
    ("phs_pw_hb_quintile", "pw_hb_quintile"),
    ("phs_pw_hb_decile", "pw_hb_decile"),
    ("phs_pw_hscp_quintile", "pw_hscp_quintile"),
    ("phs_pw_hscp_decile", "pw_hscp_decile"),
    ("phs_pw_ca_quintile", "pw_ca_quintile"),
    ("phs_pw_ca_decile", "pw_ca_decile"),
    ("phs_pw_most15pc", "most15pc"),
    ("phs_pw_least15pc", "least15pc"),
    ("gov_uw_scotland_quintile", "uw_scotland_quintile"),
    ("gov_uw_scotland_decile", "uw_scotland_decile"),
    ("gov_uw_scotland_vigintile", "uw_scotland_vigintile"),
]
VINTAGE = {e: 2011 if e in ("2016", "2020v2") else 2001 for e in EDITIONS}
VARIANTS = ("link_by_era", "link_latest")
# Independently stated: the coordinate columns the export contract withholds from both the CSV
# and the SQL results. The test states them, the generator reads the contract.
EXCLUDED = {"spd": ["GridReferenceEasting", "GridReferenceNorthing", "Latitude", "Longitude"],
            "sspl": ["GridReferenceEasting", "GridReferenceNorthing"]}
RAW = {name: [f["name"] for f in yaml.safe_load((ROOT / "simd_ingest" / spec["schema"]).read_text())["fields"]
              if f["source"] == spec["raw_source"] and f["name"] not in EXCLUDED[name]]
       for name, spec in PRODUCTS.items()}
DEMO = {"link_by_era": "    SELECT 1 AS id, CAST('AB24 2TY' AS varchar(32)) AS postcode, 2020 AS analysis_year",
        "link_latest": "    SELECT 1 AS id, CAST('AB24 2TY' AS varchar(32)) AS postcode",
        "link_as_of": "    SELECT 1 AS id, CAST('AB11 5FA' AS varchar(32)) AS postcode,\n"
                      "           CAST('2005-06-10' AS date) AS address_date, CAST(NULL AS int) AS analysis_year"}
COHORT_COLUMNS = {"link_by_era": "id, postcode, analysis_year", "link_latest": "id, postcode",
                  "link_as_of": "id, postcode, address_date, analysis_year"}
CONTRACT = ["id", "postcode", "address_date", "analysis_year", "postcode_key", "postcode_status", "simd_status",
            "index_source", "index_release", "allocation", "simd_edition", "edition_policy", "data_zone_vintage",
            "matched_pc_norm", "matched_introduced_on", "matched_is_current", "matched_user_type",
            "requested_link_postcode", "simd_source_pc_norm", "simd_source_introduced_on", "simd_source_is_current",
            "data_zone_code", "intermediate_zone_code", "phs_hb_code", "phs_hscp_code", "phs_ca_code",
            *[out for out, _ in MEASURES], "band_direction"]
OK = ("matched", "a_part", "linked_small_user")
# The classification versions, stated here independently of the generator and the registry.
RURAL = ("2003-2004", "2005-2006", "2007-2008", "2009-2010", "2011-2012", "2013-2014", "2016", "2020", "2022")
RURAL_NESTING = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4, 6: 5, 7: 6, 8: 6}


def rural_stem(version: str) -> str:
    return "urbanrural" + version.replace("-", "_")


def rural_eightfold(seed: int, version: str) -> int:
    """A different class in every version, so picking the wrong version is visible."""
    return (seed + RURAL.index(version)) % 8 + 1


def stored_values(seed: int) -> dict:
    """Every edition and measure gets its own value, so a wrong branch is visible."""
    return {f"simd{ed}_{suffix}": seed * 1000 + n * 20 + k + 1
            for n, ed in enumerate(EDITIONS) for k, (_, suffix) in enumerate(MEASURES)}


def record(name, pc="AB11AA", *, base=None, intro="2010-01-01", live=True, user="small_user",
           link="", split="N", seed=1, q=None, deleted=None, rural_status=None) -> dict:
    """One row. A deleted life ends 30 days after its introduction unless `deleted` names the day."""
    if deleted is not None:
        live = False
    row = {c: f"raw-{c}" for c in RAW[name]}
    row.update(Postcode=pc[:-3] + " " + pc[-3:], SplitIndicator=split, LinkedSmallUserPostcode=link,
               PostcodeType="L" if user == "large_user" else "S",
               DataZone2001Code=f"dz2001-{seed}", DataZone2011Code=f"dz2011-{seed}",
               IntermediateZone2001Code=f"iz2001-{seed}", IntermediateZone2011Code=f"iz2011-{seed}",
               pc_norm=pc, spd_user_type=user, introduced_on=pd.Timestamp(intro),
               deleted_on=pd.NaT if live else pd.Timestamp(deleted) if deleted else pd.Timestamp(intro) + pd.Timedelta(days=30),
               is_current=live)
    if name == "spd":
        row.update(pc_base=base or pc, spd_release="fixture-spd")
        for version in RURAL:
            eight = None if rural_status else rural_eightfold(seed, version)
            row.update({rural_stem(version) + "_8fold": eight, rural_stem(version) + "_6fold": RURAL_NESTING.get(eight),
                        rural_stem(version) + "_status": rural_status})
    else:
        row.update(sspl_release="fixture-sspl")
    for v in (2001, 2011):
        row.update({f"phs_dz{v}_{g}": f"phs-{g}-{v}-{seed}" for g in ("hb", "hscp", "ca")})
    row.update(stored_values(seed))
    if q is not None:
        row.update({f"simd{ed}_pw_scotland_quintile": q for ed in EDITIONS})
    return row


def inputs(postcode="AB1 1AA", year=2020, on=None) -> pd.DataFrame:
    return pd.DataFrame({"id": [1], "postcode": pd.Series([postcode], dtype="string"),
                         "address_date": pd.to_datetime(pd.Series([on])),
                         "analysis_year": pd.Series([year], dtype="Int64")})


@pytest.fixture
def con():
    with duckdb.connect() as connection:
        yield connection


def setup(con, name, rows):
    frame = pd.DataFrame(rows) if rows else pd.DataFrame([record(name)]).iloc[:0]
    for column in frame.columns:                          # an all-null column would otherwise have no type
        if column.startswith("urbanrural"):
            frame[column] = frame[column].astype("string" if column.endswith("_status") else "Int8")
    con.register(PRODUCTS[name]["table"], frame)


def run(con, name, variant, cohort, text=None) -> pd.DataFrame:
    sql = text or (SQL / name / f"{variant}.sql").read_text()
    assert sql.count(DEMO[variant]) == 1
    con.register("cohort", cohort)
    return con.execute(sql.replace(DEMO[variant], f"    SELECT {COHORT_COLUMNS[variant]} FROM cohort")).df()


def expect_edition(out, row, edition):
    for output, suffix in MEASURES:
        assert out[output] == row[f"simd{edition}_{suffix}"], output
    v = VINTAGE[edition]
    assert out.simd_edition == edition and out.data_zone_vintage == v
    assert out.data_zone_code == row[f"DataZone{v}Code"]
    assert out.intermediate_zone_code == row[f"IntermediateZone{v}Code"]
    for g in ("hb", "hscp", "ca"):
        assert out[f"phs_{g}_code"] == row[f"phs_dz{v}_{g}"]
    assert out.band_direction == "1 = most deprived"


# --- the files themselves --------------------------------------------------------------

@pytest.mark.parametrize("name,variant", [(n, v) for n, vs in FILES.items() for v in vs])
def test_committed_file_matches_generator(name, variant):
    assert (SQL / name / FILE_OF[variant]).read_text() == render(name, variant)
    generated = sorted(p.name for p in (SQL / name).glob("*.sql") if not p.name.startswith("walkthrough"))
    assert generated == sorted(FILE_OF[v] for v in FILES[name])


@pytest.mark.parametrize("name", PRODUCTS)
def test_independent_expectations_cover_every_stored_measure(name):
    fields = yaml.safe_load((ROOT / "simd_ingest" / PRODUCTS[name]["schema"]).read_text())["fields"]
    expected = {f"simd{edition}_{suffix}" for edition in EDITIONS for _, suffix in MEASURES}
    assert {f["name"] for f in fields if f["name"].startswith("simd")} == expected
    assert len(MEASURES) == 14 and len(expected) == 84


@pytest.mark.parametrize("name", PRODUCTS)
def test_independent_oracle_rejects_a_swapped_generator_mapping(con, name, monkeypatch):
    row = record(name)
    setup(con, name, [row])
    swapped = {"uw_scotland_quintile": "uw_scotland_decile", "uw_scotland_decile": "uw_scotland_quintile"}
    monkeypatch.setattr(sql_examples, "MEASURES",
                        [(out, swapped.get(suffix, suffix)) for out, suffix in sql_examples.MEASURES])
    out = run(con, name, "link_by_era", inputs(), render(name, "era")).iloc[0]
    with pytest.raises(AssertionError, match="gov_uw_scotland_quintile"):
        expect_edition(out, row, "2020v2")


def test_sql_server_predicates_and_dated_join_keys():
    # Targeted regressions, not a substitute for running the queries on SQL Server.
    for variant in VARIANTS:
        sql = (SQL / "spd" / f"{variant}.sql").read_text()
        assert "CASE WHEN l.is_current = 1 THEN" in sql
        assert "CASE WHEN l.is_current THEN" not in sql
    dated = (SQL / "spd/link_as_of.sql").read_text()
    assert "ORDER BY (SELECT NULL)" not in dated and "input_row" not in dated
    assert "SELECT DISTINCT postcode_key, address_date FROM requested" in dated


def test_only_the_spd_set_can_answer_a_dated_question():
    with pytest.raises(ValueError, match="one life"):
        render("sspl", "asof")


@pytest.mark.parametrize("name", PRODUCTS)
def test_shared_steps_are_identical_within_a_set(name):
    era, latest = ((SQL / name / f"{v}.sql").read_text() for v in VARIANTS)
    assert shared_block(era) == shared_block(latest)
    assert latest.count("-- EDIT EDITION") == 1 and era.count("-- EDIT EDITION") == 0


@pytest.mark.parametrize("name,variant", [(n, FILE_OF[v][:-4]) for n, vs in FILES.items() for v in vs])
def test_common_output_core_and_product_specific_context(con, name, variant):
    setup(con, name, [record(name)])
    out = run(con, name, variant, inputs())
    assert list(out.columns[:len(CONTRACT)]) == CONTRACT
    assert out.columns.str.lower().is_unique
    context = ["matched_postcode" if c == "Postcode" else c for c in RAW[name]]
    if name == "spd":
        context.insert(0, "matched_pc_base")
    if variant == "link_as_of":
        context[:0] = ["first_introduced_on", "previous_life_deleted_on", "next_life_introduced_on"]
    if name == "spd":                                     # rurality sits between the core and the context
        context[:0] = ["rurality_version", "rurality_policy", "rurality_6fold", "rurality_8fold", "rurality_status"]
    assert list(out.columns[len(CONTRACT):]) == context
    assert len(CONTRACT) == 41
    # The SPD set returns five rurality columns after the shared core; the SSPL set has none.
    assert len(out.columns) == (111 if variant == "link_as_of" else 108 if name == "spd" else 89)
    assert not set(EXCLUDED[name]) & set(out.columns)


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
    out = out.sort_values("analysis_year").reset_index(drop=True)   # the queries promise no row order
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
    assert pd.notna(out.simd_rank) if has_simd else pd.isna(out.simd_rank)


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
        key = "pc_norm, introduced_on" if name == "spd" else "pc_norm"
        con.execute(f"ALTER TABLE {spec['table']} ADD PRIMARY KEY ({key})")
    yield con
    con.close()


@pytest.mark.parametrize("name", PRODUCTS)
@pytest.mark.parametrize("year,edition", [(2000, "2004"), (2005, "2006"), (2008, "2009v2"),
                                          (2011, "2012"), (2015, "2016"), (2020, "2020v2")])
def test_real_table_every_postcode_once_and_every_value_traceable(real, name, year, edition):
    table = PRODUCTS[name]["table"]
    key = "pc_base" if name == "spd" else "pc_norm"
    real.execute(f"CREATE OR REPLACE VIEW cohort AS SELECT DISTINCT {key} AS id, {key} AS postcode, {year} AS analysis_year FROM {table}")
    sql = (SQL / name / "link_by_era.sql").read_text().replace(DEMO["link_by_era"], "    SELECT id, postcode, analysis_year FROM cohort")
    real.execute("CREATE OR REPLACE TABLE result AS " + sql)
    total = real.execute("SELECT COUNT(*) FROM cohort").fetchone()[0]
    assert real.execute("SELECT COUNT(*), COUNT(DISTINCT id) FROM result").fetchone() == (total, total)
    statuses = dict(real.execute("SELECT postcode_status, COUNT(*) FROM result GROUP BY 1").fetchall())
    assert set(statuses) <= {"matched", "a_part", "linked_small_user", "linked_small_user_not_found",
                             "unlinked_large_user", "po_box", "split_a_missing", "ambiguous_postcode"}
    assert real.execute("SELECT COUNT(*) FROM result WHERE simd_status = 'matched' AND postcode_status NOT IN ('matched','a_part','linked_small_user')").fetchone()[0] == 0
    assert real.execute("SELECT COUNT(*) FROM result WHERE simd_status <> 'matched' AND simd_rank IS NOT NULL").fetchone()[0] == 0
    # Every selected value traces to its source, including nulls on an incomplete source row.
    join = "p.pc_norm = r.simd_source_pc_norm" + (" AND p.introduced_on = r.simd_source_introduced_on" if name == "spd" else "")
    vintage = VINTAGE[edition]
    differences = " OR ".join([f"r.{out} IS DISTINCT FROM p.simd{edition}_{suffix}" for out, suffix in MEASURES]
                              + [f"r.data_zone_code IS DISTINCT FROM p.DataZone{vintage}Code",
                                 f"r.intermediate_zone_code IS DISTINCT FROM p.IntermediateZone{vintage}Code"]
                              + [f"r.phs_{g}_code IS DISTINCT FROM p.phs_dz{vintage}_{g}" for g in ("hb", "hscp", "ca")])
    assert real.execute(f"SELECT COUNT(*) FROM result r LEFT JOIN {table} p ON {join} WHERE ({differences})").fetchone()[0] == 0
    assert real.execute(f"SELECT COUNT(*) FROM result r JOIN {table} p ON {join} WHERE p.spd_user_type <> 'small_user'").fetchone()[0] == 0
    # Raw context is from the matched postcode, not silently replaced with the link target.
    own_join = "p.pc_norm = r.matched_pc_norm" + (" AND p.introduced_on = r.matched_introduced_on" if name == "spd" else "")
    own_differences = " OR ".join(f"r.{'matched_postcode' if c == 'Postcode' else c} IS DISTINCT FROM p.{c}" for c in RAW[name])
    assert real.execute(f"SELECT COUNT(*) FROM result r LEFT JOIN {table} p ON {own_join} WHERE ({own_differences})").fetchone()[0] == 0
    assert real.execute("SELECT DISTINCT simd_edition, data_zone_vintage FROM result").fetchall() == [(edition, vintage)]
    if edition == "2020v2":
        ex = real.execute("SELECT * FROM result WHERE id = 'AB242TY'").df().iloc[0]
        assert (ex.postcode_status, ex.phs_pw_scotland_quintile, ex.simd_source_pc_norm, ex.DataZone2011Code) == ("linked_small_user", 1, "AB242TN", "S01006671")
    manifest = json.loads((ROOT / "results/manifest.json").read_text())
    if known_snapshot(manifest, "history") and name == "spd":
        assert real.execute("SELECT COUNT(*) FROM result WHERE postcode_status = 'linked_small_user' AND matched_is_current").fetchone()[0] == 3249


def test_real_tables_same_zone_agrees_but_postcode_allocations_can_differ(real):
    """An observed zone/value comparison, not proof of why the products differ."""
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


# --- link_as_of.sql: the life valid on the address date (SPD only) -------------------------

LIVES = [dict(intro="1973-08-01", deleted="1978-04-01", seed=1), dict(intro="1978-11-01", seed=2)]  # deleted, then re-used


def as_of(con, rows, on, year=2020, postcode="AB1 1AA"):
    setup(con, "spd", [record("spd", **r) for r in rows])
    return run(con, "spd", "link_as_of", inputs(postcode, year, on)).iloc[0]


@pytest.mark.parametrize("on,status,seed,previous,following", [
    ("1975-06-01", "matched", 1, None, "1978-11-01"),
    ("1973-08-01", "matched", 1, None, "1978-11-01"),          # the introduction day is inside the life
    ("1978-03-31", "matched", 1, None, "1978-11-01"),          # the day before deletion is inside
    ("1978-04-01", "previous_life", 1, "1978-04-01", "1978-11-01"),  # the deletion day is not: the previous life
    ("1978-06-01", "previous_life", 1, "1978-04-01", "1978-11-01"),  # in the gap: the life before it, never the reissue
    ("1978-11-01", "matched", 2, "1978-04-01", None),          # the re-introduction day starts the new life
    ("1990-06-01", "matched", 2, "1978-04-01", None),
    ("1970-01-01", "postcode_not_yet_introduced", None, None, "1973-08-01"),
    (None, "missing_address_date", None, None, None),
])
def test_as_of_takes_the_life_containing_the_address_date(con, on, status, seed, previous, following):
    out = as_of(con, LIVES, on)
    assert (out.postcode_status, out.simd_status) == (status, "matched" if seed else status)
    assert str(out.first_introduced_on.date()) == "1973-08-01"
    assert (None if pd.isna(out.previous_life_deleted_on) else str(out.previous_life_deleted_on.date())) == previous
    assert (None if pd.isna(out.next_life_introduced_on) else str(out.next_life_introduced_on.date())) == following
    if seed:
        expect_edition(out, record("spd", seed=seed), "2020v2")
        assert out.matched_is_current == (seed == 2)
    else:
        assert pd.isna(out.matched_pc_norm) and pd.isna(out.simd_rank)


def test_as_of_after_the_only_life_is_deleted_by_date(con):
    """A postcode retired before the address date: its last life is used, reported as
    previous_life, with the deletion date beside it so the gap can be judged."""
    life = [dict(intro="1973-08-01", deleted="1999-03-22", seed=4)]
    out = as_of(con, life, "2005-06-10")
    assert (out.postcode_status, out.simd_status, str(out.previous_life_deleted_on.date())) == ("previous_life", "matched", "1999-03-22")
    assert pd.isna(out.next_life_introduced_on) and out.matched_is_current == False
    expect_edition(out, record("spd", seed=4), "2020v2")
    assert as_of(con, life, "1999-03-22").postcode_status == "previous_life"
    assert as_of(con, life, "1999-03-21").postcode_status == "matched"
    assert as_of(con, life, "2005-06-10", postcode="ZZ1 1ZZ").postcode_status == "not_found"


def test_as_of_the_edition_year_defaults_to_the_address_date_and_can_be_overridden(con):
    """analysis_year is an override. Left null, the year of the address date chooses the
    edition, which is what a single event date means. Set, it wins, which is how PHS v3.5
    section 3.2.1.2 holds one edition across a long period."""
    out = as_of(con, LIVES, "2005-06-10", year=None)          # derived: 2005 -> SIMD 2006
    assert out.analysis_year == 2005
    expect_edition(out, record("spd", seed=2), "2006")
    out = as_of(con, LIVES, "1975-06-01", year=None)          # derived: before SIMD began
    assert (out.analysis_year, out.postcode_status, out.simd_status) == (1975, "matched", "no_edition")
    out = as_of(con, LIVES, "1975-06-01", year=1975)          # the same answer, asked for
    assert (out.postcode_status, out.simd_status, out.matched_is_current) == ("matched", "no_edition", False)
    out = as_of(con, LIVES, "1975-06-01", year=2005)          # the override reaches a 1975 life
    assert out.analysis_year == 2005
    expect_edition(out, record("spd", seed=1), "2006")


def test_as_of_with_no_year_and_no_address_date_still_reports_both_problems(con):
    """Nothing to derive from: the postcode cannot be placed in time and neither can the
    edition, and each is reported in its own status rather than one masking the other."""
    out = as_of(con, LIVES, None, year=None)
    assert (out.postcode_status, out.simd_status) == ("missing_address_date", "missing_year")
    assert pd.isna(out.analysis_year) and pd.isna(out.simd_rank)


@pytest.mark.parametrize("rows,on,key,status,has_simd", [
    ([dict(pc="AB11AAA", base="AB11AA", split="Y"), dict(pc="AB11AAB", base="AB11AA", split="Y")], "2015-01-01", "AB11AAA", "a_part", True),
    ([dict(pc="AB11AAA", base="AB11AA", split="Y", live=False), dict(pc="AB11AAB", base="AB11AA", split="Y")], "2015-01-01", "AB11AAB", "split_a_missing", False),
    ([dict(), dict(pc="AB11AAA", base="AB11AA", split="Y")], "2015-01-01", "AB11AA", "ambiguous_postcode", False),
    ([dict(live=False), dict(pc="AB11AAA", base="AB11AA", split="Y", intro="2012-01-01")], "2010-01-15", "AB11AA", "matched", True),
])
def test_as_of_split_parts_among_the_lives_valid_on_the_date(con, rows, on, key, status, has_simd):
    out = as_of(con, rows, on)
    assert (out.matched_pc_norm, out.postcode_status) == (key, status)
    assert out.simd_status == ("matched" if has_simd else status)


@pytest.mark.parametrize("on,status,source_seed", [
    ("2011-01-01", "linked_small_user", 3), ("2016-01-01", "linked_small_user", 4), ("2012-06-01", "linked_small_user_not_found", None)])
def test_as_of_large_user_link_uses_the_target_life_valid_on_the_date(con, on, status, source_seed):
    rows = [dict(user="large_user", link="AB1 1AB", intro="2000-01-01", seed=9),
            dict(pc="AB11AB", intro="2010-06-01", deleted="2012-01-01", seed=3),
            dict(pc="AB11AB", intro="2015-01-01", seed=4)]
    out = as_of(con, rows, on)
    assert (out.matched_pc_norm, out.postcode_status) == ("AB11AA", status)
    if source_seed:
        assert out.simd_status == "matched" and out.simd_source_pc_norm == "AB11AB"
        expect_edition(out, record("spd", seed=source_seed), "2020v2")
    else:
        assert out.simd_status == status and pd.isna(out.simd_source_pc_norm)


def test_as_of_previous_life_is_the_last_one_that_ended_before_the_date_and_never_a_later_one(con):
    """Three lives: 1973 to 1978, 1980 to 1990, and a reissue from 2000. A date in each gap
    takes the life just before it, never the next, and a same-day record never counts."""
    lives = [dict(intro="1973-08-01", deleted="1978-04-01", seed=1), dict(intro="1980-01-01", deleted="1990-01-01", seed=2),
             dict(intro="1995-05-05", deleted="1995-05-05", seed=5), dict(intro="2000-01-01", seed=3)]
    for on, seed in (("1979-06-01", 1), ("1995-06-01", 2), ("1999-06-01", 2)):
        out = as_of(con, lives, on)
        assert out.postcode_status == "previous_life", on
        expect_edition(out, record("spd", seed=seed), "2020v2")
    assert as_of(con, lives, "1972-01-01").postcode_status == "postcode_not_yet_introduced"


def test_as_of_previous_life_keeps_every_rule_that_applies_to_a_record(con):
    """The fallback changes only which life is looked at. A retired PO box still gets nothing,
    and a retired large user takes its link as it stood on the life's last day."""
    box = [dict(intro="1990-01-01", deleted="2000-01-01", user="large_user", link="NO LINKP")]
    out = as_of(con, box, "2005-06-01")
    assert (out.postcode_status, out.simd_status) == ("po_box", "po_box") and pd.isna(out.simd_rank)
    linked = [dict(intro="1990-01-01", deleted="2000-01-01", user="large_user", link="AB1 1AB"),
              dict(pc="AB11AB", intro="1990-01-01", deleted="2000-01-01", seed=6)]      # the link ended the same day
    out = as_of(con, linked, "2005-06-01")
    assert (out.postcode_status, out.simd_source_pc_norm) == ("previous_life", "AB11AB")
    expect_edition(out, record("spd", seed=6), "2020v2")
    gone = [dict(intro="1990-01-01", deleted="2000-01-01", user="large_user", link="AB1 1AB"),
            dict(pc="AB11AB", intro="1990-01-01", deleted="1995-01-01", seed=6)]        # the link had ended earlier
    assert as_of(con, gone, "2005-06-01").postcode_status == "linked_small_user_not_found"


def test_as_of_every_input_row_comes_back_once(con):
    setup(con, "spd", [record("spd", **r) for r in LIVES])
    cohort = pd.concat([inputs(on="1975-06-01"), inputs(on="1975-06-01"), inputs(on="1978-06-01"), inputs("ZZ1 1ZZ", on="1975-06-01")], ignore_index=True)
    cohort["id"] = [1, 1, None, None]
    out = run(con, "spd", "link_as_of", cohort)
    assert len(out) == 4 and out.id.isna().sum() == 2
    assert sorted(out.postcode_status) == ["matched", "matched", "not_found", "previous_life"]
    assert list(out.columns[:len(CONTRACT)]) == CONTRACT and out.columns.str.lower().is_unique
    assert run(con, "spd", "link_as_of", cohort.iloc[:0]).empty


def test_as_of_pairs_are_stable_with_duplicate_ids_dates_and_input_order(con):
    rows = [record("spd", **r) for r in LIVES] + [record("spd", "AB11AB", intro="1970-01-01", seed=3)]
    setup(con, "spd", rows)
    cases = [
        ("AB1 1AA", "1975-06-01", 2020, "matched", 1, "2020v2"),
        ("AB1 1AA", "1975-06-01", 2005, "matched", 1, "2006"),
        (" ab1 1aa ", "1975-06-01", 2020, "matched", 1, "2020v2"),
        ("AB1 1AA", "1990-06-01", 2020, "matched", 2, "2020v2"),
        ("AB1 1AA", "1978-06-01", 2020, "previous_life", 1, "2020v2"),
        ("AB1 1AB", "1975-06-01", 2020, "matched", 3, "2020v2"),
        ("AB1 1AA", None, 2020, "missing_address_date", None, "2020v2"),
        ("ZZ1 1ZZ", None, 2020, "not_found", None, "2020v2"),
        (None, "1975-06-01", 2020, "missing_postcode", None, "2020v2"),
    ]
    cohort = pd.concat([inputs(pc, year, on) for pc, on, year, *_ in cases], ignore_index=True)
    cohort["id"] = pd.Series([None, 1, 1, None, 1, 1, None, 1, None], dtype="Int64")
    expected_rows = []
    for i, (_, _, _, status, seed, edition) in enumerate(cases):
        one = run(con, "spd", "link_as_of", cohort.iloc[[i]])
        assert one.iloc[0].postcode_status == status
        if seed:
            expect_edition(one.iloc[0], record("spd", seed=seed), edition)
        else:
            assert one[[out for out, _ in MEASURES]].isna().all().all()
        expected_rows.append(one)
    # Add exact duplicates too. Expected output comes from checked, isolated lookups.
    cohort = pd.concat([cohort, cohort.iloc[[0, 6]]], ignore_index=True)
    expected = pd.concat([*expected_rows, expected_rows[0], expected_rows[6]], ignore_index=True)

    def canonical(frame):
        # Concatenating all-null single-row results can change pandas' inferred dtypes.
        return frame.convert_dtypes().sort_values(
            ["postcode", "address_date", "analysis_year", "id"], na_position="last").reset_index(drop=True)

    for ordered in (cohort, cohort.iloc[::-1], cohort.sample(frac=1, random_state=42)):
        # Materialise the permutation: DuckDB's pandas scanner rejects negative strides.
        out = run(con, "spd", "link_as_of", ordered.copy())
        pd.testing.assert_frame_equal(canonical(out), canonical(expected))


def test_as_of_real_recycled_and_deleted_postcodes(real):
    cohort = pd.DataFrame({"id": range(1, 7), "postcode": ["FK17 8DS"] * 3 + ["TD9 7PQ"] * 3,
                           "address_date": pd.to_datetime(["1975-06-01", "1978-06-01", "1990-06-01", "1990-05-15", "1999-03-22", "1970-01-01"]),
                           "analysis_year": [2020] * 6})
    real.register("cases", cohort)  # a registered frame would shadow the cohort view created below
    sql = (SQL / "spd" / "link_as_of.sql").read_text().replace(DEMO["link_as_of"], "    SELECT id, postcode, address_date, analysis_year FROM cohort")
    out = real.execute(sql.replace("FROM cohort", "FROM cases")).df().set_index("id").sort_index()
    assert out.postcode_status.tolist() == ["matched", "previous_life", "matched", "matched", "previous_life", "postcode_not_yet_introduced"]
    # June 1978 falls between FK17 8DS's lives: the 1973 life, S01013116, never the 1978 reissue.
    assert out.loc[2, "data_zone_code"] == "S01013116" and str(out.loc[2, "matched_introduced_on"].date()) == "1973-08-01"
    # TD9 7PQ on its deletion day: its last life, retired that day, with the date beside it.
    assert out.loc[5, "simd_status"] == "matched" and not out.loc[5, "matched_is_current"]
    assert out.loc[1, "data_zone_code"] == "S01013116" and out.loc[1, "phs_pw_scotland_quintile"] == 5 and not out.loc[1, "matched_is_current"]
    assert out.loc[3, "data_zone_code"] == "S01013113" and out.loc[3, "phs_pw_scotland_quintile"] == 3 and out.loc[3, "matched_is_current"]
    assert out.loc[4, "phs_pw_scotland_quintile"] == 3 and not out.loc[4, "matched_is_current"]
    assert str(out.loc[5, "previous_life_deleted_on"].date()) == "1999-03-22"
    # Every recorded life, asked on its own introduction day, is found and its values are traceable.
    real.execute("CREATE OR REPLACE VIEW cohort AS SELECT pc_norm AS id, pc_base AS postcode, introduced_on AS address_date, 2020 AS analysis_year FROM postcode_simd_history WHERE deleted_on IS NULL OR deleted_on > introduced_on")
    real.execute("CREATE OR REPLACE TABLE result AS " + sql)
    total = real.execute("SELECT COUNT(*) FROM cohort").fetchone()[0]
    assert real.execute("SELECT COUNT(*) FROM result").fetchone()[0] == total
    assert real.execute("SELECT COUNT(*) FROM result WHERE postcode_status IN ('not_found','between_lives','postcode_deleted_by_date','postcode_not_yet_introduced','missing_address_date')").fetchone()[0] == 0
    differences = " OR ".join([f"r.{out_} IS DISTINCT FROM p.simd2020v2_{suffix}" for out_, suffix in MEASURES] + ["r.data_zone_code IS DISTINCT FROM p.DataZone2011Code"])
    assert real.execute(f"""SELECT COUNT(*) FROM result r JOIN postcode_simd_history p
        ON p.pc_norm = r.simd_source_pc_norm AND p.introduced_on = r.simd_source_introduced_on
        WHERE r.simd_status = 'matched' AND ({differences})""").fetchone()[0] == 0


def test_the_walkthrough_gives_the_same_answers_as_the_generated_dated_query(real):
    """docs/sql/spd/walkthrough_as_of.sql is written by hand so that a reviewer can read the
    logic. It returns fewer columns, but the ones it returns must agree case for case."""
    # A year of None leaves analysis_year null, which is the normal input: both queries must
    # then derive the edition from the address date and still agree.
    cases = [("FK17 8DS", "1975-06-01", 2020), ("FK17 8DS", "1978-06-01", 2020),
             ("FK17 8DS", "1990-06-01", 2020), ("FK17 8DS", "1996-06-01", 1996),
             ("AB24 2TY", "2019-11-20", 2019), ("TD9 7PQ", "1990-05-15", 1990),
             ("TD9 7PQ", "2005-01-10", 2005), ("G71 8BQ", "2020-01-01", 2020),
             ("EH1 1AA", "1993-04-01", 1993), ("ZZ1 1ZZ", "2020-01-01", 2020),
             ("AB11 5FA", "2015-06-01", None), ("AB24 2TY", "2019-11-20", None),
             ("FK17 8DS", "1975-06-01", None), ("TD9 7PQ", "2005-01-10", None),
             ("G71 8BQ", "2008-07-01", None)]
    rows = ",\n        ".join(f"({n}, '{p}', DATE '{d}', {'CAST(NULL AS INTEGER)' if y is None else y})"
                              for n, (p, d, y) in enumerate(cases, 1))
    cohort = f"    SELECT * FROM (VALUES\n        {rows}\n    ) AS v(id, postcode, address_date, analysis_year)\n"

    def run(name):
        sql = (SQL / "spd" / name).read_text()
        # The generated file demonstrates one row, the walkthrough three, so accept either shape.
        demo = re.search(r"    SELECT (?:1 AS id,|\* FROM \(VALUES).*?\n(?=\),)", sql, re.S)
        assert demo, f"{name}: no input block to replace"
        return real.execute(sql.replace(demo.group(0), cohort)).df()

    shared = ["id", "analysis_year", "postcode_status", "simd_edition", "matched_pc_norm", "matched_is_current",
              "simd_source_pc_norm", "data_zone_code", "simd_rank",
              "phs_pw_scotland_quintile", "phs_pw_scotland_decile",
              "gov_uw_scotland_quintile", "gov_uw_scotland_decile",
              "UrbanRural6Fold2022Code", "UrbanRural8Fold2022Code",
              "rurality_version", "rurality_6fold", "rurality_8fold", "rurality_status"]
    full = run("link_as_of.sql")[shared].sort_values("id").reset_index(drop=True)
    short = run("walkthrough_as_of.sql")[shared].sort_values("id").reset_index(drop=True)
    pd.testing.assert_frame_equal(full, short)
    # The cases must actually exercise the interesting branches, or agreeing proves little.
    assert set(full.postcode_status) >= {"matched", "a_part", "linked_small_user", "previous_life", "not_found"}
    # The derived rows really were derived: the reported year is the year of the address date,
    # and one of them lands before SIMD began, where deriving leaves no edition to use.
    derived = full[full.id > 10]
    assert list(derived.analysis_year) == [2015, 2019, 1975, 2005, 2008]
    assert [None if pd.isna(v) else v for v in derived.simd_edition] == \
        ["2016", "2020v2", None, "2006", "2009v2"]
    # The override is what makes the same 1975 address readable on a modern classification.
    assert full.loc[full.id == 1, "simd_edition"].iloc[0] == "2020v2"


# --- Rurality: the contemporary Urban Rural Classification, SPD set only -------------------------

RURAL_BY_YEAR = [(2003, "2003-2004"), (2004, "2003-2004"), (2005, "2005-2006"), (2010, "2009-2010"), (2012, "2011-2012"),
                 (2013, "2013-2014"), (2015, "2013-2014"), (2016, "2016"), (2019, "2016"), (2020, "2020"), (2021, "2020"),
                 (2022, "2022"), (2024, "2022"), (2031, "2022")]


def expect_rurality(out, seed, version):
    eight = rural_eightfold(seed, version)
    assert out.rurality_version == version and out.rurality_status == "matched"
    assert int(out.rurality_8fold) == eight and int(out.rurality_6fold) == RURAL_NESTING[eight]


@pytest.mark.parametrize("year,version", RURAL_BY_YEAR)
def test_rurality_version_follows_the_reference_year_not_the_publication_date(con, year, version):
    """2022, 2023 and 2024 take the 2022 version although it was published in December 2024;
    by publication date they would have taken 2020. A version runs until the next one's year."""
    setup(con, "spd", [record("spd", seed=3)])
    out = run(con, "spd", "link_by_era", inputs(year=year)).iloc[0]
    expect_rurality(out, 3, version)
    assert out.rurality_policy.startswith("project choice")
    dated = as_of(con, [dict(seed=3, intro="1990-01-01")], f"{year}-06-01", year=None)
    expect_rurality(dated, 3, version)


@pytest.mark.parametrize("year,status", [(2002, "before_first_version"), (1996, "before_first_version"), (None, "missing_year"),
                                         (0, "invalid_year"), (-1, "invalid_year"), (10000, "invalid_year")])
def test_rurality_before_the_first_version_or_without_a_year_is_empty_and_says_why(con, year, status):
    setup(con, "spd", [record("spd")])
    out = run(con, "spd", "link_by_era", inputs(year=year)).iloc[0]
    assert (out.rurality_status, out.postcode_status) == (status, "matched")
    assert pd.isna(out.rurality_version) and pd.isna(out.rurality_6fold) and pd.isna(out.rurality_8fold)
    if year == 1996:                                      # SIMD has an edition for 1996; rurality has none
        assert out.simd_status == "matched" and out.simd_edition == "2004"
    if status == "invalid_year":                          # the two statuses agree on a year that is no year
        assert out.simd_status == "invalid_year"
        dated = as_of(con, [dict()], "2020-06-01", year=year)
        assert dated.rurality_status == "invalid_year"


def test_rurality_in_the_latest_query_is_the_latest_version_throughout(con):
    setup(con, "spd", [record("spd", seed=5)])
    out = run(con, "spd", "link_latest", inputs()).iloc[0]
    expect_rurality(out, 5, "2022")
    assert "latest classification version" in out.rurality_policy


@pytest.mark.parametrize("stored", ["outside_polygons", "ambiguous_polygons", "po_box"])
def test_rurality_reports_the_reason_stored_with_the_record(con, stored):
    box = dict(user="large_user", link="NO LINKP") if stored == "po_box" else {}
    setup(con, "spd", [record("spd", rural_status=stored, **box)])
    out = run(con, "spd", "link_by_era", inputs()).iloc[0]
    assert out.rurality_status == stored and out.rurality_version == "2020"
    assert pd.isna(out.rurality_6fold) and pd.isna(out.rurality_8fold)


def test_rurality_is_the_matched_records_own_even_when_simd_comes_from_a_link(con):
    """A large user takes its SIMD from the linked small user but reports its own location."""
    setup(con, "spd", [record("spd", pc="AB11AA", user="large_user", link="AB1 1AB", seed=2), record("spd", pc="AB11AB", seed=6)])
    out = run(con, "spd", "link_by_era", inputs()).iloc[0]
    assert out.postcode_status == "linked_small_user" and out.simd_source_pc_norm == "AB11AB"
    expect_rurality(out, 2, "2020")


def test_rurality_is_withheld_when_no_single_record_stands_for_the_postcode(con):
    rows = [record("spd", pc="AB11AAB", base="AB11AA", split="Y", seed=2), record("spd", pc="AB11AAC", base="AB11AA", split="Y", seed=3)]
    setup(con, "spd", rows)
    out = run(con, "spd", "link_by_era", inputs()).iloc[0]
    assert (out.postcode_status, out.rurality_status) == ("split_a_missing", "split_a_missing")
    assert pd.isna(out.rurality_6fold) and pd.isna(out.rurality_8fold)
    setup(con, "spd", [])
    out = run(con, "spd", "link_by_era", inputs()).iloc[0]
    assert (out.postcode_status, out.rurality_status) == ("not_found", "not_found")


def test_the_sspl_set_returns_no_rurality_columns():
    for variant in FILES["sspl"]:
        assert "rurality" not in render("sspl", variant)
