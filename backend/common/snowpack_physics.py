"""Physics-based snowpack stratigraphy simulation via COSIPY (Python) or SNOWPACK (C++).

Replaces the heuristic snowpack_proxy with a real multilayer energy-balance model
that simulates layer-by-layer snowpack evolution: grain type, shear strength,
temperature gradient, density profile, and liquid water content.

When COSIPY is installed (``pip install cosipymodel``), this module runs a 1D
column simulation per grid cell using Open-Meteo weather data. When COSIPY is
unavailable, it falls back to the existing heuristic proxy so the pipeline never
crashes.

The output is a :class:`SnowpackPhysicsResult` with 10 physics-derived fields
that feed into the ML feature pipeline.
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.common.snowpack_proxy import (
    SnowpackProxy,
    compute_cell_snowpack_proxy,
    winter_season_start,
)
from backend.common.meteoio_openmeteo import (
    snowpack_binary_available,
    write_smet_file,
    run_snowpack_native,
    parse_snowpack_pro,
    generate_snowpack_config,
)
from backend.common.regions import get_zone_override as _get_zone_override, Region


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SNOWPACK_PHYSICS_ENABLED = os.getenv('SNOWPACK_PHYSICS_ENABLED', '1').strip().lower() in ('1', 'true', 'yes')
SNOWPACK_PHYSICS_CACHE_DIR = os.getenv('SNOWPACK_PHYSICS_CACHE_DIR', '')
SNOWPACK_PHYSICS_TIMEOUT_S = float(os.getenv('SNOWPACK_PHYSICS_TIMEOUT_S', '30'))

# Grain type classification thresholds (Swiss code simplified)
_DEPTH_HOAR_DENSITY_KGM3 = 250.0  # below this + large TG → depth hoar
_FACETED_DENSITY_KGM3 = 300.0     # below this + moderate TG → faceted
_SURFACE_HOAR_INDICATOR = -0.02    # surface TG threshold (K/m) for surface hoar formation

# Stability index threshold (shear strength / overburden stress)
_STABILITY_INDEX_CRITICAL = 1.0   # < 1.0 = unstable

# Zone-specific expected grain types (from Partner/SLF snow climate classification)
_ZONE_GRAIN_TYPE: dict[str, str] = {
    'pir_panjal': 'melt_form',
    'shamshabari': 'faceted',
    'great_himalaya': 'depth_hoar',
    'karakoram_ladakh': 'depth_hoar',
}


# ---------------------------------------------------------------------------
# Zone-specific calibration overrides
# ---------------------------------------------------------------------------

def load_zone_overrides(zone_type: str | None) -> dict[str, Any]:
    """Load COSIPY/SNOWPACK parameter overrides for a given zone_type.

    Returns an empty dict when zone_type is None or not found in the
    overrides file, ensuring backward compatibility for existing regions.
    """
    if not zone_type:
        return {}
    dummy_region = Region(
        name='__zone_lookup__',
        bbox=(0.0, 0.0, 0.0, 0.0),
        center=(0.0, 0.0),
        zoom=1,
        zone_type=zone_type,
    )
    return _get_zone_override(dummy_region)


# ---------------------------------------------------------------------------
# Weather history fetch (Open-Meteo archive → hourly samples for SNOWPACK/COSIPY)
# ---------------------------------------------------------------------------

OPEN_METEO_ARCHIVE_URL = 'https://archive-api.open-meteo.com/v1/archive'
ARCHIVE_HOURLY_VARS_FOR_PHYSICS = (
    'temperature_2m',
    'precipitation',
    'snowfall',
    'snow_depth',
    'windspeed_10m',
    'winddirection_10m',
    'relative_humidity_2m',
    'shortwave_radiation',
    'cloud_cover',
    'surface_pressure',
)


def fetch_weather_history_for_snowpack(
    *,
    lat: float,
    lng: float,
    as_of: datetime,
    season_start: datetime | None = None,
    max_days: int = 180,
) -> list[dict[str, Any]]:
    """Fetch hourly weather history from Open-Meteo archive API.

    Retrieves hourly data from the start of the winter season (Nov 1 by
    default) to the current date, for use as SNOWPACK/COSIPY input.

    Args:
        lat: Cell latitude
        lng: Cell longitude
        as_of: Current datetime
        season_start: Override season start (defaults to winter_season_start)
        max_days: Maximum number of days to fetch (cap to avoid API limits)

    Returns:
        List of hourly weather sample dicts with keys matching Open-Meteo
        variable names plus 'time' key with ISO timestamp.
    """
    import requests as _requests

    if season_start is None:
        season_start = winter_season_start(as_of)

    # Cap to max_days to avoid Open-Meteo API limits
    end_date = as_of.date()
    start_date = season_start.date() if hasattr(season_start, 'date') else season_start
    if (end_date - start_date).days > max_days:
        start_date = end_date - timedelta(days=max_days)

    params = {
        'latitude': f'{lat:.4f}',
        'longitude': f'{lng:.4f}',
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'hourly': ','.join(ARCHIVE_HOURLY_VARS_FOR_PHYSICS),
        'timezone': 'UTC',
    }

    try:
        response = _requests.get(
            OPEN_METEO_ARCHIVE_URL,
            params=params,
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    hourly = data.get('hourly', {})
    times = hourly.get('time', []) if isinstance(hourly, dict) else []
    if not isinstance(times, list) or not times:
        return []

    columns: dict[str, list[Any]] = {}
    for var in ARCHIVE_HOURLY_VARS_FOR_PHYSICS:
        values = hourly.get(var) if isinstance(hourly, dict) else None
        if not isinstance(values, list) or len(values) != len(times):
            return []
        columns[var] = values

    samples: list[dict[str, Any]] = []
    for i, ts in enumerate(times):
        if not isinstance(ts, str) or not ts.strip():
            return []
        try:
            parsed_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except ValueError:
            return []
        if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
            parsed_time = parsed_time.replace(tzinfo=timezone.utc)
        sample: dict[str, Any] = {'time': parsed_time.astimezone(timezone.utc).isoformat()}
        for var in ARCHIVE_HOURLY_VARS_FOR_PHYSICS:
            value = columns[var][i]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return []
            numeric = float(value)
            if not math.isfinite(numeric):
                return []
            sample[var] = numeric
        samples.append(sample)

    return samples


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SnowpackPhysicsResult:
    """Physics-based snowpack stratigraphy result from COSIPY or SNOWPACK."""

    weak_layer_depth_m: float
    weak_layer_grain_type: str          # "faceted", "depth_hoar", "surface_hoar", "melt_form", "rounded"
    weak_layer_shear_strength_kpa: float
    snowpack_stability_index: float     # shear_strength / overburden_stress
    temperature_gradient_per_m: float   # K/m through the pack
    liquid_water_content_pct: float     # percent by volume
    layer_count: int
    snow_height_m: float
    bulk_density_kgm3: float
    method: str                         # "cosipy_v2", "snowpack_native", "heuristic_fallback"
    layers: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class SnowpackPhysicsBatchResult:
    result: SnowpackPhysicsResult | None
    status: str
    error: str | None = None


# ---------------------------------------------------------------------------
# COSIPY integration (optional, pure Python)
# ---------------------------------------------------------------------------

def _cosipy_available() -> bool:
    """Check if COSIPY is importable."""
    try:
        import cosipy  # noqa: F401
        return True
    except ImportError:
        return False


def _build_cosipy_input(
    weather_history: list[dict[str, float]],
    elevation_m: float,
    lat: float,
    lng: float,
) -> dict[str, Any]:
    """Convert Open-Meteo weather history into COSIPY-compatible input dict.

    COSIPY expects: air_temp (K), rel_humidity (%), wind_speed (m/s),
    precip (mm), sw_in (W/m2), lw_in (W/m2), pressure (hPa).

    Open-Meteo forecast API provides ``terrestrial_radiation`` (W/m2) directly.
    The archive API does not, so we estimate LW from cloud cover and temperature
    using the Crawford & Duchon (1999) parameterization when terrestrial_radiation
    is unavailable.
    """
    timestamps = []
    air_temp_k = []
    rel_humidity = []
    wind_speed = []
    precip = []
    sw_in = []
    lw_in = []
    pressure = []

    for sample in weather_history:
        ts = sample.get('time') or sample.get('timestamp')
        if ts is None:
            continue
        timestamps.append(str(ts))

        temp_c = float(sample.get('temperature_2m', 0.0) or 0.0)
        air_temp_k.append(temp_c + 273.15)

        rh = float(sample.get('relative_humidity_2m', 80.0) or 80.0)
        rel_humidity.append(np.clip(rh, 0.0, 100.0))

        ws = float(sample.get('windspeed_10m', 0.0) or 0.0)
        wind_speed.append(max(0.0, ws))

        p = float(sample.get('precipitation', 0.0) or 0.0)
        precip.append(max(0.0, p))

        sw = float(sample.get('shortwave_radiation', 0.0) or 0.0)
        sw_in.append(max(0.0, sw))

        # Longwave radiation: use terrestrial_radiation if available (forecast API),
        # otherwise estimate from cloud_cover + temperature (archive API).
        lw = sample.get('terrestrial_radiation')
        if lw is not None:
            lw_in.append(max(100.0, float(lw)))
        else:
            # Crawford-Duchon (1999) cloud-cover parameterization
            cloud_cover = float(sample.get('cloud_cover', 50.0) or 50.0) / 100.0
            cloud_cover = np.clip(cloud_cover, 0.0, 1.0)
            # Clear-sky emissivity (Prata 1996)
            e_clear = 1.24 * (10.0 * rh / 100.0 * np.exp(17.27 * temp_c / (237.3 + temp_c)) / (temp_c + 273.15)) ** (1.0 / 7.0)
            e_clear = np.clip(e_clear, 0.2, 1.0)
            # Cloud factor (Crawford-Duchon)
            e_eff = e_clear * (1.0 - cloud_cover) + 0.995 * cloud_cover
            # Stefan-Boltzmann: LW = e * sigma * T^4
            sigma = 5.67e-8  # W/m2/K4
            lw_est = e_eff * sigma * (temp_c + 273.15) ** 4
            lw_in.append(max(100.0, float(lw_est)))

        # Approximate pressure from elevation using barometric formula
        p_hpa = 1013.25 * math.pow(1.0 - 2.2557e-5 * elevation_m, 5.2559)
        pressure.append(p_hpa)

    return {
        'timestamps': timestamps,
        'air_temp': np.array(air_temp_k, dtype=np.float32),
        'rel_humidity': np.array(rel_humidity, dtype=np.float32),
        'wind_speed': np.array(wind_speed, dtype=np.float32),
        'precip': np.array(precip, dtype=np.float32),
        'sw_in': np.array(sw_in, dtype=np.float32),
        'lw_in': np.array(lw_in, dtype=np.float32),
        'pressure': np.array(pressure, dtype=np.float32),
        'elevation': elevation_m,
        'lat': lat,
        'lng': lng,
    }


def _classify_grain_type(
    density: float,
    temperature_gradient: float,
    is_surface: bool,
) -> str:
    """Classify snow grain type based on density and temperature gradient.

    Uses simplified Swiss snow classification:
    - Depth hoar: low density + large temperature gradient
    - Faceted: moderate density + moderate temperature gradient
    - Surface hoar: surface layer with strong radiative cooling
    - Melt form: high liquid water content
    - Rounded: high density + small temperature gradient
    """
    if is_surface and temperature_gradient < _SURFACE_HOAR_INDICATOR:
        return 'surface_hoar'
    if density < _DEPTH_HOAR_DENSITY_KGM3 and temperature_gradient > 0.15:
        return 'depth_hoar'
    if density < _FACETED_DENSITY_KGM3 and temperature_gradient > 0.05:
        return 'faceted'
    if density > 400.0:
        return 'melt_form'
    return 'rounded'


def _compute_stability_index(
    shear_strength_kpa: float,
    snow_height_m: float,
    bulk_density_kgm3: float,
) -> float:
    """Compute snowpack stability index = shear_strength / overburden_stress.

    Overburden stress = rho * g * h (kPa)
    """
    if snow_height_m <= 0.0 or bulk_density_kgm3 <= 0.0:
        return 5.0  # very stable (no snow)
    overburden_kpa = (bulk_density_kgm3 * 9.81 * snow_height_m) / 1000.0
    if overburden_kpa < 0.01:
        return 5.0
    return float(np.clip(shear_strength_kpa / overburden_kpa, 0.0, 5.0))


def _cosipy_output_to_result(
    cosipy_data: Any,
    method: str = 'cosipy_v2',
) -> SnowpackPhysicsResult:
    """Convert COSIPY output to SnowpackPhysicsResult.

    COSIPY provides layer-by-layer data via xarray Dataset. This function
    extracts the key fields needed for avalanche prediction.
    """
    try:
        import xarray as xr

        ds = cosipy_data if isinstance(cosipy_data, xr.Dataset) else None
        if ds is None:
            raise ValueError('Expected xarray Dataset from COSIPY')

        # Get final timestep
        last_idx = -1
        snow_height = float(ds.get('height', ds.get('HS', xr.DataArray([0.0]))).isel(time=last_idx).values)
        snow_height_m = max(0.0, snow_height)

        # Get layer information
        if 'layer' in ds.dims:
            n_layers = int(ds.dims.get('layer', 1))
        else:
            n_layers = 1

        # Temperature gradient through pack
        if 'temp' in ds or 'temperature' in ds:
            temp_var = ds.get('temp', ds.get('temperature'))
            temps = temp_var.isel(time=last_idx).values
            if hasattr(temps, 'size') and temps.size > 1:
                temp_gradient = float(abs(np.diff(temps).mean())) if temps.size > 1 else 0.0
            else:
                temp_gradient = 0.0
        else:
            temp_gradient = 0.0

        # Bulk density
        if 'density' in ds:
            densities = ds['density'].isel(time=last_idx).values
            if hasattr(densities, 'size') and densities.size > 0:
                bulk_density = float(np.nanmean(densities))
            else:
                bulk_density = 300.0
        else:
            bulk_density = 300.0

        # Liquid water content
        if 'lwc' in ds or 'liquid_water_content' in ds:
            lwc_var = ds.get('lwc', ds.get('liquid_water_content'))
            lwc_vals = lwc_var.isel(time=last_idx).values
            if hasattr(lwc_vals, 'size') and lwc_vals.size > 0:
                lwc_pct = float(np.nanmean(lwc_vals)) * 100.0
            else:
                lwc_pct = 0.0
        else:
            lwc_pct = 0.0

        # Find weakest layer (lowest density or highest temperature gradient)
        weak_layer_depth = snow_height_m / 2.0  # default to mid-pack
        weak_layer_density = bulk_density
        weak_layer_shear = 3.0  # default moderate

        if 'density' in ds:
            densities_arr = ds['density'].isel(time=last_idx).values
            if hasattr(densities_arr, 'size') and densities_arr.size > 1:
                weakest_idx = int(np.nanargmin(densities_arr))
                weak_layer_density = float(densities_arr[weakest_idx])
                # Estimate shear strength from density (empirical: sigma = c * rho^2)
                weak_layer_shear = max(0.1, 0.001 * weak_layer_density ** 1.5)
                # Estimate depth from layer height
                if 'height' in ds or 'layer_height' in ds:
                    h_var = ds.get('height', ds.get('layer_height'))
                    h_vals = h_var.isel(time=last_idx).values
                    if hasattr(h_vals, 'size') and weakest_idx < h_vals.size:
                        weak_layer_depth = float(np.sum(h_vals[:weakest_idx + 1]))

        # Classify grain type
        is_surface = weak_layer_depth >= snow_height_m * 0.9 if snow_height_m > 0 else False
        grain_type = _classify_grain_type(weak_layer_density, temp_gradient, is_surface)

        # Compute stability index
        stability_index = _compute_stability_index(weak_layer_shear, snow_height_m, bulk_density)

        # Build layer summary
        layers: list[dict[str, Any]] = []
        if 'density' in ds:
            densities_arr = ds['density'].isel(time=last_idx).values
            if hasattr(densities_arr, 'size'):
                for i in range(min(n_layers, len(densities_arr))):
                    layers.append({
                        'index': i,
                        'density_kgm3': float(densities_arr[i]),
                        'grain_type': _classify_grain_type(
                            float(densities_arr[i]),
                            temp_gradient,
                            i == 0 or i == len(densities_arr) - 1,
                        ),
                    })

        return SnowpackPhysicsResult(
            weak_layer_depth_m=round(weak_layer_depth, 3),
            weak_layer_grain_type=grain_type,
            weak_layer_shear_strength_kpa=round(weak_layer_shear, 2),
            snowpack_stability_index=round(stability_index, 3),
            temperature_gradient_per_m=round(temp_gradient, 4),
            liquid_water_content_pct=round(max(0.0, lwc_pct), 2),
            layer_count=n_layers,
            snow_height_m=round(snow_height_m, 3),
            bulk_density_kgm3=round(bulk_density, 1),
            method=method,
            layers=layers[:20],  # cap for payload size
        )

    except Exception as exc:
        raise RuntimeError(f'COSIPY output parsing failed: {exc}') from exc


def run_cosipy_cell(
    *,
    lat: float,
    lng: float,
    elevation_m: float,
    weather_history: list[dict[str, float]],
    as_of: datetime,
) -> SnowpackPhysicsResult:
    """Run COSIPY 1D column simulation for a single grid cell.

    Args:
        lat: Cell latitude
        lng: Cell longitude
        elevation_m: Cell elevation in meters
        weather_history: Hourly weather samples from Nov 1 to as_of
        as_of: Current datetime for simulation end

    Returns:
        SnowpackPhysicsResult with physics-derived snowpack properties

    Raises:
        RuntimeError: If COSIPY execution fails
    """
    if not weather_history:
        raise RuntimeError('No weather history provided for COSIPY simulation')

    cosipy_input = _build_cosipy_input(weather_history, elevation_m, lat, lng)

    try:
        from cosipy.cpkernel.cosipy_core import cosipy_core
        from cosipy.cpkernel.init import init_snowpack
        import xarray as xr

        # Initialize snowpack (empty or with last season's state)
        grid = init_snowpack(cosipy_input)

        # Run COSIPY timestep by timestep
        n_steps = len(cosipy_input['timestamps'])
        for t in range(n_steps):
            grid = cosipy_core(
                grid,
                {
                    'Tair': cosipy_input['air_temp'][t],
                    'RH': cosipy_input['rel_humidity'][t],
                    'U': cosipy_input['wind_speed'][t],
                    'Prec': cosipy_input['precip'][t],
                    'G': cosipy_input['sw_in'][t],
                    'LWin': cosipy_input['lw_in'][t],
                    'p': cosipy_input['pressure'][t],
                },
                t,
            )

        # Convert grid to xarray Dataset for output parsing
        ds = grid.to_xarray() if hasattr(grid, 'to_xarray') else grid

        return _cosipy_output_to_result(ds, method='cosipy_v2')

    except ImportError:
        raise RuntimeError('COSIPY not installed. Run: pip install cosipymodel')
    except Exception as exc:
        raise RuntimeError(f'COSIPY simulation failed: {exc}') from exc


# ---------------------------------------------------------------------------
# Heuristic fallback (wraps existing snowpack_proxy)
# ---------------------------------------------------------------------------

def _heuristic_to_physics_result(
    proxy: SnowpackProxy,
    weather_inputs: dict[str, float] | None = None,
    terrain_inputs: dict[str, float] | None = None,
) -> SnowpackPhysicsResult:
    """Convert heuristic SnowpackProxy to SnowpackPhysicsResult format.

    This provides backward compatibility when COSIPY is unavailable.
    New physics fields are estimated from the heuristic scalars.
    """
    shear_kpa = proxy.estimated_shear_strength
    settlement = proxy.snow_settlement_index

    # Estimate snow height from settlement (inverse of consolidation)
    snow_height_m = max(0.0, (1.0 - settlement) * 2.0 + 0.3)

    # Estimate bulk density from settlement (more settled = denser)
    bulk_density = 200.0 + settlement * 400.0  # 200-600 kg/m3

    # Estimate temperature gradient from method
    if 'seasonal' in proxy.method:
        temp_gradient = 0.08  # moderate seasonal gradient
    else:
        temp_gradient = 0.15  # higher gradient for synthetic fallback

    # Classify grain type from density and gradient
    grain_type = _classify_grain_type(bulk_density, temp_gradient, is_surface=False)

    # Compute stability index
    stability_index = _compute_stability_index(shear_kpa, snow_height_m, bulk_density)

    # Estimate LWC from settlement (more settled = more liquid water)
    lwc_pct = settlement * 3.0

    return SnowpackPhysicsResult(
        weak_layer_depth_m=round(snow_height_m * 0.3, 3),  # weak layer at ~30% depth
        weak_layer_grain_type=grain_type,
        weak_layer_shear_strength_kpa=round(shear_kpa, 2),
        snowpack_stability_index=round(stability_index, 3),
        temperature_gradient_per_m=round(temp_gradient, 4),
        liquid_water_content_pct=round(lwc_pct, 2),
        layer_count=1,
        snow_height_m=round(snow_height_m, 3),
        bulk_density_kgm3=round(bulk_density, 1),
        method='heuristic_fallback',
        layers=[],
    )


def _fallback_physics_proxy(
    weather_inputs: dict[str, float],
    terrain_inputs: dict[str, float],
) -> SnowpackPhysicsResult:
    """Create a fallback SnowpackPhysicsResult from weather/terrain inputs.

    Used when both COSIPY and the seasonal proxy fail.
    """
    snowfall = float(weather_inputs.get('snowfall_24h', 0.0) or 0.0)
    wind = float(weather_inputs.get('wind_loading', 0.0) or 0.0)
    temp_gradient = float(weather_inputs.get('temp_gradient', 0.5) or 0.5)
    elevation = float(terrain_inputs.get('elevation', 0.5) or 0.5)

    shear = 2.0 + elevation * 4.0 - temp_gradient * 2.0 + (1 - wind) * 1.5
    shear = float(np.clip(shear, 0.5, 12.0))
    settlement = 0.2 + snowfall * 0.4 + elevation * 0.25
    settlement = float(np.clip(settlement, 0.0, 1.0))

    proxy = SnowpackProxy(
        estimated_shear_strength=round(shear, 2),
        snow_settlement_index=round(settlement, 3),
        season_start='synthetic_fallback',
        method='synthetic_fallback_v1',
    )
    return _heuristic_to_physics_result(proxy, weather_inputs, terrain_inputs)


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def _physics_cache_key(lat: float, lng: float, as_of: datetime) -> str:
    return f'{lat:.4f},{lng:.4f},{as_of.date().isoformat()}'


def _physics_cache_path(cache_dir: str | None, key: str) -> Path | None:
    if not cache_dir:
        return None
    safe_key = key.replace(',', '_').replace(':', '-')
    return Path(cache_dir) / f'{safe_key}.json'


def _load_physics_cache(path: Path | None) -> SnowpackPhysicsResult | None:
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return SnowpackPhysicsResult(
            weak_layer_depth_m=float(data['weak_layer_depth_m']),
            weak_layer_grain_type=str(data['weak_layer_grain_type']),
            weak_layer_shear_strength_kpa=float(data['weak_layer_shear_strength_kpa']),
            snowpack_stability_index=float(data['snowpack_stability_index']),
            temperature_gradient_per_m=float(data['temperature_gradient_per_m']),
            liquid_water_content_pct=float(data['liquid_water_content_pct']),
            layer_count=int(data['layer_count']),
            snow_height_m=float(data['snow_height_m']),
            bulk_density_kgm3=float(data['bulk_density_kgm3']),
            method=str(data['method']),
            layers=data.get('layers', []),
        )
    except Exception:
        return None


def _write_physics_cache(path: Path | None, result: SnowpackPhysicsResult) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'weak_layer_depth_m': result.weak_layer_depth_m,
        'weak_layer_grain_type': result.weak_layer_grain_type,
        'weak_layer_shear_strength_kpa': result.weak_layer_shear_strength_kpa,
        'snowpack_stability_index': result.snowpack_stability_index,
        'temperature_gradient_per_m': result.temperature_gradient_per_m,
        'liquid_water_content_pct': result.liquid_water_content_pct,
        'layer_count': result.layer_count,
        'snow_height_m': result.snow_height_m,
        'bulk_density_kgm3': result.bulk_density_kgm3,
        'method': result.method,
        'layers': result.layers,
    }
    tmp = path.with_suffix(f'{path.suffix}.tmp')
    tmp.write_text(json.dumps(payload, sort_keys=True), encoding='utf-8')
    tmp.replace(path)


# ---------------------------------------------------------------------------
# SNOWPACK native execution (C++ gold standard)
# ---------------------------------------------------------------------------

def run_snowpack_native_cell(
    *,
    lat: float,
    lng: float,
    elevation_m: float,
    weather_history: list[dict[str, float]],
    as_of: datetime,
    slope_angle: float = 0.0,
    aspect: float = 0.0,
) -> SnowpackPhysicsResult:
    """Run SNOWPACK C++ binary for a single grid cell.

    Generates an SMET file from Open-Meteo weather history, invokes the
    SNOWPACK binary, and parses the .pro profile output.

    Args:
        lat: Cell latitude
        lng: Cell longitude
        elevation_m: Cell elevation in meters
        weather_history: Hourly weather samples from Nov 1 to as_of
        as_of: Current datetime for simulation end
        slope_angle: Slope angle in degrees
        aspect: Slope aspect in degrees

    Returns:
        SnowpackPhysicsResult with method='snowpack_native'

    Raises:
        RuntimeError: If SNOWPACK binary is unavailable or execution fails
    """
    import tempfile

    if not weather_history:
        raise RuntimeError('No weather history provided for SNOWPACK simulation')

    if not snowpack_binary_available():
        raise RuntimeError('SNOWPACK binary not available. Run: bash scripts/build_snowpack.sh')

    season_start = winter_season_start(as_of)

    with tempfile.TemporaryDirectory(prefix='snowpack_') as tmpdir:
        tmp_path = Path(tmpdir)

        # Generate SMET input file
        smet_path = tmp_path / f'cell_{lat:.4f}_{lng:.4f}.smet'
        write_smet_file(
            output_path=smet_path,
            station_id=f'cell_{lat:.4f}_{lng:.4f}',
            latitude=lat,
            longitude=lng,
            elevation=elevation_m,
            samples=weather_history,
            slope_angle=slope_angle,
            aspect=aspect,
        )

        # Generate SNOWPACK config.  The live cell path must bind the same
        # coordinates, station, input directory, and output directory that the
        # native runner will use; otherwise config generation fails closed or
        # the binary writes profiles where the caller does not discover them.
        output_dir = tmp_path / 'output'
        config_path = tmp_path / 'snowpack.ini'
        generate_snowpack_config(
            output_path=config_path,
            season_start_date=season_start.isoformat(),
            end_date=as_of.date().isoformat(),
            station_id=f'cell_{lat:.4f}_{lng:.4f}',
            latitude=lat,
            longitude=lng,
            meteo_path=tmp_path,
            output_dir=output_dir,
        )

        # Run SNOWPACK binary
        evidence = run_snowpack_native(
            smet_path=smet_path,
            output_dir=output_dir,
            config_path=config_path,
            timeout_s=int(SNOWPACK_PHYSICS_TIMEOUT_S),
        )

        if evidence is None or not evidence.success or not evidence.pro_path:
            raise RuntimeError('SNOWPACK execution failed — no successful .pro output produced')

        # Parse .pro output
        parsed = parse_snowpack_pro(Path(evidence.pro_path))

        return SnowpackPhysicsResult(
            weak_layer_depth_m=parsed['weak_layer_depth_m'],
            weak_layer_grain_type=parsed['weak_layer_grain_type'],
            weak_layer_shear_strength_kpa=parsed['weak_layer_shear_strength_kpa'],
            snowpack_stability_index=parsed['snowpack_stability_index'],
            temperature_gradient_per_m=parsed['temperature_gradient_per_m'],
            liquid_water_content_pct=parsed['liquid_water_content_pct'],
            layer_count=parsed['layer_count'],
            snow_height_m=parsed['snow_height_m'],
            bulk_density_kgm3=parsed['bulk_density_kgm3'],
            method='snowpack_native',
            layers=parsed['layers'],
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_cell_snowpack_physics(
    *,
    lat: float,
    lng: float,
    elevation_m: float,
    as_of: datetime,
    weather_history: list[dict[str, float]] | None = None,
    weather_inputs: dict[str, float] | None = None,
    terrain_inputs: dict[str, float] | None = None,
    cache_dir: str | None = None,
    zone_type: str | None = None,
) -> SnowpackPhysicsResult:
    """Compute physics-based snowpack properties for a single grid cell.

    Tries SNOWPACK native (C++ gold standard) first, then COSIPY (Python),
    then heuristic proxy, then synthetic fallback.

    Args:
        lat: Cell latitude
        lng: Cell longitude
        elevation_m: Cell elevation in meters
        as_of: Current datetime
        weather_history: Hourly weather samples (for COSIPY/SNOWPACK)
        weather_inputs: Normalized weather inputs (for fallback)
        terrain_inputs: Normalized terrain inputs (for fallback)
        cache_dir: Optional cache directory path
        zone_type: Optional zone_type for zone-specific COSIPY calibration

    Returns:
        SnowpackPhysicsResult with physics-derived snowpack properties
    """
    key = _physics_cache_key(lat, lng, as_of)
    cache_path = _physics_cache_path(cache_dir, key)

    # Try cache first
    cached = _load_physics_cache(cache_path)
    if cached is not None:
        return cached

    result: SnowpackPhysicsResult | None = None

    # Try SNOWPACK native (C++ gold standard) if binary is available
    if SNOWPACK_PHYSICS_ENABLED and weather_history and snowpack_binary_available():
        try:
            terrain = terrain_inputs or {}
            result = run_snowpack_native_cell(
                lat=lat,
                lng=lng,
                elevation_m=elevation_m,
                weather_history=weather_history,
                as_of=as_of,
                slope_angle=float(terrain.get('slope_angle_deg', terrain.get('slope_deg', 0.0)) or 0.0),
                aspect=float(terrain.get('aspect_deg', 0.0) or 0.0),
            )
        except Exception:
            result = None  # fall through to COSIPY

    # Try COSIPY if enabled and weather history available
    if result is None and SNOWPACK_PHYSICS_ENABLED and weather_history and _cosipy_available():
        try:
            result = run_cosipy_cell(
                lat=lat,
                lng=lng,
                elevation_m=elevation_m,
                weather_history=weather_history,
                as_of=as_of,
            )
        except Exception:
            result = None  # fall through to heuristic

    # Fall back to heuristic snowpack_proxy
    if result is None:
        zone_overrides = load_zone_overrides(zone_type)
        try:
            proxy = compute_cell_snowpack_proxy(
                lat=lat,
                lng=lng,
                as_of=as_of,
                weather_inputs=weather_inputs or {},
                terrain_inputs=terrain_inputs or {},
            )
            if proxy is not None:
                result = _heuristic_to_physics_result(proxy, weather_inputs, terrain_inputs)
                # Apply zone-specific density/temperature/grain overrides to heuristic result
                if zone_overrides and result.method == 'heuristic_fallback':
                    # Use zone-specific temperature_bottom to compute a more
                    # realistic temperature gradient.  The bottom temperature
                    # from the TOML overrides represents the ground-snow
                    # interface temperature for that zone's snow climate.
                    temp_bottom_k = float(zone_overrides.get('temperature_bottom', 273.15))
                    # Estimate gradient: (surface_temp - bottom_temp) / snow_height
                    # Assume surface is at air temp (~263 K for continental winter)
                    surface_temp_k = 263.0 if zone_type in ('great_himalaya', 'karakoram_ladakh') else 273.0
                    zone_temp_gradient = abs(surface_temp_k - temp_bottom_k) / max(result.snow_height_m, 0.3)

                    # Adjust stability index using zone-specific t_star parameters
                    # Higher t_star_dry means drier snow → more stable (less wet-slab risk)
                    t_star_dry = float(zone_overrides.get('t_star_dry', 30))
                    stability_adjustment = 1.0 + (t_star_dry - 30) * 0.005
                    zone_stability = result.snowpack_stability_index * stability_adjustment

                    # Use zone-specific grain type when available
                    zone_grain = _ZONE_GRAIN_TYPE.get(zone_type or '', result.weak_layer_grain_type)

                    result = SnowpackPhysicsResult(
                        weak_layer_depth_m=result.weak_layer_depth_m,
                        weak_layer_grain_type=zone_grain,
                        weak_layer_shear_strength_kpa=result.weak_layer_shear_strength_kpa,
                        snowpack_stability_index=round(zone_stability, 3),
                        temperature_gradient_per_m=round(zone_temp_gradient, 4),
                        liquid_water_content_pct=result.liquid_water_content_pct,
                        layer_count=result.layer_count,
                        snow_height_m=result.snow_height_m,
                        bulk_density_kgm3=float(zone_overrides.get('initial_top_density_snowpack', result.bulk_density_kgm3)),
                        method=result.method + '_zone_calibrated',
                        layers=result.layers,
                    )
        except Exception:
            result = None

    # Final fallback: synthetic
    if result is None:
        result = _fallback_physics_proxy(
            weather_inputs or {},
            terrain_inputs or {},
        )

    # Cache the result
    _write_physics_cache(cache_path, result)

    return result


def compute_batch_snowpack_physics(
    *,
    coordinates: list[tuple[float, float, float]],  # (lat, lng, elevation_m)
    as_of: datetime,
    weather_history_fn: Any | None = None,  # callable(lat, lng) -> list[dict]
    weather_inputs_fn: Any | None = None,    # callable(lat, lng) -> dict[str, float]
    terrain_inputs_fn: Any | None = None,    # callable(lat, lng) -> dict[str, float]
    cache_dir: str | None = None,
    zone_type: str | None = None,
    max_workers: int | None = None,
    progress_callback: Any | None = None,  # callable(completed, total) -> None
) -> list[SnowpackPhysicsBatchResult]:
    """Compute physics-based snowpack properties for multiple grid cells.

    F5: Uses ThreadPoolExecutor for parallel execution when max_workers > 1.
    Falls back to sequential loop if parallel execution fails.

    Args:
        coordinates: List of (lat, lng, elevation_m) tuples
        as_of: Current datetime
        weather_history_fn: Optional callable returning weather history per cell
        weather_inputs_fn: Optional callable returning normalized weather inputs per cell
        terrain_inputs_fn: Optional callable returning normalized terrain inputs per cell
        cache_dir: Optional cache directory path
        zone_type: Optional zone_type for zone-specific COSIPY calibration
        max_workers: Number of parallel workers (default: min(cpu_count, 8))
        progress_callback: Optional callable(completed: int, total: int) -> None

    Returns:
        List of SnowpackPhysicsBatchResult, one per coordinate
    """
    total = len(coordinates)
    if total == 0:
        return []

    resolved_workers = max_workers or min(os.cpu_count() or 4, 8)
    use_parallel = resolved_workers > 1 and total > 1

    def _process_single(idx: int) -> tuple[int, SnowpackPhysicsBatchResult]:
        lat, lng, elevation_m = coordinates[idx]
        try:
            weather_history = weather_history_fn(lat, lng) if weather_history_fn else None
            weather_inputs = weather_inputs_fn(lat, lng) if weather_inputs_fn else None
            terrain_inputs = terrain_inputs_fn(lat, lng) if terrain_inputs_fn else None

            result = compute_cell_snowpack_physics(
                lat=lat,
                lng=lng,
                elevation_m=elevation_m,
                as_of=as_of,
                weather_history=weather_history,
                weather_inputs=weather_inputs,
                terrain_inputs=terrain_inputs,
                cache_dir=cache_dir,
                zone_type=zone_type,
            )
            return idx, SnowpackPhysicsBatchResult(result=result, status='ok')
        except Exception as exc:
            return idx, SnowpackPhysicsBatchResult(
                result=None,
                status='error',
                error=str(exc),
            )

    results: list[SnowpackPhysicsBatchResult | None] = [None] * total
    completed = 0

    if use_parallel:
        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=resolved_workers) as executor:
                futures = {
                    executor.submit(_process_single, i): i
                    for i in range(total)
                }
                for future in as_completed(futures):
                    idx, batch_result = future.result()
                    results[idx] = batch_result
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, total)
        except Exception:
            # Fall back to sequential if parallel fails
            results = [None] * total
            completed = 0
            use_parallel = False

    if not use_parallel:
        for i in range(total):
            idx, batch_result = _process_single(i)
            results[idx] = batch_result
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    return [r for r in results if r is not None]


def compute_grid_snowpack_physics(
    *,
    grid_cells: list[dict[str, Any]],
    as_of: datetime,
    weather_history_fn: Any | None = None,
    weather_inputs_fn: Any | None = None,
    terrain_inputs_fn: Any | None = None,
    cache_dir: str | None = None,
    max_workers: int | None = None,
    progress_callback: Any | None = None,
) -> dict[str, SnowpackPhysicsResult]:
    """F5: Grid-scale parallel snowpack physics computation.

    Groups cells by zone_type for zone-specific calibration, then runs
    compute_batch_snowpack_physics per zone group.

    Args:
        grid_cells: List of cell dicts with keys: cell_id, lat, lng, elevation_m, zone_type (optional)
        as_of: Current datetime
        weather_history_fn: Optional callable(lat, lng) -> list[dict]
        weather_inputs_fn: Optional callable(lat, lng) -> dict[str, float]
        terrain_inputs_fn: Optional callable(lat, lng) -> dict[str, float]
        cache_dir: Optional cache directory
        max_workers: Parallel workers per zone group
        progress_callback: Optional callable(completed, total) -> None

    Returns:
        Dict mapping cell_id -> SnowpackPhysicsResult. Cells with errors
        are omitted from the dict.
    """
    if not grid_cells:
        return {}

    zone_groups: dict[str | None, list[tuple[int, dict[str, Any]]]] = {}
    for idx, cell in enumerate(grid_cells):
        zone = cell.get('zone_type')
        zone_groups.setdefault(zone, []).append((idx, cell))

    total = len(grid_cells)
    completed = 0
    results_by_cell_id: dict[str, SnowpackPhysicsResult] = {}

    for zone, group in zone_groups.items():
        coordinates = [
            (float(c['lat']), float(c['lng']), float(c['elevation_m']))
            for _, c in group
        ]
        cell_ids = [str(c.get('cell_id') or f'cell_{idx}') for idx, c in group]

        batch_results = compute_batch_snowpack_physics(
            coordinates=coordinates,
            as_of=as_of,
            weather_history_fn=weather_history_fn,
            weather_inputs_fn=weather_inputs_fn,
            terrain_inputs_fn=terrain_inputs_fn,
            cache_dir=cache_dir,
            zone_type=zone,
            max_workers=max_workers,
        )

        for cell_id, batch_result in zip(cell_ids, batch_results):
            if batch_result.result is not None:
                results_by_cell_id[cell_id] = batch_result.result
            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    return results_by_cell_id


def physics_result_to_proxy_dict(result: SnowpackPhysicsResult) -> dict[str, Any]:
    """Convert SnowpackPhysicsResult to the dict format expected by the UI/API.

    This mirrors the existing snowpack_proxy payload format for backward
    compatibility with the frontend and data lineage tracking.
    """
    return {
        'estimated_shear_strength': result.weak_layer_shear_strength_kpa,
        'snow_settlement_index': float(np.clip(1.0 - result.bulk_density_kgm3 / 600.0, 0.0, 1.0)),
        'season_start': 'physics_model',
        'method': result.method,
        'weak_layer_depth_m': result.weak_layer_depth_m,
        'weak_layer_grain_type': result.weak_layer_grain_type,
        'snowpack_stability_index': result.snowpack_stability_index,
        'temperature_gradient_per_m': result.temperature_gradient_per_m,
        'liquid_water_content_pct': result.liquid_water_content_pct,
        'layer_count': result.layer_count,
        'snow_height_m': result.snow_height_m,
        'bulk_density_kgm3': result.bulk_density_kgm3,
    }


def export_constraint_targets(result: SnowpackPhysicsResult) -> dict[str, float | None]:
    """Export physics constraint targets for PINN training.

    Provides mass-balance, energy-balance, and density-profile targets
    that the PINN residual MLP uses as conservation constraints.

    Args:
        result: A SnowpackPhysicsResult from COSIPY/SNOWPACK or heuristic.

    Returns:
        Dict with constraint target values:
        - mass_balance_kgm2: SWE = density * height
        - energy_balance_K: surface temperature proxy
        - density_profile_kgm3: bulk density
        - temp_gradient_K_per_m: temperature gradient
        - liquid_water_content_pct: LWC
    """
    swe = result.bulk_density_kgm3 * result.snow_height_m if result.bulk_density_kgm3 and result.snow_height_m else None

    return {
        'mass_balance_kgm2': swe,
        'energy_balance_K': None,  # would come from surface temp field
        'density_profile_kgm3': result.bulk_density_kgm3,
        'temp_gradient_K_per_m': result.temperature_gradient_per_m,
        'liquid_water_content_pct': result.liquid_water_content_pct,
        'method': result.method,
    }
