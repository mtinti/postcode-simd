"""The point-in-polygon step, on shapefiles small enough to reason about by eye.

Eight squares in a row, each 20 km wide so every one straddles a 10 km cell edge, carrying
8-fold classes 1 to 8 from west to east. Everything below follows from that picture.
"""

from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import pandas as pd
import pytest
import shapely

from simd_ingest.core.checks import BuildStopped, Report
from simd_ingest.core.rurality import (NESTING, STATUS_AMBIGUOUS, STATUS_OUTSIDE, STATUS_PO_BOX, AreaLost, classify, column_names, cut,
                                         place, polygon_parts, read_version, status_name)

WIDTH = 20_000
COLUMNS = {"sixfold": "UR6FOLD", "eightfold": "UR8FOLD"}


def squares(crs=27700, sixfold=None) -> gpd.GeoDataFrame:
    eight = list(range(1, 9))
    return gpd.GeoDataFrame({"UR6FOLD": sixfold or [NESTING[c] for c in eight], "UR8FOLD": eight},
                            geometry=[shapely.box(i * WIDTH, 0, (i + 1) * WIDTH, WIDTH) for i in range(8)], crs=crs)


def version(tmp: Path, key="2022", year=2022, frame=None, polygons=8) -> dict:
    name = f"ur_{key}.shp"
    (squares() if frame is None else frame).to_file(tmp / name)
    return {"key": key, "file": name, "reference_year": year, "polygons": polygons, "columns": COLUMNS}


def polygons_of(tmp: Path, **kwargs):
    report = Report()
    return read_version(version(tmp, **kwargs), tmp, report), report


def index_of(points) -> pd.DataFrame:
    return pd.DataFrame({"GridReferenceEasting": [str(e) for e, _ in points], "GridReferenceNorthing": [str(n) for _, n in points]})


def test_a_point_gets_the_class_of_the_polygon_it_is_in(tmp_path):
    g, report = polygons_of(tmp_path)
    assert not report.blocking_failures
    out = place([5_000, 45_000, 155_000], [5_000, 5_000, 5_000], g)
    assert out.eightfold.tolist() == [1, 3, 8] and out.sixfold.tolist() == [1, 3, 6]
    assert out.status.isna().all()


def test_a_point_in_no_polygon_is_null_and_never_the_nearest(tmp_path):
    g, _ = polygons_of(tmp_path)
    out = place([5_000, 5_000], [WIDTH + 0.5, -50_000], g)       # half a metre out, and far out
    assert out.eightfold.isna().all() and out.sixfold.isna().all()
    assert out.status.tolist() == [STATUS_OUTSIDE, STATUS_OUTSIDE]


def test_a_point_on_an_edge_between_two_classes_is_null_and_says_so(tmp_path):
    g, _ = polygons_of(tmp_path)
    out = place([WIDTH], [5_000], g).iloc[0]                       # exactly between class 1 and class 2
    assert pd.isna(out.eightfold) and pd.isna(out.sixfold) and out.status == STATUS_AMBIGUOUS


def test_a_cell_edge_inside_one_polygon_changes_nothing(tmp_path):
    """The 10 km cut puts a new boundary through the middle of every square. A point exactly on
    it touches two pieces of the same polygon, which is a placement, not an ambiguity."""
    g, _ = polygons_of(tmp_path)
    out = place([10_000, 10_000, 30_000], [5_000, 10_000, 10_000], g)
    assert out.eightfold.tolist() == [1, 1, 2] and out.status.isna().all()


def test_a_point_on_an_edge_between_the_same_sixfold_class_still_needs_the_eightfold_to_agree(tmp_path):
    g, _ = polygons_of(tmp_path)
    out = place([4 * WIDTH], [5_000], g).iloc[0]                   # 8-fold 4 and 5 are both 6-fold 4
    assert out.status == STATUS_AMBIGUOUS and pd.isna(out.sixfold)


@pytest.mark.parametrize("fault,check", [("wrong_reference_system", "reference_system"), ("folds_do_not_nest", "folds_nest"),
                                         ("polygon_count", "polygons"), ("missing_column", "columns_present"),
                                         ("missing_class", "eightfold_values")])
