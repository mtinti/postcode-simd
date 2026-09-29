"""Python historical/record-level lookup tests; the latest-postcode SQL is tested separately."""

from __future__ import annotations

import unittest
import unittest.mock
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
                 ("AB10 1BF", "2004-06-01", lookup.UNIQUE, 2), ("AB10 1BF", "2008-01-01", lookup.PREVIOUS_LIFE, 2),
                 ("AB10 1BF", "2005-10-05", lookup.PREVIOUS_LIFE, 2), ("AB10 1BF", "2011-10-13", lookup.UNIQUE, 3),
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
        # 2008 falls between AB10 1BF's lives: the life that ended in 2005 is used, never the 2011 one.
        self.assertEqual(out["simd_status"].tolist(), [lookup.A_PART, lookup.UNIQUE, lookup.PREVIOUS_LIFE, lookup.A_PART, lookup.NOT_FOUND, lookup.NOT_FOUND, lookup.UNIQUE])
        self.assertEqual([None if pd.isna(v) else int(v) for v in out["simd_value"]], [5, 2, 2, 4, None, None, 2])
        self.assertEqual(out["simd_pc_norm"].tolist()[:2], ["G718BQA", "AB101BF"])
        self.assertEqual(out.attrs["simd_label"], "SIMD 2020v2, PHS population-weighted, within-Scotland quintile, 1 = most deprived, split postcodes resolved to the A part")
        reported = lookup.attach(cohort, self.t, "postcode", "event_date", edition="2020v2", split="report")
        self.assertEqual(reported["simd_status"].tolist(), [lookup.SPLIT_CONFLICT, lookup.UNIQUE, lookup.PREVIOUS_LIFE, lookup.SPLIT_CONSENSUS, lookup.NOT_FOUND, lookup.NOT_FOUND, lookup.UNIQUE])
        self.assertEqual([None if pd.isna(v) else int(v) for v in reported["simd_value"]], [None, 2, 2, 4, None, None, 2])
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
        # Changing SQL policy must not silently change existing Python consumers. The previous-
        # life fallback of 3.0.0 changed both deliberately and together: see decision
        # previous-life-fallback.
        for edition in ("2004", "2006", "2009v2", "2012", "2016"):
            self.t[f"simd{edition}_pw_scotland_quintile"] = self.t["simd2020v2_pw_scotland_quintile"]
        events = pd.DataFrame({
            "id": [1, 1, 2, 3], "postcode": ["AB10 1BF"] * 4,
            "event_date": ["2004-06-01", "2008-01-01", "2020-01-01", "1995-12-31"],
        })
        out = lookup.attach_by_era(events, self.t, "postcode", "event_date")
        self.assertEqual(out.id.tolist(), [1, 1, 2, 3])
        self.assertEqual(out.simd_edition.tolist(), ["2006", "2009v2", "2020v2", None])
        self.assertEqual(out.simd_status.tolist(), [lookup.UNIQUE, lookup.PREVIOUS_LIFE, lookup.UNIQUE, lookup.NO_EDITION])
        self.assertEqual([None if pd.isna(v) else int(v) for v in out.simd_value], [2, 2, 3, None])


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
        r = lookup.lookup(self.t, "AB10 1BF", edition="2009v2", on="2008-01-01")
        self.assertEqual((r.status, r.value), (lookup.PREVIOUS_LIFE, 3))
        self.assertEqual(r.candidates["deleted_on"].dt.strftime("%Y-%m-%d").tolist(), ["2005-10-05"])

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


