"""Strict Open-Meteo Single Runs source-point ingestion.

The output of this module is a verified native-source-point payload. It is not
a target-grid interpolation, a forcing cube, a model artifact, or a forecast
publication. Missing values and malformed source responses fail closed.
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from .contracts import OpenForcingContractError, ensure_utc
from .coverage import NativeForcingPoint


_RUN_FORMAT = "%Y-%m-%dT%H:%M"
_COORDINATE_EPSILON = 1e-6
_MAX_FORECAST_HOURS = 24 * 16


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise OpenForcingContractError(f"{field_name} contains a non-numeric value") from exc
    if not math.isfinite(converted):
        raise OpenForcingContractError(f"{field_name} contains a non-finite value")
    return converted


@dataclass(frozen=True)
class OpenMeteoRunRequest:
    latitudes: tuple[float, ...]
    longitudes: tuple[float, ...]
    model_id: str
    run_id: str
    forecast_hours: int
    hourly_variables: tuple[str, ...]

    def validate(self) -> None:
        if not self.latitudes or len(self.latitudes) != len(self.longitudes):
            raise OpenForcingContractError("latitudes and longitudes must be non-empty and aligned")
        for latitude, longitude in zip(self.latitudes, self.longitudes):
            if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
                raise OpenForcingContractError("request coordinates are invalid")
        if len(set(zip(self.latitudes, self.longitudes))) != len(self.latitudes):
            raise OpenForcingContractError("request coordinates must be unique")
        if not self.model_id.strip() or self.model_id.strip().lower() in {"best_match", "unknown", "unresolved"}:
            raise OpenForcingContractError("an explicit model_id is required")
        if not self.run_id.strip() or self.run_id.strip().lower() in {"best_match", "unknown", "unresolved"}:
            raise OpenForcingContractError("an explicit run_id is required")
        try:
            parsed_run = datetime.strptime(self.run_id, _RUN_FORMAT).replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise OpenForcingContractError("run_id must be UTC YYYY-MM-DDTHH:MM") from exc
        if parsed_run.hour not in {0, 6, 12, 18} or parsed_run.minute != 0:
            raise OpenForcingContractError("run_id must use a documented model cycle hour")
        if self.forecast_hours <= 0 or self.forecast_hours > _MAX_FORECAST_HOURS:
            raise OpenForcingContractError("forecast_hours is outside the bounded source request")
        if not self.hourly_variables or any(not value.strip() for value in self.hourly_variables):
            raise OpenForcingContractError("hourly_variables must be non-empty")
        if len(set(self.hourly_variables)) != len(self.hourly_variables):
            raise OpenForcingContractError("hourly_variables must be unique")

    @property
    def url(self) -> str:
        self.validate()
        query = (
            ("latitude", ",".join(f"{value:.6f}" for value in self.latitudes)),
            ("longitude", ",".join(f"{value:.6f}" for value in self.longitudes)),
            ("hourly", ",".join(sorted(self.hourly_variables))),
            ("models", self.model_id),
            ("run", self.run_id),
            ("forecast_hours", str(self.forecast_hours)),
            ("timezone", "UTC"),
        )
        return "https://single-runs-api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(query)


@dataclass(frozen=True)
class OpenMeteoPointSeries:
    point: NativeForcingPoint
    times: tuple[datetime, ...]
    records: tuple[dict[str, float | None], ...]

    def validate(self, required_variables: tuple[str, ...]) -> None:
        self.point.validate()
        if not self.times or len(self.times) != len(self.records):
            raise OpenForcingContractError("source point times and records must be non-empty and aligned")
        previous: datetime | None = None
        for index, timestamp in enumerate(self.times):
            current = ensure_utc(timestamp)
            if previous is not None and current - previous != timedelta(hours=1):
                raise OpenForcingContractError("source point timestamps must be contiguous hourly UTC values")
            previous = current
            record = self.records[index]
            if set(record) != set(required_variables):
                raise OpenForcingContractError("source point record variables do not match the requested schema")


@dataclass(frozen=True)
class NativeSourcePointPayload:
    request: OpenMeteoRunRequest
    points: tuple[OpenMeteoPointSeries, ...]
    raw_payload_sha256: str
    synthetic_inputs_present: bool = False
    training_eligible: bool = False
    production_eligible: bool = False
    publication_eligible: bool = False
    research_only: bool = True

    def validate(self) -> None:
        self.request.validate()
        if len(self.points) != len(self.request.latitudes):
            raise OpenForcingContractError("source response point count does not match the request")
        for index, point_series in enumerate(self.points):
            expected = NativeForcingPoint(
                f"p{index:03d}",
                self.request.latitudes[index],
                self.request.longitudes[index],
            )
            if abs(point_series.point.latitude - expected.latitude) > _COORDINATE_EPSILON:
                raise OpenForcingContractError("source response latitude/order does not match the request")
            if abs(point_series.point.longitude - expected.longitude) > _COORDINATE_EPSILON:
                raise OpenForcingContractError("source response longitude/order does not match the request")
            point_series.validate(self.request.hourly_variables)
            if index > 0 and point_series.times != self.points[0].times:
                raise OpenForcingContractError("source response points must share the same hourly timeline")
        if len(self.raw_payload_sha256) != 64 or any(char not in "0123456789abcdef" for char in self.raw_payload_sha256.lower()):
            raise OpenForcingContractError("raw_payload_sha256 must be a SHA-256 digest")
        if self.synthetic_inputs_present or self.training_eligible or self.production_eligible or self.publication_eligible:
            raise OpenForcingContractError("native source payload cannot enter training, publication, or production")
        if not self.research_only:
            raise OpenForcingContractError("native source payload must remain research_only")

    @property
    def point_count(self) -> int:
        self.validate()
        return len(self.points)


def _response_objects(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    if isinstance(payload, Mapping):
        return (payload,)
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        if not all(isinstance(item, Mapping) for item in payload):
            raise OpenForcingContractError("source response list contains a non-object item")
        return tuple(payload)
    raise OpenForcingContractError("source response must be one object or a list of objects")


def parse_open_meteo_single_run(
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    request: OpenMeteoRunRequest,
    *,
    raw_payload: bytes | None = None,
) -> NativeSourcePointPayload:
    """Parse and validate a raw Single Runs response without resampling."""

    request.validate()
    responses = _response_objects(payload)
    if len(responses) != len(request.latitudes):
        raise OpenForcingContractError("source response point count does not match the request")
    points: list[OpenMeteoPointSeries] = []
    for index, response in enumerate(responses):
        latitude = _number(response.get("latitude"), "latitude")
        longitude = _number(response.get("longitude"), "longitude")
        if latitude is None or longitude is None:
            raise OpenForcingContractError("source response requires latitude and longitude")
        hourly = response.get("hourly")
        if not isinstance(hourly, Mapping):
            raise OpenForcingContractError("source response requires an hourly object")
        raw_times = hourly.get("time")
        if not isinstance(raw_times, Sequence) or isinstance(raw_times, (str, bytes, bytearray)):
            raise OpenForcingContractError("source hourly.time must be a sequence")
        if len(raw_times) != request.forecast_hours:
            raise OpenForcingContractError("source hourly.time length differs from forecast_hours")
        times: list[datetime] = []
        for raw_time in raw_times:
            if not isinstance(raw_time, str):
                raise OpenForcingContractError("source times must be ISO strings")
            try:
                timestamp = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
            except ValueError as exc:
                raise OpenForcingContractError("source time is not valid ISO-8601") from exc
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            times.append(ensure_utc(timestamp))
        columns: dict[str, tuple[float | None, ...]] = {}
        for variable in request.hourly_variables:
            values = hourly.get(variable)
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
                raise OpenForcingContractError(f"source response is missing required variable: {variable}")
            if len(values) != len(times):
                raise OpenForcingContractError(f"source variable length differs from time for {variable}")
            columns[variable] = tuple(_number(value, variable) for value in values)
        records = tuple(
            {variable: columns[variable][time_index] for variable in request.hourly_variables}
            for time_index in range(len(times))
        )
        series = OpenMeteoPointSeries(
            point=NativeForcingPoint(f"p{index:03d}", latitude, longitude),
            times=tuple(times),
            records=records,
        )
        series.validate(request.hourly_variables)
        points.append(series)
    raw = raw_payload if raw_payload is not None else _canonical_bytes(payload)
    result = NativeSourcePointPayload(request=request, points=tuple(points), raw_payload_sha256=_sha256(raw))
    result.validate()
    return result
