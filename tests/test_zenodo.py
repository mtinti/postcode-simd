"""Zenodo: the citation metadata, the sources record and the archived-mirror fallback.

docs/plans/Zenodo_Plan.md. Nothing here touches the network: staging writes to a temporary
directory, and the fetcher's downloads are replaced by fakes.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from fixture_project import project
from simd_ingest.core import fetch
from simd_ingest.core.sources import load_registry, sha256
from simd_ingest.zenodo_sources import RefusedFile, stage
from support import ROOT


# --- citation metadata -----------------------------------------------------------------------------

def test_citation_metadata_agrees_with_the_package():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    cff = yaml.safe_load((ROOT / "CITATION.cff").read_text())
    zenodo = json.loads((ROOT / ".zenodo.json").read_text())
    assert cff["version"] == version and cff["license"] == "MIT" and zenodo["license"] == "MIT"
    assert cff["title"] == zenodo["title"] and zenodo["upload_type"] == "software"
    assert [a["family-names"] for a in cff["authors"]] == [c["name"].split(",")[0] for c in zenodo["creators"]]


# --- the registry's redistribution settings ---------------------------------------------------------

def registry_with(tmp_path: Path, change) -> Path:
    raw = yaml.safe_load((ROOT / "simd_ingest" / "sources.yaml").read_text())
    change(raw)
    path = tmp_path / "sources.yaml"
    path.write_text(yaml.safe_dump(raw))
    (tmp_path / "sgs_2020_housing_rank_disagreements.csv").write_bytes(
        (ROOT / "simd_ingest" / "sgs_2020_housing_rank_disagreements.csv").read_bytes())
    return path


def test_every_publisher_is_upload_or_cite_and_nrs_is_cited():
    registry = load_registry(ROOT / "simd_ingest" / "sources.yaml")
    assert registry.redistribution["nrs"] == "cite"
    assert {registry.redistribution[o.publisher] for o in registry.objects if o.publisher != "nrs"} == {"upload"}


@pytest.mark.parametrize("change,message", [
    (lambda raw: raw["redistribution"].pop("phs"), "every publisher needs upload or cite"),
    (lambda raw: raw["redistribution"].update(phs="maybe"), "every publisher needs upload or cite"),
    (lambda raw: next(o for o in raw["remote_objects"] if o["publisher"] == "nrs").update(mirror="https://example.invalid/x"),
     "cannot have a mirror"),
])
def test_the_registry_refuses_a_bad_setting(tmp_path, change, message):
    with pytest.raises(ValueError, match=message):
        load_registry(registry_with(tmp_path, change))


# --- the sources record -----------------------------------------------------------------------------

@pytest.fixture
def synthetic(tmp_path):
    """The synthetic project: its sources are plain files, NRS among them, as the real registry."""
    cfg = yaml.safe_load(project(tmp_path).read_text())
    return load_registry(Path(cfg["source_manifest"])), Path(cfg["source_roots"]["offline"]), tmp_path


def test_staging_uploads_open_files_and_only_cites_nrs(synthetic, tmp_path):
    registry, root, _ = synthetic
    manifest = stage(tmp_path / "record", registry, cache=tmp_path / "no-cache", root=root)
    assert len(manifest["objects"]) == len(registry.objects)
    for entry in manifest["objects"]:
        cited = registry.redistribution[next(o.publisher for o in registry.objects if o.key == entry["key"])] == "cite"
        assert entry["included"] is not cited, entry["key"]
        if cited:
            assert entry["file"] is None and entry["sha256"] in entry["citation"] and entry["url"] in entry["citation"]
        else:
            assert sha256(tmp_path / "record" / entry["file"]) == entry["sha256"]
    staged = {p.name for p in (tmp_path / "record").iterdir()}
    assert not any(e["key"] in n for e in manifest["objects"] if not e["included"] for n in staged)
    assert {"MANIFEST.json", "README.md", "sources.yaml"} <= staged
    assert "Cited, not included" in (tmp_path / "record" / "README.md").read_text()


def test_a_file_whose_bytes_differ_from_the_pin_is_refused(synthetic, tmp_path):
    registry, root, _ = synthetic
    target = next(o for o in registry.objects if registry.redistribution[o.publisher] == "upload")
    (root / target.files[0].path).write_text("not the pinned bytes")
    with pytest.raises(RefusedFile, match=target.key):
        stage(tmp_path / "record", registry, cache=tmp_path / "no-cache", root=root)


# --- the fetcher's archived mirror -------------------------------------------------------------------

def remote(tmp_path, mirror=True):
    from simd_ingest.core.sources import LogicalFile, RemoteObject
    data = b"the pinned bytes"
    import hashlib
    digest = hashlib.sha256(data).hexdigest()
    files = (LogicalFile(path="x.csv", sha256=digest, object_key="obj", publisher="phs"),)
    return RemoteObject("obj", "phs", "https://publisher.invalid/x.csv", "file", digest, files,
                        "https://zenodo.invalid/x.csv" if mirror else None), data


def fake_download(served: dict):
    import hashlib

    def download(url, part):
        body = served[url]
        if isinstance(body, Exception):
            raise body
        Path(part).write_bytes(body)
        return hashlib.sha256(body).hexdigest(), len(body)
    return download


def test_a_dead_publisher_falls_back_to_the_mirror(tmp_path):
    import requests
    obj, data = remote(tmp_path)
    served = {obj.url: requests.ConnectionError("gone"), obj.mirror: data}
    with patch.object(fetch, "_download", fake_download(served)), patch.object(fetch.time, "sleep"):
        path = fetch._fetch_object(obj, tmp_path, log=lambda *_: None)
    assert path.read_bytes() == data


def test_changed_publisher_bytes_fall_back_to_the_mirror_and_wrong_mirror_bytes_are_refused(tmp_path):
    obj, data = remote(tmp_path)
    with patch.object(fetch, "_download", fake_download({obj.url: b"changed", obj.mirror: data})), patch.object(fetch.time, "sleep"):
        assert fetch._fetch_object(obj, tmp_path / "a", log=lambda *_: None).read_bytes() == data
    with patch.object(fetch, "_download", fake_download({obj.url: b"changed", obj.mirror: b"also wrong"})), patch.object(fetch.time, "sleep"):
        with pytest.raises(fetch.FetchError, match="mirror"):
            fetch._fetch_object(obj, tmp_path / "b", log=lambda *_: None)


def test_without_a_mirror_changed_bytes_still_stop(tmp_path):
    obj, _ = remote(tmp_path, mirror=False)
    with patch.object(fetch, "_download", fake_download({obj.url: b"changed"})), patch.object(fetch.time, "sleep"):
        with pytest.raises(fetch.FetchError, match="publisher"):
            fetch._fetch_object(obj, tmp_path, log=lambda *_: None)