def rural_fixture() -> pd.DataFrame:
    """fixture() plus two classification versions. The reused postcode's two lives sit in
    different classes, one life is outside the polygons in 2005-2006, and a PO box has none."""
    t = fixture()
    t["spd_user_type"], t["LinkedSmallUserPostcode"] = "small_user", ""
    box = pd.DataFrame([dict(pc_norm="AB991AA", pc_base="AB991AA", introduced_on=pd.Timestamp("2000-01-01"), deleted_on=pd.NaT,
                             is_current=True, simd2020v2_pw_scotland_quintile=1, spd_user_type="large_user", LinkedSmallUserPostcode="NO LINKP")])
    t = pd.concat([t, box], ignore_index=True)
    for v, codes, statuses in (("2005_2006", [7, 2, 1, 1, 3, 3, 1, None], [None, None, None, None, None, None, None, "po_box"]),
                               ("2022",      [7, 2, 1, 1, 3, 3, 1, None], [None, None, None, None, None, None, None, "po_box"])):
        t[f"urbanrural{v}_8fold"] = pd.array(codes, dtype="Int8")
        t[f"urbanrural{v}_6fold"] = pd.array([None if c is None else {1: 1, 2: 2, 3: 3, 7: 6}[c] for c in codes], dtype="Int8")
        t[f"urbanrural{v}_status"] = pd.array(statuses, dtype="string")
    t.loc[0, ["urbanrural2005_2006_6fold", "urbanrural2005_2006_8fold"]] = pd.NA      # the 2003 life, off the 2005-2006 coast
    t.loc[0, "urbanrural2005_2006_status"] = "outside_polygons"
    return t


class Rurality(unittest.TestCase):
    def setUp(self):
        self.t = rural_fixture()
        self.versions = [(2003, 2004, "2003-2004"), (2005, 2006, "2005-2006"), (2007, 2021, "2020"), (2022, 9999, "2022")]
        self.patch = unittest.mock.patch.object(lookup, "rurality_versions", return_value=self.versions)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_version_by_year_and_the_reason_when_there_is_no_code(self):
        # Only two versions exist as columns in the fixture; the windows name them by year.
        self.versions[:] = [(2005, 2021, "2005-2006"), (2022, 9999, "2022")]
        cohort = pd.DataFrame({"postcode": ["AB10 1BF", "AB10 1BF", "AB10 1BF", "G71 8BQ", "ZZ1 1ZZ", "AB10 1BF"],
                               "on": ["2005-06-01", "2012-06-01", "2023-06-01", "2023-06-01", "2023-06-01", "2001-01-01"]})
        out = lookup.attach_rurality(cohort, self.t, "postcode", "on")
        self.assertEqual(out.rurality_status.tolist(), ["outside_polygons", "unique", "unique", "a_part", "not_found", "before_first_version"])
        self.assertEqual([None if pd.isna(v) else int(v) for v in out.rurality_value], [None, 2, 2, 1, None, None])
        self.assertEqual(out.rurality_version.tolist()[:5], ["2005-2006", "2005-2006", "2022", "2022", "2022"])
        self.assertTrue(pd.isna(out.rurality_version.iloc[5]))
        eight = lookup.attach_rurality(cohort, self.t, "postcode", "on", fold=8)
        self.assertEqual(int(eight.rurality_value.iloc[1]), 2)
        self.assertIn("project choice", out.rurality_label.iloc[0])

    def test_one_version_throughout_and_current_records(self):
        cohort = pd.DataFrame({"postcode": ["AB10 1BF", "G71 8BQ"]})
        out = lookup.attach_rurality(cohort, self.t, "postcode", None, version="2022")
        self.assertEqual(out.rurality_status.tolist(), ["unique", "a_part"])
        self.assertEqual([int(v) for v in out.rurality_value], [2, 1])
        with self.assertRaises(ValueError):
            lookup.attach_rurality(cohort, self.t, "postcode", None)                 # no year and no version
        with self.assertRaises(ValueError):
            lookup.attach_rurality(cohort, self.t, "postcode", None, version="1999")
        with self.assertRaises(ValueError):
            lookup.attach_rurality(cohort, self.t, "postcode", None, version="2022", fold=3)

    def test_po_boxes_are_excluded_unless_asked_for_and_then_say_why(self):
        cohort = pd.DataFrame({"postcode": ["AB99 1AA"], "on": ["2023-01-01"]})
        self.versions[:] = [(2005, 2021, "2005-2006"), (2022, 9999, "2022")]
        self.assertEqual(lookup.attach_rurality(cohort, self.t, "postcode", "on").rurality_status.tolist(), ["not_found"])
        out = lookup.attach_rurality(cohort, self.t, "postcode", "on", include_po_boxes=True)
        self.assertEqual(out.rurality_status.tolist(), ["po_box"])
        self.assertTrue(pd.isna(out.rurality_value.iloc[0]))

    def test_a_table_without_versions_is_refused(self):
        with self.assertRaises(ValueError):
            lookup.attach_rurality(pd.DataFrame({"postcode": ["AB10 1BF"]}), fixture(), "postcode", None, version="2022")


