"""Archive the pinned open-licence sources on Zenodo, byte for byte (docs/plans/Zenodo_Plan.md).

    python -m simd_ingest.zenodo_sources stage            # stage the record locally; no network
    python -m simd_ingest.zenodo_sources draft            # stage, then create or update a Zenodo draft
    python -m simd_ingest.zenodo_sources draft --sandbox  # the same on sandbox.zenodo.org

A draft is private: visible only to its owner, editable and deletable. This script never publishes;
publishing, which makes the record permanent and mints its DOI, is done on Zenodo by a person.

Each download a publisher allows to be redistributed (`redistribution: upload` in sources.yaml) is
uploaded exactly as the registry pins it, the object as fetched, so its SHA256 verifies it. Each
download that is only cited (`cite`, the NRS postcode products) is described in full in the
manifest and README, product, release, URL and SHA256, and never uploaded. A file whose bytes
differ from the registry is refused. The token is read from ZENODO_TOKEN and never written.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from .core.sources import load_registry, sha256

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
HOSTS = {"zenodo": "https://zenodo.org", "sandbox": "https://sandbox.zenodo.org"}
PUBLISHER = {"phs": "Public Health Scotland", "maps_gov_scot": "Scottish Government (maps.gov.scot / data.gov.uk)",
             "statistics_gov_scot": "Scottish Government (statistics.gov.scot)", "nrs": "National Records of Scotland"}


class RefusedFile(ValueError):
    """A file that must not be uploaded: its bytes differ from the pin, or it is only cited."""


def archive_name(obj) -> str:
    """A unique, readable file name in the record: the registry key, then the downloaded name."""
    name = PurePosixPath(urlparse(obj.url).path).name
    if obj.format == "file":
        name = PurePosixPath(obj.files[0].path).name
    return f"{obj.key}__{name}"


def locate(obj, cache: Path, root: Path) -> Path:
    """The download as fetched: the build's cache, or for a plain file its pinned copy. Refused unless
    its SHA256 is the registry's."""
    candidates = [Path(cache) / "objects" / obj.key / PurePosixPath(urlparse(obj.url).path).name]
    if obj.format == "file":
        candidates.append(Path(root) / obj.files[0].path)
    for path in candidates:
        if path.is_file():
            if sha256(path) != obj.sha256:
                raise RefusedFile(f"{obj.key}: {path} has SHA256 {sha256(path)[:12]}, the registry pins {obj.sha256[:12]}")
            return path
    raise FileNotFoundError(f"{obj.key}: not found in the cache or the source root; fetch it first")


def stage(out: Path, registry=None, cache: Path = ROOT / "data" / "cache", root: Path = ROOT / "manual_data") -> dict:
    """Write the record into `out`: the uploadable downloads, MANIFEST.json, README.md, sources.yaml.
    Returns the manifest."""
    registry = registry or load_registry(PACKAGE / "sources.yaml")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    entries = []
    for obj in registry.objects:
        setting = registry.redistribution[obj.publisher]
        entry = {"key": obj.key, "publisher": PUBLISHER.get(obj.publisher, obj.publisher), "url": obj.url,
                 "sha256": obj.sha256, "licence": registry.licences.get(obj.publisher),
                 "members": [{"path": f.path, "sha256": f.sha256, "member": f.member, "role": f.role} for f in obj.files]}
        if setting == "upload":
            source = locate(obj, cache, root)
            name = archive_name(obj)
            shutil.copyfile(source, out / name)
            if sha256(out / name) != obj.sha256:
                raise RefusedFile(f"{obj.key}: the staged copy does not match the pin")
            evidence = registry.redistribution_evidence[obj.key]
            entry.update(included=True, file=name, size=(out / name).stat().st_size, licence=evidence["licence"],
                         licence_evidence=evidence["evidence"], credit=evidence["credit"])
        else:
            entry.update(included=False, file=None,
                         citation=f"{PUBLISHER.get(obj.publisher, obj.publisher)}. {obj.key}. Downloaded from {obj.url}; "
                                  f"SHA256 {obj.sha256}. Not redistributed: fetch it from the publisher and verify the hash.")
        entries.append(entry)
    manifest = {"title": "Pinned public sources of postcode-SIMD", "registry": "simd_ingest/sources.yaml",
                "registry_sha256": registry.sha256, "commit": commit,
                "spd_release": registry.spd_release, "sspl_release": registry.sspl_release, "objects": entries}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.copyfile(PACKAGE / "sources.yaml", out / "sources.yaml")
    (out / "README.md").write_text(readme(manifest))
    return manifest


