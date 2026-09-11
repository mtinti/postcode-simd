"""The source registry: what is pinned, where it comes from, and how to verify it."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

from .checks import Report


@dataclass(frozen=True)
class LogicalFile:
    path: str
    sha256: str
    object_key: str
    publisher: str
    member: str | None = None
    role: str = "data"


@dataclass(frozen=True)
class RemoteObject:
    key: str
    publisher: str
    url: str
    format: str
    sha256: str
    files: tuple


@dataclass(frozen=True)
class Registry:
    path: Path
    sha256: str
    spd_release: str
    licences: dict
    objects: tuple
    phs_editions: tuple
    govscot_editions: tuple
    spd_files: tuple
    spd_published_totals: dict

    @property
    def files(self) -> tuple:
        return tuple(f for o in self.objects for f in o.files)

    def file(self, path: str) -> LogicalFile:
        for f in self.files:
            if f.path == path:
                return f
        raise KeyError(path)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_registry(path: Path) -> Registry:
    path = Path(path)
    raw = yaml.safe_load(path.read_text())
    if raw.get("version") != 2:
        raise ValueError(f"Unsupported registry version {raw.get('version')!r}; expected 2")
    objects = []
    for o in raw["remote_objects"]:
        if o["format"] not in ("file", "zip"):
            raise ValueError(f"{o['key']}: unknown format {o['format']!r}")
        files = tuple(LogicalFile(path=f["path"], sha256=f["sha256"], object_key=o["key"],
                                  publisher=o["publisher"], member=f.get("member"),
                                  role=f.get("role", "data")) for f in o["files"])
        if o["format"] == "file" and (len(files) != 1 or files[0].sha256 != o["sha256"]):
            raise ValueError(f"{o['key']}: a plain file object must have one file with the same hash")
        if o["format"] == "zip" and any(f.member is None for f in files):
            raise ValueError(f"{o['key']}: every archive file needs a member name")
        objects.append(RemoteObject(o["key"], o["publisher"], o["url"], o["format"], o["sha256"], files))
    paths = [f.path for o in objects for f in o.files]
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate logical file path in registry")
    reg = Registry(path=path, sha256=sha256(path), spd_release=str(raw["spd_release"]),
                   licences=raw.get("licences", {}), objects=tuple(objects),
                   phs_editions=tuple(raw["phs_editions"]), govscot_editions=tuple(raw["govscot_editions"]),
                   spd_files=tuple(raw["spd_files"]), spd_published_totals=raw["spd_published_totals"])
    known = set(paths)
    for section in (reg.phs_editions, reg.govscot_editions, reg.spd_files):
        for entry in section:
            if entry["file"] not in known:
                raise ValueError(f"{entry['file']} is referenced but not pinned as a logical file")
    return reg


def verify_root(registry: Registry, root: Path, report: Report) -> bool:
    """Every logical file is present under root with its pinned hash."""
    root = Path(root)
    ok = True
    for f in registry.files:
        target = root / f.path
        if not target.is_file():
            ok &= report.add(f"source.present.{f.path}", False, f"missing at {target}")
            continue
        actual = sha256(target)
        ok &= report.equal(f"source.hash.{f.path}", actual, f.sha256,
                           detail=("hash matches" if actual == f.sha256 else f"expected {f.sha256[:12]}, got {actual[:12]}"))
    return ok
