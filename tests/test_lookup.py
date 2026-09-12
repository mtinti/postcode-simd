"""Python historical/record-level lookup tests; the latest-postcode SQL is tested separately."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from simd_ingest import lookup

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "results" / "postcode_simd_history.parquet"  # dated questions need every life


def fixture() -> pd.DataFrame:
    """A tiny table: a reused postcode with two lives, a split pair, and a same-day record."""
    rows = [
        # pc_norm,   pc_base,   intro,        deleted,      current, q2020v2
        ("AB101BF", "AB101BF", "2003-04-15", "2005-10-05", False, 2),
        ("AB101BF", "AB101BF", "2011-10-13", None,         True,  3),
        ("G718BQA", "G718BQ",  "1996-04-01", None,         True,  5),
        ("G718BQB", "G718BQ",  "1996-04-01", None,         True,  2),
        ("AB123GQA", "AB123GQ", "2010-01-01", None,        True,  4),
        ("AB123GQB", "AB123GQ", "2010-01-01", None,        True,  4),
        ("KA66EYA", "KA66EY",  "2026-02-18", "2026-02-18", False, 1),
    ]
    t = pd.DataFrame(rows, columns=["pc_norm", "pc_base", "introduced_on", "deleted_on", "is_current", "simd2020v2_pw_scotland_quintile"])
    t["introduced_on"] = pd.to_datetime(t["introduced_on"])
    t["deleted_on"] = pd.to_datetime(t["deleted_on"])
    return t


class Statuses(unittest.TestCase):
    def setUp(self):
        self.t = fixture()

    def test_each_status(self):
        cases = [("ZZ1 1ZZ", None, lookup.NOT_FOUND, None), ("ab10 1bf", None, lookup.UNIQUE, 3),
                 ("AB10 1BF", "2004-06-01", lookup.UNIQUE, 2), ("AB10 1BF", "2008-01-01", lookup.DELETED, None),
                 ("AB10 1BF", "2005-10-05", lookup.DELETED, None), ("AB10 1BF", "2011-10-13", lookup.UNIQUE, 3),
                 ("G71 8BQ", None, lookup.A_PART, 5), ("G71 8BQA", None, lookup.UNIQUE, 5), ("G71 8BQB", None, lookup.UNIQUE, 2),
                 ("AB12 3GQ", None, lookup.A_PART, 4), ("KA6 6EY", "2026-02-18", lookup.DELETED, None)]
        for postcode, on, status, value in cases:
            with self.subTest(postcode=postcode, on=on):
                r = lookup.lookup(self.t, postcode, edition="2020v2", on=on)
                self.assertEqual((r.status, r.value), (status, value))
        # The report rule refuses to choose.
        r = lookup.lookup(self.t, "G71 8BQ", edition="2020v2", split="report")
        self.assertEqual((r.status, r.value), (lookup.SPLIT_CONFLICT, None))
        r = lookup.lookup(self.t, "AB12 3GQ", edition="2020v2", split="report")
        self.assertEqual((r.status, r.value), (lookup.SPLIT_CONSENSUS, 4))
        with self.assertRaises(ValueError):
            lookup.lookup(self.t, "G71 8BQ", edition="2020v2", split="majority")

    def test_attach_keeps_every_row_in_order(self):
        cohort = pd.DataFrame({"id": [1, 2, 3, 4, 5, 6, 7],
                               "postcode": ["G71 8BQ", "AB10 1BF", "AB10 1BF", "AB12 3GQ", None, "ZZ1 1ZZ", "G71 8BQB"],
                               "event_date": ["2020-01-01", "2004-06-01", "2008-01-01", "2020-01-01", "2020-01-01", "2020-01-01", "2020-01-01"]})
        out = lookup.attach(cohort, self.t, "postcode", "event_date", edition="2020v2")
        self.assertEqual(out["id"].tolist(), cohort["id"].tolist())
        self.assertEqual(out["simd_status"].tolist(), [lookup.A_PART, lookup.UNIQUE, lookup.DELETED, lookup.A_PART, lookup.NOT_FOUND, lookup.NOT_FOUND, lookup.UNIQUE])
        self.assertEqual([None if pd.isna(v) else int(v) for v in out["simd_value"]], [5, 2, None, 4, None, None, 2])
        self.assertEqual(out["simd_pc_norm"].tolist()[:2], ["G718BQA", "AB101BF"])
        self.assertEqual(out.attrs["simd_label"], "SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived, split postcodes resolved to the A part")
        reported = lookup.attach(cohort, self.t, "postcode", "event_date", edition="2020v2", split="report")
        self.assertEqual(reported["simd_status"].tolist(), [lookup.SPLIT_CONFLICT, lookup.UNIQUE, lookup.DELETED, lookup.SPLIT_CONSENSUS, lookup.NOT_FOUND, lookup.NOT_FOUND, lookup.UNIQUE])
        self.assertEqual([None if pd.isna(v) else int(v) for v in reported["simd_value"]], [None, 2, None, 4, None, None, 2])
        current = lookup.attach(cohort, self.t, "postcode", None, edition="2020v2")
        self.assertEqual(current["simd_status"].tolist()[1:3], [lookup.UNIQUE, lookup.UNIQUE])

    def test_latest_life_table_refuses_dates_and_needs_no_pc_base(self):
        latest = self.t[self.t["is_current"] & self.t["pc_norm"].eq(self.t["pc_base"])].drop(columns="pc_base")
        latest.attrs["index_source"] = "sspl"
        self.assertEqual(lookup.lookup(latest, "AB10 1BF", edition="2020v2").value, 3)
        with self.assertRaises(ValueError):
            lookup.lookup(latest, "AB10 1BF", edition="2020v2", on="2020-01-01")
        events = pd.DataFrame({"postcode": ["AB10 1BF"], "day": ["2020-01-01"]})
        with self.assertRaises(ValueError):
            lookup.attach(events, latest, "postcode", "day", edition="2020v2")
        self.assertEqual(lookup.attach(events, latest, "postcode", None, edition="2020v2")["simd_value"].tolist(), [3])

    def test_recommended_edition_and_labels(self):
        self.assertEqual([lookup.recommended_edition(y) for y in (1996, 2003, 2004, 2007, 2010, 2014, 2017, 2026)],
                         ["2004", "2004", "2006", "2009v2", "2012", "2016", "2020v2", "2020v2"])
        with self.assertRaises(ValueError):
            lookup.recommended_edition(1995)
        self.assertEqual(lookup.label("simd2004_uw_scotland_decile", "report"), "SIMD 2004, Scottish Government unweighted, within-Scotland decile, 1 = most deprived, split postcodes reported")
        self.assertEqual(lookup.label("simd2016_pw_hb_quintile"), "SIMD 2016, PHS population-weighted, within-NHS-Board quintile, 1 = most deprived, split postcodes resolved to the A part")
        self.assertEqual(lookup.label("simd2012_rank", "report"), "SIMD 2012 rank, 1 = most deprived, split postcodes reported")

    def test_by_era_keeps_python_historical_policy(self):
        # Changing SQL policy must not silently change existing Python consumers.
        for edition in ("2004", "2006", "2009v2", "2012", "2016"):
            self.t[f"simd{edition}_pw_scotland_quintile"] = self.t["simd2020v2_pw_scotland_quintile"]
        events = pd.DataFrame({
            "id": [1, 1, 2, 3], "postcode": ["AB10 1BF"] * 4,
            "event_date": ["2004-06-01", "2008-01-01", "2020-01-01", "1995-12-31"],
        })
        out = lookup.attach_by_era(events, self.t, "postcode", "event_date")
        self.assertEqual(out.id.tolist(), [1, 1, 2, 3])
        self.assertEqual(out.simd_edition.tolist(), ["2006", "2009v2", "2020v2", None])
        self.assertEqual(out.simd_status.tolist(), [lookup.UNIQUE, lookup.DELETED, lookup.UNIQUE, lookup.NO_EDITION])
        self.assertEqual([None if pd.isna(v) else int(v) for v in out.simd_value], [2, None, 3, None])


@unittest.skipUnless(FILE.is_file(), "no build output")
class RealFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        from support import known_snapshot
        manifest = json.loads((ROOT / "results/manifest.json").read_text())
        if known_snapshot(manifest) is None:
            raise unittest.SkipTest("documented 2026/2 examples do not apply to this snapshot")
        cls.t = lookup.load(FILE)

    def test_documented_examples(self):
        r = lookup.lookup(self.t, "G71 8BQ", edition="2020v2")
        self.assertEqual((r.status, r.value), (lookup.A_PART, 5))
        self.assertEqual(sorted(r.candidates["simd2020v2_pw_scotland_quintile"]), [2, 5])
        self.assertEqual(lookup.lookup(self.t, "G71 8BQ", edition="2020v2", split="report").status, lookup.SPLIT_CONFLICT)
        r = lookup.lookup(self.t, "AB12 3GQ", edition="2020v2")
        self.assertEqual((r.status, r.value), (lookup.A_PART, 4))
        self.assertEqual((lookup.lookup(self.t, "AB12 3GQ", edition="2020v2", measure="rank").status, lookup.lookup(self.t, "AB12 3GQ", edition="2020v2", measure="rank").value), (lookup.A_PART, 5484))
        self.assertEqual(lookup.lookup(self.t, "AB12 3GQ", edition="2020v2", measure="rank", split="report").status, lookup.SPLIT_CONFLICT)
        self.assertEqual(lookup.lookup(self.t, "AB12 3GQ", edition="2020v2", split="report").status, lookup.SPLIT_CONSENSUS)
        r = lookup.lookup(self.t, "AB10 1BF", edition="2006", on="2004-06-01")
        self.assertEqual(r.status, lookup.UNIQUE)
        self.assertEqual(lookup.lookup(self.t, "AB10 1BF", edition="2009v2", on="2008-01-01").status, lookup.DELETED)

    def test_ambiguous_current_postcodes_split_into_consensus_and_conflict(self):
        current = self.t[self.t["is_current"]]
        multi = current.groupby("pc_base").size()
        multi = multi[multi > 1].index
        default = [lookup.lookup(self.t, base, edition="2020v2", measure="rank").status for base in multi]
        self.assertEqual(len(default), 226)
        self.assertEqual(default.count(lookup.A_PART), 226)
        reported = [lookup.lookup(self.t, base, edition="2020v2", measure="rank", split="report").status for base in multi]
        self.assertEqual(reported.count(lookup.SPLIT_CONFLICT), 203)
        self.assertEqual(reported.count(lookup.SPLIT_CONSENSUS), 23)


if __name__ == "__main__":
    unittest.main()
