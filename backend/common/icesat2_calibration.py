"""ICESat-2 ATL06/08 snow-depth calibration adapter.

Uses NASA Earthdata CMR search (free login) to discover ICESat-2
granules for calibration anchoring of Wave C depth models.

ICESat-2 provides ATL06 (land ice height) and ATL08 (land vegetation
canopy height) products. For snow depth, ATL06 ground tracks serve
as calibration anchors when differenced against snow-free DEM.

Env flags:
  ICESAT2_CALIBRATION_ENABLED — master switch (default: false)
  EARTHDATA_TOKEN — NASA Earthdata bearer token
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.common.remote_sensing_adapter import (
    RemoteSensingAdapter,
    SceneData,
    SceneMetadata,
)

ICESAT2_CALIBRATION_ENABLED = os.getenv(
    'ICESAT2_CALIBRATION_ENABLED', 'false'
).lower() not in {'0', 'false', 'off', 'no'}

EARTHDATA_TOKEN = os.getenv('EARTHDATA_TOKEN', '')

CMR_BASE = 'https://cmr.earthdata.nasa.gov/search/granules.json'
ATL06_COLLECTION = 'C1997324106-NSIDC_ECS'  # ATL06 Land Ice Height
ATL08_COLLECTION = 'C2011401975-NSIDC_ECS'  # ATL08 Land Vegetation


@dataclass
class ICESat2CalibrationResult:
    """Calibration result from ICESat-2 vs DEM differencing."""

    track_id: str
    acquisition_time: datetime | None = None
    snow_depth_m: float | None = None
    uncertainty_m: float = 0.1
    lat: float | None = None
    lng: float | None = None
    source: str = 'icesat2_atl06'
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'track_id': self.track_id,
            'acquisition_time': self.acquisition_time.isoformat() if self.acquisition_time else None,
            'snow_depth_m': self.snow_depth_m,
            'uncertainty_m': self.uncertainty_m,
            'lat': self.lat,
            'lng': self.lng,
            'source': self.source,
            'metadata': self.metadata,
        }


class ICESat2Adapter(RemoteSensingAdapter):
    """ICESat-2 calibration adapter."""

    @property
    def sensor_name(self) -> str:
        return 'icesat2_atl06'

    def available(self) -> bool:
        """True only when flag is on AND Earthdata token is set."""
        return ICESAT2_CALIBRATION_ENABLED and bool(EARTHDATA_TOKEN)

    def query(
        self,
        *,
        region_key: str,
        bbox: tuple[float, float, float, float],
        date_range: tuple[datetime, datetime],
    ) -> list[SceneMetadata]:
        """Search CMR for ICESat-2 ATL06 granules."""
        if not ICESAT2_CALIBRATION_ENABLED:
            return []

        params = {
            'collection_concept_id': ATL06_COLLECTION,
            'bounding_box': f'{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}',
            'temporal': f'{date_range[0].isoformat()},{date_range[1].isoformat()}',
            'page_size': '20',
        }
        query_str = '&'.join(f'{k}={v}' for k, v in params.items())
        url = f'{CMR_BASE}?{query_str}'

        try:
            req = urllib.request.Request(url, headers={'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except Exception:
            return []

        results: list[SceneMetadata] = []
        for entry in data.get('feed', {}).get('entry', []):
            scene_id = entry.get('producer_granule_id') or entry.get('id', '')
            time_str = entry.get('time_start')
            acq_time = None
            if time_str:
                try:
                    acq_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                except Exception:
                    pass

            results.append(SceneMetadata(
                scene_id=scene_id,
                sensor=self.sensor_name,
                acquisition_time=acq_time,
                bbox=bbox,
                metadata={'cmr_entry': entry},
            ))

        return results

    def retrieve(self, scene_id: str) -> SceneData | None:
        """Retrieve ICESat-2 granule. Requires Earthdata token."""
        if not self.available():
            return None

        # Real download would use NSIDC DAAC with Earthdata auth
        # Stub — returns None until implementation
        return None

    def normalize(self, scene_data: SceneData) -> dict[str, Any]:
        """Normalize ICESat-2 data into verification-spine format."""
        return {
            'source': self.sensor_name,
            'snow_depth_m': None,
            'freshness_hours': None,
            'scene_id': scene_data.scene_id,
            'metadata': scene_data.metadata,
        }

    def compute_snow_depth(
        self,
        *,
        atl06_height_m: float,
        dem_height_m: float,
    ) -> float | None:
        """Compute snow depth from ICESat-2 vs DEM differencing.

        snow_depth = ATL06_elevation - snow_free_DEM_elevation
        """
        if atl06_height_m is None or dem_height_m is None:
            return None
        depth = atl06_height_m - dem_height_m
        if depth < -1.0 or depth > 10.0:
            return None  # filter unrealistic values
        return max(depth, 0.0)