def readme(manifest: dict) -> str:
    included = [e for e in manifest["objects"] if e["included"]]
    cited = [e for e in manifest["objects"] if not e["included"]]
    lines = ["# Pinned public sources of postcode-SIMD", "",
             "The downloads the postcode-SIMD pipeline (https://github.com/mtinti/postcode-simd) builds from, exactly as "
             "its registry pins them: each file's SHA256 is the one in `sources.yaml`, so the build verifies an archived copy "
             "as it does the publisher's. Column provenance: https://mtinti.github.io/postcode-simd/", "",
             f"Registry at commit `{manifest['commit'][:12]}` (`sources.yaml`, SHA256 `{manifest['registry_sha256'][:12]}…`). "
             f"SPD release {manifest['spd_release'].replace('_', '/')}, SSPL release {manifest['sspl_release'].replace('_', '/')}.", "",
             f"## Included ({len(included)} downloads)", "",
             "Each is licensed under the Open Government Licence (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/), "
             "which allows redistribution with attribution. The evidence for each file's licence and the credit its publisher "
             "requires are listed below and in `MANIFEST.json`; the original notices inside each archive are unchanged.", "",
             "| File | Publisher | Original URL | SHA256 |", "| --- | --- | --- | --- |"]
    lines += [f"| `{e['file']}` | {e['publisher']} | <{e['url']}> | `{e['sha256']}` |" for e in included]
    lines += ["", "### Licence evidence and required credit, per file", ""]
    for e in included:
        lines += [f"- `{e['file']}`: {e['licence']}, {e['licence_evidence']}. Credit: \"{e['credit']}\""]
    lines += ["",
              f"## Cited, not included ({len(cited)} downloads)", "",
              "The National Records of Scotland postcode products are not redistributed here. Fetch them from NRS; "
              "the build verifies each by its SHA256.", "",
              "| Product | Original URL | SHA256 of the download |", "| --- | --- | --- |"]
    lines += [f"| {e['publisher']}: `{e['key']}` | <{e['url']}> | `{e['sha256']}` |" for e in cited]
    lines += ["", "`MANIFEST.json` lists every download with its licence and the files the build reads from it, each with its SHA256.", ""]
    return "\n".join(lines)


def metadata(manifest: dict) -> dict:
    return {"metadata": {
        "title": f"Pinned public sources of postcode-SIMD (SPD {manifest['spd_release'].replace('_', '/')})",
        "upload_type": "dataset",
        "description": ("<p>The open-licence downloads the postcode-SIMD pipeline builds from, archived byte for byte as its "
                        "registry pins them, with a manifest of every pinned source and its SHA256. The National Records of "
                        "Scotland postcode products are cited, not redistributed. Software: "
                        "<a href=\"https://github.com/mtinti/postcode-simd\">https://github.com/mtinti/postcode-simd</a>; "
                        "column provenance: <a href=\"https://mtinti.github.io/postcode-simd/\">https://mtinti.github.io/postcode-simd/</a>.</p>"),
        "creators": [{"name": "Tinti, Michele", "affiliation": "Health Informatics Centre (HIC), University of Dundee",
                      "orcid": "0000-0002-0051-017X"}],
        "license": "OGL-UK-3.0",
        "access_right": "open",
        "keywords": ["SIMD", "Scottish Index of Multiple Deprivation", "Urban Rural Classification", "Scotland", "deprivation"],
        "related_identifiers": [{"identifier": "https://github.com/mtinti/postcode-simd", "relation": "isSupplementTo", "scheme": "url"}],
        "version": f"sources {manifest['commit'][:7]}",
    }}


def draft(staged: Path, manifest: dict, host: str, token: str, log=print) -> dict:
    """Create a draft deposition, or reuse the draft this script made before, and upload the staged
    files to it. Never publishes."""
    import requests
    api = f"{HOSTS[host]}/api/deposit/depositions"
    headers = {"Authorization": f"Bearer {token}"}
    state = staged / ".zenodo_draft.json"
    deposition = None
    if state.is_file():
        previous = json.loads(state.read_text())
        r = requests.get(f"{api}/{previous['id']}", headers=headers, timeout=60)
        if r.ok and r.json().get("state") != "done" and not r.json().get("submitted"):
            deposition = r.json()
    if deposition is None:
        r = requests.post(api, headers=headers, json={}, timeout=60)
        r.raise_for_status()
        deposition = r.json()
    r = requests.put(f"{api}/{deposition['id']}", headers=headers, json=metadata(manifest), timeout=60)
    r.raise_for_status()
    bucket = deposition["links"]["bucket"]
    names = [e["file"] for e in manifest["objects"] if e["included"]] + ["MANIFEST.json", "README.md", "sources.yaml"]
    for name in names:
        with open(staged / name, "rb") as fh:
            r = requests.put(f"{bucket}/{name}", headers=headers, data=fh, timeout=3600)
        r.raise_for_status()
        log(f"  uploaded {name}")
    state.write_text(json.dumps({"id": deposition["id"], "host": host}) + "\n")
    deposition = requests.get(f"{api}/{deposition['id']}", headers=headers, timeout=60).json()
    # Verify what Zenodo holds: every staged file is there with the MD5 checksum of the staged copy,
    # whose SHA256 was checked against the registry when it was staged.
    held = {f["filename"]: f for f in deposition.get("files", [])}
    unexpected = sorted(set(held) - set(names))
    if unexpected:
        raise RuntimeError(f"the draft holds files this record does not stage: {unexpected}")
    wrong = [n for n in names if n not in held or held[n]["checksum"].removeprefix("md5:") != _md5(staged / n)]
    if wrong:
        raise RuntimeError(f"the draft does not hold these files as staged: {wrong}")
    log(f"  verified {len(names)} files on Zenodo by MD5")
    return deposition


def _md5(path: Path) -> str:
    import hashlib
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["stage", "draft"])
    ap.add_argument("--sandbox", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "build" / "zenodo_sources"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    manifest = stage(out)
    included = [e for e in manifest["objects"] if e["included"]]
    print(f"staged {len(included)} downloads ({sum(e['size'] for e in included) / 1e6:.0f} MB) in {out}; "
          f"cited only: {[e['key'] for e in manifest['objects'] if not e['included']]}")
    if args.action == "stage":
        return 0
    token = os.environ.get("ZENODO_TOKEN")
    if not token:
        print("ZENODO_TOKEN is not set"); return 2
    deposition = draft(out, manifest, "sandbox" if args.sandbox else "zenodo", token)
    print(f"draft {deposition['id']}: {deposition['links']['html']} (private until published on Zenodo)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
