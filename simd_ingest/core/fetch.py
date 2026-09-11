"""Download pinned remote objects and place their logical files, or verify files in place.

Both modes end in the same state: every logical file present under the source root with its
pinned hash. Nothing downstream knows which mode ran.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import time
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import requests

from .checks import Report
from .sources import Registry, RemoteObject, sha256, verify_root

# NRS rejects the default Python user agent with HTTP 403. The others do not care.
USER_AGENT = "Mozilla/5.0 (compatible; simd-ingest/0.1)"
TIMEOUT = 120
ATTEMPTS = 3


class FetchError(Exception):
    """A download or extraction did not produce the pinned bytes."""


def ensure_sources(registry: Registry, mode: str, root: Path, cache: Path, report: Report, log=print) -> bool:
    """Make every logical file available under root, then verify all of them."""
    if mode == "offline":
        log(f"offline mode: verifying {len(registry.files)} files under {root}")
        return verify_root(registry, root, report)
    if mode != "download":
        raise ValueError(f"unknown source_mode {mode!r}")
    for obj in registry.objects:
        object_path = _fetch_object(obj, cache, log)
        _place_files(obj, object_path, root, log)
    return verify_root(registry, root, report)


def ensure_file(registry: Registry, path: str, mode: str, root: Path, cache: Path, report: Report, log=print) -> str:
    """Make one logical file available under root and verify it. Returns its actual hash.

    In download mode the file's remote object is fetched if the cache lacks it, and every
    declared member of that object is placed, so sibling files arrive together.
    """
    f = registry.file(path)
    if mode == "download":
        obj = next(o for o in registry.objects if o.key == f.object_key)
        _place_files(obj, _fetch_object(obj, cache, log), root, log)
    elif mode != "offline":
        raise ValueError(f"unknown source_mode {mode!r}")
    target = Path(root) / f.path
    if not target.is_file():
        report.add(f"source.present.{f.path}", False, f"missing at {target}")
        return ""
    actual = sha256(target)
    report.equal(f"source.hash.{f.path}", actual, f.sha256,
                 detail=("hash matches" if actual == f.sha256 else f"expected {f.sha256[:12]}, got {actual[:12]}"))
    return actual


def _fetch_object(obj: RemoteObject, cache: Path, log) -> Path:
    target = Path(cache) / "objects" / obj.key / PurePosixPath(urlparse(obj.url).path).name
    if target.is_file() and sha256(target) == obj.sha256:
        log(f"  cached   {obj.key}")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    last = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            digest, size = _download(obj.url, part)
            if digest != obj.sha256:
                part.unlink(missing_ok=True)
                raise FetchError(f"{obj.key}: expected {obj.sha256[:12]}, downloaded {digest[:12]} ({size:,} bytes)")
            os.replace(part, target)
            log(f"  fetched  {obj.key}  {size:,} bytes  {digest[:12]}")
            return target
        except (requests.RequestException, OSError) as exc:
            last = exc
            part.unlink(missing_ok=True)
            log(f"  retry    {obj.key} attempt {attempt}: {exc}")
            time.sleep(2 ** attempt)
    raise FetchError(f"{obj.key}: download failed after {ATTEMPTS} attempts: {last}")


def _download(url: str, part: Path) -> tuple:
    h = hashlib.sha256()
    size = 0
    with requests.get(url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        with part.open("wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
                h.update(chunk)
                size += len(chunk)
    return h.hexdigest(), size


def _place_files(obj: RemoteObject, object_path: Path, root: Path, log) -> None:
    for f in obj.files:
        dest = Path(root) / f.path
        if dest.is_file() and sha256(dest) == f.sha256:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        if obj.format == "file":
            shutil.copyfile(object_path, part)
        else:
            _extract_member(object_path, f.member, part)
        actual = sha256(part)
        if actual != f.sha256:
            part.unlink(missing_ok=True)
            raise FetchError(f"{f.path}: expected {f.sha256[:12]}, extracted {actual[:12]}")
        os.replace(part, dest)
        log(f"  placed   {f.path}")


def _extract_member(zip_path: Path, member: str, dest: Path) -> None:
    """Extract exactly one declared member, refusing anything that is not a plain file."""
    parts = PurePosixPath(member).parts
    if PurePosixPath(member).is_absolute() or ".." in parts or not parts:
        raise FetchError(f"refusing archive member path {member!r}")
    with zipfile.ZipFile(zip_path) as zf:
        try:
            info = zf.getinfo(member)
        except KeyError:
            raise FetchError(f"{zip_path.name}: declared member {member!r} not in archive") from None
        if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
            raise FetchError(f"{zip_path.name}: member {member!r} is not a regular file")
        with zf.open(info) as src, dest.open("wb") as out:
            shutil.copyfileobj(src, out, 1 << 20)
