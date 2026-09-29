"""The Scottish Government SIMD domain ranks: copied exactly as published, halves included.

Domain ranks are not whole numbers: many end in .5, and ties are only mostly averaged, so the
tests below pin exactness through every layer, the reader's refusals, availability by edition
(2004 has no crime domain), and an independent second publication of the 2020v2 ranks.
"""

from __future__ import annotations

import gzip
import io
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from fixture_project import dbf_bytes
from simd_ingest import lookup
from simd_ingest.core import output, text_output
from simd_ingest.core.checks import Report
from simd_ingest.core.govscot import read_gov_edition
from simd_ingest.core.sources import DOMAINS, declared_domains, load_registry
from support import ROOT, source_root

HISTORY = ROOT / "results" / "postcode_simd_history.parquet"
REGISTRY = load_registry(ROOT / "simd_ingest" / "sources.yaml")


# --- the registry and the reader, on small synthetic files ------------------------------------

def gov_edition(tmp: Path, ranks: list, domains=("income",), rows=2) -> tuple:
    zones = [f"S0100000{i}" for i in range(1, rows + 1)]
    table = [dict(datazone=z, rank=i, quintile=1, decile=1, vigintile=1, population=100,
                  **{f"dom{d[:5]}": ranks[i - 1] for d in domains})
             for i, z in enumerate(zones, 1)]
    (tmp / "gov.dbf").write_bytes(dbf_bytes(table))
    ed = {"key": "2020v2", "file": "gov.dbf", "dz_vintage": 2011, "rows": rows,
          "columns": {k: k for k in ("datazone", "rank", "quintile", "decile", "vigintile", "population")},
          "domains": {d: f"dom{d[:5]}" for d in domains}}
    return ed, tmp


def test_the_registry_declares_six_domains_for_2004_and_seven_after():
    counts = {e["key"]: declared_domains(e) for e in REGISTRY.govscot_editions}
    assert counts["2004"] == [d for d in DOMAINS if d != "crime"]
    assert all(counts[k] == list(DOMAINS) for k in ("2006", "2009v2", "2012", "2016", "2020v2"))
    assert REGISTRY.govscot_editions[-1]["domains"]["income"] == "incrankv2"


def test_an_unknown_domain_is_refused(tmp_path):
    import yaml
    raw = yaml.safe_load((ROOT / "simd_ingest" / "sources.yaml").read_text())
    raw["govscot_editions"][0]["domains"]["wealth"] = "wealthrank"
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="unknown SIMD domain"):
        load_registry(path)


def test_a_half_rank_is_read_exactly(tmp_path):
    ed, root = gov_edition(tmp_path, [1.5, 1.5])
    report = Report()
    out = read_gov_edition(ed, root, report)
    assert not report.blocking_failures
    assert out["income_domain_rank"].tolist() == [1.5, 1.5]
    assert report.observations["govscot.2020v2.income_domain.tied_values"] == 1


@pytest.mark.parametrize("ranks,check", [([1.25, 2.0], "half_units"), ([0.5, 2.0], "range"), ([1.0, 3.0], "range")])
def test_a_rank_that_is_not_a_published_shape_is_refused(tmp_path, ranks, check):
    ed, root = gov_edition(tmp_path, ranks)
    report = Report()
    read_gov_edition(ed, root, report)
    assert f"govscot.2020v2.income_domain.{check}" in [c.name for c in report.blocking_failures]


def test_a_declared_domain_missing_from_the_file_is_refused(tmp_path):
    ed, root = gov_edition(tmp_path, [1.0, 2.0])
    ed["domains"]["crime"] = "crimerank"                     # as if 2004 declared crime
    report = Report()
    read_gov_edition(ed, root, report)
    assert "govscot.2020v2.crime_domain.present" in [c.name for c in report.blocking_failures]


# --- a half survives every layer ---------------------------------------------------------------

def rank_schema() -> dict:
    return {"fields": [{"name": "k", "type": "string", "nullable": False, "source": "t"},
                       {"name": "simd2020v2_income_domain_rank", "type": "rank", "nullable": False, "source": "govscot"}],
            "key": ["k"], "version": "t", "table": "t", "index_source": "spd", "allocation": "x", "sha256": "0" * 64}


