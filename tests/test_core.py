"""Unit fixtures for the core rules, and integrity of the saved table where a build exists."""

from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from simd_ingest.core.checks import Report
from simd_ingest.core.fetch import FetchError, _extract_member
from simd_ingest.core.sources import load_registry, sha256, verify_root
from simd_ingest.core.spd import (active_on, classify_links, current_candidates, interval_summary,
                                  parse_dates, postcode_keys)

ROOT = Path(__file__).resolve().parent.parent


class KeyAndDateRules(unittest.TestCase):
    def test_short_split_suffix_and_large_user_flag(self):
        small = pd.DataFrame({"Postcode": ["G1 1AAA", "AB1 0LTA", "ab12 3gqa", "AB12 3GQ"], "SplitIndicator": ["Y", "Y", "Y", "N"]})
        r = postcode_keys(small, "small_user")
        self.assertEqual(r["pc_norm"].tolist(), ["G11AAA", "AB10LTA", "AB123GQA", "AB123GQ"])
        self.assertEqual(r["pc_base"].tolist(), ["G11AA", "AB10LT", "AB123GQ", "AB123GQ"])
        large = pd.DataFrame({"Postcode": ["G46 8DB"], "SplitIndicator": ["Y"]})
        r = postcode_keys(large, "large_user")
        self.assertEqual(r["pc_norm"].tolist(), r["pc_base"].tolist())

    def test_malformed_and_false_split_postcodes_fail(self):
        for postcode, split in [("AB12\t3GQ", "N"), ("AB12  3GQ", "N"), ("AB12 3GQ", "Y"), ("AB12 3GQD", "Y"), ("AB12 3GQA", "N")]:
            with self.subTest(postcode=postcode), self.assertRaises(ValueError):
                postcode_keys(pd.DataFrame({"Postcode": [postcode], "SplitIndicator": [split]}), "small_user")

    def test_same_day_record_is_kept_but_never_active(self):
        d = pd.DataFrame({"pc_norm": ["G11AA"] * 3, "spd_user_type": ["small_user", "large_user", "small_user"],
                          "DateOfIntroduction": ["1/1/2020 00:00:00", "1/2/2020 00:00:00", "1/2/2020 00:00:00"],
                          "DateOfDeletion": ["1/2/2020 00:00:00", "", "1/2/2020 00:00:00"]})
        parsed = pd.concat([d, parse_dates(d)], axis=1)
        self.assertEqual(active_on(parsed, "2020-02-01").tolist(), [False, True, False])
        self.assertEqual(active_on(parsed, "2020-01-31").tolist(), [True, False, False])
        summary, _ = interval_summary(parsed)
        self.assertEqual(summary["strict_overlaps"], 0)
        self.assertEqual(summary["touching_pairs"], 3)

    def test_nested_overlaps_are_detected(self):
        d = pd.DataFrame({"pc_norm": ["G11AA"] * 3, "spd_user_type": ["small_user"] * 3,
                          "DateOfIntroduction": ["1/1/2020 00:00:00", "1/2/2020 00:00:00", "15/3/2020 00:00:00"],
                          "DateOfDeletion": ["1/4/2020 00:00:00", "1/3/2020 00:00:00", "1/5/2020 00:00:00"]})
        summary, _ = interval_summary(pd.concat([d, parse_dates(d)], axis=1))
        self.assertEqual(summary["strict_overlaps"], 2)

    def test_invalid_dates_fail_without_fabrication(self):
        for intro, deletion in [("2/1/2020 00:00:00", "1/1/2020 00:00:00"), ("31/2/2020 00:00:00", ""), ("", ""), ("1/1/2020 12:00:00", "")]:
            with self.subTest(intro=intro), self.assertRaises(ValueError):
                parse_dates(pd.DataFrame({"DateOfIntroduction": [intro], "DateOfDeletion": [deletion]}))

    def test_links_and_candidates(self):
        links = pd.Series(["NO LINKP", "NO LINK", "AB1 0NX", "ZZ1 1ZZ"])
        self.assertEqual(classify_links(links, pd.Series(["AB10NX"])).tolist(), ["NO LINKP", "NO LINK", "linked", "unresolved"])
        d = pd.DataFrame({"pc_norm": ["AB123GQA", "AB123GQB", "G11AA"], "pc_base": ["AB123GQ", "AB123GQ", "G11AA"]})
        self.assertEqual(current_candidates(d, "ab12 3gq")["selection_status"], "ambiguous")
        self.assertEqual(current_candidates(d, "G1 1AA")["selection_status"], "unique")
        self.assertEqual(current_candidates(d, "ZZ1 1ZZ")["selection_status"], "not_found")