class RuralityOnTheBuiltTable(unittest.TestCase):
    """Python and the dated SQL query choose the same record and the same version, so on
    small-user postcodes they must return the same class."""

    def test_python_agrees_with_the_dated_sql_query(self):
        if not FILE.is_file():
            self.skipTest("no built history table")
        import duckdb
        h = lookup.load(str(FILE))
        if "urbanrural2022_6fold" not in h:
            self.skipTest("the saved table predates the rurality columns")
        cases = pd.DataFrame({"id": range(1, 7),
                              "postcode": ["AB11 5FA", "AB11 5FA", "AB21 0SB", "FK17 8DS", "FK17 8DS", "TD9 7PQ"],
                              "on": pd.to_datetime(["2005-06-10", "2015-06-01", "2015-06-01", "1990-06-01", "2020-06-01", "1998-05-15"])})
        py = lookup.attach_rurality(cases, h, "postcode", "on")
        con = duckdb.connect()
        con.execute(f"CREATE VIEW postcode_simd_history AS SELECT * FROM read_parquet('{FILE}')")
        con.register("cohort", cases.rename(columns={"on": "address_date"}).assign(analysis_year=pd.array([None] * 6, dtype="Int64")))
        sql = (ROOT / "docs/sql/spd/link_as_of.sql").read_text()
        demo = ("    SELECT 1 AS id, CAST('AB11 5FA' AS varchar(32)) AS postcode,\n"
                "           CAST('2005-06-10' AS date) AS address_date, CAST(NULL AS int) AS analysis_year")
        self.assertEqual(sql.count(demo), 1)
        q = con.execute(sql.replace(demo, "    SELECT id, postcode, address_date, analysis_year FROM cohort")).df().sort_values("id")
        self.assertEqual(py.rurality_version.fillna("none").tolist(), q.rurality_version.fillna("none").tolist())
        self.assertEqual([None if pd.isna(v) else int(v) for v in py.rurality_value],
                         [None if pd.isna(v) else int(v) for v in q.rurality_6fold])
        self.assertEqual(py.rurality_status.replace({"unique": "matched", "a_part": "matched"}).tolist(), q.rurality_status.tolist())


class PreviousLife(unittest.TestCase):
    """The same rule as the dated SQL: no record valid on the date, a life that ended before
    it, so that life is used. Never a later one; never without a date; never a same-day record."""

    def test_the_last_life_before_the_date_and_never_a_later_one(self):
        t = fixture()
        for on, status, value in (("2008-01-01", lookup.PREVIOUS_LIFE, 2), ("2003-01-01", lookup.DELETED, None),
                                  ("2011-10-13", lookup.UNIQUE, 3)):
            r = lookup.lookup(t, "AB10 1BF", edition="2020v2", on=on)
            self.assertEqual((r.status, r.value), (status, value), on)
        # A same-day record never lived, so it is never the previous life.
        self.assertEqual(lookup.lookup(t, "KA6 6EY", edition="2020v2", on="2026-03-01").status, lookup.DELETED)
        # Without a date nothing falls back: a retired postcode with no current record is deleted.
        self.assertEqual(lookup.lookup(t, "KA6 6EY", edition="2020v2").status, lookup.DELETED)


