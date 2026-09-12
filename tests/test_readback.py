"""Small saved-file corruption fixtures: no downloads or pre-existing build required."""

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from simd_ingest.pipeline import write_output
from simd_ingest.core import output
from simd_ingest.core.checks import BuildStopped, Report
from simd_ingest.core.join import attach
from simd_ingest.core.phs import BANDS, FLAGS
from simd_ingest.core.sources import load_registry, sha256

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def sample(tmp_path):
    registry = load_registry(ROOT / "simd_ingest/sources.yaml")
    schema = output.load_schema(ROOT / "simd_ingest/output_schema_history.yaml")
    main_schema = output.load_schema(ROOT / "simd_ingest/output_schema.yaml")
    decisions = ROOT / "simd_ingest/decisions.yaml"
    digest = sha256(decisions)
    # All original/derived index columns; nullable text includes absent, supplied and blank.
    index = pd.DataFrame({f["name"]: [""] * 3 for f in schema["fields"][:72]})
    index["pc_norm"] = index["pc_base"] = ["AB101AA", "AB101AB", "AB101AC"]
    index["Postcode"] = ["AB10 1AA", "AB10 1AB", "AB10 1AC"]
    index["spd_user_type"] = ["small_user", "large_user", "large_user"]
    index["spd_release"] = registry.spd_release
    index["introduced_on"] = pd.Timestamp("2020-01-01")
    index["deleted_on"] = pd.NaT
    index["is_current"] = True
    index["LinkedSmallUserPostcode"] = [None, "AB10 1AA", ""]
    for vintage in (2001, 2011):
        index[f"DataZone{vintage}Code"] = f"DZ{vintage}"
    phs = pd.DataFrame([dict(edition=ed["key"], dz_vintage=ed["dz_vintage"],
                             dz_code=f"DZ{ed['dz_vintage']}", hb="HB", hscp="HSCP", ca="CA", rank=1,
                             **{c: 1 for c in BANDS.values()}, **{c: 0 for c in FLAGS.values()})
                        for ed in registry.phs_editions])
    gov = pd.DataFrame([dict(edition=ed["key"], dz_code=f"DZ{ed['dz_vintage']}",
                             uw_scotland_quintile=1, uw_scotland_decile=1, uw_scotland_vigintile=1)
                        for ed in registry.govscot_editions])
    table = pd.concat([index, attach(index, phs, gov, registry)], axis=1)[[f["name"] for f in schema["fields"]]]
    path = tmp_path / "table.parquet"
    output.write_table(table, schema, path, output.table_metadata(registry, schema, digest))
    # The main table's index: the same postcodes as whole postcodes, no nullable text.
    latest = pd.DataFrame({f["name"]: [""] * 3 for f in main_schema["fields"][:56]})
    latest["pc_norm"] = ["AB101AA", "AB101AB", "AB101AC"]
    latest["Postcode"] = ["AB10 1AA", "AB10 1AB", "AB10 1AC"]
    latest["PostcodeType"] = ["S", "L", "L"]
    latest["spd_user_type"] = ["small_user", "large_user", "large_user"]
    latest["sspl_release"] = registry.sspl_release
    latest["introduced_on"] = pd.Timestamp("2020-01-01")
    latest["deleted_on"] = pd.NaT
    latest["is_current"] = True
    latest["LinkedSmallUserPostcode"] = ["", "AB10 1AA", "NO LINKP"]
    for vintage in (2001, 2011):
        latest[f"DataZone{vintage}Code"] = f"DZ{vintage}"
    main_table = pd.concat([latest, attach(latest, phs, gov, registry)], axis=1)[[f["name"] for f in main_schema["fields"]]]
    return dict(registry=registry, schema=schema, index=index, phs=phs, gov=gov, table=table,
                path=path, decisions=decisions, digest=digest, main_schema=main_schema, latest=latest, main_table=main_table)


def read(sample):
    report = Report()
    output.readback(sample["path"], sample["schema"], sample["index"], sample["phs"], sample["gov"],
                    sample["registry"], report, decisions_sha256=sample["digest"])
    return report


