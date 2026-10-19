"""Version-aware COSIPY adapter for the isolated open-forcing lane.

The installed COSIPY 2.x API consumes an xarray Dataset and returns a tuple
from ``cosipy_core(DATA, indY, indX, ...)``. The older repository adapter passed
a dictionary and attempted timestep-by-timestep calls, which is incompatible
with that API. This adapter deliberately has no heuristic fallback: failed
physics execution must remain visibly failed in research artifacts.
"""

from __future__ import annotations

import inspect
import math
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterator, Mapping, Sequence

import numpy as np

from .contracts import OpenForcingContractError, OpenForcingPolicy, ensure_utc


@dataclass(frozen=True)
class CosipyForcingSeries:
    """One-cell meteorological series in COSIPY input units."""

    times: tuple[datetime, ...]
    latitude: float
    longitude: float
    elevation_m: float
    air_temp_k: tuple[float, ...]
    relative_humidity_pct: tuple[float, ...]
    wind_speed_ms: tuple[float, ...]
    pressure_hpa: tuple[float, ...]
    shortwave_wm2: tuple[float, ...]
    precipitation_mm: tuple[float, ...]
    cloud_fraction: tuple[float, ...]
    longwave_wm2: tuple[float | None, ...] | None = None
    snowfall_m: tuple[float | None, ...] | None = None
    slope_deg: float = 0.0
    aspect_deg: float = 0.0

    @classmethod
    def from_open_meteo_records(
        cls,
        records: Sequence[Mapping[str, Any]],
        *,
        latitude: float,
        longitude: float,
        elevation_m: float,
        slope_deg: float = 0.0,
        aspect_deg: float = 0.0,
    ) -> "CosipyForcingSeries":
        """Convert explicit Open-Meteo field names and units.

        Open-Meteo temperature is Celsius, snowfall is centimetres, and cloud
        cover is percent. The adapter converts these values once and records
        the resulting COSIPY units in the dataset contract.
        """

        if not records:
            raise OpenForcingContractError("at least one forcing record is required")

        def number(record: Mapping[str, Any], key: str, *, default: Any = None) -> float | None:
            value = record.get(key, default)
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise OpenForcingContractError(f"{key} must be numeric") from exc

        times: list[datetime] = []
        temp: list[float] = []
        rh: list[float] = []
        wind: list[float] = []
        pressure: list[float] = []
        shortwave: list[float] = []
        precip: list[float] = []
        cloud: list[float] = []
        longwave: list[float | None] = []
        snowfall: list[float | None] = []

        for index, record in enumerate(records):
            raw_time = record.get("time", record.get("timestamp"))
            if not isinstance(raw_time, datetime):
                raise OpenForcingContractError(f"record {index} requires a timezone-aware datetime")
            times.append(ensure_utc(raw_time))

            temperature_c = number(record, "temperature_2m")
            if temperature_c is None:
                raise OpenForcingContractError(f"record {index} missing temperature_2m")
            temp.append(temperature_c + 273.15)
            rh.append(number(record, "relative_humidity_2m", default=0.0) or 0.0)
            wind.append(number(record, "windspeed_10m", default=0.0) or 0.0)
            pressure.append(number(record, "surface_pressure", default=1013.25) or 1013.25)
            shortwave.append(number(record, "shortwave_radiation", default=0.0) or 0.0)
            precip.append(number(record, "precipitation", default=0.0) or 0.0)
            cloud.append((number(record, "cloud_cover", default=0.0) or 0.0) / 100.0)
            # terrestrial_radiation is top-of-atmosphere solar radiation, not
            # COSIPY incoming longwave. Use only a true longwave field; when it
            # is absent COSIPY still receives cloud_fraction for its own
            # documented parameterization.
            longwave.append(number(record, "longwave_radiation"))
            snowfall_cm = number(record, "snowfall")
            snowfall.append(None if snowfall_cm is None else snowfall_cm / 100.0)

        result = cls(
            times=tuple(times),
            latitude=float(latitude),
            longitude=float(longitude),
            elevation_m=float(elevation_m),
            air_temp_k=tuple(temp),
            relative_humidity_pct=tuple(rh),
            wind_speed_ms=tuple(wind),
            pressure_hpa=tuple(pressure),
            shortwave_wm2=tuple(shortwave),
            precipitation_mm=tuple(precip),
            cloud_fraction=tuple(cloud),
            longwave_wm2=tuple(longwave),
            snowfall_m=tuple(snowfall),
            slope_deg=float(slope_deg),
            aspect_deg=float(aspect_deg),
        )
        result.validate()
        return result

    def validate(self) -> None:
        if len(self.times) == 0:
            raise OpenForcingContractError("times must not be empty")
        lengths = {
            len(self.times),
            len(self.air_temp_k),
            len(self.relative_humidity_pct),
            len(self.wind_speed_ms),
            len(self.pressure_hpa),
            len(self.shortwave_wm2),
            len(self.precipitation_mm),
            len(self.cloud_fraction),
        }
        if self.longwave_wm2 is not None:
            lengths.add(len(self.longwave_wm2))
        if self.snowfall_m is not None:
            lengths.add(len(self.snowfall_m))
        if len(lengths) != 1:
            raise OpenForcingContractError("all forcing series must have equal length")
        if not (-90.0 <= self.latitude <= 90.0 and -180.0 <= self.longitude <= 180.0):
            raise OpenForcingContractError("latitude/longitude are outside valid ranges")
        if self.elevation_m < -500.0:
            raise OpenForcingContractError("elevation_m is invalid")
        previous: datetime | None = None
        for timestamp in self.times:
            current = ensure_utc(timestamp)
            if previous is not None and current <= previous:
                raise OpenForcingContractError("times must be strictly increasing")
            previous = current

        def finite(values: Sequence[float | None], name: str, lower: float | None = None, upper: float | None = None) -> None:
            for value in values:
                if value is None:
                    continue
                if not math.isfinite(float(value)):
                    raise OpenForcingContractError(f"{name} contains a non-finite value")
                if lower is not None and value < lower:
                    raise OpenForcingContractError(f"{name} contains a value below {lower}")
                if upper is not None and value > upper:
                    raise OpenForcingContractError(f"{name} contains a value above {upper}")

        finite(self.air_temp_k, "air_temp_k", 200.0, 350.0)
        finite(self.relative_humidity_pct, "relative_humidity_pct", 0.0, 100.0)
        finite(self.wind_speed_ms, "wind_speed_ms", 0.0, 150.0)
        finite(self.pressure_hpa, "pressure_hpa", 300.0, 1200.0)
        finite(self.shortwave_wm2, "shortwave_wm2", 0.0, 2500.0)
        finite(self.precipitation_mm, "precipitation_mm", 0.0, 1000.0)
        finite(self.cloud_fraction, "cloud_fraction", 0.0, 1.0)
        if self.longwave_wm2 is not None:
            finite(self.longwave_wm2, "longwave_wm2", 0.0, 1500.0)
        if self.snowfall_m is not None:
            finite(self.snowfall_m, "snowfall_m", 0.0, 20.0)


