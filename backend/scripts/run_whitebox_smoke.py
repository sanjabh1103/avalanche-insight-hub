from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin


def _build_demo_dem(path: Path) -> tuple[float, float]:
    width = 128
    height = 128
    transform = from_origin(77.0, 35.0, 0.00025, 0.00025)
    rows = np.arange(height, dtype=np.float32)[:, None]
    cols = np.arange(width, dtype=np.float32)[None, :]
    dem = 4100.0 - (rows * 6.0) - (np.abs(cols - (width / 2.0)) * 0.8)
    profile = {
        'driver': 'GTiff',
        'height': height,
        'width': width,
        'count': 1,
        'dtype': 'float32',
        'crs': 'EPSG:4326',
        'transform': transform,
        'compress': 'lzw',
    }
    with rasterio.open(path, 'w', **profile) as dataset:
        dataset.write(dem.astype(np.float32), 1)
    center_row = 16
    center_col = width // 2
    lng = float(transform.c + ((center_col + 0.5) * transform.a))
    lat = float(transform.f + ((center_row + 0.5) * transform.e))
    return lat, lng


def main() -> int:
    from backend.common import runout

    if not getattr(runout, '_HAS_RASTERIO', False):
        raise RuntimeError('rasterio is unavailable; whitebox smoke cannot run')
    if not getattr(runout, '_HAS_WHITEBOX', False) and runout._whitebox_cli_bin() is None:
        raise RuntimeError('whitebox runtime is unavailable; install whitebox or whitebox_tools')

    with tempfile.TemporaryDirectory(prefix='whitebox-smoke-') as tmpdir:
        tmp_root = Path(tmpdir)
        dem_root = tmp_root / 'dem'
        dem_root.mkdir(parents=True, exist_ok=True)
        dem_path = dem_root / 'whitebox_smoke.tif'
        lat, lng = _build_demo_dem(dem_path)

        runout.RUN_PHYSICS_RUNOUT = True
        runout.DEM_ROOT = dem_root

        polygon = runout.runout_polygon_for_cell(
            region_key='whitebox_smoke',
            cell={
                'row': 0,
                'col': 0,
                'lat': lat,
                'lng': lng,
                'lat_end': lat + 0.00025,
                'lng_end': lng + 0.00025,
                'risk_score': 5,
                'probability': 0.88,
                'terrain_inputs': {
                    'slope_deg': 38.0,
                    'aspect_deg': 180.0,
                },
            },
        )
        result = {
            'status': 'ok' if polygon.method == 'alpha_beta_whitebox' and polygon.polygon else 'failed',
            'method': polygon.method,
            'polygon_vertex_count': len(polygon.polygon),
            'dem_path': str(dem_path),
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        if result['status'] != 'ok':
            raise SystemExit(2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