class ReviewOf9fa39d4(unittest.TestCase):
    """Four faults found in review, each pinned on a table small enough to read."""

    def box_history(self) -> pd.DataFrame:
        # A linked large user in the 1990s, a PO box from 2005: the box life covers 2025.
        t = pd.DataFrame([("AB101WS", "AB101WS", "1996-04-01", "1996-12-04", False, 5, "large_user", "AB10 1XE"),
                          ("AB101WS", "AB101WS", "2005-07-20", None,         True,  4, "large_user", "NO LINKP")],
                         columns=["pc_norm", "pc_base", "introduced_on", "deleted_on", "is_current",
                                  "simd2020v2_pw_scotland_quintile", "spd_user_type", "LinkedSmallUserPostcode"])
        t["introduced_on"], t["deleted_on"] = pd.to_datetime(t["introduced_on"]), pd.to_datetime(t["deleted_on"])
        return t

    def test_an_excluded_po_box_is_not_answered_by_an_older_life(self):
        t = self.box_history()
        r = lookup.lookup(t, "AB10 1WS", edition="2020v2", on="2025-01-01")
        self.assertEqual((r.status, r.value), (lookup.NOT_FOUND, None))
        out = lookup.attach(pd.DataFrame({"pc": ["AB10 1WS", "AB10 1WS"], "on": ["2025-01-01", None]}), t, "pc", "on", edition="2020v2")
        self.assertEqual(out.simd_status.tolist(), [lookup.NOT_FOUND, lookup.MISSING_DATE])
        self.assertTrue(out.simd_value.isna().all())
        # Asked for, the box answers with its own value; the 1990s life never does.
        r = lookup.lookup(t, "AB10 1WS", edition="2020v2", on="2025-01-01", include_po_boxes=True)
        self.assertEqual((r.status, r.value), (lookup.UNIQUE, 4))
        # Before the box existed, the linked large user is still found as before.
        self.assertEqual(lookup.lookup(t, "AB10 1WS", edition="2020v2", on="1996-06-01").value, 5)

    def split_parts(self, codes, statuses) -> pd.DataFrame:
        t = pd.DataFrame({"pc_norm": ["HS65HTA", "HS65HTB"], "pc_base": ["HS65HT"] * 2,
                          "introduced_on": pd.to_datetime(["2000-01-01"] * 2), "deleted_on": pd.NaT, "is_current": True})
        t["urbanrural2005_2006_6fold"] = pd.array(codes, dtype="Int8")
        t["urbanrural2005_2006_8fold"] = pd.array(codes, dtype="Int8")
        t["urbanrural2005_2006_status"] = pd.array(statuses, dtype="string")
        return t

    def rural(self, table, split):
        with unittest.mock.patch.object(lookup, "rurality_versions", return_value=[(2005, 9999, "2005-2006")]):
            return lookup.attach_rurality(pd.DataFrame({"postcode": ["HS6 5HT"]}), table, "postcode", None,
                                          version="2005-2006", split=split).iloc[0]

    def test_split_parts_resolve_the_class_and_its_reason_together_nulls_included(self):
        mixed = self.split_parts([6, None], [None, "outside_polygons"])
        out = self.rural(mixed, "report")                     # one part has a class, the other none
        self.assertEqual(out.rurality_status, lookup.SPLIT_CONFLICT)
        self.assertTrue(pd.isna(out.rurality_value))
        out = self.rural(mixed, "a_part")
        self.assertEqual((out.rurality_status, int(out.rurality_value)), (lookup.A_PART, 6))
        outside = self.split_parts([None, None], ["outside_polygons", "outside_polygons"])
        for split in ("report", "a_part"):                    # both parts outside: found, and why it has no class
            out = self.rural(outside, split)
            self.assertEqual(out.rurality_status, "outside_polygons", split)
            self.assertTrue(pd.isna(out.rurality_value))

    def test_repeated_index_labels_and_empty_cohorts_keep_their_shape(self):
        t = fixture()
        for edition in ("2004", "2006", "2009v2", "2012", "2016"):
            t[f"simd{edition}_pw_scotland_quintile"] = t["simd2020v2_pw_scotland_quintile"]
        cohort = pd.DataFrame({"postcode": ["G71 8BQ", "AB10 1BF", "AB10 1BF"], "on": ["2020-01-01", "2004-06-01", "1990-01-01"]},
                              index=["x", "x", "y"])
        out = lookup.attach_by_era(cohort, t, "postcode", "on")
        self.assertEqual(out.index.tolist(), ["x", "x", "y"])
        self.assertEqual(out.postcode.tolist(), cohort.postcode.tolist())
        self.assertEqual(out.simd_status.tolist(), [lookup.A_PART, lookup.UNIQUE, lookup.NO_EDITION])
        empty = cohort.iloc[:0]
        self.assertEqual(len(lookup.attach_by_era(empty, t, "postcode", "on")), 0)
        self.assertEqual(len(lookup.attach(empty, t, "postcode", "on", edition="2020v2")), 0)
        rural = rural_fixture()
        with unittest.mock.patch.object(lookup, "rurality_versions", return_value=[(2005, 2021, "2005-2006"), (2022, 9999, "2022")]):
            out = lookup.attach_rurality(cohort, rural, "postcode", "on")
            self.assertEqual(out.index.tolist(), ["x", "x", "y"])
            self.assertEqual(out.postcode.tolist(), cohort.postcode.tolist())
            self.assertEqual(out.rurality_status.tolist(), ["a_part", lookup.BEFORE_FIRST_VERSION, lookup.BEFORE_FIRST_VERSION])
            self.assertEqual(len(lookup.attach_rurality(empty, rural, "postcode", "on")), 0)

    def test_a_missing_date_is_reported_as_missing_not_as_early(self):
        t = fixture()
        for edition in ("2004", "2006", "2009v2", "2012", "2016"):
            t[f"simd{edition}_pw_scotland_quintile"] = t["simd2020v2_pw_scotland_quintile"]
        cohort = pd.DataFrame({"postcode": ["AB10 1BF", "AB10 1BF"], "on": [None, "1990-01-01"]})
        self.assertEqual(lookup.attach_by_era(cohort, t, "postcode", "on").simd_status.tolist(), [lookup.MISSING_DATE, lookup.NO_EDITION])
        self.assertEqual(lookup.attach(cohort, t, "postcode", "on", edition="2020v2").simd_status.tolist()[0], lookup.MISSING_DATE)
        with unittest.mock.patch.object(lookup, "rurality_versions", return_value=[(2005, 9999, "2005-2006")]):
            out = lookup.attach_rurality(cohort, rural_fixture(), "postcode", "on")
        self.assertEqual(out.rurality_status.tolist(), [lookup.MISSING_DATE, lookup.BEFORE_FIRST_VERSION])


