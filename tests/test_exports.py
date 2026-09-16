"""The CSV rendering and the row digest a database load is checked against.

The expectations here are stated independently of the writer: the renderings are spelled out
rather than imported, so a change of convention has to be made deliberately in both places.
"""

import gzip
import json

import pandas as pd
import pytest
import yaml

from simd_ingest.core import output, text_output as tx
from simd_ingest.core.checks import Report
from simd_ingest.core.sources import sha256
from support import ROOT, known_snapshot

CONTRACT = ROOT / "simd_ingest/export_contract.yaml"
COORDINATES = {"main": ["GridReferenceEasting", "GridReferenceNorthing"],
               "history": ["GridReferenceEasting", "GridReferenceNorthing", "Latitude", "Longitude"]}
SCHEMA_OF = {"main": "output_schema.yaml", "history": "output_schema_history.yaml"}


@pytest.fixture(scope="module")
def contract():
    return tx.load_contract(CONTRACT)


def tiny_schema() -> dict:
    return {"version": "fixture", "table": "t", "index_source": "spd", "allocation": "x",
            "key": ["k"], "sha256": "none",
            "fields": [{"name": "k", "type": "string", "nullable": False, "source": "directory", "note": ""},
                       {"name": "text", "type": "string", "nullable": True, "source": "directory", "note": ""},
                       {"name": "drop_me", "type": "string", "nullable": True, "source": "directory", "note": ""},
                       {"name": "when", "type": "date32", "nullable": True, "source": "derived", "note": ""},
                       {"name": "flag", "type": "bool", "nullable": False, "source": "derived", "note": ""},
                       {"name": "count", "type": "int16", "nullable": False, "source": "govscot", "note": ""}]}


def tiny_table() -> pd.DataFrame:
    """A blank and a null side by side, a leading zero, a date and its absence."""
    return pd.DataFrame({
        "k": pd.array(["A1", "A2", "A3"], dtype="string"),
        "text": pd.array(["007", "", None], dtype="string"),
        "drop_me": pd.array(["x", "y", "z"], dtype="string"),
        "when": [pd.Timestamp("2020-01-02").date(), None, pd.Timestamp("1973-08-01").date()],
        "flag": [True, False, True],
        "count": pd.array([1, 20, 300], dtype="int16"),
    })


def tiny_contract(contract: dict) -> dict:
    spec = dict(contract)
    spec["tables"] = {"t": {"file": "t.csv.gz", "exclude": ["drop_me"], "structural_nulls": {}}}
    return spec


def test_contract_excludes_only_coordinates_and_matches_the_schemas(contract):
    assert set(contract["tables"]) == set(COORDINATES)
    for table, expected in COORDINATES.items():
        assert contract["tables"][table]["exclude"] == expected
        schema = output.load_schema(ROOT / "simd_ingest" / SCHEMA_OF[table])
        columns = tx.exported_columns(schema, contract, table)
        assert not set(expected) & set(columns)
        assert len(columns) == len(schema["fields"]) - len(expected)
        # Order is the schema's, with holes closed up.
        assert columns == [f["name"] for f in schema["fields"] if f["name"] not in set(expected)]


def test_unknown_excluded_column_is_refused(contract):
    spec = tiny_contract(contract)
    spec["tables"]["t"]["exclude"] = ["not_a_column"]
    with pytest.raises(ValueError, match="not in the schema"):
        tx.exported_columns(tiny_schema(), spec, "t")


def test_render_writes_each_type_as_stated(contract):
    spec = tiny_contract(contract)
    rendered = tx.render(tiny_table(), tiny_schema(), tx.exported_columns(tiny_schema(), spec, "t"), spec)
    assert list(rendered.columns) == ["k", "text", "when", "flag", "count"]
    assert rendered["text"].tolist() == ["007", "", "\x00"]          # leading zero, blank, null
    assert rendered["when"].tolist() == ["2020-01-02", "\x00", "1973-08-01"]
    assert rendered["flag"].tolist() == ["1", "0", "1"]
    assert rendered["count"].tolist() == ["1", "20", "300"]


@pytest.mark.parametrize("value", ["\x00", "\x1f", "a\x1fb"])
def test_reserved_characters_in_source_text_stop_the_export(contract, value):
    spec = tiny_contract(contract)
    table = tiny_table()
    table.loc[0, "text"] = value
    with pytest.raises(tx.ReservedCharacter, match="reserves"):
        tx.render(table, tiny_schema(), tx.exported_columns(tiny_schema(), spec, "t"), spec)