def build_cosipy_dataset(forcing: CosipyForcingSeries) -> Any:
    """Build the single-grid-cell Dataset required by COSIPY 2.x core.

    ``cosipy_core(DATA, indY, indX)`` is a single-cell API. Its meteorological
    arrays must therefore be one-dimensional ``(time,)`` values; a spatial
    ``(time, lat, lon)`` cube belongs to COSIPY's outer grid driver and causes
    scalar conversion failures inside the core loop.
    """

    return _build_cosipy_dataset(forcing)


def _build_cosipy_dataset(
    forcing: CosipyForcingSeries,
    *,
    coupled: bool = False,
    timestep_seconds: int = 3600,
    max_layers: int = 200,
    measurement_height_m: float = 2.0,
) -> Any:
    forcing.validate()
    if timestep_seconds <= 0 or max_layers <= 0 or measurement_height_m <= 0:
        raise OpenForcingContractError("COSIPY coupled metadata must be positive")
    import xarray as xr

    time = np.asarray([timestamp.replace(tzinfo=None) for timestamp in forcing.times], dtype="datetime64[ns]")
    def series(values: Sequence[float]) -> tuple[tuple[str], np.ndarray]:
        return ("time",), np.asarray(values, dtype=np.float64)

    data: dict[str, Any] = {
        "T2": series(forcing.air_temp_k),
        "RH2": series(forcing.relative_humidity_pct),
        "U2": series(forcing.wind_speed_ms),
        "PRES": series(forcing.pressure_hpa),
        "G": series(forcing.shortwave_wm2),
        "RRR": series(forcing.precipitation_mm),
        "N": series(forcing.cloud_fraction),
        "HGT": np.asarray(forcing.elevation_m, dtype=np.float64),
        "MASK": np.asarray(1.0, dtype=np.float64),
        "SLOPE": np.asarray(forcing.slope_deg, dtype=np.float64),
        "ASPECT": np.asarray(forcing.aspect_deg, dtype=np.float64),
    }
    if forcing.longwave_wm2 is not None and all(value is not None for value in forcing.longwave_wm2):
        data["LWin"] = series([float(value) for value in forcing.longwave_wm2])
    if forcing.snowfall_m is not None and all(value is not None for value in forcing.snowfall_m):
        data["SNOWFALL"] = series([float(value) for value in forcing.snowfall_m])
    if coupled:
        # COSIPY's WRF_X_CSPY/coupled branch reads these as scalar data vars.
        data["DT"] = np.asarray(int(timestep_seconds), dtype=np.int64)
        data["max_layers"] = np.asarray(int(max_layers), dtype=np.int64)
        data["ZLVL"] = np.asarray(float(measurement_height_m), dtype=np.float64)

    dataset = xr.Dataset(
        data,
        coords={
            "time": time,
            # COSIPY's restart writer expects scalar spatial coordinates even
            # though the forcing variables themselves are single-cell series.
            "lat": np.asarray(forcing.latitude, dtype=np.float64),
            "lon": np.asarray(forcing.longitude, dtype=np.float64),
        },
    )
    dataset.attrs.update({
        "open_forcing_lane": "true",
        "production_eligible": "false",
        "training_eligible": "false",
        "latitude": forcing.latitude,
        "longitude": forcing.longitude,
        "elevation_m": forcing.elevation_m,
        "cosipy_input_units": "T2=K,RH2=%,U2=m/s,PRES=hPa,G=W/m2,RRR=mm,SNOWFALL=m",
    })
    return dataset