def test_a_half_survives_parquet_csv_and_the_digest(tmp_path):
    frame = pd.DataFrame({"k": ["a", "b", "c"], "simd2020v2_income_domain_rank": [5955.5, 5955.0, 6969.0]})
    schema = rank_schema()
    path = tmp_path / "t.parquet"
    output.write_table(frame, schema, path, {})
    back = pq.read_table(path).to_pandas()
    assert back["simd2020v2_income_domain_rank"].tolist() == [5955.5, 5955.0, 6969.0]
    contract = text_output.load_contract(ROOT / "simd_ingest" / "export_contract.yaml")
    rendered = text_output.render(back, schema, ["k", "simd2020v2_income_domain_rank"], contract)
    assert rendered["simd2020v2_income_domain_rank"].tolist() == ["5955.5", "5955.0", "6969.0"]
    # A half and its whole neighbour are different rows to the digest.
    totals = [text_output.row_digest(rendered.iloc[[i]], contract)["total"] for i in range(3)]
    assert len(set(totals)) == 3


def test_the_sql_server_scripts_keep_the_half():
    importer = (ROOT / "docs/sql/import_csv.sql").read_text()
    check = (ROOT / "docs/sql/check_loaded_digest.sql").read_text()
    assert "[simd2020v2_income_domain_rank] decimal(6,1) NOT NULL" in importer
    assert "CONVERT(decimal(6,1), NULLIF([simd2020v2_income_domain_rank], ''))" in importer
    assert "CONVERT(varchar(12), CONVERT(decimal(6,1), [simd2020v2_income_domain_rank]))" in check
    assert "simd2004_crime_domain_rank" not in importer and "simd2004_crime_domain_rank" not in check


def test_no_query_names_a_domain_an_edition_did_not_publish():
    for path in (ROOT / "docs/sql").glob("*/*.sql"):
        assert "simd2004_crime_domain_rank" not in path.read_text(), path.name


# --- on the built table -------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built():
    if not HISTORY.is_file():
        pytest.skip("no built history table")
    table = pq.ParquetFile(HISTORY).read().to_pandas(date_as_object=False)
    if "simd2020v2_income_domain_rank" not in table:
        pytest.skip("the saved table predates the domain ranks")
    return table


def test_published_halves_and_unaveraged_ties_arrive_exactly(built):
    row = built[built.DataZone2011Code == "S01006523"].iloc[0]
    assert row.simd2020v2_income_domain_rank == 5955.5
    # Two ties the publisher did not average: copied as published, never recalculated.
    assert (built.simd2009v2_income_domain_rank == 5521.0).any() and not (built.simd2009v2_income_domain_rank == 5521.5).any()
    assert (built.simd2020v2_income_domain_rank == 6969.0).any() and not (built.simd2020v2_income_domain_rank == 6970.5).any()
    assert "simd2004_crime_domain_rank" not in built.columns


def test_every_2020v2_domain_rank_equals_the_second_publication(built):
    """The Scottish Government's SIMD 2020v2 ranks workbook, a retired pin kept on disk, is the
    only other publication of the domain ranks. Where it is present, every saved rank equals it."""
    workbook = ROOT / "manual_data" / "gov.scot" / "SIMD+2020v2+-+ranks.xlsx"
    if not workbook.is_file():
        pytest.skip("the retired 2020v2 ranks workbook is not on disk")
    pytest.importorskip("openpyxl", reason="reading the workbook needs openpyxl, which the image does not carry")
    w = pd.read_excel(workbook, sheet_name="SIMD 2020v2 ranks").set_index("Data_Zone")
    columns = {"income": "SIMD2020v2_Income_Domain_Rank", "employment": "SIMD2020_Employment_Domain_Rank",
               "health": "SIMD2020_Health_Domain_Rank", "education": "SIMD2020_Education_Domain_Rank",
               "access": "SIMD2020_Access_Domain_Rank", "crime": "SIMD2020_Crime_Domain_Rank",
               "housing": "SIMD2020_Housing_Domain_Rank"}
    saved = built.drop_duplicates("DataZone2011Code").set_index("DataZone2011Code")
    for domain, column in columns.items():
        mine = saved[f"simd2020v2_{domain}_domain_rank"]
        theirs = pd.to_numeric(w.loc[mine.index, column]).astype(float)
        assert (mine == theirs).all(), domain


def test_python_keeps_halves_and_answers_2004_crime_as_not_published(built):
    table = lookup.load(str(HISTORY))
    cohort = pd.DataFrame({"pc": ["AB11 5FA", "AB11 5FA"], "on": ["2000-06-01", "2021-06-10"]})
    out = lookup.attach_by_era(cohort, table, "pc", "on", measure="crime_domain_rank")
    assert out.simd_edition.tolist() == ["2004", "2020v2"]
    assert pd.isna(out.simd_value.iloc[0]) and out.simd_value.iloc[1] == 544.0
    assert "not published" in out.simd_label.iloc[0] and "not published" not in out.simd_label.iloc[1]
    income = lookup.attach_by_era(cohort.iloc[[1]], table, "pc", "on", measure="income_domain_rank")
    assert str(income.simd_value.dtype) == "Float64" and income.simd_value.iloc[0] == 3313.5
