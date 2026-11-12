"""SnowEx LiDAR raster shadow adapter.

Ingests SnowEx airborne LiDAR-derived snow depth rasters (GeoTIFF) and
produces shadow-training-compatible feature values aligned to forecast grid
cells.  This adapter follows the ``RemoteSensingAdapter`` pattern but is
strictly shadow-only — it cannot promote a public forecast.

Data source: NSIDC SnowEx campaigns (airborne LiDAR snow depth).
https://nsidc.org/data/snowex

Env flags:
  SNOWEX_LIDAR_ENABLED — master switch (default: false)
  SNOWEX_DATA_DIR — local directory containing SnowEx GeoTIFF rasters
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from backend.common.remote_sensing_adapter import RemoteSensingAdapter, SceneData
from backend.common.supabase_io import has_supabase_credentials, rest_insert, rest_upsert

logger = logging.getLogger(__name__)

SNOWEX_LIDAR_ENABLED = os.getenv('SNOWEX_LIDAR_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}
SNOWEX_DATA_DIR = os.getenv('SNOWEX_DATA_DIR', '')
SNOWEX_SOURCE_URL = os.getenv('SNOWEX_SOURCE_URL', 'https://nsidc.org/data/snowex')
SNOWEX_DOI = os.getenv('SNOWEX_DOI', '')
DATE_IN_NAME_RE = re.compile(r'(20\d{2}-\d{2}-\d{2})')


@dataclass(frozen=True)
class SnowExRasterCell:
    """A single grid cell's LiDAR-derived snow depth statistics."""
    region_key: str
    cell_row: int
    cell_col: int
    forecast_date: str
    snow_depth_mean_m: float
    snow_depth_std_m: float
    snow_depth_p25_m: float
    snow_depth_p50_m: float
    snow_depth_p75_m: float
    n_valid_pixels: int
    acquisition_time_utc: str
    source_hash: str
    source: str = 'snowex_lidar'
    scene_source_hash: str = ''
    source_url: str = SNOWEX_SOURCE_URL
    doi: str = ''
    crs: str | None = None
    nodata_fraction: float = 0.0
    quality_state: str = 'provisional'
    synthetic: bool = False