@dataclass(frozen=True)
class CosipyApi:
    init_snowpack: Callable[..., Any]
    cosipy_core: Callable[..., Any]
    package_version: str


def _assert_supported_real_runtime() -> None:
    """Reject unsupported hosts before any real COSIPY/Numba execution."""

    if sys.version_info[:2] != (3, 12):
        raise OpenForcingContractError(
            "real COSIPY physics requires Python 3.12; "
            f"host is Python {sys.version_info[0]}.{sys.version_info[1]}"
        )
    jit_disabled = os.environ.get("NUMBA_DISABLE_JIT", "").strip().lower()
    if jit_disabled in {"1", "true", "yes", "on"}:
        raise OpenForcingContractError(
            "NUMBA_DISABLE_JIT is not an accepted real-physics environment"
        )


def load_cosipy_api() -> CosipyApi:
    """Load and validate the installed COSIPY 2.x function signatures."""

    try:
        import cosipy
        from cosipy.cpkernel.cosipy_core import cosipy_core
        from cosipy.cpkernel.init import init_snowpack
    except ImportError as exc:
        raise OpenForcingContractError("COSIPY is not installed in the research environment") from exc

    init_params = list(inspect.signature(init_snowpack).parameters)
    core_params = list(inspect.signature(cosipy_core).parameters)
    if init_params != ["DATA"] or core_params[:3] != ["DATA", "indY", "indX"]:
        raise OpenForcingContractError(
            f"unsupported COSIPY API: init={init_params}, core={core_params}"
        )
    package_version = getattr(cosipy, "__version__", None)
    if not package_version:
        try:
            from importlib.metadata import version as distribution_version

            package_version = distribution_version("cosipymodel")
        except Exception:  # pragma: no cover - packaging metadata is environment-dependent
            package_version = "unknown"
    return CosipyApi(
        init_snowpack=init_snowpack,
        cosipy_core=cosipy_core,
        package_version=str(package_version),
    )


@dataclass(frozen=True)
class CosipyNativeResult:
    """Native bulk-state outputs and explicit research-only metadata."""

    native_fields: dict[str, float | int | None]
    engine_version: str
    source_time_start: datetime
    source_time_end: datetime
    snow_water_equivalent_m: float | None = None
    density_profile_kg_m3: tuple[float, ...] = ()
    temperature_profile_k: tuple[float, ...] = ()
    liquid_water_content_m: tuple[float, ...] = ()
    production_eligible: bool = False
    training_eligible: bool = False
    stratigraphy_native: bool = False


def _last_scalar(value: Any) -> float | int | None:
    if value is None:
        return None
    array = np.asarray(value)
    if array.size == 0:
        return None
    scalar = array.reshape(-1)[-1]
    if not np.isfinite(scalar):
        return None
    return float(scalar)


def _finite_profile(value: Any) -> tuple[float, ...]:
    if value is None:
        return ()
    array = np.asarray(value, dtype=np.float64).reshape(-1)
    return tuple(float(item) for item in array if np.isfinite(item))


def _snow_water_equivalent_m(
    heights_m: tuple[float, ...],
    density_kg_m3: tuple[float, ...],
    liquid_water_m: tuple[float, ...],
) -> float | None:
    if not heights_m or len(heights_m) != len(density_kg_m3):
        return None
    liquid = liquid_water_m or (0.0,) * len(heights_m)
    if len(liquid) != len(heights_m):
        return None
    # COSIPY's layer heights/densities are native; LWC is already m w.e.
    # Exclude the ice domain (density >= 900 kg m-3) from SWE.
    value = sum(
        height * density / 1000.0 + water
        for height, density, water in zip(heights_m, density_kg_m3, liquid)
        if density < 900.0
    )
    return float(value)


