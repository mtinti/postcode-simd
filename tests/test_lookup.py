"""Fixtures for every lookup status, and the documented examples against the real file."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from simd_ingest import lookup

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "results" / "postcode_simd.parquet"


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
                 ("G71 8BQ", None, lookup.SPLIT_CONFLICT, None), ("G71 8BQA", None, lookup.UNIQUE, 5),
                 ("AB12 3GQ", None, lookup.SPLIT_CONSENSUS, 4), ("KA6 6EY", "2026-02-18", lookup.DELETED, None)]
        for postcode, on, status, value in cases:
            with self.subTest(postcode=postcode, on=on):
                r = lookup.lookup(self.t, postcode, edition="2020v2", on=on)
                self.assertEqual((r.status, r.value), (status, value))

    def test_attach_keeps_every_row_in_order(self):
        cohort = pd.DataFrame({"id": [1, 2, 3, 4, 5, 6, 7],
                               "postcode": ["G71 8BQ", "AB10 1BF", "AB10 1BF", "AB12 3GQ", None, "ZZ1 1ZZ", "G71 8BQB"],
                               "event_date": ["2020-01-01", "2004-06-01", "2008-01-01", "2020-01-01", "2020-01-01", "2020-01-01", "2020-01-01"]})
        out = lookup.attach(cohort, self.t, "postcode", "event_date", edition="2020v2")
        self.assertEqual(out["id"].tolist(), cohort["id"].tolist())
        self.assertEqual(out["simd_status"].tolist(), [lookup.SPLIT_CONFLICT, lookup.UNIQUE, lookup.DELETED, lookup.SPLIT_CONSENSUS, lookup.NOT_FOUND, lookup.NOT_FOUND, lookup.UNIQUE])
        self.assertEqual([None if pd.isna(v) else int(v) for v in out["simd_value"]], [None, 2, None, 4, None, None, 2])
        self.assertEqual(out["simd_pc_norm"].tolist()[1], "AB101BF")
        self.assertEqual(out.attrs["simd_label"], "SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived")
        current = lookup.attach(cohort, self.t, "postcode", None, edition="2020v2")
        self.assertEqual(current["simd_status"].tolist()[1:3], [lookup.UNIQUE, lookup.UNIQUE])

    def test_recommended_edition_and_labels(self):
        self.assertEqual([lookup.recommended_edition(y) for y in (1996, 2003, 2004, 2007, 2010, 2014, 2017, 2026)],
                         ["2004", "2004", "2006", "2009v2", "2012", "2016", "2020v2", "2020v2"])
        with self.assertRaises(ValueError):
            lookup.recommended_edition(1995)
        self.assertEqual(lookup.label("simd2004_uw_scotland_decile"), "SIMD 2004, Scottish Government unweighted, within-Scotland decile, 1 = most deprived")
        self.assertEqual(lookup.label("simd2016_pw_hb_quintile"), "SIMD 2016, PHS population-weighted, within-NHS-Board quintile, 1 = most deprived")
        self.assertEqual(lookup.label("simd2012_rank"), "SIMD 2012 rank, 1 = most deprived")


@unittest.skipUnless(FILE.is_file(), "no build output")
class RealFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = lookup.load(FILE)

    def test_documented_examples(self):
        r = lookup.lookup(self.t, "G71 8BQ", edition="2020v2")
        self.assertEqual(r.status, lookup.SPLIT_CONFLICT)
        self.assertEqual(sorted(r.candidates["simd2020v2_pw_scotland_quintile"]), [2, 5])
        r = lookup.lookup(self.t, "AB12 3GQ", edition="2020v2")
        self.assertEqual((r.status, r.value), (lookup.SPLIT_CONSENSUS, 4))
        self.assertEqual(lookup.lookup(self.t, "AB12 3GQ", edition="2020v2", measure="rank").status, lookup.SPLIT_CONFLICT)
        r = lookup.lookup(self.t, "AB10 1BF", edition="2006", on="2004-06-01")
        self.assertEqual(r.status, lookup.UNIQUE)
        self.assertEqual(lookup.lookup(self.t, "AB10 1BF", edition="2009v2", on="2008-01-01").status, lookup.DELETED)

    def test_ambiguous_current_postcodes_split_into_consensus_and_conflict(self):
        current = self.t[self.t["is_current"]]
        multi = current.groupby("pc_base").size()
        multi = multi[multi > 1].index
        statuses = [lookup.lookup(self.t, base, edition="2020v2", measure="rank").status for base in multi]
        self.assertEqual(len(statuses), 226)
        self.assertEqual(statuses.count(lookup.SPLIT_CONFLICT), 203)
        self.assertEqual(statuses.count(lookup.SPLIT_CONSENSUS), 23)



@unittest.skipUnless(FILE.is_file(), "no build output")
class ByEraPythonAndSqlAgree(unittest.TestCase):
    """The SQL in docs/sql/link_by_era.sql and lookup.attach_by_era give the same answer on a
    synthetic cohort drawn from the real directory: current and deleted postcodes, split parts,
    full NRS keys, unknown and missing postcodes, and dates from before SIMD to today."""

    @classmethod
    def setUpClass(cls):
        import duckdb
        import numpy as np
        cls.t = lookup.load(FILE)
        rng = np.random.default_rng(20260911)
        t = cls.t
        bases = pd.concat([t.loc[t["is_current"], "pc_base"].drop_duplicates().sample(1200, random_state=1),
                           t.loc[~t["is_current"], "pc_base"].drop_duplicates().sample(400, random_state=2),
                           t.loc[t["pc_norm"] != t["pc_base"], "pc_norm"].drop_duplicates().sample(150, random_state=3),
                           t.loc[t["pc_norm"] != t["pc_base"], "pc_base"].drop_duplicates().sample(150, random_state=4)])
        keys = bases.tolist() + ["ZZ1 1ZZ"] * 20 + [None] * 20
        dates = pd.to_datetime("1994-01-01") + pd.to_timedelta(rng.integers(0, 365 * 32, len(keys)), unit="D")
        # Write postcodes the way people do: a space before the inward code, mixed case.
        written = [None if k is None else (k[:-3].lower() + " " + k[-3:]) if len(k) <= 7 else (k[:-4] + " " + k[-4:]) for k in keys]
        cls.events = pd.DataFrame({"id": range(1, len(keys) + 1), "postcode": written, "event_date": dates}).sample(frac=1, random_state=5).reset_index(drop=True)
        cls.py = lookup.attach_by_era(cls.events, t, "postcode", "event_date")
        con = duckdb.connect()
        con.execute(f"CREATE VIEW postcode_simd AS SELECT * FROM '{FILE}'")
        con.register("events", cls.events)
        cls.sql = con.execute((ROOT / "docs" / "sql" / "link_by_era.sql").read_text()).df()

    def test_same_status_value_and_key_for_every_event(self):
        py = self.py.sort_values("id").reset_index(drop=True)
        sql = self.sql.sort_values("id").reset_index(drop=True)
        self.assertEqual(len(py), len(sql))
        self.assertEqual(py["simd_status"].tolist(), sql["simd_status"].tolist())
        norm = lambda s: [None if pd.isna(v) else int(v) for v in s]
        self.assertEqual(norm(py["simd_value"]), norm(sql["simd_value"]))
        self.assertEqual([None if pd.isna(v) else v for v in py["simd_pc_norm"]], [None if pd.isna(v) else v for v in sql["simd_pc_norm"]])
        self.assertEqual([None if pd.isna(v) else v for v in py["simd_edition"]], [None if pd.isna(v) else v for v in sql["simd_edition"]])
        counts = py["simd_status"].value_counts()
        self.assertTrue(set(lookup.STATUSES) <= set(counts.index), counts.to_dict())

if __name__ == "__main__":
    unittest.main()
