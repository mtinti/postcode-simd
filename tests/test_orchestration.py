"""The four step 2 done conditions, run through the Dagster job against a temporary instance.

Each test executes the real job. They take about twenty seconds each and need the pinned
sources under manual_data.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from dagster import AssetKey, DagsterInstance

from support import ROOT, source_root, write_config

MANUAL = source_root()


def mirror_sources(temp: Path, corrupt: str | None = None) -> Path:
    """A source root of symlinks to manual_data, with one file optionally copied and corrupted."""
    from simd_ingest.core.sources import load_registry
    root = temp / "sources"
    for f in load_registry(ROOT / "simd_ingest" / "sources.yaml").files:
        dest = root / f.path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if f.path == corrupt:
            shutil.copyfile(MANUAL / f.path, dest)
            with dest.open("ab") as fh:
                fh.write(b"x")
        else:
            dest.symlink_to(MANUAL / f.path)
    return root


def data_versions(instance: DagsterInstance, keys) -> dict:
    out = {}
    for key in keys:
        event = instance.get_latest_materialization_event(key)
        out[key.to_user_string()] = event.asset_materialization.tags.get("dagster/data_version") if event else None
    return out


@unittest.skipUnless(MANUAL is not None, "pinned sources not present")
class DagsterJob(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="simd_dagster_"))
        self.home = self.temp / "dagster_home"
        self.home.mkdir()
        (self.home / "dagster.yaml").write_text("telemetry:\n  enabled: false\n")
        os.environ["DAGSTER_HOME"] = str(self.home)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)
        os.environ.pop("DAGSTER_HOME", None)

    def run_job(self, cfg: Path, raise_on_error=True):
        from simd_ingest.orchestration.definitions import build_definitions
        defs = build_definitions(cfg)
        job = defs.resolve_job_def("build_postcode_simd")
        instance = DagsterInstance.get()
        result = job.execute_in_process(instance=instance, raise_on_error=raise_on_error)
        return defs, instance, result

    def test_job_reproduces_cli_hash_and_versions_repeat(self):
        cfg = write_config(self.temp, MANUAL, ROOT / "simd_ingest" / "decisions.yaml")
        # Build a fresh CLI reference in its own temporary output, not an old local manifest.
        from simd_ingest.cli import cmd_build, load_config
        cli_cfg = load_config(cfg)
        cli_cfg["results_root"] = self.temp / "cli_results"
        self.assertEqual(cmd_build(cli_cfg, "offline"), 0)
        cli_manifest = json.loads((cli_cfg["results_root"] / "manifest.json").read_text())
        defs, instance, result = self.run_job(cfg)
        self.assertTrue(result.success)
        manifest = json.loads((self.temp / "results" / "manifest.json").read_text())
        self.assertEqual(manifest["output"]["logical_fingerprint"], cli_manifest["output"]["logical_fingerprint"])
        self.assertEqual(manifest["output"]["sha256"], cli_manifest["output"]["sha256"])
        self.assertEqual(manifest["output"]["rows"], 247773)
        # Same core evidence, irrespective of which independent asset completed first.
        records = lambda m: sorted(m["checks"], key=lambda c: c["name"])
        self.assertEqual(records(manifest), records(cli_manifest))
        self.assertEqual(manifest["summary"], cli_manifest["summary"])
        self.assertEqual(sum(c["name"].startswith("source.hash.") for c in manifest["checks"]), 17)
        report = (self.temp / "results/BUILD_REPORT.md").read_text()
        self.assertIn("17 of 17 files present with the pinned hash. All match.", report)
        self.assertNotIn("upstream", report)
        self.assertNotIn("NOT RECORDED", report)
        cli_report = (cli_cfg["results_root"] / "BUILD_REPORT.md").read_text()
        self.assertEqual(report.splitlines()[3:], cli_report.splitlines()[3:])  # Ignore build time.
        evaluations = result.get_asset_check_evaluations()
        self.assertTrue(all(e.passed for e in evaluations), [e.check_name for e in evaluations if not e.passed])
        keys = [k for k in defs.resolve_asset_graph().get_all_asset_keys()]
        first = data_versions(instance, keys)
        self.assertTrue(all(first.values()), first)
        _, instance, result = self.run_job(cfg)
        self.assertTrue(result.success)
        second = data_versions(instance, keys)
        self.assertEqual(first, second)

        # A new final-only run must not treat this run's successful upstream checks as its own.
        previous_output = (self.temp / "results/postcode_simd.parquet").read_bytes()
        previous_manifest = (self.temp / "results/manifest.json").read_bytes()
        partial = defs.resolve_job_def("build_postcode_simd").execute_in_process(
            instance=instance, asset_selection=[AssetKey("postcode_simd")], raise_on_error=False)
        self.assertFalse(partial.success)
        self.assertTrue(any("Missing upstream check evidence" in e.event_specific_data.error.message
                            for e in partial.get_step_failure_events()))
        self.assertEqual((self.temp / "results/postcode_simd.parquet").read_bytes(), previous_output)
        self.assertEqual((self.temp / "results/manifest.json").read_bytes(), previous_manifest)

    def test_corrupted_source_fails_its_check_and_blocks_downstream(self):
        bad = "PHS/simd2004_02042020.csv"
        cfg = write_config(self.temp, mirror_sources(self.temp, corrupt=bad), ROOT / "simd_ingest" / "decisions.yaml")
        defs, instance, result = self.run_job(cfg, raise_on_error=False)
        self.assertFalse(result.success)
        failed = {e.check_name: e for e in result.get_asset_check_evaluations() if not e.passed}
        self.assertIn("pin_verified", failed)
        self.assertEqual(failed["pin_verified"].asset_key, AssetKey(["source", "phs", "simd2004_02042020_csv"]))
        materialised = {e.asset_key.to_user_string() for e in result.get_asset_materialization_events()}
        self.assertNotIn("phs_bands", materialised)
        self.assertNotIn("postcode_simd", materialised)
        self.assertIn("source/phs/simd2006_02042020_csv", materialised)
        self.assertFalse((self.temp / "results" / "postcode_simd.parquet").exists())

    def test_edited_decisions_change_their_version(self):
        decisions = self.temp / "decisions.yaml"
        shutil.copyfile(ROOT / "simd_ingest" / "decisions.yaml", decisions)
        cfg = write_config(self.temp, MANUAL, decisions)
        from simd_ingest.orchestration.definitions import DECISIONS_KEY, build_definitions
        from dagster import materialize
        instance = DagsterInstance.get()
        defs = build_definitions(cfg)
        decisions_asset = next(a for a in defs.assets if DECISIONS_KEY in a.keys)
        materialize([decisions_asset], instance=instance)
        before = data_versions(instance, [DECISIONS_KEY])
        with decisions.open("a") as fh:
            fh.write("\n# reviewed again\n")
        materialize([decisions_asset], instance=instance)
        after = data_versions(instance, [DECISIONS_KEY])
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
