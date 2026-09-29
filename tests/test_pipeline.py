"""The CLI must support a postcode refresh and a later edition using configuration only."""

import json
from unittest.mock import patch

import pandas as pd
import pytest
import yaml

from fixture_project import project
from simd_ingest.cli import main
from simd_ingest.core.changes import compare_snapshot
from simd_ingest.core.sources import load_registry, sha256


def manifest(tmp):
    return json.loads((tmp / "results/manifest.json").read_text())


def repin(tmp, filename):
    path = tmp / "sources.yaml"
    registry = yaml.safe_load(path.read_text())
    for obj in registry["remote_objects"]:
        if obj["files"][0]["path"] == filename:
            obj["sha256"] = obj["files"][0]["sha256"] = sha256(tmp / "sources" / filename)
    path.write_text(yaml.safe_dump(registry, sort_keys=False))


def test_postcode_refresh_replaces_snapshot_and_reports_changes(tmp_path):
    cfg = project(tmp_path)
    assert main(["build", "--config", str(cfg)]) == 0
    first = manifest(tmp_path)
    assert {name: c["status"] for name, c in first["observations"]["snapshot_changes"].items()} == {"history": "unavailable", "main": "unavailable"}
    cfg = project(tmp_path, "test-2")
    assert main(["build", "--config", str(cfg)]) == 0
    second = manifest(tmp_path)
    changes = second["observations"]["snapshot_changes"]["history"]
    assert (changes["added_records"], changes["removed_records"], changes["changed_records"]) == (3, 1, 2)
    assert changes["newly_deleted_records"] == 1
    assert changes["previous_release"] == "test-1"
    assert "spd_release" not in changes["changed_fields"]
    assert second["observations"]["spd.small_user"]["split_records"] == 2
    saved = pd.read_parquet(tmp_path / "results/postcode_simd_history.parquet").set_index("pc_norm")
    assert len(saved) == 6 and "AB101AC" not in saved.index
    assert saved.loc["AB101AA", "simd2020v2_rank"] == 2
    assert saved.loc["AB101AFA", "pc_base"] == "AB101AF"
    assert saved.loc["AB101AFB", "simd2004_pw_scotland_quintile"] == 5
    assert not saved.loc["AB101AB", "is_current"]
    # The main table: whole postcodes, one life each, the lookup's own zones and release.
    changes = second["observations"]["snapshot_changes"]["main"]
    assert (changes["added_records"], changes["removed_records"], changes["changed_records"]) == (2, 1, 3)
    assert changes["newly_deleted_records"] == 1 and changes["previous_release"] == "test-1-lookup"
    assert "sspl_release" not in changes["changed_fields"]
    latest = pd.read_parquet(tmp_path / "results/postcode_simd.parquet").set_index("pc_norm")
    assert len(latest) == 5 and "AB101AC" not in latest.index and "pc_base" not in latest.columns
    assert latest.loc["AB101AF", "SplitIndicator"] == "Y" and latest.loc["AB101AF", "simd2020v2_rank"] == 1
    assert latest.loc["AB101AD", "LinkedSmallUserPostcode"] == "AB10 1AFA"
    assert latest["sspl_release"].eq("test-2-lookup").all()
    agreement = second["observations"]["table_agreement"]
    assert agreement["shared"] == 5 and agreement["only_in_history"] == 0
    narrative = (tmp_path / "results/BUILD_REPORT.md").read_text()
    assert "not a causal decomposition" in narrative
    assert "before consumer SQL follows any large-user link" in narrative
    assert second["tables"]["main"]["key"] == ["pc_norm"] and second["tables"]["history"]["key"] == ["pc_norm", "introduced_on"]
    runs = sorted((tmp_path / "results/runs").iterdir())
    assert len(runs) == 2
    assert json.loads((runs[0] / "manifest.json").read_text())["tables"] == first["tables"]
    for run in runs:
        record = json.loads((run / "run.json").read_text())
        assert record["status"] == "published"
        assert record["code_sha256"]["pipeline.py"]
        assert "dagster" not in record["dependencies"]
        assert (run / "source_manifest.yaml").is_file()
    assert main(["audit", "--config", str(cfg)]) == 0
    # Same release rerun produces identical data and file bytes, but a fresh run record.
    assert main(["build", "--config", str(cfg)]) == 0
    third = manifest(tmp_path)
    for name in ("main", "history"):
        assert third["tables"][name]["sha256"] == second["tables"][name]["sha256"]
        assert third["observations"]["snapshot_changes"][name]["changed_records"] == 0