def change_cell(path, column, row, value):
    table = pq.read_table(path)
    col = table.schema.get_field_index(column)
    values = table.column(col).to_pylist()
    values[row] = value
    table = table.set_column(col, table.schema.field(col), pa.array(values, type=table.schema.field(col).type))
    pq.write_table(table, path)


def test_good_file_preserves_nullable_text(sample):
    assert not read(sample).blocking_failures
    values = pq.read_table(sample["path"], columns=["LinkedSmallUserPostcode"]).column(0).to_pylist()
    assert values == [None, "AB10 1AA", ""]


@pytest.mark.parametrize("row,value", [(1, None), (2, None), (0, ""), (0, "invented")])
def test_null_and_supplied_value_are_not_equal(sample, row, value):
    change_cell(sample["path"], "LinkedSmallUserPostcode", row, value)
    assert "readback.index.LinkedSmallUserPostcode" in {c.name for c in read(sample).blocking_failures}


@pytest.mark.parametrize("column,value", [("simd2004_pw_scotland_quintile", 5),
                                         ("simd2020v2_most15pc", 1), ("phs_dz2001_hb", "WRONG")])
def test_attached_values_are_compared(sample, column, value):
    change_cell(sample["path"], column, 0, value)
    assert "readback.attached_values" in {c.name for c in read(sample).blocking_failures}


@pytest.mark.parametrize("key", ["band_convention", "schema_version", "index_release", "index_source", "allocation", "key", "sources", "decisions_sha256"])
def test_metadata_values_not_just_names_are_checked(sample, key):
    table = pq.read_table(sample["path"])
    metadata = dict(table.schema.metadata)
    metadata[key.encode()] = b"wrong"
    pq.write_table(table.replace_schema_metadata(metadata), sample["path"])
    assert f"readback.metadata.{key}" in {c.name for c in read(sample).blocking_failures}


def test_changed_expected_decisions_are_rejected(sample):
    sample["digest"] = "0" * 64
    assert "readback.metadata.decisions_sha256" in {c.name for c in read(sample).blocking_failures}


@pytest.mark.parametrize("corruption", ["null", "metadata", "schema"])
def test_failed_readback_leaves_previous_publication_untouched(sample, tmp_path, corruption):
    finals = [tmp_path / "postcode_simd.parquet", tmp_path / "postcode_simd_history.parquet"]
    for final in finals:
        final.write_bytes(b"previous output")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"previous": True}))
    cfg = {"results_root": tmp_path, "decisions": sample["decisions"],
           "spd_schema": ROOT / "simd_ingest/spd_schema.yaml", "sspl_schema": ROOT / "simd_ingest/sspl_schema.yaml"}
    original_write = output.write_table

    def corrupt_after_write(table, schema, path, metadata):
        original_write(table, schema, path, metadata)
        if corruption == "null":
            if path.name == "postcode_simd_history.parquet":  # nullable there, not in the main table
                change_cell(path, "LinkedSmallUserPostcode", 1, None)
        else:
            saved = pq.read_table(path)
            if corruption == "metadata":
                altered = dict(saved.schema.metadata)
                altered[b"band_convention"] = b"wrong"
                saved = saved.replace_schema_metadata(altered)
            else:
                saved = saved.drop(["Postcode"])
            pq.write_table(saved, path)

    with patch.object(output, "write_table", side_effect=corrupt_after_write), pytest.raises(BuildStopped):
        write_output(cfg, sample["registry"], {"history": sample["schema"], "main": sample["main_schema"]}, "offline",
                     {"history": sample["table"], "main": sample["main_table"]},
                     {"spd": sample["index"], "sspl": sample["latest"]}, sample["phs"], sample["gov"], Report(), {})
    assert all(final.read_bytes() == b"previous output" for final in finals)
    assert json.loads(manifest.read_text()) == {"previous": True}
    assert not list(tmp_path.glob(".build-*"))
