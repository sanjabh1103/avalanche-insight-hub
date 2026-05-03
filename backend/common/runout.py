"""Story 18: Alpha-Beta avalanche runout physics.

Implements an OOM-safe runout polygon generator:

1. Receives high-risk cells (probability > 0.65).
2. Dynamically crops the regional DEM to a 5 km x 5 km window centered on
   each cell (Challenge OOM-fix).
3. Calls WhiteboxTools (when available) for an Alpha-Beta flow path; if the
   binary or the raster dependencies are not installed, falls back to an
   Alpha-Beta analytical polygon derived from the cell's slope angle.

The module is fully optional — if rasterio / whitebox / shapely are missing
the inference script still produces simple rectangular footprints so the
rollout never breaks. Controlled by env flag ``RUN_PHYSICS_RUNOUT`` and
availability of ``backend/data/dem/<region_key>.tif``.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

try:  # pragma: no cover - optional deps guarded by feature flag
    import rasterio
    from rasterio.features import shapes as raster_shapes
    from rasterio.windows import Window
    _HAS_RASTERIO = True
except Exception:  # pragma: no cover - fallback
    rasterio = None
    raster_shapes = None
    Window = None
    _HAS_RASTERIO = False

try:  # pragma: no cover - optional deps
    import whitebox
    _HAS_WHITEBOX = True
except Exception:  # pragma: no cover - fallback
    whitebox = None
    _HAS_WHITEBOX = False

try:  # pragma: no cover - optional deps
    import shapefile
    _HAS_SHAPEFILE = True
except Exception:  # pragma: no cover - fallback
    shapefile = None
    _HAS_SHAPEFILE = False


RUN_PHYSICS_RUNOUT = os.getenv('RUN_PHYSICS_RUNOUT', 'false').lower() in ('1', 'true', 'yes')
RUNOUT_MAX_CELLS_PER_REGION = int(os.getenv('RUNOUT_MAX_CELLS_PER_REGION', '25'))
RUNOUT_WINDOW_KM = float(os.getenv('RUNOUT_WINDOW_KM', '5.0'))
DEM_ROOT = Path(os.getenv('DEM_ROOT', 'backend/data/dem'))
WHITEBOXTOOLS_BIN = os.getenv('WHITEBOXTOOLS_BIN', '').strip()


@dataclass(frozen=True)
class RunoutPolygon:
    row: int
    col: int
    risk_score: int
    polygon: list[list[float]]
    method: str


def _coerce_probability(value: object, *, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _rectangular_polygon(lat: float, lng: float, lat_end: float, lng_end: float) -> list[list[float]]:
    return [
        [lng, lat],
        [lng_end, lat],
        [lng_end, lat_end],
        [lng, lat_end],
        [lng, lat],
    ]


def _alpha_beta_elliptical(
    *, lat: float, lng: float, slope_deg: float, aspect_deg: float, probability: float,
) -> list[list[float]]:
    """Analytical Alpha-Beta approximation used when WhiteboxTools is unavailable.

    Uses the widely-cited Lied & Bakkehoi relationship alpha ≈ 0.96 * beta − 1.4
    (degrees), where beta is the slope angle at the transition to the runout
    zone. We approximate by projecting a downslope flow vector in the aspect
    direction, scaled by probability, and wrapping a slender polygon around it.
    """
    # Translate aspect to a unit vector (meters).
    aspect_rad = math.radians(aspect_deg)
    dir_lat = -math.cos(aspect_rad)   # aspect 0 = north, so downslope is south
    dir_lng = math.sin(aspect_rad)

    beta = max(15.0, min(55.0, float(slope_deg)))
    alpha = max(10.0, 0.96 * beta - 1.4)
    # Vertical drop per meter travelled.
    runout_length_m = 300.0 + probability * 900.0  # 300 m minimum, scaled by probability
    # Width narrows for very steep beta, widens for gentler deposition zones.
    half_width_m = 40.0 + (beta - alpha) * 6.0

    meters_per_deg_lat = 111_320.0
    meters_per_deg_lng = max(1.0, meters_per_deg_lat * math.cos(math.radians(lat)))

    tip_lat = lat + (dir_lat * runout_length_m) / meters_per_deg_lat
    tip_lng = lng + (dir_lng * runout_length_m) / meters_per_deg_lng
    # Perpendicular direction for width.
    perp_lat = -dir_lng
    perp_lng = dir_lat

    def offset(base_lat: float, base_lng: float, side: float) -> list[float]:
        return [
            base_lng + side * perp_lng * half_width_m / meters_per_deg_lng,
            base_lat + side * perp_lat * half_width_m / meters_per_deg_lat,
        ]

    return [
        offset(lat, lng, +1.0),
        offset(tip_lat, tip_lng, +1.0),
        offset(tip_lat, tip_lng, -1.0),
        offset(lat, lng, -1.0),
        offset(lat, lng, +1.0),
    ]


def _whitebox_wrapper() -> object | None:
    if not _HAS_WHITEBOX:
        return None
    try:  # pragma: no cover - runtime-only wrapper setup
        wrapper = whitebox.WhiteboxTools()
    except Exception:
        return None
    try:
        wrapper.verbose = False
    except Exception:
        pass
    return wrapper


def _whitebox_cli_bin() -> str | None:
    candidate = WHITEBOXTOOLS_BIN
    if candidate and Path(candidate).exists():
        return candidate
    binary = shutil.which('whitebox_tools')
    if binary:
        return binary
    if _HAS_WHITEBOX and getattr(whitebox, '__file__', None):
        packaged = Path(str(whitebox.__file__)).resolve().parent / 'whitebox_tools'
        if packaged.exists():
            return str(packaged)
    return None


def _write_seed_points_shapefile(path: Path, *, profile: dict, row: int, col: int) -> bool:
    if not _HAS_SHAPEFILE:
        return False
    transform = profile.get('transform')
    if transform is None:
        return False
    x, y = transform * (float(col) + 0.5, float(row) + 0.5)
    with shapefile.Writer(str(path)) as writer:  # pragma: no cover - runtime-only with pyshp installed
        writer.field('id', 'N', decimal=0)
        writer.point(float(x), float(y))
        writer.record(1)
    crs = profile.get('crs')
    if crs is not None and hasattr(crs, 'to_wkt'):
        path.with_suffix('.prj').write_text(crs.to_wkt(), encoding='utf-8')
    return path.exists()


def _dilate_mask(mask: np.ndarray, *, iterations: int = 1) -> np.ndarray:
    dilated = mask.astype(bool)
    for _ in range(max(0, iterations)):
        padded = np.pad(dilated, 1, mode='constant', constant_values=False)
        next_mask = dilated.copy()
        for row_offset in (-1, 0, 1):
            for col_offset in (-1, 0, 1):
                next_mask |= padded[
                    1 + row_offset:1 + row_offset + dilated.shape[0],
                    1 + col_offset:1 + col_offset + dilated.shape[1],
                ]
        dilated = next_mask
    return dilated


def _ring_area(points: list[list[float]]) -> float:
    if len(points) < 4:
        return 0.0
    total = 0.0
    for idx in range(len(points) - 1):
        x1, y1 = points[idx]
        x2, y2 = points[idx + 1]
        total += (x1 * y2) - (x2 * y1)
    return abs(total) / 2.0


def _largest_polygon_from_mask(mask: np.ndarray, *, transform) -> Optional[list[list[float]]]:
    if raster_shapes is None:
        return None
    best_polygon: list[list[float]] | None = None
    best_area = 0.0
    for geometry, value in raster_shapes(mask.astype(np.uint8), mask=mask, transform=transform):
        if int(value) != 1:
            continue
        if geometry.get('type') != 'Polygon':
            continue
        coordinates = geometry.get('coordinates')
        if not isinstance(coordinates, list) or not coordinates:
            continue
        ring = coordinates[0]
        if not isinstance(ring, list) or len(ring) < 4:
            continue
        polygon = [[float(point[0]), float(point[1])] for point in ring]
        area = _ring_area(polygon)
        if area > best_area:
            best_area = area
            best_polygon = polygon
    return best_polygon


def _call_whitebox_wrapper(
    *,
    workdir: Path,
    crop_dem: Path,
    filled_dem: Path,
    d8_pointer: Path,
    seed_points: Path,
    flowpath_raster: Path,
) -> bool:
    wrapper = _whitebox_wrapper()
    if wrapper is None:
        return False
    try:  # pragma: no cover - runtime-only when whitebox is installed
        if hasattr(wrapper, 'set_working_dir'):
            wrapper.set_working_dir(str(workdir))
        fill_depressions = getattr(wrapper, 'fill_depressions', None) or getattr(wrapper, 'FillDepressions', None)
        d8_pointer_tool = getattr(wrapper, 'd8_pointer', None) or getattr(wrapper, 'D8Pointer', None)
        trace_flowpaths = getattr(wrapper, 'trace_downslope_flowpaths', None) or getattr(wrapper, 'TraceDownslopeFlowpaths', None)
        if not callable(fill_depressions) or not callable(d8_pointer_tool) or not callable(trace_flowpaths):
            return False
        fill_depressions(str(crop_dem), str(filled_dem), fix_flats=True)
        d8_pointer_tool(str(filled_dem), str(d8_pointer))
        trace_flowpaths(str(seed_points), str(d8_pointer), str(flowpath_raster), zero_background=True)
        return flowpath_raster.exists()
    except Exception:
        return False


def _run_whitebox_cli(command: list[str], *, workdir: Path) -> bool:
    binary = _whitebox_cli_bin()
    if binary is None:
        return False
    result = subprocess.run(
        [binary, *command],
        cwd=str(workdir),
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _call_whitebox_cli(
    *,
    workdir: Path,
    crop_dem: Path,
    filled_dem: Path,
    d8_pointer: Path,
    seed_points: Path,
    flowpath_raster: Path,
) -> bool:
    if not _run_whitebox_cli(
        ['-r=FillDepressions', '-v', f'--wd={workdir}', f'--dem={crop_dem}', f'-o={filled_dem}', '--fix_flats'],
        workdir=workdir,
    ):
        return False
    if not _run_whitebox_cli(
        ['-r=D8Pointer', '-v', f'--wd={workdir}', f'--dem={filled_dem}', f'-o={d8_pointer}'],
        workdir=workdir,
    ):
        return False
    trace_variants = [
        ['-r=TraceDownslopeFlowpaths', '-v', f'--wd={workdir}', f'--seed_pts={seed_points}', f'--d8_pntr={d8_pointer}', f'-o={flowpath_raster}', '--zero_background'],
        ['-r=TraceDownslopeFlowpaths', '-v', f'--wd={workdir}', f'--seed_pts={seed_points}', f'--flow_dir={d8_pointer}', f'--output={flowpath_raster}', '--zero_background'],
    ]
    for command in trace_variants:
        if _run_whitebox_cli(command, workdir=workdir) and flowpath_raster.exists():
            return True
    return False


def _execute_whitebox_flowpath(
    *,
    workdir: Path,
    crop_dem: Path,
    filled_dem: Path,
    d8_pointer: Path,
    seed_points: Path,
    flowpath_raster: Path,
) -> bool:
    return _call_whitebox_wrapper(
        workdir=workdir,
        crop_dem=crop_dem,
        filled_dem=filled_dem,
        d8_pointer=d8_pointer,
        seed_points=seed_points,
        flowpath_raster=flowpath_raster,
    ) or _call_whitebox_cli(
        workdir=workdir,
        crop_dem=crop_dem,
        filled_dem=filled_dem,
        d8_pointer=d8_pointer,
        seed_points=seed_points,
        flowpath_raster=flowpath_raster,
    )


def _whitebox_runout(
    *, dem_path: Path, lat: float, lng: float, probability: float,
) -> Optional[list[list[float]]]:
    """Attempt a real WhiteboxTools flow path on a bounded DEM crop.

    Returns None on any failure so the caller can fall back gracefully.
    """
    if not _HAS_RASTERIO:
        return None
    try:  # pragma: no cover - runtime-heavy path
        with rasterio.open(dem_path) as src:
            x_res = abs(float(src.res[0]))
            y_res = abs(float(src.res[1]))
            if src.crs and getattr(src.crs, 'is_geographic', False):
                meters_per_deg_lat = 111_320.0
                meters_per_deg_lng = max(1.0, meters_per_deg_lat * math.cos(math.radians(lat)))
                x_res_m = x_res * meters_per_deg_lng
                y_res_m = y_res * meters_per_deg_lat
            else:
                x_res_m = x_res
                y_res_m = y_res
            pixels_per_m = 1.0 / max(min(x_res_m, y_res_m), 1e-6)
            half_px = int(RUNOUT_WINDOW_KM * 1000.0 * pixels_per_m / 2.0)
            row, col = src.index(lng, lat)
            row_start = max(0, row - half_px)
            row_end = min(src.height, row + half_px + 1)
            col_start = max(0, col - half_px)
            col_end = min(src.width, col + half_px + 1)
            window = Window(
                col_off=col_start,
                row_off=row_start,
                width=max(1, col_end - col_start),
                height=max(1, row_end - row_start),
            )
            crop = src.read(1, window=window)
            if crop.size == 0:
                return None
            transform = src.window_transform(window)
            profile = src.profile.copy()
            profile.update(
                driver='GTiff',
                count=1,
                height=int(window.height),
                width=int(window.width),
                transform=transform,
                compress='lzw',
                tiled=False,
            )
        local_row = row - row_start
        local_col = col - col_start
        with tempfile.TemporaryDirectory(prefix='whitebox-runout-') as tmpdir:
            workdir = Path(tmpdir)
            crop_dem = workdir / 'crop_dem.tif'
            filled_dem = workdir / 'filled_dem.tif'
            d8_pointer = workdir / 'd8_pointer.tif'
            seed_points = workdir / 'seed_points.shp'
            flowpath_raster = workdir / 'flowpath.tif'

            with rasterio.open(crop_dem, 'w', **profile) as dataset:
                dataset.write(crop, 1)
            if not _write_seed_points_shapefile(seed_points, profile=profile, row=local_row, col=local_col):
                return None

            if not _execute_whitebox_flowpath(
                workdir=workdir,
                crop_dem=crop_dem,
                filled_dem=filled_dem,
                d8_pointer=d8_pointer,
                seed_points=seed_points,
                flowpath_raster=flowpath_raster,
            ):
                return None

            with rasterio.open(flowpath_raster) as traced:
                flow_mask = traced.read(1) > 0
                if not np.any(flow_mask):
                    return None
                dilated = _dilate_mask(flow_mask, iterations=1 + int(probability >= 0.8))
                polygon = _largest_polygon_from_mask(dilated, transform=traced.transform)
                return polygon
    except Exception:
        return None


def runout_polygon_for_cell(
    *,
    region_key: str,
    cell: dict,
) -> RunoutPolygon:
    """Produce a RunoutPolygon for a single high-risk cell.

    Method precedence:
        1. alpha_beta_whitebox  (requires RUN_PHYSICS_RUNOUT + DEM + WhiteboxTools)
        2. alpha_beta_elliptical (always works when slope data is present)
        3. rectangular_footprint (final safe fallback, preserves v1 behavior)
    """
    lat = float(cell['lat'])
    lng = float(cell['lng'])
    lat_end = float(cell.get('lat_end', lat))
    lng_end = float(cell.get('lng_end', lng))
    probability = _coerce_probability(cell.get('probability'), default=0.5)
    slope_deg = (
        float(cell.get('terrain_inputs', {}).get('slope_angle_deg', 0.0))
        or float(cell.get('terrain_inputs', {}).get('slope_deg', 0.0))
        or float(cell.get('slope_angle_deg', 0.0))
        or float(cell.get('slope_deg', 0.0))
    )
    aspect_deg = float(cell.get('terrain_inputs', {}).get('aspect_deg', 0.0)) or float(cell.get('aspect_deg', 0.0))
    if slope_deg <= 0:
        # If slope not supplied, derive a conservative 30° assumption so the
        # analytical polygon still renders useful downstream.
        slope_deg = 30.0

    if RUN_PHYSICS_RUNOUT:
        dem_path = DEM_ROOT / f'{region_key}.tif'
        if dem_path.exists():
            whitebox_poly = _whitebox_runout(
                dem_path=dem_path, lat=lat, lng=lng, probability=probability,
            )
            if whitebox_poly is not None:
                return RunoutPolygon(
                    row=int(cell['row']),
                    col=int(cell['col']),
                    risk_score=int(cell.get('risk_score', 0)),
                    polygon=whitebox_poly,
                    method='alpha_beta_whitebox',
                )

    try:
        analytical_poly = _alpha_beta_elliptical(
            lat=lat, lng=lng, slope_deg=slope_deg, aspect_deg=aspect_deg, probability=probability,
        )
        return RunoutPolygon(
            row=int(cell['row']),
            col=int(cell['col']),
            risk_score=int(cell.get('risk_score', 0)),
            polygon=analytical_poly,
            method='alpha_beta_elliptical',
        )
    except Exception:  # pragma: no cover - defensive
        return RunoutPolygon(
            row=int(cell['row']),
            col=int(cell['col']),
            risk_score=int(cell.get('risk_score', 0)),
            polygon=_rectangular_polygon(lat, lng, lat_end, lng_end),
            method='rectangular_footprint',
        )


def build_runout_polygons(region_key: str, cells: list[dict]) -> list[dict]:
    """Generate runout polygons for the TOP-N high-risk cells in a region.

    Hard caps at RUNOUT_MAX_CELLS_PER_REGION to keep the scheduled run bounded.
    """
    candidates = [
        cell
        for cell in cells
        if str(cell.get('status') or 'ready') == 'ready'
        and cell.get('runout_seed')
    ]
    candidates.sort(
        key=lambda cell: _coerce_probability(cell.get('probability'), default=0.0),
        reverse=True,
    )
    capped = candidates[:RUNOUT_MAX_CELLS_PER_REGION]

    polygons: list[dict] = []
    for cell in capped:
        poly = runout_polygon_for_cell(region_key=region_key, cell=cell)
        polygons.append({
            'row': poly.row,
            'col': poly.col,
            'risk_score': poly.risk_score,
            'polygon': poly.polygon,
            'method': poly.method,
        })
    # If there were more candidates than the cap, annotate the deferred tail.
    deferred = len(candidates) - len(capped)
    if deferred > 0:
        polygons.append({
            'row': -1,
            'col': -1,
            'risk_score': 0,
            'polygon': [],
            'method': 'deferred_oom_guard',
            'deferred_count': deferred,
        })
    return polygons