def test_a_shapefile_that_is_not_what_was_declared_is_refused(tmp_path, fault, check):
    frame, count = squares(), 8
    if fault == "wrong_reference_system":
        frame = squares(crs=4326)
    elif fault == "folds_do_not_nest":
        frame = squares(sixfold=[1, 2, 3, 4, 5, 5, 6, 6])          # 8-fold 5 belongs to 6-fold 4
    elif fault == "polygon_count":
        count = 9
    elif fault == "missing_column":
        frame = frame.rename(columns={"UR8FOLD": "UR8Class"})
    else:
        frame = frame.iloc[:7]
        count = 7
    g, report = polygons_of(tmp_path, frame=frame, polygons=count)
    assert g is None
    assert [c.name for c in report.blocking_failures] == [f"rurality.2022.{check}"]


def test_a_self_intersecting_ring_is_repaired_and_counted_not_fatal(tmp_path):
    frame = squares()
    bowtie = shapely.Polygon([(0, 0), (WIDTH, WIDTH), (WIDTH, 0), (0, WIDTH), (0, 0)])
    assert not bowtie.is_valid
    frame.loc[0, "geometry"] = bowtie
    g, report = polygons_of(tmp_path, frame=frame)
    assert not report.blocking_failures and report.observations["rurality.2022.invalid_geometries_repaired"] == 1
    assert place([1_000], [10_000], g).eightfold.tolist() == [1]   # inside the left wing of the bowtie


def test_every_version_is_classified_in_row_order_with_shared_points_placed_once(tmp_path):
    shifted = squares().assign(UR8FOLD=list(range(8, 0, -1)))       # the same squares, classes reversed
    shifted["UR6FOLD"] = shifted.UR8FOLD.map(NESTING)
    registry = SimpleNamespace(rurality_versions=(version(tmp_path, "2003-2004", 2003), version(tmp_path, "2022", 2022, frame=shifted)))
    index = index_of([(155_000, 5_000), (5_000, 5_000), (155_000, 5_000), (5_000, 90_000)])
    index.index = [40, 10, 30, 20]                                  # an index that is neither sorted nor 0..n
    report = Report()
    out = classify(index, registry, tmp_path, report)
    assert not report.blocking_failures and out.index.tolist() == [40, 10, 30, 20]
    early, late = column_names("2003-2004"), column_names("2022")
    assert early == ("urbanrural2003_2004_6fold", "urbanrural2003_2004_8fold")
    assert out[early[1]].tolist()[:3] == [8, 1, 8] and out[late[1]].tolist()[:3] == [1, 8, 1]
    assert out[early[0]].tolist()[:3] == [6, 1, 6]
    codes = [c for c in out.columns if not c.endswith("_status")]
    assert out.loc[20, codes].isna().all() and set(map(str, out[codes].dtypes)) == {"Int8"}
    # The reason travels with the row, in both versions, and is null where the codes are present.
    assert out[status_name("2022")].fillna("placed").tolist() == ["placed", "placed", "placed", STATUS_OUTSIDE]
    assert out.loc[20, status_name("2003-2004")] == STATUS_OUTSIDE
    assert str(out[status_name("2022")].dtype) == "string"
    assert report.observations["rurality.2022.outside_polygons"] == 1
    assert report.observations["rurality.2022.ambiguous_polygons"] == 0


def test_an_ambiguous_row_keeps_its_own_status_apart_from_an_outside_one(tmp_path):
    registry = SimpleNamespace(rurality_versions=(version(tmp_path),))
    out = classify(index_of([(WIDTH, 5_000), (5_000, 90_000), (5_000, 5_000)]), registry, tmp_path, Report())
    assert out[status_name("2022")].fillna("placed").tolist() == [STATUS_AMBIGUOUS, STATUS_OUTSIDE, "placed"]


