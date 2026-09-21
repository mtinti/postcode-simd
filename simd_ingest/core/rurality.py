"""The Scottish Government Urban Rural Classification of every published version, placed on
each postcode life by its own grid reference.

The directory carries one classification, the 2022 one. Every version's polygons are still
published, so a life's point can be placed in each of them: the same point-in-polygon the
directory's own code reproduces on 247,770 of 247,773 lives (docs/plans/
Rurality_By_Version_Plan.md, section 2a). Nothing is interpolated or repaired into a class:

- a point inside no polygon is null, never the nearest polygon (decided 21 September 2026);
- a point inside polygons of two classes is null too, and counted, because choosing would be
  arbitrary. No published version has produced one.

Geometry is only ever British National Grid. A shapefile in any other reference system stops
the build rather than being reprojected quietly.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .checks import Report
from .sources import Registry

BNG = 27700
# Each version is eight multipolygons of up to 380,000 vertices. Cut into 10 km cells, a point
# is tested against a small piece instead: the same answers, about fifteen times faster. The
# cell edges are new boundaries, but both sides of one carry the same class by construction.
CELL = 10_000
# The 6-fold is the 8-fold with the remote and very remote classes merged. A polygon whose two
# codes break this was mislabelled at source.
NESTING = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4, 6: 5, 7: 6, 8: 6}
STATUS_OUTSIDE, STATUS_AMBIGUOUS = "outside_polygons", "ambiguous_polygons"


def column_names(key: str) -> tuple:
    """The two code columns of a version, on the pattern of simd2004_rank."""
    stem = "urbanrural" + key.replace("-", "_")
    return f"{stem}_6fold", f"{stem}_8fold"


def status_name(key: str) -> str:
    """The column saying why a version's codes are null for a row; null when they are not."""
    return "urbanrural" + key.replace("-", "_") + "_status"


def polygon_parts(geometry) -> list:
    """Every Polygon inside a geometry, however deeply nested. make_valid may return a
    GeometryCollection holding a MultiPolygon beside stray lines; one level of unpacking would
    leave that MultiPolygon whole and a type filter would then drop its entire area."""
    if geometry is None or geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [p for part in shapely.get_parts(geometry) for p in polygon_parts(part)]
    return []                                             # lines and points carry no area


def read_version(entry: dict, root: Path, report: Report) -> gpd.GeoDataFrame | None:
    """One version's polygons as (sixfold, eightfold, geometry), checked against its declaration."""
    label = f"rurality.{entry['key']}"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = gpd.read_file(Path(root) / entry["file"])
    cols = entry["columns"]
    missing = [c for c in cols.values() if c not in raw.columns]
    ok = report.equal(f"{label}.columns_present", missing, [])
    ok &= report.equal(f"{label}.reference_system", raw.crs.to_epsg() if raw.crs else None, BNG)
    ok &= report.equal(f"{label}.polygons", len(raw), entry["polygons"])
    if not ok:
        return None
    g = gpd.GeoDataFrame({"sixfold": raw[cols["sixfold"]].astype(int), "eightfold": raw[cols["eightfold"]].astype(int)},
                         geometry=raw.geometry, crs=raw.crs)
    ok &= report.equal(f"{label}.eightfold_values", sorted(g.eightfold.unique().tolist()), list(range(1, 9)))
    broken = g[g.eightfold.map(NESTING) != g.sixfold]
    ok &= report.equal(f"{label}.folds_nest", broken[["sixfold", "eightfold"]].values.tolist(), [])
    ok &= report.equal(f"{label}.geometry_present", int(g.geometry.is_empty.sum() + g.geometry.isna().sum()), 0)
    # Several versions ship self-intersecting rings. Repairing them changes no placement, but an
    # unrepaired ring can make the cell cut fail, so the repair is unconditional and counted.
    report.observe(f"{label}.invalid_geometries_repaired", int((~g.geometry.is_valid).sum()))
    g["geometry"] = g.geometry.make_valid()
    return g if ok else None


class AreaLost(ValueError):
    """Cutting the polygons changed their area: geometry was dropped, so points would go null
    for no reason a reader could see. Never tolerated."""


