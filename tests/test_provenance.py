"""The column provenance site: every column traced, every reference real, the awkward cases right.

docs/plans/Column_Provenance_Site_Plan.md. The lineage map is derived from the registry and the
readers; these tests hold it to the schemas, the registry, the decision log and the build's own
check names, and state the exceptional cases by hand.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from simd_ingest.lineage import TABLES, lineage
from simd_ingest.provenance_site import describe_check, write
from support import ROOT

PACKAGE = ROOT / "simd_ingest"
SCHEMAS = {t: yaml.safe_load((PACKAGE / f).read_text())["fields"] for t, f in TABLES.items()}
MANIFEST = ROOT / "results" / "manifest.json"


@pytest.fixture(scope="module")
def L():
    return lineage()


# --- coverage --------------------------------------------------------------------------------------

def test_every_column_of_each_table_has_a_lineage_record(L):
    for table, fields in SCHEMAS.items():
        assert [c for (t, c) in L if t == table] == [f["name"] for f in fields]
    assert len(L) == 442 + 399


def test_every_column_has_a_description():
    descriptions = yaml.safe_load((PACKAGE / "column_descriptions.yaml").read_text())
    for table, fields in SCHEMAS.items():
        for f in fields:
            nrs = f["source"] in ("directory", "lookup")
            assert (f.get("note") or "").strip() or (nrs and f["name"] in descriptions), (table, f["name"])


def test_every_table_variant_has_a_nonempty_description():
    """Per table, not per name: a history NRS field needs an SPD dictionary entry for a file it is
    in, a main one an SSPL entry, and every other column a schema note."""
    descriptions = yaml.safe_load((PACKAGE / "column_descriptions.yaml").read_text())
    spd = yaml.safe_load((PACKAGE / "spd_schema.yaml").read_text())
    for f in SCHEMAS["history"]:
        if f["source"] == "directory":
            labels = [l for l, role in (("spd_small_user", "small_user"), ("spd_large_user", "large_user")) if f["name"] in spd[role]]
            assert any(descriptions[f["name"]].get(l, {}).get("text") for l in labels), f["name"]
        else:
            assert (f.get("note") or "").strip(), f["name"]
    for f in SCHEMAS["main"]:
        if f["source"] == "lookup":
            assert descriptions[f["name"]].get("sspl", {}).get("text"), f["name"]
        else:
            assert (f.get("note") or "").strip(), f["name"]


def test_unreviewed_descriptions_are_labelled_on_the_pages(tmp_path):
    write(tmp_path)
    descriptions = yaml.safe_load((PACKAGE / "column_descriptions.yaml").read_text())
    unreviewed = [n for n, e in descriptions.items() if not e.get("reviewed")]
    home = (tmp_path / "index.md").read_text()
    assert f"{len(unreviewed)} of {len(descriptions)} not yet reviewed" in home
    for name in unreviewed:
        page = tmp_path / "columns" / f"{name}.md"
        if page.is_file():
            assert "not yet reviewed" in page.read_text(), name


def test_each_nrs_description_names_its_pinned_dictionary():
    from simd_ingest.core.sources import load_registry
    pinned = {f.path: f.sha256 for f in load_registry(PACKAGE / "sources.yaml").files}
    for name, entry in yaml.safe_load((PACKAGE / "column_descriptions.yaml").read_text()).items():
        for label in ("spd_small_user", "spd_large_user", "sspl"):
            if label in entry:
                assert pinned[entry[label]["source"]["file"]] == entry[label]["source"]["sha256"], name


# --- references are real -------------------------------------------------------------------------

def test_every_input_reference_exists(L):
    from simd_ingest.core.sources import load_registry
    pinned = {f.path for f in load_registry(PACKAGE / "sources.yaml").files}
    for key, r in L.items():
        assert r["inputs"], key
        for i in r["inputs"]:
            if i["kind"] == "pinned_file":
                assert i["path"] in pinned, (key, i["path"])
            elif i["kind"] == "repository_file":
                assert (ROOT / i["path"]).is_file(), (key, i["path"])
            elif i["kind"] == "derived_column":
                assert i["field"] in {f["name"] for f in SCHEMAS[key[0]]}, (key, i["field"])


def test_every_decision_exists(L):
    ids = {d["id"] for d in yaml.safe_load((PACKAGE / "decisions.yaml").read_text())["decisions"]}
    assert {d for r in L.values() for d in r["decisions"]} <= ids
    assert all(r["decisions"] for r in L.values())


def test_every_cited_check_has_a_definition(L):
    assert all(describe_check(c) for r in L.values() for c in r["checks"])


def test_every_cited_check_is_one_the_build_emits(L):
    """Read from the build's manifest.json["checks"], every emitted check; never from
    BUILD_REPORT.md, which only summarises them."""
    if not MANIFEST.is_file():
        pytest.skip("no build manifest")
    emitted = {c["name"] for c in json.loads(MANIFEST.read_text())["checks"]}
    cited = {c for r in L.values() for c in r["checks"]}
    if not any(c.startswith("weighted.") for c in emitted):
        pytest.skip("the saved build predates the lineage's columns")
    assert sorted(cited - emitted) == []


# --- the exceptional cases, by hand --------------------------------------------------------------

def field(table, name):
    return next(f for f in SCHEMAS[table] if f["name"] == name)


def test_census_counts_differ_between_the_tables():
    assert field("history", "CensusPopulationCount2022")["nullable"] is True
    assert field("main", "CensusPopulationCount2022")["nullable"] is False


def test_user_type_comes_from_different_places(L):
    history, main = L[("history", "spd_user_type")], L[("main", "spd_user_type")]
    assert {i["path"].rsplit("/", 1)[-1] for i in history["inputs"]} == {"SmallUser.csv", "LargeUser.csv"}
    assert [i["field"] for i in main["inputs"]] == ["PostcodeType"]


def test_a_field_only_one_spd_file_has_is_conditional(L):
    inputs = L[("history", "LinkedSmallUserPostcode")]["inputs"]
    assert len(inputs) == 1 and inputs[0]["path"].endswith("LargeUser.csv")
    assert "only the large-user file has it" in inputs[0]["condition"]


def test_phs_2004_decile_is_inverted(L):
    r = L[("history", "simd2004_pw_scotland_decile")]
    assert [i["field"] for i in r["inputs"]] == ["SIMD2004CountryDecile"] and r["inputs"][0]["path"] == "PHS/simd2004_02042020.csv"
    assert r["transformation"]["kind"] == "inverted" and "invert-2004-2006-phs-bands" in r["decisions"]
    assert L[("history", "simd2020v2_pw_scotland_decile")]["transformation"]["kind"] == "copied"


def test_the_housing_status_reads_the_committed_list(L):
    r = L[("main", "simd2020v2_housing_domain_rank_source_status")]
    kinds = [i["kind"] for i in r["inputs"]]
    assert kinds == ["repository_file", "pinned_file", "pinned_file"]
    assert r["inputs"][0]["path"] == "simd_ingest/sgs_2020_housing_rank_disagreements.csv"


def test_computed_bands_are_cut_over_every_zone_not_the_rows(L):
    r = L[("history", "simd2020v2_income_domain_pw_scotland_decile")]
    assert r["transformation"]["kind"] == "computed"
    assert "every data zone" in r["scope"] and "never the table's rows" in r["scope"]
    assert "weighted.2020v2.reproduces_phs_scotland_decile" in r["checks"]


def test_only_the_2022_rurality_is_compared_directly_with_nrs(L):
    r2022, r2016 = L[("history", "urbanrural2022_6fold")], L[("history", "urbanrural2016_6fold")]
    assert "rurality.agreement.current_small_user" in r2022["checks"]
    assert not any(c.startswith("rurality.agreement") for c in r2016["checks"])
    assert "no direct comparison" in r2016["transformation"]["rule"]


def test_published_bands_carry_their_exact_source_row(L):
    i = L[("history", "simd2009v2_employment_domain_decile")]["inputs"][0]
    assert i["condition"] == "SIMD Domain = Employment, Measurement = Decile, DateCode = 2009"
    assert i["path"] == "statistics.gov.scot/simd_historical_2004_2012.csv"


# --- the generated site ---------------------------------------------------------------------------

def test_the_site_has_a_page_per_column_and_every_link_resolves(tmp_path):
    counts = write(tmp_path)
    names = {f["name"] for fields in SCHEMAS.values() for f in fields}
    assert counts["columns"] == len(names) == 444
    pages = list(tmp_path.rglob("*.md"))
    column_pages = {p.stem for p in (tmp_path / "columns").glob("*.md")
                    if p.stem != "index" and not p.stem.startswith(("edition-", "category-"))}
    assert column_pages == names
    for page in pages:
        for target in re.findall(r"\]\(([^)#]+\.md)\)", page.read_text()):
            assert (page.parent / target).resolve().is_file(), (page.name, target)


def test_a_page_never_claims_a_check_passed(tmp_path):
    write(tmp_path)
    text = (tmp_path / "columns" / "simd2020v2_income_domain_decile.md").read_text()
    assert "manifest.json[\"checks\"]" in text
    assert not re.search(r"\b(passed|pass)\b", text.split("**How it is checked**")[1].split("**Why")[0].split(")", 1)[1])


def test_housing_bands_carry_the_declared_disagreements(L):
    """The band pages, not only the status page, must say that 628 zones are admitted although
    their two ranks differ, and cite the list and its check."""
    for band in ("quintile", "decile", "vigintile"):
        r = L[("history", f"simd2020v2_housing_domain_{band}")]
        assert any(i["path"] == "simd_ingest/sgs_2020_housing_rank_disagreements.csv" for i in r["inputs"])
        assert "govscot.2020v2.bands.housing.rank_disagreements_as_pinned" in r["checks"]
        assert "disagreement list" in r["transformation"]["rule"]
    other = L[("history", "simd2020v2_income_domain_decile")]
    assert not any(i["kind"] == "repository_file" for i in other["inputs"])


def test_rurality_names_the_po_box_rule_and_its_inputs(L):
    r = L[("history", "urbanrural2016_6fold")]
    fields = [i["field"] for i in r["inputs"]]
    assert "LinkedSmallUserPostcode" in fields and "spd_user_type" in fields
    assert "attach_rurality" in r["transformation"]["code"] and "PO box" in r["transformation"]["rule"]


def test_pc_base_depends_on_the_split_indicator(L):
    assert "SplitIndicator" in [i["field"] for i in L[("history", "pc_base")]["inputs"]]


def test_joins_name_both_keys(L):
    assert L[("main", "simd2016_pw_scotland_decile")]["inputs"][0]["join"] == "DataZone2011Code = DataZone"
    assert L[("history", "simd2004_income_domain_rank")]["inputs"][0]["join"] == "DataZone2001Code = datazone"
    assert L[("history", "simd2009v2_employment_domain_decile")]["inputs"][0]["join"] == "DataZone2001Code = FeatureCode"


def test_sources_are_mapped_per_pinned_file_and_columns_can_be_filtered(tmp_path):
    from simd_ingest.core.sources import load_registry
    counts = write(tmp_path)
    files = load_registry(PACKAGE / "sources.yaml").files
    assert counts["sources"] == len(files) == 59
    assert len([p for p in (tmp_path / "sources").glob("*.md") if p.stem != "index"]) == 59
    assert (tmp_path / "columns" / "edition-2020v2.md").is_file() and (tmp_path / "columns" / "category-computed.md").is_file()
    decile = (tmp_path / "sources" / "statistics.gov.scot-simd_2020.csv.md").read_text()
    assert "simd2020v2_housing_domain_decile" in decile
