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
    directory_rank: dict | None
    sspl_release: str
    sspl_file: dict
    rurality_versions: tuple = ()
    rurality_published: dict | None = None

    @property
    def files(self) -> tuple:
        return tuple(f for o in self.objects for f in o.files)


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
                   spd_files=tuple(raw["spd_files"]), spd_published_totals=raw["spd_published_totals"],
                   directory_rank=raw.get("directory_rank"),
                   sspl_release=str(raw["sspl_release"]), sspl_file=raw["sspl_file"],
                   rurality_versions=tuple(raw.get("rurality_versions", ())),
                   rurality_published=raw.get("rurality_published"))
    known = set(paths)
    for section in (reg.phs_editions, reg.govscot_editions, reg.spd_files, (reg.sspl_file,)):
        for entry in section:
            if entry["file"] not in known:
                raise ValueError(f"{entry['file']} is referenced but not pinned as a logical file")
    # A shapefile is four files; reading the geometry with one missing fails late and obscurely.
    for entry in reg.rurality_versions:
        stem = entry["file"].removesuffix(".shp")
        if entry["file"] not in known or stem == entry["file"]:
            raise ValueError(f"{entry['file']} is not a pinned .shp logical file")
        missing = [ext for ext in (".shx", ".dbf", ".prj") if stem + ext not in known]
        if missing:
            raise ValueError(f"{entry['key']}: shapefile members not pinned: {missing}")
        if set(entry["columns"]) != {"sixfold", "eightfold"} or entry["polygons"] < 1:
            raise ValueError(f"{entry['key']}: declare the sixfold and eightfold columns and a polygon count")
    versions = [e["key"] for e in reg.rurality_versions]
    years = [e["reference_year"] for e in reg.rurality_versions]
    if len(set(versions)) != len(versions) or years != sorted(set(years)):
        raise ValueError("Rurality versions need unique keys and strictly increasing reference years")
    gate = reg.rurality_published
    if reg.rurality_versions and not gate:
        raise ValueError("Rurality versions are declared without rurality_published: the placement would go unchecked")
    if gate and (gate["version"] not in versions or not 0 < gate["other_cohorts"] <= gate["current_small_user"] <= 1
                 or gate["min_cohort"] < 1):
        raise ValueError("rurality_published must name a declared version and sensible thresholds")
    if len({o.key for o in objects}) != len(objects):
        raise ValueError("Duplicate remote object key")
    phs = {e["key"]: e for e in reg.phs_editions}
    gov = {e["key"]: e for e in reg.govscot_editions}
    if not phs or len(phs) != len(reg.phs_editions) or len(gov) != len(reg.govscot_editions):
        raise ValueError("Edition keys must be nonempty and unique within each publisher")
    if phs.keys() != gov.keys():
        raise ValueError("PHS and Government must declare the same edition keys")
    for key, ed in phs.items():
        if (ed["dz_vintage"], ed["rows"]) != (gov[key]["dz_vintage"], gov[key]["rows"]):
            raise ValueError(f"{key}: publishers disagree on declared vintage or zone count")
        if ed["rows"] < 2 or not isinstance(ed["invert_bands"], bool):
            raise ValueError(f"{key}: invalid row count or band-direction declaration")
        geo = ed["geography_columns"]
        if set(geo) != {"DataZone", "IntZone", "HB", "HSCP", "CA"} or len(geo) != 5:
            raise ValueError(f"{key}: declare the five PHS geography columns in source order")
    if sorted(s["role"] for s in reg.spd_files) != ["large_user", "small_user"]:
        raise ValueError("Declare exactly one small-user and one large-user file")
    totals = reg.spd_published_totals
    if (sum(s["rows"] for s in reg.spd_files) != totals["all"]
            or sum(s["live"] for s in reg.spd_files) != totals["live"]
            or totals["all"] - totals["live"] != totals["deleted"]):
        raise ValueError("Published postcode counts are inconsistent")
    if reg.directory_rank and reg.directory_rank["edition"] not in phs:
        raise ValueError("Directory rank must reference a configured SIMD edition")
    lookup = reg.sspl_file
    if (lookup["small_user"] + lookup["large_user"] != lookup["rows"] or not 0 <= lookup["live"] <= lookup["rows"]
            or lookup.get("totals_basis") not in ("counted", "published")):
        raise ValueError("Lookup counts are inconsistent or their basis is not declared")
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