def test_csv_writes_null_and_blank_alike_and_reads_back(tmp_path, contract):
    spec = tiny_contract(contract)
    rendered = tx.render(tiny_table(), tiny_schema(), tx.exported_columns(tiny_schema(), spec, "t"), spec)
    path = tmp_path / "t.csv.gz"
    info = tx.write_csv(rendered, spec, path)
    assert (info["rows"], info["columns"], info["compression"]) == (3, 5, "gzip")
    assert info["sha256"] == sha256(path)
    text = gzip.decompress(path.read_bytes()).decode("utf-8")
    assert text == ("k,text,when,flag,count\n"
                    "A1,007,2020-01-02,1,1\n"
                    "A2,,,0,20\n"
                    "A3,,1973-08-01,1,300\n")
    report = Report()
    tx.readback_csv(path, rendered, spec, report, "csv.t")
    assert not report.blocking_failures


def test_the_same_rows_give_the_same_bytes(tmp_path, contract):
    spec = tiny_contract(contract)
    rendered = tx.render(tiny_table(), tiny_schema(), tx.exported_columns(tiny_schema(), spec, "t"), spec)
    first = tx.write_csv(rendered, spec, tmp_path / "a.csv.gz")
    second = tx.write_csv(rendered, spec, tmp_path / "b.csv.gz")
    assert first["sha256"] == second["sha256"]  # gzip mtime 0, not the wall clock


@pytest.mark.parametrize("column,row,value", [("text", 0, "7"), ("text", 1, "x"), ("when", 0, "2020-01-03"),
                                              ("flag", 0, "0"), ("count", 2, "30")])
def test_a_changed_cell_fails_the_readback(tmp_path, contract, column, row, value):
    spec = tiny_contract(contract)
    rendered = tx.render(tiny_table(), tiny_schema(), tx.exported_columns(tiny_schema(), spec, "t"), spec)
    path = tmp_path / "t.csv.gz"
    tx.write_csv(rendered, spec, path)
    damaged = rendered.copy()
    damaged.loc[row, column] = value
    report = Report()
    tx.readback_csv(path, damaged, spec, report, "csv.t")
    assert [c.name for c in report.blocking_failures] == ["csv.t.cells"]


@pytest.mark.parametrize("damage", ["drop_column", "truncate", "reorder"])
def test_structural_damage_fails_the_readback(tmp_path, contract, damage):
    spec = tiny_contract(contract)
    rendered = tx.render(tiny_table(), tiny_schema(), tx.exported_columns(tiny_schema(), spec, "t"), spec)
    path = tmp_path / "t.csv.gz"
    tx.write_csv(rendered, spec, path)
    lines = gzip.decompress(path.read_bytes()).decode().splitlines(keepends=True)
    if damage == "drop_column":
        body = "".join(",".join(line.rstrip("\n").split(",")[:-1]) + "\n" for line in lines)
    elif damage == "truncate":
        body = "".join(lines[:-1])
    else:
        body = "".join(",".join(reversed(line.rstrip("\n").split(","))) + "\n" for line in lines)
    path.write_bytes(gzip.compress(body.encode()))
    report = Report()
    with pytest.raises(Exception):
        tx.readback_csv(path, rendered, spec, report, "csv.t")
        report.require()


@pytest.mark.parametrize("value", ["a,b", 'a"b', "a\nb", "naïve", "𝄞clef", " padded ", "NA"])
def test_quoting_and_unicode_survive_a_round_trip(tmp_path, contract, value):
    """The real data has none of these today. The writer must still carry them."""
    spec = tiny_contract(contract)
    table = tiny_table()
    table.loc[0, "text"] = value
    rendered = tx.render(table, tiny_schema(), tx.exported_columns(tiny_schema(), spec, "t"), spec)
    path = tmp_path / "t.csv.gz"
    tx.write_csv(rendered, spec, path)
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        saved = pd.read_csv(fh, dtype=str, keep_default_na=False)
    assert saved["text"].tolist() == [value, "", ""]
    report = Report()
    tx.readback_csv(path, rendered, spec, report, "csv.t")
    assert not report.blocking_failures


# --- the digest -----------------------------------------------------------------------------

def digest_of(rows, contract):
    """The expected total, computed here from the definition, not from the writer."""
    import hashlib
    total = 0
    for row in rows:
        line = "\x1f".join(row).encode("utf-8")
        total += int.from_bytes(hashlib.sha256(line).digest()[:8], "big", signed=True)
    return str(total)


def test_digest_matches_an_independently_computed_total(contract):
    spec = tiny_contract(contract)
    rendered = tx.render(tiny_table(), tiny_schema(), tx.exported_columns(tiny_schema(), spec, "t"), spec)
    digest = tx.row_digest(rendered, spec)
    expected = [["A1", "007", "2020-01-02", "1", "1"],
                ["A2", "", "\x00", "0", "20"],
                ["A3", "\x00", "1973-08-01", "1", "300"]]
    assert (digest["rows"], digest["version"]) == (3, 1)
    assert digest["total"] == digest_of(expected, spec)
    assert isinstance(digest["total"], str)  # a JSON reader must not round it