class SourceSafety(unittest.TestCase):
    def test_registry_loads_and_wrong_bytes_fail_verification(self):
        reg = load_registry(ROOT / "simd_ingest" / "sources.yaml")
        self.assertEqual(len(reg.objects), 13)
        self.assertEqual(len(reg.files), 17)
        with tempfile.TemporaryDirectory() as temp:
            f = reg.files[0]
            path = Path(temp) / f.path
            path.parent.mkdir(parents=True)
            path.write_bytes(b"changed")
            report = Report()
            self.assertFalse(verify_root(reg, Path(temp), report))
            failed = [c.name for c in report.blocking_failures]
            self.assertIn(f"source.hash.{f.path}", failed)
            self.assertEqual(path.read_bytes(), b"changed")

    def test_archive_member_traversal_and_undeclared_members_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            z = Path(temp) / "a.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("good.csv", "x")
                zf.writestr("../evil.csv", "x")
            dest = Path(temp) / "out"
            for member in ["../evil.csv", "/abs.csv", "missing.csv"]:
                with self.subTest(member=member), self.assertRaises(FetchError):
                    _extract_member(z, member, dest)
            _extract_member(z, "good.csv", dest)
            self.assertEqual(dest.read_text(), "x")


class SavedTableIntegrity(unittest.TestCase):
    """A modified cell in the saved file must fail readback, and the good file must pass it."""

    @classmethod
    def setUpClass(cls):
        from simd_ingest.config import load_config
        from simd_ingest.pipeline import prepare
        from support import source_root, write_config
        source = source_root()
        if source is None or not (ROOT / "results" / "postcode_simd.parquet").is_file():
            raise unittest.SkipTest("no pinned sources or no build output")
        cls.temp = tempfile.mkdtemp(prefix="simd_core_")
        cls.cfg = load_config(write_config(Path(cls.temp), source, ROOT / "simd_ingest" / "decisions.yaml"))
        cls.registry, phs_tables, gov_tables, cls.index = prepare(cls.cfg, "offline", Report())
        cls.simd = pd.concat(phs_tables.values(), ignore_index=True)
        cls.gov = pd.concat(gov_tables.values(), ignore_index=True)
        from simd_ingest.core import output
        cls.output = output
        cls.schema = output.load_schema(cls.cfg["output_schema"])
        # This optional test audits an older local artifact, using its retained manifest,
        # not today's decision log. Fresh builds are tested separately.
        import json
        manifest = json.loads((ROOT / "results/manifest.json").read_text())
        if (manifest["schema_sha256"] != cls.schema["sha256"]
                or sorted(o["sha256"] for o in manifest["sources"]) != sorted(o.sha256 for o in cls.registry.objects)):
            raise unittest.SkipTest("saved artifact belongs to another source/schema contract")
        cls.decisions_sha = manifest["decisions_sha256"]

    def test_good_file_passes_and_modified_cell_fails(self):
        path = ROOT / "results" / "postcode_simd.parquet"
        report = Report()
        self.output.readback(path, self.schema, self.index, self.simd, self.gov, self.registry, report,
                             decisions_sha256=self.decisions_sha)
        self.assertEqual([c.name for c in report.blocking_failures], [])
        table = pq.read_table(path)
        with tempfile.TemporaryDirectory() as temp:
            bad = Path(temp) / "bad.parquet"
            col = table.schema.get_field_index("simd2020v2_pw_scotland_decile")
            values = table.column(col).to_pylist()
            values[123] = 10 if values[123] != 10 else 9
            import pyarrow as pa
            table2 = table.set_column(col, table.schema.field(col), pa.array(values, type=table.schema.field(col).type))
            pq.write_table(table2, bad)
            report = Report()
            self.output.readback(bad, self.schema, self.index, self.simd, self.gov, self.registry, report,
                                 decisions_sha256=self.decisions_sha)
            self.assertIn("readback.attached_values", [c.name for c in report.blocking_failures])
