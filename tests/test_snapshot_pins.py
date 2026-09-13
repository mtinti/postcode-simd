"""Refreshing one postcode product cannot disable the other's unchanged regression."""

import json

from support import ROOT, known_snapshot


def pinned_manifest():
    known = json.loads((ROOT / "tests/known_snapshot.json").read_text())
    return {"sources": [{"key": "nrs_sspl_fixture" if sha == known["sspl_object_sha256"] else str(i),
                         "sha256": sha} for i, sha in enumerate(known["remote_object_sha256"])],
            "tables": {"main": {"schema_sha256": known["main_schema_sha256"]},
                       "history": {"schema_sha256": known["schema_sha256"]}}}


def test_sspl_refresh_keeps_history_regression():
    manifest = pinned_manifest()
    assert known_snapshot(manifest, "main") and known_snapshot(manifest, "history")
    next(o for o in manifest["sources"] if o["key"].startswith("nrs_sspl"))["sha256"] = "new-sspl"
    assert known_snapshot(manifest, "main") is None
    assert known_snapshot(manifest, "history") is not None


def test_main_schema_change_does_not_match_old_main_fingerprint():
    manifest = pinned_manifest()
    manifest["tables"]["main"]["schema_sha256"] = "new-main-schema"
    assert known_snapshot(manifest, "main") is None
    assert known_snapshot(manifest, "history") is not None