class SnowExLiDARAdapter(RemoteSensingAdapter):
    """Shadow-only adapter for SnowEx airborne LiDAR snow depth rasters.

    Reads GeoTIFF rasters from a local directory, regrids to forecast cells,
    and produces feature values compatible with the evidence replay frame.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        data_dir: str | None = None,
    ) -> None:
        self._enabled = SNOWEX_LIDAR_ENABLED if enabled is None else enabled
        self._data_dir = SNOWEX_DATA_DIR if data_dir is None else data_dir

    @property
    def sensor_name(self) -> str:
        return 'snowex_lidar'

    def available(self) -> bool:
        return self._enabled and bool(self._data_dir) and os.path.isdir(self._data_dir)

    @staticmethod
    def _sha256_file(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, 'rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _sidecar(path: str) -> dict[str, Any]:
        sidecar_path = f'{path}.json'
        if not os.path.isfile(sidecar_path):
            return {}
        try:
            with open(sidecar_path, encoding='utf-8') as handle:
                payload = json.load(handle)
            return dict(payload) if isinstance(payload, dict) else {}
        except (OSError, ValueError, TypeError) as exc:
            logger.warning('SnowEx metadata sidecar could not be read: %s', exc)
            return {}

    @staticmethod
    def _acquisition_time(metadata: dict[str, Any], scene_id: str) -> str | None:
        value = metadata.get('acquisition_time')
        if isinstance(value, str) and value.strip():
            return value.strip()
        match = DATE_IN_NAME_RE.search(scene_id)
        if match:
            return f'{match.group(1)}T00:00:00Z'
        return None

    def query(
        self,
        *,
        region_key: str,
        forecast_date: str,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> list[dict[str, Any]]:
        """List available SnowEx rasters for the region and date."""
        if not self.available():
            return []
        results: list[dict[str, Any]] = []
        prefix = f'{region_key}_{forecast_date}'
        try:
            for fname in os.listdir(self._data_dir):
                if fname.startswith(prefix) and fname.endswith('.tif'):
                    fpath = os.path.join(self._data_dir, fname)
                    stat = os.stat(fpath)
                    sidecar = self._sidecar(fpath)
                    results.append({
                        'scene_id': fname,
                        'region_key': region_key,
                        'forecast_date': forecast_date,
                        'file_size_bytes': stat.st_size,
                        'source_sha256': self._sha256_file(fpath),
                        'acquisition_time': self._acquisition_time(sidecar, fname),
                        'source_url': sidecar.get('source_url') or SNOWEX_SOURCE_URL,
                        'doi': sidecar.get('doi') or SNOWEX_DOI,
                        'source': self.sensor_name,
                    })
        except OSError as exc:
            logger.warning('SnowEx query failed: %s', exc)
        return results

    def retrieve(self, scene_id: str) -> SceneData | None:
        """Retrieve a SnowEx raster file as SceneData."""
        if not self.available():
            return None
        fpath = os.path.join(self._data_dir, scene_id)
        if not os.path.isfile(fpath):
            return None
        sidecar = self._sidecar(fpath)
        source_hash = self._sha256_file(fpath)
        try:
            from osgeo import gdal
        except ImportError:
            try:
                import rasterio
                with rasterio.open(fpath) as ds:
                    data = ds.read(1)
                    meta = dict(ds.meta)
                    bounds = ds.bounds
                    meta.update({
                        'transform': ds.transform,
                        'crs': ds.crs,
                        'nodata': ds.nodata,
                    })
            except ImportError:
                logger.warning('Neither GDAL nor rasterio available — cannot read GeoTIFF')
                return None
        else:
            ds = gdal.Open(fpath)
            if ds is None:
                return None
            data = ds.GetRasterBand(1).ReadAsArray()
            meta = {
                'width': ds.RasterXSize,
                'height': ds.RasterYSize,
                'projection': ds.GetProjection(),
            }
            bounds = None
            ds = None

        return SceneData(
            scene_id=scene_id,
            sensor=self.sensor_name,
            raw_data=data,
            metadata={
                **meta,
                'file_path': fpath,
                'bounds': list(bounds) if bounds else None,
                'acquisition_time': self._acquisition_time(sidecar, scene_id),
                'source_sha256': source_hash,
                'source_url': sidecar.get('source_url') or SNOWEX_SOURCE_URL,
                'doi': sidecar.get('doi') or SNOWEX_DOI,
                'metadata_verified': sidecar.get('metadata_verified') is True,
            },
        )

    def normalize(self, scene_data: SceneData) -> dict[str, Any]:
        """Normalize SnowEx raster into verification-spine format."""
        data = scene_data.raw_data
        if data is None:
            return {}
        arr = np.asarray(data, dtype=np.float64)
        valid = arr[np.isfinite(arr) & (arr >= 0)]
        if valid.size == 0:
            return {}
        total_pixels = int(arr.size)
        nodata_fraction = float(1.0 - (valid.size / total_pixels)) if total_pixels else 1.0
        metadata = scene_data.metadata
        return {
            'source': self.sensor_name,
            'snow_depth_mean_m': float(np.mean(valid)),
            'snow_depth_std_m': float(np.std(valid)),
            'snow_depth_p25_m': float(np.percentile(valid, 25)),
            'snow_depth_p50_m': float(np.percentile(valid, 50)),
            'snow_depth_p75_m': float(np.percentile(valid, 75)),
            'n_valid_pixels': int(valid.size),
            'scene_id': scene_data.scene_id,
            'acquisition_time': metadata.get('acquisition_time'),
            'source_sha256': metadata.get('source_sha256'),
            'source_url': metadata.get('source_url') or SNOWEX_SOURCE_URL,
            'doi': metadata.get('doi') or SNOWEX_DOI,
            'crs': str(metadata.get('crs')) if metadata.get('crs') is not None else None,
            'nodata_fraction': nodata_fraction,
            'quality_state': 'verified' if metadata.get('metadata_verified') is True else 'provisional',
            'synthetic': False,
        }

    @staticmethod
    def _reproject_to_forecast_grid(
        scene_data: SceneData,
        *,
        grid_size: int,
        bbox: tuple[float, float, float, float],
    ) -> np.ndarray | None:
        """Reproject a georeferenced raster to the forecast grid when possible."""
        metadata = scene_data.metadata
        source_transform = metadata.get('transform')
        source_crs = metadata.get('crs')
        if source_transform is None or source_crs is None:
            return None
        try:
            import rasterio
            from rasterio.enums import Resampling
            from rasterio.transform import from_bounds
            from rasterio.warp import reproject

            destination = np.full((grid_size, grid_size), np.nan, dtype=np.float64)
            destination_transform = from_bounds(*bbox, width=grid_size, height=grid_size)
            reproject(
                source=np.asarray(scene_data.raw_data, dtype=np.float64),
                destination=destination,
                src_transform=source_transform,
                src_crs=source_crs,
                src_nodata=metadata.get('nodata'),
                dst_transform=destination_transform,
                dst_crs='EPSG:4326',
                dst_nodata=np.nan,
                resampling=Resampling.average,
            )
            return destination
        except (ImportError, TypeError, ValueError, RuntimeError) as exc:
            logger.warning('SnowEx raster reproject unavailable; using source grid: %s', exc)
            return None

    def regrid_to_cells(
        self,
        scene_data: SceneData,
        *,
        region_key: str,
        forecast_date: str,
        grid_size: int,
        bbox: tuple[float, float, float, float],
    ) -> list[SnowExRasterCell]:
        """Regrid a SnowEx raster to forecast grid cells.

        Simple equal-area binning: divides the raster into grid_size x grid_size
        cells and computes per-cell statistics.
        """
        data = scene_data.raw_data
        if data is None:
            return []
        arr = self._reproject_to_forecast_grid(
            scene_data,
            grid_size=grid_size,
            bbox=bbox,
        )
        if arr is None:
            arr = np.asarray(data, dtype=np.float64)
        h, w = arr.shape
        if h < grid_size or w < grid_size:
            logger.warning('Raster too small for grid_size=%d', grid_size)
            return []
        cell_h = h // grid_size
        cell_w = w // grid_size

        metadata = scene_data.metadata
        acquisition_time = metadata.get('acquisition_time') or ''
        scene_source_hash = str(metadata.get('source_sha256') or '')
        source_url = str(metadata.get('source_url') or SNOWEX_SOURCE_URL)
        doi = str(metadata.get('doi') or SNOWEX_DOI)
        crs = str(metadata.get('crs')) if metadata.get('crs') is not None else None
        cells: list[SnowExRasterCell] = []
        for row in range(grid_size):
            for col in range(grid_size):
                tile = arr[row * cell_h:(row + 1) * cell_h, col * cell_w:(col + 1) * cell_w]
                valid = tile[np.isfinite(tile) & (tile >= 0)]
                if valid.size == 0:
                    continue
                nodata_fraction = float(1.0 - (valid.size / tile.size)) if tile.size else 1.0
                source_hash = hashlib.sha256(
                    json.dumps({
                        'scene_id': scene_data.scene_id,
                        'scene_source_hash': scene_source_hash,
                        'region_key': region_key,
                        'row': row,
                        'col': col,
                        'n_valid': int(valid.size),
                        'mean': float(np.mean(valid)),
                        'std': float(np.std(valid)),
                    }, sort_keys=True).encode('utf-8')
                ).hexdigest()
                cells.append(SnowExRasterCell(
                    region_key=region_key,
                    cell_row=row,
                    cell_col=col,
                    forecast_date=forecast_date,
                    snow_depth_mean_m=float(np.mean(valid)),
                    snow_depth_std_m=float(np.std(valid)),
                    snow_depth_p25_m=float(np.percentile(valid, 25)),
                    snow_depth_p50_m=float(np.percentile(valid, 50)),
                    snow_depth_p75_m=float(np.percentile(valid, 75)),
                    n_valid_pixels=int(valid.size),
                    acquisition_time_utc=acquisition_time,
                    source_hash=source_hash,
                    scene_source_hash=scene_source_hash,
                    source_url=source_url,
                    doi=doi,
                    crs=crs,
                    nodata_fraction=nodata_fraction,
                    quality_state='verified' if metadata.get('metadata_verified') is True else 'provisional',
                    synthetic=False,
                ))
        return cells

    def build_scene_lineage(
        self,
        scene_data: SceneData,
        *,
        region_key: str,
    ) -> dict[str, Any]:
        """Build an append-only scene lineage row without writing to Supabase."""
        metadata = scene_data.metadata
        return {
            'region_key': region_key,
            'sensor': self.sensor_name,
            'scene_id': scene_data.scene_id,
            'acquisition_time': metadata.get('acquisition_time'),
            'coverage_state': 'available' if scene_data.raw_data is not None else 'unavailable',
            'metadata': {
                'source': self.sensor_name,
                'source_sha256': metadata.get('source_sha256'),
                'source_url': metadata.get('source_url') or SNOWEX_SOURCE_URL,
                'doi': metadata.get('doi') or SNOWEX_DOI,
                'crs': str(metadata.get('crs')) if metadata.get('crs') is not None else None,
                'shadow_only': True,
                'synthetic': False,
                'lineage_method': 'snowex_lidar_raster_v1',
            },
        }

    def build_verification_observation_rows(
        self,
        cells: list[SnowExRasterCell],
        *,
        region_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Convert cells into append-only verification observations.

        Cells without an acquisition timestamp are deliberately excluded: they
        cannot satisfy the replay freshness/alignment contract.
        """
        rows: list[dict[str, Any]] = []
        for cell in cells:
            if not cell.acquisition_time_utc.strip():
                continue
            cell_region = region_key or cell.region_key
            rows.append({
                'region_key': cell_region,
                'cell_id': f'{cell_region}:{cell.cell_row}:{cell.cell_col}',
                'sensor': self.sensor_name,
                'variable': 'snow_depth_m',
                'value': cell.snow_depth_mean_m,
                'unit': 'm',
                'uncertainty': cell.snow_depth_std_m,
                'acquisition_time': cell.acquisition_time_utc,
                'freshness_hours': None,
                'quality_state': cell.quality_state,
                'lineage': {
                    'verified': cell.quality_state == 'verified',
                    'source_hash': cell.source_hash,
                    'scene_source_hash': cell.scene_source_hash,
                    'source_url': cell.source_url,
                    'doi': cell.doi,
                    'grid_row': cell.cell_row,
                    'grid_col': cell.cell_col,
                    'crs': cell.crs,
                },
                'synthetic': False,
                'metadata': {
                    'shadow_only': True,
                    'nodata_fraction': cell.nodata_fraction,
                    'n_valid_pixels': cell.n_valid_pixels,
                    'source': self.sensor_name,
                },
            })
        return rows

    def persist_shadow_evidence(
        self,
        scene_data: SceneData,
        cells: list[SnowExRasterCell],
        *,
        region_key: str,
    ) -> dict[str, Any]:
        """Persist lineage and observations only through service-role writes."""
        if not self._enabled:
            return {'status': 'disabled', 'scene_rows': 0, 'observation_rows': 0}
        if not has_supabase_credentials():
            return {'status': 'credentials_unavailable', 'scene_rows': 0, 'observation_rows': 0}

        scene_row = self.build_scene_lineage(scene_data, region_key=region_key)
        observation_rows = self.build_verification_observation_rows(cells, region_key=region_key)
        try:
            rest_upsert(
                'remote_sensing_scenes',
                [scene_row],
                on_conflict='region_key,sensor,scene_id',
            )
            if observation_rows:
                rest_insert('verification_observations', observation_rows, returning='minimal')
        except Exception as exc:
            logger.warning('SnowEx shadow evidence persistence failed: %s', exc)
            return {
                'status': 'persistence_failed',
                'scene_rows': 0,
                'observation_rows': 0,
            }
        return {
            'status': 'ok',
            'scene_rows': 1,
            'observation_rows': len(observation_rows),
            'shadow_only': True,
        }

    def to_shadow_feature_values(
        self,
        cells: list[SnowExRasterCell],
    ) -> dict[str, dict[str, float]]:
        """Convert regridded cells to shadow-training feature_values format.

        Returns a dict keyed by ``cell_row_col`` with feature values compatible
        with the evidence replay frame's ``raw_layers.feature_values``.
        """
        features: dict[str, dict[str, float]] = {}
        for cell in cells:
            key = f'{cell.cell_row}_{cell.cell_col}'
            features[key] = {
                'snowex_snow_depth_mean_m': cell.snow_depth_mean_m,
                'snowex_snow_depth_std_m': cell.snow_depth_std_m,
                'snowex_snow_depth_p25_m': cell.snow_depth_p25_m,
                'snowex_snow_depth_p50_m': cell.snow_depth_p50_m,
                'snowex_snow_depth_p75_m': cell.snow_depth_p75_m,
            }
        return features