def test_new_simd_edition_and_new_vintage_need_no_pipeline_code_change(tmp_path):
    cfg = project(tmp_path)
    assert main(["build", "--config", str(cfg)]) == 0
    files = ["results/postcode_simd_history.parquet", "results/postcode_simd.parquet"]
    before = [pd.read_parquet(tmp_path / f) for f in files]
    cfg = project(tmp_path, extra_edition=True)
    assert main(["build", "--config", str(cfg)]) == 0
    after = [pd.read_parquet(tmp_path / f) for f in files]
    for old, new in zip(before, after):
        pd.testing.assert_frame_equal(old, new[old.columns])
        assert len(new.columns) == len(old.columns) + 17
        assert new["phs_dz2022_hb"].tolist() == ["HB"] * 4
    assert after[0]["simdfuture_rank"].tolist() == [1, 2, 1, 2]
    assert after[0]["simdfuture_pw_scotland_quintile"].tolist() == [1, 5, 1, 5]
    assert after[1]["simdfuture_rank"].tolist() == [1, 2, 2, 2]
    assert main(["audit", "--config", str(cfg)]) == 0


@pytest.mark.parametrize("fault", ["hash", "published_count", "schema", "unmatched_zone", "shared_geography",
                                   "lookup_count", "lookup_suffix", "lookup_duplicate", "lookup_blank_zone",
                                   "lookup_bad_link", "lookup_unmatched_zone"])
def test_bad_refresh_keeps_previous_publication_and_retains_failure(tmp_path, fault):
    cfg = project(tmp_path)
    assert main(["build", "--config", str(cfg)]) == 0
    previous = manifest(tmp_path)
    cfg = project(tmp_path, "test-2")
    if fault in ("published_count", "lookup_count"):
        path = tmp_path / "sources.yaml"
        raw = yaml.safe_load(path.read_text())
        if fault == "published_count":
            raw["spd_files"][0]["rows"] += 1
            raw["spd_published_totals"]["all"] += 1
            raw["spd_published_totals"]["deleted"] += 1
        else:
            raw["sspl_file"]["rows"] += 1
            raw["sspl_file"]["small_user"] += 1
        path.write_text(yaml.safe_dump(raw))
    else:
        filename = {"shared_geography": "phs_2006.csv"}.get(fault, "sspl.csv" if fault.startswith("lookup_") else "small_user.csv")
        path = tmp_path / "sources" / filename
        data = pd.read_csv(path, dtype=str, keep_default_na=False)
        if fault == "schema":
            data["unexpected"] = "x"
        elif fault in ("unmatched_zone", "lookup_unmatched_zone"):
            data.loc[0, "DataZone2001Code"] = "UNKNOWN"
        elif fault == "shared_geography":
            data.loc[0, "HB"] = "DIFFERENT"
        elif fault == "lookup_suffix":
            data.loc[0, "Postcode"] = "AB10 1AAA"
        elif fault == "lookup_duplicate":
            data.loc[1, "Postcode"] = data.loc[0, "Postcode"]
        elif fault == "lookup_blank_zone":
            data.loc[0, "DataZone2011Code"] = ""
        elif fault == "lookup_bad_link":
            data.loc[data["PostcodeType"] == "L", "LinkedSmallUserPostcode"] = "UNKNOWN"
        else:
            data.loc[0, "Postcode"] = "AB10 1AZ"
        data.to_csv(path, index=False)
        if fault != "hash":
            repin(tmp_path, filename)
    assert main(["build", "--config", str(cfg)]) == 1
    assert manifest(tmp_path) == previous
    for name, file in (("history", "postcode_simd_history.parquet"), ("main", "postcode_simd.parquet")):
        assert sha256(tmp_path / "results" / file) == previous["tables"][name]["sha256"]
    run = sorted((tmp_path / "results/runs").iterdir())[-1]
    record = json.loads((run / "run.json").read_text())
    assert record["status"] == "failed" and record["error"]
    assert not list((tmp_path / "results").glob(".build-*"))


def test_audit_never_fetches_even_with_download_mode(tmp_path):
    cfg = project(tmp_path)
    assert main(["build", "--config", str(cfg)]) == 0
    before = {p: sha256(p) for p in (tmp_path / "results").rglob("*") if p.is_file()}
    with patch("simd_ingest.pipeline.ensure_sources", side_effect=AssertionError("audit downloaded")):
        assert main(["audit", "--config", str(cfg), "--source-mode", "download"]) == 0
        (tmp_path / "sources/small_user.csv").unlink()
        assert main(["audit", "--config", str(cfg), "--source-mode", "download"]) == 1
    assert before == {p: sha256(p) for p in (tmp_path / "results").rglob("*") if p.is_file()}