def test_digest_does_not_depend_on_row_order(contract):
    spec = tiny_contract(contract)
    columns = tx.exported_columns(tiny_schema(), spec, "t")
    forwards = tx.row_digest(tx.render(tiny_table(), tiny_schema(), columns, spec), spec)
    backwards = tx.row_digest(tx.render(tiny_table().iloc[::-1].copy(), tiny_schema(), columns, spec), spec)
    assert forwards["total"] == backwards["total"]


@pytest.mark.parametrize("column,row,value", [
    ("text", 0, "7"),                       # a lost leading zero
    ("text", 1, None),                      # a blank turned into a null
    ("text", 2, ""),                        # a null turned into a blank
    ("when", 1, pd.Timestamp("1900-01-01").date()),   # an empty date turned into 1900-01-01
    ("k", 0, "A1 "),                        # a trailing space
    ("count", 0, 2),                        # a changed number
])
def test_digest_catches_the_corruptions_a_load_can_introduce(contract, column, row, value):
    spec = tiny_contract(contract)
    columns = tx.exported_columns(tiny_schema(), spec, "t")
    good = tx.row_digest(tx.render(tiny_table(), tiny_schema(), columns, spec), spec)
    damaged = tiny_table()
    damaged[column] = damaged[column].astype(object)
    damaged.loc[row, column] = value
    after = tx.row_digest(tx.render(damaged, tiny_schema(), columns, spec), spec)
    assert after["total"] != good["total"]


def test_digest_of_an_empty_table_is_zero(contract):
    spec = tiny_contract(contract)
    columns = tx.exported_columns(tiny_schema(), spec, "t")
    rendered = tx.render(tiny_table().iloc[:0], tiny_schema(), columns, spec)
    assert tx.row_digest(rendered, spec) | {"rows": 0, "total": "0"} == tx.row_digest(rendered, spec)


def test_digest_survives_a_row_larger_than_eight_thousand_bytes(contract):
    spec = tiny_contract(contract)
    table = tiny_table()
    table["text"] = table["text"].astype(object)
    table.loc[0, "text"] = "x" * 9000
    columns = tx.exported_columns(tiny_schema(), spec, "t")
    digest = tx.row_digest(tx.render(table, tiny_schema(), columns, spec), spec)
    assert digest["total"] != tx.row_digest(tx.render(tiny_table(), tiny_schema(), columns, spec), spec)["total"]


# --- the built tables -----------------------------------------------------------------------

@pytest.fixture(scope="module")
def manifest():
    path = ROOT / "results/manifest.json"
    if not path.is_file():
        pytest.skip("no build output")
    return json.loads(path.read_text())


@pytest.mark.parametrize("table", ["main", "history"])
def test_built_csv_matches_its_manifest_entry(manifest, contract, table):
    if "csv" not in manifest["tables"][table]:
        pytest.skip("the saved build predates the CSV export")
    entry = manifest["tables"][table]["csv"]
    path = ROOT / "results" / entry["file"]
    if not path.is_file():
        pytest.skip("no CSV beside the build")
    assert sha256(path) == entry["sha256"]
    assert entry["excluded"] == COORDINATES[table]
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
        header = pd.read_csv(fh, nrows=0).columns.tolist()
    schema = output.load_schema(ROOT / "simd_ingest" / SCHEMA_OF[table])
    assert header == tx.exported_columns(schema, contract, table)
    assert not set(COORDINATES[table]) & set(header)
    assert entry["columns"] == len(header) == manifest["tables"][table]["columns"] - len(COORDINATES[table])


@pytest.mark.parametrize("table", ["main", "history"])
def test_built_digest_recomputes_from_the_saved_table(manifest, contract, table):
    parquet = ROOT / "results" / ("postcode_simd.parquet" if table == "main" else "postcode_simd_history.parquet")
    if not parquet.is_file() or "csv" not in manifest["tables"][table]:
        pytest.skip("no build output")
    schema = output.load_schema(ROOT / "simd_ingest" / SCHEMA_OF[table])
    saved = pd.read_parquet(parquet)
    rendered = tx.render(saved, schema, tx.exported_columns(schema, contract, table), contract)
    digest = tx.row_digest(rendered, contract)
    recorded = manifest["tables"][table]["csv"]["digest"]
    assert (digest["total"], digest["rows"]) == (recorded["total"], recorded["rows"])


def test_attribution_names_every_publisher_and_both_releases(manifest, contract):
    path = ROOT / "results/CSV_README.txt"
    if not path.is_file():
        pytest.skip("no build output")
    text = path.read_text()
    assert sha256(path) == manifest["attribution"]["sha256"]
    for line in contract["attribution"]:
        assert " ".join(line.split()) in " ".join(text.split())
    assert manifest["spd_release"] in text and manifest["sspl_release"] in text
    for table, columns in COORDINATES.items():
        assert ", ".join(columns) in text
    if known_snapshot(manifest, "history"):
        assert manifest["tables"]["history"]["csv"]["sha256"] in text
