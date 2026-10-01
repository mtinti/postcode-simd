"""The computed population-weighted domain bands (docs/plans/Weighted_Domain_Bands_Plan.md).

Not published by anyone, so the tests pin the rule itself by hand, the check that the rule
reproduces PHS's published overall bands, and that the bands are cut from every data zone of
the source, once, never from a postcode table.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from simd_ingest import lookup
from simd_ingest.core.checks import Report
from simd_ingest.core.govscot import read_gov_edition
from simd_ingest.core.join import join_edition
from simd_ingest.core.phs import canonicalise_phs, read_phs_source
from simd_ingest.core.sources import load_registry
from simd_ingest.core.weighted import gate_against_phs, population_bands
from support import ROOT

REGISTRY = load_registry(ROOT / "simd_ingest" / "sources.yaml")
SOURCES = ROOT / "manual_data"
HISTORY = ROOT / "results" / "postcode_simd_history.parquet"
MAIN = ROOT / "results" / "postcode_simd.parquet"


# --- the rule, by hand ---------------------------------------------------------------------------

def test_the_cut_points_fall_where_the_arithmetic_says():
    # Ten zones of 10 people: midpoints 5, 15, ..., 95 of 100, so deciles 1 to 10 and quintiles in pairs.
    ranks, pops = range(1, 11), [10] * 10
    assert population_bands(ranks, pops, 10).tolist() == list(range(1, 11))
    assert population_bands(ranks, pops, 5).tolist() == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_equal_ranks_are_one_block_and_share_a_band():
    # Ranks 2.5 and 2.5 form one block of 40 people: cumulative 50, midpoint 30 of 100: decile 3.
    out = population_bands([1, 2.5, 2.5, 4], [10, 20, 20, 50], 10)
    assert out.tolist() == [1, 3, 3, 8]
    assert out[1] == out[2]


def test_input_order_does_not_matter():
    rng = np.random.default_rng(3)
    ranks, pops = rng.permutation(200) + 1.0, rng.integers(0, 900, 200)
    order = rng.permutation(200)
    assert (population_bands(ranks, pops, 10)[order] == population_bands(ranks[order], pops[order], 10)).all()


def test_zero_population_zones():
    # A zero-population zone takes the band of its midpoint; one ranked first has midpoint 0 and
    # goes to band 1, never band 0.
    assert population_bands([1, 2, 3], [0, 50, 50], 5).tolist() == [1, 2, 4]
    # Midpoints 20, 40, 55, 85 of 100: a midpoint exactly on a cut stays in the lower band, and the
    # zero-population zone, with midpoint 40, sits on the cut between bands 2 and 3.
    assert population_bands([1, 2, 3, 4], [40, 0, 30, 30], 5).tolist() == [1, 2, 3, 5]


@pytest.mark.parametrize("pops", [[0, 0, 0], [10, -1, 5]])
def test_nothing_to_weight_by_is_refused(pops):
    with pytest.raises(ValueError):
        population_bands([1, 2, 3], pops, 5)


# --- the check against PHS -------------------------------------------------------------------------

def phs_and_gov(key: str) -> tuple:
    gov_ed = next(e for e in REGISTRY.govscot_editions if e["key"] == key)
    phs_ed = next(e for e in REGISTRY.phs_editions if e["key"] == key)
    return (canonicalise_phs(phs_ed, read_phs_source(phs_ed, SOURCES, Report()), Report()),
            read_gov_edition(gov_ed, SOURCES, Report()))


@pytest.fixture(scope="module")
def editions():
    if not (SOURCES / "PHS").is_dir():
        pytest.skip("no pinned sources")
    return {e["key"]: phs_and_gov(e["key"]) for e in REGISTRY.govscot_editions}


def test_the_rule_reproduces_phs_scotland_bands_in_every_edition(editions):
    for key, (phs, gov) in editions.items():
        report = Report()
        gate_against_phs(phs, gov, key, report)
        assert not report.blocking_failures, key


def test_the_check_stops_on_a_single_disagreeing_zone(editions):
    phs, gov = editions["2016"]
    wrong = phs.copy()
    wrong.loc[wrong.index[0], "pw_scotland_decile"] = (wrong.loc[wrong.index[0], "pw_scotland_decile"] % 10) + 1
    report = Report()
    gate_against_phs(wrong, gov, "2016", report)
    assert [c.name for c in report.blocking_failures] == ["weighted.2016.reproduces_phs_scotland_decile"]


# --- cut from the source's complete zones, never from a postcode table ----------------------------

def test_shares_on_the_complete_source_zones_are_near_equal(editions):
    for key, (_, gov) in editions.items():
        total = gov["population"].sum()
        for column in [c for c in gov if c.endswith(("_pw_scotland_quintile", "_pw_scotland_decile"))]:
            k = 5 if column.endswith("quintile") else 10
            shares = gov.groupby(column)["population"].sum() / total * 100
            assert (shares - 100 / k).abs().max() < 0.05, (key, column)


def test_one_zone_by_hand(editions):
    _, gov = editions["2020v2"]
    g = gov.sort_values("income_domain_rank")
    zone = g.iloc[1000]
    block = g[g.income_domain_rank == zone.income_domain_rank]
    before = g[g.income_domain_rank < zone.income_domain_rank].population.sum()
    midpoint = before + block.population.sum() / 2
    assert zone.income_domain_pw_scotland_decile == int(np.ceil(midpoint * 10 / gov.population.sum()))


def test_postcode_rows_cannot_move_a_band(editions):
    """Duplicate some postcodes, drop every postcode of some zones: each joined band is still the
    source zone's, because the band was cut before any postcode was seen."""
    _, gov = editions["2020v2"]
    ed = next(e for e in REGISTRY.govscot_editions if e["key"] == "2020v2")
    zones = gov["dz_code"].tolist()
    kept = zones[: len(zones) // 2]                                   # half the zones have no postcode
    index = pd.DataFrame({"DataZone2011Code": kept * 3 + kept[:7]})   # and the rest repeat unevenly
    joined = join_edition(index, gov, ed, "gov", REGISTRY, Report())
    expected = gov.set_index("dz_code")["income_domain_pw_scotland_decile"]
    assert (joined["simd2020v2_income_domain_pw_scotland_decile"].to_numpy()
            == expected.reindex(joined["DataZone2011Code"]).to_numpy()).all()


def test_cutting_from_a_postcode_table_would_be_wrong(editions):
    """Why the source: the main table lacks four 2011 zones (801 people in 2017), and cutting from
    its zones alone would change five 2020v2 income deciles."""
    if not MAIN.is_file():
        pytest.skip("no built main table")
    _, gov = editions["2020v2"]
    present = set(pd.read_parquet(MAIN, columns=["DataZone2011Code"]).DataZone2011Code)
    missing = gov[~gov.dz_code.isin(present)]
    assert sorted(missing.dz_code) == ["S01010206", "S01010226", "S01010227", "S01011598"]
    assert int(missing.population.sum()) == 801
    sub = gov[gov.dz_code.isin(present)]
    from_table = population_bands(sub.income_domain_rank, sub.population, 10)
    assert int((from_table != sub.income_domain_pw_scotland_decile.to_numpy()).sum()) == 5


# --- on the built tables and in Python -----------------------------------------------------------

@pytest.fixture(scope="module")
def table():
    if not HISTORY.is_file():
        pytest.skip("no built history table")
    t = lookup.load(str(HISTORY))
    if "simd2020v2_income_domain_pw_scotland_decile" not in t:
        pytest.skip("the saved table predates the computed bands")
    return t


def test_both_tables_carry_the_source_bands_and_population(table, editions):
    _, gov = editions["2016"]
    source = gov.set_index("dz_code")
    for t in (table, pd.read_parquet(MAIN)):
        z = t.drop_duplicates("DataZone2011Code").set_index("DataZone2011Code")
        assert (z["simd2016_health_domain_pw_scotland_quintile"] == source.loc[z.index, "health_domain_pw_scotland_quintile"]).all()
        assert (z["simd2016_population"] == source.loc[z.index, "population"]).all()
    assert "simd2004_crime_domain_pw_scotland_decile" not in table


def test_python_labels_them_computed_and_answers_2004_crime_as_unpublished(table):
    r = lookup.lookup(table, "AB11 5FA", "2020v2", "income_domain_pw_scotland_decile", on="2021-06-01")
    assert r.status in ("unique", "a_part") and 1 <= r.value <= 10
    assert "computed population-weighted" in r.label and "not published" in r.label
    crime = lookup.lookup(table, "AB11 5FA", "2004", "crime_domain_pw_scotland_decile", on="2003-01-01")
    assert pd.isna(crime.value) and "not published for this edition" in crime.label
    # The housing source status describes the rank these bands are cut from.
    flagged = lookup.lookup(table, "FK3 0EN", "2020v2", "housing_domain_pw_scotland_decile", on="2021-06-01")
    assert flagged.source_status == "rank_sources_disagree"
