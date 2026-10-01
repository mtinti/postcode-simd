"""The Scottish Government's published domain bands: copied as published, gated rank against rank.

The bands come from statistics.gov.scot, the ranks from the shapefiles, so the tests below pin
the gate that admits a band only where its ranking is ours, the source-status flag for the
2020v2 housing zones where two Government publications disagree, and the flag's passage through
the tables, the SQL and the Python lookups (docs/plans/Domain_Bands_Plan.md).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from simd_ingest import lookup
from simd_ingest.core.checks import Report
from simd_ingest.core.govscot import read_published_bands
from simd_ingest.core.sources import RANK_SOURCES_DISAGREE, load_registry
from support import ROOT

HISTORY = ROOT / "results" / "postcode_simd_history.parquet"
MAIN = ROOT / "results" / "postcode_simd.parquet"
AUDIT = ROOT / "simd_ingest" / "sgs_2020_housing_rank_disagreements.csv"
STATUS = "simd2020v2_housing_domain_rank_source_status"
NAMES = {"overall": "SIMD", "income": "Income", "housing": "Housing", "crime": "Crime"}


# --- the gate, on small synthetic sources ------------------------------------------------------

def shapefile_table() -> pd.DataFrame:
    """Four zones as the shapefile gives them: overall rank and bands, and two domain ranks, one
    with a tied half."""
    return pd.DataFrame({"dz_code": ["Z1", "Z2", "Z3", "Z4"], "rank": [1, 2, 3, 4],
                         "uw_scotland_quintile": [1, 2, 4, 5], "uw_scotland_decile": [1, 4, 7, 10],
                         "uw_scotland_vigintile": [1, 8, 13, 20],
                         "income_domain_rank": [1.0, 2.5, 2.5, 4.0], "housing_domain_rank": [1.0, 2.0, 3.0, 4.0]})


def published(gov: pd.DataFrame, ranks=None, bands=None, date_code=2020, drop=None, extra=None) -> pd.DataFrame:
    """The same values laid out as statistics.gov.scot publishes them, with overrides:
    ranks[(domain, zone)] and bands[(domain, zone, measurement)]."""
    ranks, bands, rows = ranks or {}, bands or {}, []
    for i, r in gov.iterrows():
        for domain in ("overall", "income", "housing"):
            rank = ranks.get((domain, r.dz_code), float(r["rank"] if domain == "overall" else r[f"{domain}_domain_rank"]))
            base = {"Quintile": r.uw_scotland_quintile, "Decile": r.uw_scotland_decile, "Vigintile": r.uw_scotland_vigintile}
            for m, v in [("Rank", rank), *base.items()]:
                v = bands.get((domain, r.dz_code, m), v)
                rows.append(dict(FeatureCode=r.dz_code, FeatureName=r.dz_code, FeatureType="2011 Data Zone", DateCode=date_code,
                                 Measurement=m, Units=m, Value=v, **{"SIMD Domain": NAMES[domain]}))
    out = pd.DataFrame(rows + (extra or []))
    if drop:
        out = out[~out.FeatureCode.eq(drop)]
    return out


def gate(tmp: Path, frame: pd.DataFrame, half_ranks="exact", listed=None, gov=None):
    from simd_ingest.core import govscot
    govscot._published.cache_clear()  # the reader caches by path; a build never rewrites a pinned file
    frame.to_csv(tmp / "bands.csv", index=False)
    ed = {"key": "t", "dz_vintage": 2011, "domains": {"income": "i", "housing": "h"},
          "bands": {"file": "bands.csv", "date_code": 2020, "half_ranks": half_ranks}}
    if listed is not None:
        (tmp / "list.csv").write_text("data_zone,shapefile_rank,published_rank\n" + "".join(f"{z},{a},{b}\n" for z, a, b in listed))
        ed["bands"]["rank_disagreements"] = {"housing": str(tmp / "list.csv")}
    report = Report()
    try:
        out = read_published_bands(ed, tmp, report, shapefile_table() if gov is None else gov)
    except Exception:  # report.require() raises once a blocking check has failed
        out = None
    return out, report


def failed(report) -> list:
    return [c.name.removeprefix("govscot.") for c in report.blocking_failures]


def test_the_published_bands_are_copied_beside_the_shapefile_ranks(tmp_path):
    out, report = gate(tmp_path, published(shapefile_table()))
    assert not failed(report)
    assert out["income_domain_decile"].tolist() == [1, 4, 7, 10]
    assert out["housing_domain_rank"].tolist() == [1.0, 2.0, 3.0, 4.0]          # the rank stays the shapefile's


@pytest.mark.parametrize("case,expect", [
    ("missing_zone", "t.bands.overall.zones"),
    ("duplicate", "t.bands.unique"),
    ("unpublished_domain", "t.bands.domains"),
    ("unknown_domain", "t.bands.domain_names_known"),
    ("wrong_date", "t.bands.years"),
    ("undeclared_year", "t.bands.years"),
    ("out_of_range", "t.bands.income.decile.range"),
    ("falls", "t.bands.income.decile.monotone"),
    ("rank_differs", "t.bands.housing.ranks_agree"),
    ("overall_differs", "t.bands.overall.decile_agrees"),
])
def test_the_gate_refuses(tmp_path, case, expect):
    gov = shapefile_table()
    row = dict(FeatureCode="Z1", FeatureName="Z1", FeatureType="2011 Data Zone", DateCode=2020, Measurement="Rank",
               Units="Rank", Value=1.0)
    frame = {
        "missing_zone": lambda: published(gov, drop="Z4"),
        "duplicate": lambda: published(gov, extra=[{**row, "SIMD Domain": "Income"}]),
        "unpublished_domain": lambda: published(gov, extra=[{**row, "SIMD Domain": "Crime"}]),
        "unknown_domain": lambda: published(gov, extra=[{**row, "SIMD Domain": "Wealth"}]),
        "wrong_date": lambda: published(gov, date_code=2019),
        # Valid 2020 rows plus one row of a year no edition declared.
        "undeclared_year": lambda: published(gov, extra=[{**row, "DateCode": 2021, "SIMD Domain": "Income"}]),
        "out_of_range": lambda: published(gov, bands={("income", "Z4", "Decile"): 11}),
        "falls": lambda: published(gov, bands={("income", "Z4", "Decile"): 3}),
        "rank_differs": lambda: published(gov, ranks={("housing", "Z2"): 2.5}),
        "overall_differs": lambda: published(gov, bands={("overall", "Z2", "Decile"): 5}),
    }[case]()
    _, report = gate(tmp_path, frame)
    assert expect in failed(report)


def test_a_split_tie_is_allowed_and_counted(tmp_path):
    # Z2 and Z3 share income rank 2.5; the publisher may place them in adjacent bands.
    out, report = gate(tmp_path, published(shapefile_table(), bands={("income", "Z3", "Decile"): 5}))
    assert not failed(report)
    assert out["income_domain_decile"].tolist() == [1, 4, 5, 10]                 # as published, not evened out
    assert report.observations["govscot.t.bands.income.decile.split_ties"] == 1


def test_a_half_rounded_up_is_allowed_only_where_declared_and_only_up(tmp_path):
    gov = shapefile_table()
    up = published(gov, ranks={("income", "Z2"): 3.0, ("income", "Z3"): 3.0})
    assert not failed(gate(tmp_path, up, half_ranks="rounded_up")[1])
    assert "t.bands.income.ranks_agree" in failed(gate(tmp_path, up, half_ranks="exact")[1])
    down = published(gov, ranks={("income", "Z2"): 2.0, ("income", "Z3"): 2.0})
    assert "t.bands.income.ranks_agree" in failed(gate(tmp_path, down, half_ranks="rounded_up")[1])


def test_the_disagreement_list_must_match_exactly(tmp_path):
    gov = shapefile_table()
    frame = published(gov, ranks={("housing", "Z2"): 2.5})
    out, report = gate(tmp_path, frame, listed=[("Z2", 2.0, 2.5)])
    assert not failed(report)
    assert out["housing_domain_rank_source_status"].fillna("").tolist() == ["", RANK_SOURCES_DISAGREE, "", ""]
    for listed in ([("Z2", 2.0, 3.0)],                                  # other ranks than published
                   [("Z2", 2.0, 2.5), ("Z3", 3.0, 3.0)],                # an extra zone whose ranks agree
                   []):                                                  # a differing zone not listed
        assert "t.bands.housing.rank_disagreements_as_pinned" in failed(gate(tmp_path, frame, listed=listed)[1])


# --- the registry ----------------------------------------------------------------------------------

def test_the_registry_declares_bands_for_every_edition_and_one_disagreement_list():
    registry = load_registry(ROOT / "simd_ingest" / "sources.yaml")
    bands = {e["key"]: e["bands"] for e in registry.govscot_editions}
    assert [b["half_ranks"] for b in bands.values()] == ["rounded_up"] * 4 + ["exact"] * 2
    assert [b["date_code"] for b in bands.values()] == [2004, 2006, 2009, 2012, 2016, 2020]
    assert list(bands["2020v2"]["rank_disagreements"]) == ["housing"]
    assert all("rank_disagreements" not in b for k, b in bands.items() if k != "2020v2")
    # The shared 2004 to 2012 file must hold exactly those four years.
    assert bands["2006"]["file_date_codes"] == [2004, 2006, 2009, 2012] and bands["2016"]["file_date_codes"] == [2016]


def test_the_audit_list_holds_the_628_zones():
    listed = pd.read_csv(AUDIT, comment="#")
    assert len(listed) == 628 and listed.data_zone.is_unique
    assert listed.set_index("data_zone").loc["S01008634"].tolist() == [2093.0, 2092.5]


# --- on the built tables -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built():
    if not (HISTORY.is_file() and MAIN.is_file()):
        pytest.skip("no built tables")
    history = pd.read_parquet(HISTORY)
    if STATUS not in history:
        pytest.skip("the saved tables predate the domain bands")
    return history, pd.read_parquet(MAIN)


def test_published_values_arrive_exactly(built):
    history, _ = built
    z01 = history.drop_duplicates("DataZone2001Code").set_index("DataZone2001Code")
    z11 = history.drop_duplicates("DataZone2011Code").set_index("DataZone2011Code")
    # A tie the publisher split across bands, copied as published.
    assert z01.loc[["S01001951", "S01006050"], "simd2009v2_employment_domain_rank"].tolist() == [1952.0, 1952.0]
    assert z01.loc[["S01001951", "S01006050"], "simd2009v2_employment_domain_decile"].tolist() == [3, 4]
    # The same tie placed differently in 2016 and 2020v2, each as published; ranks agree, so no status.
    pair = z11.loc[["S01008149", "S01012978"]]
    assert pair.simd2016_housing_domain_decile.tolist() == [5, 5] and pair.simd2020v2_housing_domain_decile.tolist() == [4, 4]
    assert pair[STATUS].isna().all()
    assert z11.loc["S01008634", [STATUS, "simd2020v2_housing_domain_rank", "simd2020v2_housing_domain_decile"]].tolist() == \
        [RANK_SOURCES_DISAGREE, 2093.0, 3]
    assert "simd2004_crime_domain_decile" not in history


def test_the_status_is_the_audit_list_within_each_table(built):
    listed = set(pd.read_csv(AUDIT, comment="#").data_zone)
    for table in built:
        represented = set(table.DataZone2011Code)
        flagged = set(table.loc[table[STATUS].notna(), "DataZone2011Code"])
        assert flagged == listed & represented
        assert set(table[STATUS].dropna()) == {RANK_SOURCES_DISAGREE}
    history, main = built
    assert len(listed & set(history.DataZone2011Code)) == 628
    assert len(listed & set(main.DataZone2011Code)) == 627 and "S01011598" not in set(main.DataZone2011Code)


def test_the_bands_are_copied_not_derived(built):
    history, _ = built
    raw = pd.read_csv(ROOT / "manual_data" / "statistics.gov.scot" / "simd_historical_2004_2012.csv")
    pub = raw[(raw.DateCode == 2006) & (raw["SIMD Domain"] == "Employment") & (raw.Measurement == "Decile")]
    pub = pub.set_index("FeatureCode")["Value"].astype(int)
    saved = history.drop_duplicates("DataZone2001Code").set_index("DataZone2001Code")["simd2006_employment_domain_decile"]
    assert (saved == pub.reindex(saved.index)).all()


# --- Python: the flag of the record that answers ---------------------------------------------------

@pytest.fixture(scope="module")
def table(built):
    return lookup.load(str(HISTORY))


def test_python_carries_the_status_of_the_answering_record(table):
    cohort = pd.DataFrame({"pc": ["FK3 0EN", "AB11 5FA", "FK3 0EN"], "on": ["2021-06-01", "2021-06-01", "2021-06-01"]})
    out = lookup.attach(cohort, table, "pc", "on", "2020v2", "housing_domain_decile")
    assert out.simd_source_status.fillna("").tolist() == [RANK_SOURCES_DISAGREE, "", RANK_SOURCES_DISAGREE]
    r = lookup.lookup(table, "FK3 0EN", "2020v2", "housing_domain_rank", on="2021-06-01")
    assert r.source_status == RANK_SOURCES_DISAGREE
    # Another domain, or another edition, carries none.
    assert lookup.lookup(table, "FK3 0EN", "2020v2", "income_domain_decile", on="2021-06-01").source_status is None
    era = lookup.attach_by_era(pd.DataFrame({"pc": ["FK3 0EN"] * 2, "on": ["2010-01-01", "2021-01-01"]}), table, "pc", "on",
                               measure="housing_domain_decile")
    assert era.simd_edition.tolist() == ["2012", "2020v2"]
    assert era.simd_source_status.fillna("").tolist() == ["", RANK_SOURCES_DISAGREE]


def test_split_parts_must_agree_on_value_and_status_through_both_apis(table):
    """EH37 5TF: A and B agree on the housing decile, 7, but only B's zone is flagged."""
    cohort = pd.DataFrame({"pc": ["EH37 5TF"]})
    a = lookup.lookup(table, "EH37 5TF", "2020v2", "housing_domain_decile")
    attached = lookup.attach(cohort, table, "pc", None, "2020v2", "housing_domain_decile")
    assert (a.status, a.value, a.source_status) == ("a_part", 7, None)
    assert attached[["simd_status", "simd_value"]].values.tolist() == [["a_part", 7]] and attached.simd_source_status.isna().all()
    r = lookup.lookup(table, "EH37 5TF", "2020v2", "housing_domain_decile", split="report")
    reported = lookup.attach(cohort, table, "pc", None, "2020v2", "housing_domain_decile", split="report")
    assert (r.status, r.value, r.source_status) == ("split_conflict", None, None)
    assert reported.simd_status.tolist() == ["split_conflict"] and reported.simd_value.isna().all()
    # FK8 3RA's parts agree on the housing decile and neither is flagged: consensus in both.
    agree = pd.DataFrame({"pc": ["FK8 3RA"]})
    assert lookup.lookup(table, "FK8 3RA", "2020v2", "housing_domain_decile", split="report").status == "split_consensus"
    assert lookup.attach(agree, table, "pc", None, "2020v2", "housing_domain_decile", split="report").simd_status.tolist() == ["split_consensus"]


