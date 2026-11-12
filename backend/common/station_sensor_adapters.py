"""Station sensor adapters — infrasound array + X-band radar.

Thin adapter stubs implementing the RemoteSensingAdapter ABC for
Partner station-based sensors. These are interface-only stubs that
return available() -> False until Partner provides live station feeds.

Env flags:
  STATION_SENSOR_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from backend.common.remote_sensing_adapter import (
    RemoteSensingAdapter,
    SceneData,
    SceneMetadata,
)

STATION_SENSOR_ENABLED = os.getenv(
    'STATION_SENSOR_ENABLED', 'false'
).lower() not in {'0', 'false', 'off', 'no'}


class InfrasoundArrayAdapter(RemoteSensingAdapter):
    """Infrasound array avalanche detection adapter.

    Infrasound arrays detect low-frequency acoustic signals from
    avalanches and snowpack fracturing. Partner operates arrays in
    Himalayan zones.
    """

    @property
    def sensor_name(self) -> str:
        return 'infrasound_array'

    def available(self) -> bool:
        """False until Partner provides live station feed access."""
        return STATION_SENSOR_ENABLED

    def query(
        self,
        *,
        region_key: str,
        bbox: tuple[float, float, float, float],
        date_range: tuple[datetime, datetime],
    ) -> list[SceneMetadata]:
        """Query for infrasound detections. Empty until feed exists."""
        if not self.available():
            return []
        return []

    def retrieve(self, scene_id: str) -> SceneData | None:
        """Retrieve infrasound data. None until feed exists."""
        return None

    def normalize(self, scene_data: SceneData) -> dict[str, Any]:
        """Normalize infrasound data into verification-spine format."""
        return {
            'source': self.sensor_name,
            'snow_depth_m': None,
            'wet_snow_fraction': None,
            'freshness_hours': None,
            'metadata': scene_data.metadata,
        }


class XBandRadarAdapter(RemoteSensingAdapter):
    """X-band weather radar snowfall rate adapter.

    X-band radars provide high-resolution precipitation and snowfall
    rate estimates. Partner operates X-band radars at key Himalayan
    observation posts.
    """

    @property
    def sensor_name(self) -> str:
        return 'xband_radar'

    def available(self) -> bool:
        """False until Partner provides live radar feed access."""
        return STATION_SENSOR_ENABLED

    def query(
        self,
        *,
        region_key: str,
        bbox: tuple[float, float, float, float],
        date_range: tuple[datetime, datetime],
    ) -> list[SceneMetadata]:
        """Query for X-band radar scans. Empty until feed exists."""
        if not self.available():
            return []
        return []

    def retrieve(self, scene_id: str) -> SceneData | None:
        """Retrieve radar data. None until feed exists."""
        return None

    def normalize(self, scene_data: SceneData) -> dict[str, Any]:
        """Normalize X-band radar data into verification-spine format."""
        return {
            'source': self.sensor_name,
            'snow_depth_m': None,
            'loading_rate_24h': None,
            'freshness_hours': None,
            'metadata': scene_data.metadata,
        }