def _native_result_from_raw(
    raw_result: tuple[Any, ...],
    *,
    api: CosipyApi,
    forcing: CosipyForcingSeries,
) -> CosipyNativeResult:
    if not isinstance(raw_result, tuple) or len(raw_result) < 19:
        raise OpenForcingContractError("COSIPY returned an unexpected result tuple")
    heights = _finite_profile(raw_result[33] if len(raw_result) > 33 else None)
    densities = _finite_profile(raw_result[34] if len(raw_result) > 34 else None)
    temperatures = _finite_profile(raw_result[35] if len(raw_result) > 35 else None)
    liquid_water = _finite_profile(raw_result[36] if len(raw_result) > 36 else None)
    swe = _snow_water_equivalent_m(heights, densities, liquid_water)
    return CosipyNativeResult(
        native_fields={
            "snow_height_m": _last_scalar(raw_result[14]),
            "total_height_m": _last_scalar(raw_result[15]),
            "surface_temperature_k": _last_scalar(raw_result[16]),
            "layer_count": int(_last_scalar(raw_result[18]) or 0),
            "snow_water_equivalent_m": swe,
        },
        engine_version=api.package_version,
        source_time_start=forcing.times[0],
        source_time_end=forcing.times[-1],
        snow_water_equivalent_m=swe,
        density_profile_kg_m3=densities,
        temperature_profile_k=temperatures,
        liquid_water_content_m=liquid_water,
    )


@contextmanager
def _cosipy_coupled_mode() -> Iterator[None]:
    """Temporarily select COSIPY's scalar-output coupled execution branch."""

    try:
        import importlib

        config_module = importlib.import_module("cosipy.config")
        core_module = importlib.import_module("cosipy.cpkernel.cosipy_core")
        surface_module = importlib.import_module("cosipy.modules.surfaceTemperature")
    except ImportError as exc:
        raise OpenForcingContractError("COSIPY coupled mode is unavailable") from exc

    config = config_module.Config
    previous = (
        getattr(config, "WRF_X_CSPY", False),
        getattr(config, "full_field", False),
        getattr(core_module, "WRF_X_CSPY", False),
        getattr(surface_module, "WRF_X_CSPY", False),
    )
    config.WRF_X_CSPY = True
    config.full_field = True
    core_module.WRF_X_CSPY = True
    surface_module.WRF_X_CSPY = True
    try:
        yield
    finally:
        config.WRF_X_CSPY, config.full_field, core_module.WRF_X_CSPY, surface_module.WRF_X_CSPY = previous


def run_cosipy_reference(
    forcing: CosipyForcingSeries,
    *,
    policy: OpenForcingPolicy | None = None,
    api: CosipyApi | None = None,
) -> CosipyNativeResult:
    """Run the official COSIPY core call once for one forcing column.

    No fallback is performed here. Callers must record a failed physics run
    and may not relabel a heuristic proxy as a COSIPY result.
    """

    forcing.validate()
    selected_policy = policy or OpenForcingPolicy(enabled=True)
    selected_policy.validate()
    if not selected_policy.enabled:
        raise OpenForcingContractError("open-forcing policy is disabled")
    # An injected API is a contract-test seam. The real/default path must
    # prove the supported Python/Numba environment before importing/running
    # COSIPY; this keeps host Python 3.14 checks from being misreported as
    # physics evidence.
    if api is None:
        _assert_supported_real_runtime()
    selected_api = api or load_cosipy_api()
    dataset = build_cosipy_dataset(forcing)
    return _native_result_from_raw(
        selected_api.cosipy_core(dataset, 0, 0), api=selected_api, forcing=forcing
    )


def run_cosipy_coupled_reference(
    forcing: CosipyForcingSeries,
    *,
    policy: OpenForcingPolicy | None = None,
    api: CosipyApi | None = None,
) -> CosipyNativeResult:
    """Run the real COSIPY coupled branch with explicit scalar-output metadata.

    COSIPY 2.0.0's standalone writer path can return one-element arrays that
    fail its own scalar output assignment. The coupled branch is the supported
    scalar-output seam for this adapter; it remains research-only and does not
    alter the repository's existing production physics module.
    """

    forcing.validate()
    selected_policy = policy or OpenForcingPolicy(enabled=True)
    selected_policy.validate()
    if not selected_policy.enabled:
        raise OpenForcingContractError("open-forcing policy is disabled")
    if api is None:
        _assert_supported_real_runtime()
    selected_api = api or load_cosipy_api()
    dataset = _build_cosipy_dataset(forcing, coupled=True)
    with _cosipy_coupled_mode():
        raw_result = selected_api.cosipy_core(dataset, 0, 0)
    return _native_result_from_raw(raw_result, api=selected_api, forcing=forcing)
