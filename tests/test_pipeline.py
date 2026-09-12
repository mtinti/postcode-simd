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
    assert first["observations"]["snapshot_changes"]["status"] == "unavailable"
    cfg = project(tmp_path, "test-2")
    assert main(["build", "--config", str(cfg)]) == 0
    second = manifest(tmp_path)
    changes = second["observations"]["snapshot_changes"]
    assert (changes["added_records"], changes["removed_records"], changes["changed_records"]) == (3, 1, 2)
    assert changes["newly_deleted_records"] == 1
    assert "spd_release" not in changes["changed_fields"]
    assert second["observations"]["spd.small_user"]["split_records"] == 2
    saved = pd.read_parquet(tmp_path / "results/postcode_simd.parquet").set_index("pc_norm")
    assert len(saved) == 6 and "AB101AC" not in saved.index
    assert saved.loc["AB101AA", "simd2020v2_rank"] == 2
    assert saved.loc["AB101AFA", "pc_base"] == "AB101AF"
    assert saved.loc["AB101AFB", "simd2004_pw_scotland_quintile"] == 5
    assert not saved.loc["AB101AB", "is_current"]
    runs = sorted((tmp_path / "results/runs").iterdir())
    assert len(runs) == 2
    assert json.loads((runs[0] / "manifest.json").read_text())["output"] == first["output"]
    for run in runs:
        record = json.loads((run / "run.json").read_text())
        assert record["status"] == "published"
        assert record["code_sha256"]["pipeline.py"]
        assert "dagster" not in record["dependencies"]
        assert (run / "source_manifest.yaml").is_file()
    assert main(["audit", "--config", str(cfg)]) == 0
    # Same release rerun produces identical data and file bytes, but a fresh run record.
    assert main(["build", "--config", str(cfg)]) == 0
    assert manifest(tmp_path)["output"]["sha256"] == second["output"]["sha256"]
    assert manifest(tmp_path)["observations"]["snapshot_changes"]["changed_records"] == 0


def test_new_simd_edition_and_new_vintage_need_no_pipeline_code_change(tmp_path):
    cfg = project(tmp_path)
    assert main(["build", "--config", str(cfg)]) == 0
    before = pd.read_parquet(tmp_path / "results/postcode_simd.parquet")
    cfg = project(tmp_path, extra_edition=True)
    assert main(["build", "--config", str(cfg)]) == 0
    after = pd.read_parquet(tmp_path / "results/postcode_simd.parquet")
    pd.testing.assert_frame_equal(before, after[before.columns])
    assert len(after.columns) == len(before.columns) + 17
    assert after["simdfuture_rank"].tolist() == [1, 2, 1, 2]
    assert after["simdfuture_pw_scotland_quintile"].tolist() == [1, 5, 1, 5]
    assert after["phs_dz2022_hb"].tolist() == ["HB"] * 4
    assert main(["audit", "--config", str(cfg)]) == 0


@pytest.mark.parametrize("fault", ["hash", "published_count", "schema", "unmatched_zone", "shared_geography"])
def test_bad_refresh_keeps_previous_publication_and_retains_failure(tmp_path, fault):
    cfg = project(tmp_path)
    assert main(["build", "--config", str(cfg)]) == 0
    previous = manifest(tmp_path)
    cfg = project(tmp_path, "test-2")
    if fault == "published_count":
        path = tmp_path / "sources.yaml"
        raw = yaml.safe_load(path.read_text())
        raw["spd_files"][0]["rows"] += 1
        raw["spd_published_totals"]["all"] += 1
        raw["spd_published_totals"]["deleted"] += 1
        path.write_text(yaml.safe_dump(raw))
    else:
        filename = "phs_2006.csv" if fault == "shared_geography" else "small_user.csv"
        path = tmp_path / "sources" / filename
        data = pd.read_csv(path, dtype=str, keep_default_na=False)
        if fault == "schema":
            data["unexpected"] = "x"
        elif fault == "unmatched_zone":
            data.loc[0, "DataZone2001Code"] = "UNKNOWN"
        elif fault == "shared_geography":
            data.loc[0, "HB"] = "DIFFERENT"
        else:
            data.loc[0, "Postcode"] = "AB10 1AZ"
        data.to_csv(path, index=False)
        if fault != "hash":
            repin(tmp_path, filename)
    assert main(["build", "--config", str(cfg)]) == 1
    assert manifest(tmp_path) == previous
    assert sha256(tmp_path / "results/postcode_simd.parquet") == previous["output"]["sha256"]
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
    changes = compare_snapshot(table, path, tmp_path / "results/manifest.json")
    assert changes["status"] == "unavailable"
    assert "hash" in changes["reason"]
    assert main(["build", "--config", str(cfg)]) == 0
    assert manifest(tmp_path)["observations"]["snapshot_changes"]["status"] == "unavailable"


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
    assert sha256(tmp_path / "results/postcode_simd.parquet") == previous["output"]["sha256"]


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


def test_real_pinned_data_build_matches_contract_and_known_fingerprint(tmp_path):
    from support import ROOT, known_snapshot, source_root, write_config
    source = source_root()
    if source is None:
        pytest.skip("Optional integration: no downloaded sources")
    cfg = write_config(tmp_path, source, ROOT / "simd_ingest/decisions.yaml")
    assert main(["build", "--config", str(cfg)]) == 0
    result = manifest(tmp_path)
    registry = load_registry(ROOT / "simd_ingest/sources.yaml")
    schema = yaml.safe_load((ROOT / "simd_ingest/output_schema.yaml").read_text())
    assert result["output"]["rows"] == registry.spd_published_totals["all"]
    assert result["output"]["columns"] == len(schema["fields"])
    known = known_snapshot(result)
    if known is not None:
        assert result["output"]["logical_fingerprint"] == known["logical_fingerprint"]
    assert main(["audit", "--config", str(cfg)]) == 0


def test_historical_expectations_do_not_gate_other_releases(tmp_path):
    from support import known_snapshot
    cfg = project(tmp_path, "test-2", extra_edition=True)
    assert main(["build", "--config", str(cfg)]) == 0
    assert known_snapshot(manifest(tmp_path)) is None
