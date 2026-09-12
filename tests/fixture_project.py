"""Tiny, real CSV/DBF inputs for maintenance tests. No network or local data needed."""

import copy
import struct
from pathlib import Path

import pandas as pd
import yaml

from simd_ingest.core.phs import BANDS, FLAGS
from simd_ingest.core.sources import sha256
from simd_ingest.core.spd import DERIVED

ROOT = Path(__file__).resolve().parent.parent


def dbf_bytes(rows):
    """Minimal dBase III fixture, with one character and six numeric fields."""
    fields = [(name, "C" if name == "datazone" else "N", 12 if name == "datazone" else 6)
              for name in rows[0]]
    header = bytearray(32)
    header[:4] = bytes([3, 126, 9, 12])
    struct.pack_into("<IHH", header, 4, len(rows), 33 + 32 * len(fields), 1 + sum(f[2] for f in fields))
    for name, kind, width in fields:
        field = bytearray(32)
        field[:len(name)] = name.encode()
        field[11], field[16] = ord(kind), width
        header.extend(field)
    header.extend(b"\r")
    for row in rows:
        header.extend(b" ")
        for name, kind, width in fields:
            text = str(row[name])
            header.extend((text.ljust(width) if kind == "C" else text.rjust(width)).encode())
    return bytes(header) + b"\x1a"


def project(tmp: Path, release="test-1", extra_edition=False) -> Path:
    raw = yaml.safe_load((ROOT / "simd_ingest/sources.yaml").read_text())
    raw["spd_release"] = release
    raw["remote_objects"] = []
    sources = tmp / "sources"
    sources.mkdir(exist_ok=True)

    def pin(path, publisher):
        digest = sha256(sources / path)
        raw["remote_objects"].append(dict(
            key=path.replace("/", "_"), publisher=publisher, url=f"https://example.invalid/{path}",
            format="file", sha256=digest, files=[dict(path=path, sha256=digest)]))

    if extra_edition:
        p = copy.deepcopy(raw["phs_editions"][-1])
        p.update(key="future", prefix="SIMDFUTURE", dz_vintage=2022)
        raw["phs_editions"].append(p)
        g = copy.deepcopy(raw["govscot_editions"][-1])
        g.update(key="future", dz_vintage=2022)
        raw["govscot_editions"].append(g)
    for ed in raw["phs_editions"]:
        ed.update(rows=2, file=f"phs_{ed['key']}.csv")
        prefix = ed["prefix"]
        data = {"DataZone": [f"D{ed['dz_vintage']}A", f"D{ed['dz_vintage']}B"],
                "IntZone": ["IZ", "IZ"], "HB": ["HB", "HB"], "HSCP": ["HSCP", "HSCP"], "CA": ["CA", "CA"]}
        data[prefix + "Rank"] = [1, 2]
        for src, canon in BANDS.items():
            width = 10 if canon.endswith("decile") else 5
            data[prefix + src] = [width, 1] if ed["invert_bands"] else [1, width]
        data[prefix + "Most15pc"] = [1, 0]
        data[prefix + "Least15pc"] = [0, 1]
        pd.DataFrame(data)[ed["geography_columns"] + [prefix + s for s in ["Rank", *BANDS, *FLAGS]]].to_csv(sources / ed["file"], index=False)
        pin(ed["file"], "PHS")
    for ed in raw["govscot_editions"]:
        ed.update(rows=2, file=f"gov_{ed['key']}.dbf")
        ed["columns"] = {k: k for k in ("datazone", "rank", "quintile", "decile", "vigintile", "population")}
        rows = [dict(datazone=f"D{ed['dz_vintage']}{letter}", rank=i, quintile=1 if i == 1 else 5,
                     decile=1 if i == 1 else 10, vigintile=1 if i == 1 else 20, population=100)
                for i, letter in enumerate("AB", 1)]
        (sources / ed["file"]).write_bytes(dbf_bytes(rows))
        pin(ed["file"], "Scottish Government")

    headers = ["Postcode", "SplitIndicator", "DateOfIntroduction", "DateOfDeletion",
               "DataZone2001Code", "DataZone2011Code", "DataZone2022Code",
               "ScottishIndexOfMultipleDeprivation2020Rank"]
    spd_schema = {"version": 1, "small_user": headers, "large_user": headers + ["LinkedSmallUserPostcode"]}

    def row(postcode, zone=1, deleted="", split="N"):
        return dict(Postcode=postcode, SplitIndicator=split, DateOfIntroduction="1/1/2020 00:00:00",
                    DateOfDeletion=deleted, **{f"DataZone{v}Code": f"D{v}{'A' if zone == 1 else 'B'}" for v in (2001, 2011, 2022)},
                    ScottishIndexOfMultipleDeprivation2020Rank=str(zone))

    small = [row("AB10 1AA"), row("AB10 1AB", 2), row("AB10 1AC")]
    if release != "test-1":
        small = [row("AB10 1AA", 2), row("AB10 1AB", 2, deleted="1/9/2026 00:00:00"),
                 row("AB10 1AE"), row("AB10 1AFA", split="Y"), row("AB10 1AFB", 2, split="Y")]
    large = [dict(row("AB10 1AD", 2), LinkedSmallUserPostcode="AB10 1AA")]
    raw["spd_files"] = []
    for role, rows in (("small_user", small), ("large_user", large)):
        file = f"{role}.csv"
        pd.DataFrame(rows)[spd_schema[role]].to_csv(sources / file, index=False)
        pin(file, "NRS")
        raw["spd_files"].append(dict(role=role, file=file, rows=len(rows),
                                     live=sum(not r["DateOfDeletion"] for r in rows)))
    total = len(small) + len(large)
    live = sum(s["live"] for s in raw["spd_files"])
    raw["spd_published_totals"] = dict(all=total, live=live, deleted=total - live)
    schema = yaml.safe_load((ROOT / "simd_ingest/output_schema.yaml").read_text())
    wanted = set(headers + ["LinkedSmallUserPostcode"] + DERIVED)
    schema["fields"] = [f for f in schema["fields"] if f["name"] in wanted or f["name"].startswith(("simd", "phs_dz"))]
    if extra_edition:
        new_fields = [copy.deepcopy(f) for f in schema["fields"] if f["name"].startswith(("simd2020v2_", "phs_dz2011_"))]
        for f in new_fields:
            f["name"] = f["name"].replace("2020v2", "future").replace("2011", "2022")
        schema["fields"].extend(new_fields)
        schema["version"] = "test-extension"
    for filename, data in (("sources.yaml", raw), ("spd_schema.yaml", spd_schema),
                           ("output_schema.yaml", schema), ("decisions.yaml", {"decisions": []})):
        (tmp / filename).write_text(yaml.safe_dump(data, sort_keys=False))
    config = dict(source_manifest=str(tmp / "sources.yaml"), spd_schema=str(tmp / "spd_schema.yaml"),
                  output_schema=str(tmp / "output_schema.yaml"), decisions=str(tmp / "decisions.yaml"),
                  source_mode="offline", source_roots={"offline": str(sources), "download": str(sources)},
                  cache_root=str(tmp / "cache"), results_root=str(tmp / "results"))
    path = tmp / "workflow.yaml"
    path.write_text(yaml.safe_dump(config))
    return path