def test_polygons_nested_inside_a_collection_are_all_kept():
    """What make_valid can return for a badly broken ring: a collection holding a MultiPolygon
    beside a stray line. Unpacking one level leaves the MultiPolygon whole, and a filter on
    Polygon then drops its whole area, so an interior point reads as outside."""
    nested = shapely.GeometryCollection([
        shapely.MultiPolygon([shapely.box(0, 0, 10, 10), shapely.box(20, 0, 30, 10)]),
        shapely.GeometryCollection([shapely.box(40, 0, 50, 10), shapely.LineString([(0, 0), (5, 5)])]),
        shapely.Point(1, 1)])
    assert sorted(p.bounds[0] for p in polygon_parts(nested)) == [0, 20, 40]
    assert polygon_parts(shapely.LineString([(0, 0), (1, 1)])) == [] and polygon_parts(None) == []
    frame = gpd.GeoDataFrame({"sixfold": [1], "eightfold": [1]}, geometry=[nested], crs=27700)
    out = place([5, 25, 45, 15], [5, 5, 5, 5], frame)
    assert out.eightfold.tolist()[:3] == [1, 1, 1] and out.status.tolist()[3] == STATUS_OUTSIDE


def test_cutting_that_loses_area_stops_rather_than_nulling_points(tmp_path, monkeypatch):
    g, _ = polygons_of(tmp_path)
    assert abs(cut(g).area.sum() - g.area.sum()) < 1.0               # the real cut loses nothing
    import simd_ingest.core.rurality as module
    monkeypatch.setattr(module, "polygon_parts", lambda geometry: [] if geometry.bounds[0] == 0 else [geometry])
    with pytest.raises(AreaLost):
        cut(g)


def test_a_missing_grid_reference_stops_the_build(tmp_path):
    registry = SimpleNamespace(rurality_versions=(version(tmp_path),))
    index = index_of([(5_000, 5_000)])
    index.loc[0, "GridReferenceEasting"] = ""
    with pytest.raises(BuildStopped):
        classify(index, registry, tmp_path, Report())


def test_the_real_2022_polygons_reproduce_the_codes_the_directory_publishes():
    """The gate from the plan, kept as a regression test. The directory carries NRS's own 2022
    codes, so the method has a ground truth: thresholds were fixed before the first run at
    99.5% for current small users and 99% for every other cohort of more than 1,000 lives.
    Nothing is suppressed, and a point in no polygon counts as wrong."""
    from support import ROOT, source_root
    from simd_ingest.core.sources import load_registry
    root, table = source_root(), ROOT / "results" / "postcode_simd_history.parquet"
    if root is None or not table.is_file():
        pytest.skip("needs the pinned sources and a built history table")
    registry = load_registry(ROOT / "simd_ingest" / "sources.yaml")
    only_2022 = SimpleNamespace(rurality_versions=tuple(v for v in registry.rurality_versions if v["key"] == "2022"))
    h = pd.read_parquet(table, columns=["GridReferenceEasting", "GridReferenceNorthing", "is_current", "spd_user_type",
                                        "UrbanRural6Fold2022Code", "UrbanRural8Fold2022Code"])
    report = Report()
    out = classify(h, only_2022, root, report)
    assert not report.blocking_failures
    six, eight = column_names("2022")
    right = ((out[six].astype("string") == h.UrbanRural6Fold2022Code) & (out[eight].astype("string") == h.UrbanRural8Fold2022Code)).fillna(False)
    current_small = h.is_current & (h.spd_user_type == "small_user")
    assert right[current_small].mean() >= 0.995
    for cohort in (~h.is_current, h.spd_user_type == "large_user", ~h.is_current & (h.spd_user_type == "small_user")):
        assert cohort.sum() > 1_000 and right[cohort].mean() >= 0.99
    # Every miss is a point outside the polygons; none is a different class.
    assert out.loc[~right, eight].isna().all()
    assert report.observations["rurality.2022.ambiguous_polygons"] == 0


GATE = {"version": "2022", "sixfold": "UrbanRural6Fold2022Code", "eightfold": "UrbanRural8Fold2022Code",
        "current_small_user": 0.995, "other_cohorts": 0.99, "min_cohort": 1000}


def gated_index(points, published, link=None, user="small_user", current=True) -> pd.DataFrame:
    index = index_of(points)
    index["UrbanRural8Fold2022Code"] = [str(c) for c in published]
    index["UrbanRural6Fold2022Code"] = [str(NESTING[c]) for c in published]
    index["spd_user_type"], index["is_current"] = user, current
    index["LinkedSmallUserPostcode"] = link if link is not None else ""
    return index