def test_untrusted_previous_snapshot_is_not_used_as_comparison(tmp_path):
    cfg = project(tmp_path)
    assert main(["build", "--config", str(cfg)]) == 0
    path = tmp_path / "results/postcode_simd.parquet"
    table = pd.read_parquet(path)
    path.write_bytes(b"broken previous snapshot")
    changes = compare_snapshot(table, path, tmp_path / "results/manifest.json", "main", ["pc_norm"])
    assert changes["status"] == "unavailable"
    assert "hash" in changes["reason"]
    assert main(["build", "--config", str(cfg)]) == 0
    assert manifest(tmp_path)["observations"]["snapshot_changes"]["main"]["status"] == "unavailable"
    assert manifest(tmp_path)["observations"]["snapshot_changes"]["history"]["status"] == "compared"


def test_invalid_config_fails_without_traceback(tmp_path, capsys):
    cfg = tmp_path / "broken.yaml"
    cfg.write_text("source_manifest: [")
    assert main(["build", "--config", str(cfg)]) == 1
    assert "Stopped:" in capsys.readouterr().err


def test_report_write_failure_does_not_replace_publication(tmp_path):
    cfg = project(tmp_path)
    assert main(["build", "--config", str(cfg)]) == 0
    previous = manifest(tmp_path)
    with patch("simd_ingest.pipeline.build_report.render", side_effect=OSError("Cannot prepare report")):
        assert main(["build", "--config", str(cfg)]) == 1
    assert manifest(tmp_path) == previous
    for name, file in (("history", "postcode_simd_history.parquet"), ("main", "postcode_simd.parquet")):
        assert sha256(tmp_path / "results" / file) == previous["tables"][name]["sha256"]


@pytest.mark.parametrize("fault", ["missing_government", "duplicate_edition", "wrong_vintage"])
def test_registry_rejects_incomplete_or_inconsistent_edition_registration(tmp_path, fault):
    project(tmp_path)
    path = tmp_path / "sources.yaml"
    raw = yaml.safe_load(path.read_text())
    if fault == "missing_government":
        raw["govscot_editions"].pop()
    elif fault == "duplicate_edition":
        raw["phs_editions"].append(raw["phs_editions"][0])
    else:
        raw["govscot_editions"][0]["dz_vintage"] = 2022
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError):
        load_registry(path)


@pytest.mark.parametrize("fault", ["member_not_pinned", "shp_not_pinned", "duplicate_version", "years_out_of_order", "missing_fold",
                                   "no_gate", "gate_names_unknown_version", "gate_thresholds_inverted"])
def test_registry_rejects_an_incomplete_or_inconsistent_rurality_version(tmp_path, fault):
    """A shapefile is four files and a version is read for two named columns. Each of these
    would otherwise fail late, inside the geometry library, or silently pick the wrong year."""
    from support import ROOT
    real = yaml.safe_load((ROOT / "simd_ingest" / "sources.yaml").read_text())
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump(real))
    load_registry(path)                                   # the real registry is accepted as it stands
    versions = real["rurality_versions"]
    if fault == "member_not_pinned":
        obj = next(o for o in real["remote_objects"] if o["key"] == "sg_urbanrural_2022")
        obj["files"] = [f for f in obj["files"] if not f["path"].endswith(".prj")]
    elif fault == "shp_not_pinned":
        versions[0]["file"] = "data.gov.uk/SG_UrbanRural_1999/SG_UrbanRural_1999.shp"
    elif fault == "duplicate_version":
        versions.append(dict(versions[-1]))
    elif fault == "years_out_of_order":
        versions[0]["reference_year"], versions[1]["reference_year"] = versions[1]["reference_year"], versions[0]["reference_year"]
    elif fault == "missing_fold":
        del versions[0]["columns"]["eightfold"]
    elif fault == "no_gate":
        del real["rurality_published"]                    # versions with nothing to check them against
    elif fault == "gate_names_unknown_version":
        real["rurality_published"]["version"] = "1999"
    else:
        real["rurality_published"].update(current_small_user=0.9, other_cohorts=0.99)
    path.write_text(yaml.safe_dump(real))
    with pytest.raises(ValueError):
        load_registry(path)