def test_python_answers_an_unpublished_band_as_null_and_refuses_an_unknown_one(table):
    r = lookup.lookup(table, "AB11 5FA", "2004", "crime_domain_decile", on="2003-01-01")
    assert pd.isna(r.value) and "not published" in r.label
    with pytest.raises(ValueError, match="unknown SIMD domain"):
        lookup.lookup(table, "AB11 5FA", "2020v2", "wealth_domain_decile")


# --- SQL: the flag travels with the geography record -------------------------------------------------

def test_sql_takes_the_status_from_the_record_that_supplies_the_geography(built):
    con = duckdb.connect()
    con.execute(f"CREATE TABLE postcode_simd_history AS SELECT * FROM read_parquet('{HISTORY}')")
    link = (ROOT / "docs/sql/spd/link_as_of.sql").read_text()
    walk = (ROOT / "docs/sql/spd/walkthrough_as_of.sql").read_text()
    demo_link = link[link.index("    SELECT 1 AS id,"):link.index("AS analysis_year\n") + len("AS analysis_year\n")]
    demo_walk = walk[walk.index("    SELECT * FROM (VALUES"):walk.index(") AS v(id, postcode, address_date, analysis_year)\n")
                     + len(") AS v(id, postcode, address_date, analysis_year)\n")]
    # FK3 0EN is a large user linked to a small user in a listed zone; AB11 5FA is not listed.
    cohort = "    SELECT * FROM (VALUES (1, 'FK3 0EN', DATE '2021-06-01', CAST(NULL AS INTEGER)), (2, 'AB11 5FA', DATE '2021-06-01', CAST(NULL AS INTEGER))) AS v(id, postcode, address_date, analysis_year)\n"
    cols = "id, postcode_status, data_zone_code, gov_housing_domain_decile, gov_housing_domain_rank_source_status"
    a = con.execute(f"SELECT {cols} FROM ({link.replace(demo_link, cohort).rstrip().rstrip(';')}) ORDER BY id").fetchall()
    b = con.execute(f"SELECT {cols} FROM ({walk.replace(demo_walk, cohort).rstrip().rstrip(';')}) ORDER BY id").fetchall()
    assert a == b
    assert a[0][1] == "linked_small_user" and a[0][4] == RANK_SOURCES_DISAGREE
    assert a[1][4] is None