def test_the_build_stops_when_the_placement_disagrees_with_the_published_codes(tmp_path):
    """Readback only proves a saved value equals its recomputation. A placement that is wrong,
    and wrong the same way twice, passed both build and audit until the build compared itself
    with the codes the directory publishes."""
    from simd_ingest.core.rurality import attach_rurality
    registry = SimpleNamespace(rurality_versions=(version(tmp_path),), rurality_published=GATE)
    points = [(5_000, 5_000), (25_000, 5_000), (45_000, 5_000), (65_000, 5_000)]      # classes 1, 2, 3, 4
    report = Report()
    out = attach_rurality(gated_index(points, [1, 2, 3, 4]), registry, tmp_path, report)
    assert not report.blocking_failures and out["urbanrural2022_8fold"].tolist() == [1, 2, 3, 4]
    assert report.observations["rurality.agreement"]["current_small_user"] == {"lives": 4, "agreement": 1.0}

    report = Report()
    with pytest.raises(BuildStopped):
        attach_rurality(gated_index(points, [8, 7, 6, 5]), registry, tmp_path, report)   # 0% agreement
    assert [c.name for c in report.blocking_failures] == ["rurality.agreement.current_small_user"]


def test_the_gate_runs_before_boxes_are_withheld_and_counts_an_outside_point_as_wrong(tmp_path):
    from simd_ingest.core.rurality import agreement_gate, attach_rurality
    registry = SimpleNamespace(rurality_versions=(version(tmp_path),), rurality_published=GATE)
    # Boxes carry published codes. Withheld first, all four would read as disagreements.
    boxes = gated_index([(5_000, 5_000)] * 4, [1, 1, 1, 1], link="NO LINKP", user="large_user")
    small = gated_index([(5_000, 5_000)], [1])
    index = pd.concat([small, boxes], ignore_index=True)
    report = Report()
    out = attach_rurality(index, registry, tmp_path, report)
    assert not report.blocking_failures
    assert report.observations["rurality.agreement"]["po_box"] == {"lives": 4, "agreement": 1.0}
    assert out["urbanrural2022_status"].fillna("placed").tolist() == ["placed"] + [STATUS_PO_BOX] * 4
    # A point in no polygon is in the denominator and is wrong, not excused.
    report = Report()
    index = gated_index([(5_000, 5_000), (5_000, 90_000)], [1, 1])
    agreement_gate(index, classify(index, registry, tmp_path, Report()), registry, report)
    assert report.observations["rurality.agreement"]["current_small_user"] == {"lives": 2, "agreement": 0.5}
    assert [c.name for c in report.blocking_failures] == ["rurality.agreement.current_small_user"]


def test_a_small_cohort_is_reported_but_only_a_large_one_is_gated(tmp_path):
    from simd_ingest.core.rurality import agreement_gate
    registry = SimpleNamespace(rurality_versions=(version(tmp_path),), rurality_published={**GATE, "min_cohort": 3})
    good = gated_index([(5_000, 5_000)] * 5, [1] * 5)
    few = gated_index([(5_000, 5_000)] * 3, [8] * 3, current=False)                      # 3 lives, not more than 3
    many = gated_index([(5_000, 5_000)] * 4, [8] * 4, current=False)
    for deleted, failures in ((few, []), (many, ["rurality.agreement.deleted_small_user"])):
        index, report = pd.concat([good, deleted], ignore_index=True), Report()
        agreement_gate(index, classify(index, registry, tmp_path, Report()), registry, report)
        assert [c.name for c in report.blocking_failures] == failures
        assert report.observations["rurality.agreement"]["deleted_small_user"]["agreement"] == 0.0


def test_an_empty_principal_cohort_is_a_failure_not_a_pass(tmp_path):
    from simd_ingest.core.rurality import agreement_gate
    registry = SimpleNamespace(rurality_versions=(version(tmp_path),), rurality_published=GATE)
    index, report = gated_index([(5_000, 5_000)], [1], current=False), Report()
    agreement_gate(index, classify(index, registry, tmp_path, Report()), registry, report)
    assert [c.name for c in report.blocking_failures] == ["rurality.agreement.current_small_users_present"]