def test_real_pinned_data_build_matches_contract_and_known_fingerprint(tmp_path):
    from support import ROOT, known_snapshot, source_root, write_config
    source = source_root()
    if source is None:
        pytest.skip("Optional integration: no downloaded sources")
    cfg = write_config(tmp_path, source, ROOT / "simd_ingest/decisions.yaml")
    assert main(["build", "--config", str(cfg)]) == 0
    result = manifest(tmp_path)
    registry = load_registry(ROOT / "simd_ingest/sources.yaml")
    history = yaml.safe_load((ROOT / "simd_ingest/output_schema_history.yaml").read_text())
    main_schema = yaml.safe_load((ROOT / "simd_ingest/output_schema.yaml").read_text())
    assert result["tables"]["history"]["rows"] == registry.spd_published_totals["all"]
    assert result["tables"]["history"]["columns"] == len(history["fields"])
    assert result["tables"]["main"]["rows"] == registry.sspl_file["rows"]
    assert result["tables"]["main"]["columns"] == len(main_schema["fields"])
    for name, fingerprint in (("history", "logical_fingerprint"), ("main", "main_logical_fingerprint")):
        known = known_snapshot(result, name)
        if known is not None:
            assert result["tables"][name]["logical_fingerprint"] == known[fingerprint]
    known = known_snapshot(result, "history")
    if known is not None:
        # The rurality columns were appended; the 162 columns that were there before must be
        # exactly what they were, which the whole-table fingerprint can no longer show.
        import pyarrow.parquet as pq
        from simd_ingest.core.output import logical_fingerprint
        saved = pq.ParquetFile(tmp_path / "results" / "postcode_simd_history.parquet").read().to_pandas(date_as_object=False)
        original = [f["name"] for f in history["fields"] if f["source"] != "rurality"]
        assert len(original) == 162 and list(saved.columns[:162]) == original
        assert logical_fingerprint(saved[original]) == known["wide_v1_columns_fingerprint"]
    assert main(["audit", "--config", str(cfg)]) == 0


def test_historical_expectations_do_not_gate_other_releases(tmp_path):
    from support import known_snapshot
    cfg = project(tmp_path, "test-2", extra_edition=True)
    assert main(["build", "--config", str(cfg)]) == 0
    assert known_snapshot(manifest(tmp_path)) is None


def test_main_table_answers_current_questions_and_refuses_dated_ones(tmp_path):
    from simd_ingest import lookup
    cfg = project(tmp_path)
    assert main(["build", "--config", str(cfg)]) == 0
    latest = lookup.load(tmp_path / "results/postcode_simd.parquet")
    history = lookup.load(tmp_path / "results/postcode_simd_history.parquet")
    assert latest.attrs["index_source"] == "sspl" and history.attrs["index_source"] == "spd"
    # AB10 1AC: the lookup places it in zone 2, the directory in zone 1. Each table answers for itself.
    assert lookup.lookup(latest, "AB10 1AC", edition="2020v2", measure="rank").value == 2
    assert lookup.lookup(history, "AB10 1AC", edition="2020v2", measure="rank").value == 1
    assert lookup.lookup(history, "AB10 1AC", edition="2020v2", on="2021-01-01").status == lookup.UNIQUE
    with pytest.raises(ValueError, match="history"):
        lookup.lookup(latest, "AB10 1AC", edition="2020v2", on="2021-01-01")
    events = pd.DataFrame({"postcode": ["AB10 1AC"], "day": ["2021-01-01"]})
    with pytest.raises(ValueError, match="history"):
        lookup.attach(events, latest, "postcode", "day", edition="2020v2")
    with pytest.raises(ValueError, match="history"):
        lookup.lookup(latest, "AB10 1AC", edition="2020v2", split="report")
    with pytest.raises(ValueError, match="history"):
        lookup.attach_by_era(events.assign(day="1990-01-01"), latest, "postcode", "day")
    # Direct pandas loads must not silently evade the latest-life guard.
    raw = pd.read_parquet(tmp_path / "results/postcode_simd.parquet")
    with pytest.raises(ValueError, match="history"):
        lookup.lookup(raw, "AB10 1AC", edition="2020v2", on="2021-01-01")
    assert lookup.attach(events, latest, "postcode", None, edition="2020v2")["simd_status"].tolist() == [lookup.UNIQUE]
    # PO boxes are excluded at lookup time in both tables; AB10 1AD is a linked large user, so it is found.
    assert lookup.lookup(latest, "AB10 1AD", edition="2020v2").status == lookup.UNIQUE
    assert lookup.lookup(latest, "AB10 1AD", edition="2020v2", include_large_users=False).status == lookup.NOT_FOUND
