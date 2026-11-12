"""Source-agnostic remote sensing adapter ABC.

Defines the contract for all remote sensing source adapters:
  - query: search for available scenes
  - retrieve: fetch scene data
  - normalize: convert to SensorReading for fusion/anomaly detection

All adapters implement this ABC so the verification spine can treat
S1, S2, NISAR, ICESat-2, and station sensors uniformly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SceneMetadata:
    """Metadata for a remote sensing scene."""

    scene_id: str
    sensor: str
    acquisition_time: datetime | None = None
    orbit: str | None = None
    cloud_cover: float | None = None
    coverage_state: str | None = None
    eecu_cost: float | None = None
    task_id: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneData:
    """Retrieved scene data ready for normalization."""

    scene_id: str
    sensor: str
    raw_data: Any | None = None
    bands: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class RemoteSensingAdapter(ABC):
    """Abstract base class for remote sensing source adapters."""

    @property
    @abstractmethod
    def sensor_name(self) -> str:
        """Human-readable sensor name (e.g. 'sentinel1', 'sentinel2')."""
        ...

    @abstractmethod
    def available(self) -> bool:
        """Check if this adapter has the credentials/config to operate."""
        ...

    @abstractmethod
    def query(
        self,
        *,
        region_key: str,
        bbox: tuple[float, float, float, float],
        date_range: tuple[datetime, datetime],
    ) -> list[SceneMetadata]:
        """Search for available scenes matching the criteria."""
        ...

    @abstractmethod
    def retrieve(self, scene_id: str) -> SceneData | None:
        """Retrieve scene data by scene ID. Returns None if unavailable."""
        ...

    @abstractmethod
    def normalize(self, scene_data: SceneData) -> dict[str, Any]:
        """Normalize scene data into verification-spine-compatible dict.

        Returns a dict with keys like 'snow_cover_fraction', 'snow_depth_m',
        'wet_snow_fraction', 'freshness_hours', etc.
        """
        ...