class ReviewCasesOnTheBuiltTable(unittest.TestCase):
    """The reviewer's own postcodes, against the built history table: Python must now say what
    the dated SQL query says."""

    def test_the_reviewed_postcodes(self):
        if not FILE.is_file():
            self.skipTest("no built history table")
        h = lookup.load(str(FILE))
        if "urbanrural2005_2006_6fold" not in h or not (h.pc_base == "AB101WS").any():
            self.skipTest("the saved table is not the 2026/2 build with rurality")
        r = lookup.lookup(h, "AB10 1WS", edition="2020v2", on="2025-01-01")
        self.assertEqual((r.status, r.value), (lookup.NOT_FOUND, None))            # SQL: po_box, no value
        cases = pd.DataFrame({"postcode": ["HS6 5HT", "PA66 6BN"]})
        report = lookup.attach_rurality(cases, h, "postcode", None, version="2005-2006", split="report")
        self.assertEqual(report.rurality_status.tolist(), [lookup.SPLIT_CONFLICT, "outside_polygons"])
        a_part = lookup.attach_rurality(cases, h, "postcode", None, version="2005-2006")
        self.assertEqual(a_part.rurality_status.tolist(), [lookup.A_PART, "outside_polygons"])   # SQL: the A part
        self.assertEqual([None if pd.isna(v) else int(v) for v in a_part.rurality_value], [6, None])
