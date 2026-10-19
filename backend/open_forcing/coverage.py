"""Deterministic source-point coverage planning for the research lane.

This module plans which native source points cover an AOI. It does not fetch
data, interpolate missing values, or claim that a target grid has target-grid
information content. A complete plan means only that every target cell has a
nearest native source point within the configured assignment radius.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from .contracts import OpenForcingContractError, ensure_utc


_EARTH_RADIUS_M = 6_371_000.0
_LICENSE_REVIEW_STATUSES = {"pending", "approved", "rejected"}


@dataclass(frozen=True)
class AoiBounds:
    min_latitude: float
    min_longitude: float
    max_latitude: float
    max_longitude: float

    def validate(self) -> None:
        if not (-90.0 <= self.min_latitude < self.max_latitude <= 90.0):
            raise OpenForcingContractError("AOI latitude bounds are invalid")
        if not (-180.0 <= self.min_longitude < self.max_longitude <= 180.0):
            raise OpenForcingContractError("AOI longitude bounds are invalid")


@dataclass(frozen=True)
class NativeForcingPoint:
    point_id: str
    latitude: float
    longitude: float

    def validate(self) -> None:
        if not self.point_id.strip():
            raise OpenForcingContractError("native source point_id is required")
        if not (-90.0 <= self.latitude <= 90.0 and -180.0 <= self.longitude <= 180.0):
            raise OpenForcingContractError("native source point coordinates are invalid")


@dataclass(frozen=True)
class AoiCoveragePlan:
    source_id: str
    provider: str
    model_id: str
    run_id: str
    aoi: AoiBounds
    target_rows: int
    target_cols: int
    target_resolution_m: float
    native_resolution_m: float
    required_variables: tuple[str, ...]
    valid_times: tuple[datetime, ...]
    native_points: tuple[NativeForcingPoint, ...]
    assignments: tuple[str | None, ...]
    max_assignment_distance_m: float
    license_review_status: str = "pending"
    research_only: bool = True

    def validate(self) -> None:
        self.aoi.validate()
        for name, value in (
            ("target_resolution_m", self.target_resolution_m),
            ("native_resolution_m", self.native_resolution_m),
            ("max_assignment_distance_m", self.max_assignment_distance_m),
        ):
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise OpenForcingContractError(f"{name} must be positive and finite")
        if not self.source_id.strip() or not self.provider.strip() or not self.model_id.strip() or not self.run_id.strip():
            raise OpenForcingContractError("source coverage requires exact source/provider/model/run metadata")
        if self.target_rows <= 0 or self.target_cols <= 0:
            raise OpenForcingContractError("target grid dimensions must be positive")
        if not self.required_variables or any(not item.strip() for item in self.required_variables):
            raise OpenForcingContractError("required_variables must be non-empty")
        if len(set(self.required_variables)) != len(self.required_variables):
            raise OpenForcingContractError("required_variables must be unique")
        if not self.valid_times:
            raise OpenForcingContractError("valid_times must be non-empty")
        previous: datetime | None = None
        for timestamp in self.valid_times:
            current = ensure_utc(timestamp)
            if previous is not None and current <= previous:
                raise OpenForcingContractError("valid_times must be strictly increasing")
            previous = current
        if not self.native_points:
            raise OpenForcingContractError("at least one native source point is required")
        point_ids = set()
        for point in self.native_points:
            point.validate()
            if point.point_id in point_ids:
                raise OpenForcingContractError("native source point IDs must be unique")
            point_ids.add(point.point_id)
        if len(self.assignments) != self.target_rows * self.target_cols:
            raise OpenForcingContractError("assignments must cover every target cell")
        if any(item is not None and item not in point_ids for item in self.assignments):
            raise OpenForcingContractError("assignments reference an unknown native source point")
        if self.license_review_status not in _LICENSE_REVIEW_STATUSES:
            raise OpenForcingContractError("unsupported license_review_status")
        if not self.research_only:
            raise OpenForcingContractError("AOI coverage plans must remain research_only")

    @property
    def target_cell_count(self) -> int:
        return self.target_rows * self.target_cols

    @property
    def coverage_fraction(self) -> float:
        self.validate()
        return sum(item is not None for item in self.assignments) / self.target_cell_count

    @property
    def complete_spatial_coverage(self) -> bool:
        return self.coverage_fraction == 1.0

    @property
    def effective_information_scale_m(self) -> float:
        self.validate()
        return max(self.native_resolution_m, self.target_resolution_m)

    @property
    def can_enter_forcing_pipeline(self) -> bool:
        """Allow only spatially complete, license-approved research inputs."""

        self.validate()
        return self.complete_spatial_coverage and self.license_review_status == "approved"


def _distance_m(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    lat_a = math.radians(latitude_a)
    lat_b = math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    haversine = math.sin(delta_lat / 2.0) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2.0) ** 2
    return 2.0 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(haversine)))


def construct_aoi_coverage_plan(
    *,
    source_id: str,
    provider: str,
    model_id: str,
    run_id: str,
    aoi: AoiBounds,
    target_rows: int,
    target_cols: int,
    target_resolution_m: float,
    native_resolution_m: float,
    required_variables: tuple[str, ...],
    valid_times: tuple[datetime, ...],
    native_points: tuple[NativeForcingPoint, ...],
    max_assignment_distance_m: float | None = None,
    license_review_status: str = "pending",
) -> AoiCoveragePlan:
    """Assign each target cell to its nearest native source point.

    The assignment radius defaults to 1.5 native cell diagonals. This is a
    coverage calculation only; it deliberately does not create field values.
    """

    aoi.validate()
    if target_rows <= 0 or target_cols <= 0:
        raise OpenForcingContractError("target grid dimensions must be positive")
    radius = max_assignment_distance_m or native_resolution_m * math.sqrt(2.0) * 1.5
    lat_step = (aoi.max_latitude - aoi.min_latitude) / target_rows
    lon_step = (aoi.max_longitude - aoi.min_longitude) / target_cols
    assignments: list[str | None] = []
    for row in range(target_rows):
        latitude = aoi.min_latitude + (row + 0.5) * lat_step
        for col in range(target_cols):
            longitude = aoi.min_longitude + (col + 0.5) * lon_step
            nearest = min(
                native_points,
                key=lambda point: _distance_m(latitude, longitude, point.latitude, point.longitude),
            )
            distance = _distance_m(latitude, longitude, nearest.latitude, nearest.longitude)
            assignments.append(nearest.point_id if distance <= radius else None)
    plan = AoiCoveragePlan(
        source_id=source_id,
        provider=provider,
        model_id=model_id,
        run_id=run_id,
        aoi=aoi,
        target_rows=target_rows,
        target_cols=target_cols,
        target_resolution_m=target_resolution_m,
        native_resolution_m=native_resolution_m,
        required_variables=required_variables,
        valid_times=valid_times,
        native_points=native_points,
        assignments=tuple(assignments),
        max_assignment_distance_m=radius,
        license_review_status=license_review_status,
    )
    plan.validate()
    return plan