def cut(polygons: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The polygons split along a fixed 10 km grid. The grid is anchored at multiples of CELL,
    not at the data's own corner, so the pieces do not depend on which polygons are present.

    The pieces must cover exactly what the polygons covered. That is asserted, because the
    alternative failure is silent: a dropped area only ever shows up as outside_polygons."""
    rows = [(r.sixfold, r.eightfold, part) for r in polygons.itertuples() for part in polygon_parts(r.geometry)]
    parts = gpd.GeoDataFrame({"sixfold": [r[0] for r in rows], "eightfold": [r[1] for r in rows]},
                             geometry=[r[2] for r in rows], crs=polygons.crs)
    minx, miny, maxx, maxy = parts.total_bounds
    xs = np.arange(np.floor(minx / CELL) * CELL, maxx, CELL)
    ys = np.arange(np.floor(miny / CELL) * CELL, maxy, CELL)
    grid = gpd.GeoDataFrame(geometry=[shapely.box(x, y, x + CELL, y + CELL) for x in xs for y in ys], crs=polygons.crs)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pieces = gpd.overlay(parts, grid, how="intersection", keep_geom_type=True)
    pieces = pieces.explode(index_parts=False).reset_index(drop=True)
    before, after = float(polygons.geometry.area.sum()), float(pieces.geometry.area.sum())
    if abs(before - after) > max(1.0, before * 1e-9):     # a square metre, or a part in a billion
        raise AreaLost(f"polygons cover {before:.1f} m2 but their pieces cover {after:.1f} m2")
    return pieces


def place(easting: np.ndarray, northing: np.ndarray, polygons: gpd.GeoDataFrame) -> pd.DataFrame:
    """One row per input point, in input order: sixfold, eightfold (nullable Int8) and status
    (null when placed). A point on a shared edge intersects both neighbours; that is only a
    problem, and only reported, when they disagree."""
    pieces = cut(polygons)
    tree = shapely.STRtree(pieces.geometry.values)
    point, piece = tree.query(shapely.points(easting, northing), predicate="intersects")
    hits = pd.DataFrame({"point": point, "sixfold": pieces.sixfold.values[piece], "eightfold": pieces.eightfold.values[piece]})
    per = hits.groupby("point").agg(sixfold=("sixfold", "min"), eightfold=("eightfold", "min"),
                                    classes=("eightfold", "nunique")).reindex(range(len(easting)))
    ambiguous = (per.classes > 1).to_numpy()
    out = pd.DataFrame({"sixfold": per.sixfold.astype("Int8").mask(ambiguous), "eightfold": per.eightfold.astype("Int8").mask(ambiguous)})
    out["status"] = pd.Series(pd.NA, index=out.index, dtype="string")
    out.loc[per.classes.isna().to_numpy(), "status"] = STATUS_OUTSIDE
    out.loc[ambiguous, "status"] = STATUS_AMBIGUOUS
    return out.reset_index(drop=True)


def classify(index: pd.DataFrame, registry: Registry, root: Path, report: Report) -> pd.DataFrame:
    """Every version's two codes and its status for every row of a postcode index, aligned to
    its rows. The status is null where the codes are present and otherwise says why they are
    not, row by row: a count in the build report cannot tell a reader which rows.

    Distinct points are placed once: a fifth of lives share a point with another. Post-office
    boxes are placed like any other row; withholding their result is a policy applied by the
    caller, so that this function can be checked against the published codes unsuppressed.
    """
    e = pd.to_numeric(index["GridReferenceEasting"], errors="coerce")
    n = pd.to_numeric(index["GridReferenceNorthing"], errors="coerce")
    report.equal("rurality.points_present", int((e.isna() | n.isna()).sum()), 0)
    report.require()
    points = pd.DataFrame({"e": e.to_numpy(), "n": n.to_numpy()})
    distinct = points.drop_duplicates().reset_index(drop=True)
    back = points.merge(distinct.reset_index(names="at"), on=["e", "n"], how="left")["at"].to_numpy()
    out = pd.DataFrame(index=index.index)
    for entry in registry.rurality_versions:
        polygons = read_version(entry, root, report)
        report.require()
        placed = place(distinct.e.to_numpy(), distinct.n.to_numpy(), polygons).iloc[back]
        six, eight = column_names(entry["key"])
        out[six], out[eight] = placed.sixfold.to_numpy(), placed.eightfold.to_numpy()
        out[six], out[eight] = out[six].astype("Int8"), out[eight].astype("Int8")
        out[status_name(entry["key"])] = pd.array(placed.status.to_numpy(), dtype="string")
        label = f"rurality.{entry['key']}"
        report.observe(f"{label}.outside_polygons", int((placed.status == STATUS_OUTSIDE).sum()))
        report.observe(f"{label}.ambiguous_polygons", int((placed.status == STATUS_AMBIGUOUS).sum()))
    return out
