"""Research-only open-forcing lane.

This package is intentionally separate from the existing RF/TreeSHAP runtime.
It can build and validate open gridded forcing inputs, but it cannot publish
forecasts or produce authoritative danger labels.

Physics adapter modules (cosipy_adapter, snowpack_adapter) are loaded lazily
via PEP 562 module-level __getattr__ to prevent unintended loading of physics
dependencies in the T2A research lane.
"""
from .contracts import (
    OPEN_FORCING_LANE,
    OpenForcingContractError,
    OpenForcingPolicy,
    SourceSnapshot,
)
from .source_registry import (
    DEFAULT_SOURCE_DEFINITIONS,
    ForcingSnapshotManifest,
    SourceDefinition,
    SourceRegistry,
)
from .downscaling import (
    EffectiveResolution,
    WindVector,
    downscale_shortwave_radiation,
    downscale_temperature_celsius,
    redistribute_precipitation_mm,
    resolution_metadata,
    terrain_radiation_factor,
    transform_wind_vector,
)
from .replay import CoverageMask, PhysicalValidationReport, SourceReplay
from .physical_validation import PhysicalObservation, compare_continuous_observations
from .coverage import AoiBounds, AoiCoveragePlan, NativeForcingPoint, construct_aoi_coverage_plan
from .open_meteo_source import (
    NativeSourcePointPayload,
    OpenMeteoPointSeries,
    OpenMeteoRunRequest,
    parse_open_meteo_single_run,
)

# T2A Sprint 1B: Lazy imports for physics adapters — only loaded when accessed.
# This prevents cosipy_adapter and snowpack_adapter from being imported when
# a consumer only needs non-physics functionality (contracts, source registry,
# downscaling, replay, coverage, open-meteo).
_LAZY_IMPORTS = {
    'CosipyForcingSeries': ('.cosipy_adapter', 'CosipyForcingSeries'),
    'CosipyNativeResult': ('.cosipy_adapter', 'CosipyNativeResult'),
    'build_cosipy_dataset': ('.cosipy_adapter', 'build_cosipy_dataset'),
    'load_cosipy_api': ('.cosipy_adapter', 'load_cosipy_api'),
    'run_cosipy_coupled_reference': ('.cosipy_adapter', 'run_cosipy_coupled_reference'),
    'run_cosipy_reference': ('.cosipy_adapter', 'run_cosipy_reference'),
    'HimalayanSiteSpec': ('.snowpack_adapter', 'HimalayanSiteSpec'),
    'HimalayanSnowpackForcing': ('.snowpack_adapter', 'HimalayanSnowpackForcing'),
    'build_himalayan_snowpack_forcing': ('.snowpack_adapter', 'build_himalayan_snowpack_forcing'),
    'precipitation_phase_fraction': ('.snowpack_adapter', 'precipitation_phase_fraction'),
    'write_himalayan_smet': ('.snowpack_adapter', 'write_himalayan_smet'),
}

__all__ = [
    "OPEN_FORCING_LANE",
    "OpenForcingContractError",
    "OpenForcingPolicy",
    "SourceSnapshot",
    "CosipyForcingSeries",
    "CosipyNativeResult",
    "build_cosipy_dataset",
    "load_cosipy_api",
    "run_cosipy_reference",
    "run_cosipy_coupled_reference",
    "DEFAULT_SOURCE_DEFINITIONS",
    "ForcingSnapshotManifest",
    "SourceDefinition",
    "SourceRegistry",
    "EffectiveResolution",
    "WindVector",
    "downscale_shortwave_radiation",
    "downscale_temperature_celsius",
    "redistribute_precipitation_mm",
    "resolution_metadata",
    "terrain_radiation_factor",
    "transform_wind_vector",
    "CoverageMask",
    "PhysicalValidationReport",
    "SourceReplay",
    "PhysicalObservation",
    "compare_continuous_observations",
    "AoiBounds",
    "AoiCoveragePlan",
    "NativeForcingPoint",
    "construct_aoi_coverage_plan",
    "NativeSourcePointPayload",
    "OpenMeteoPointSeries",
    "OpenMeteoRunRequest",
    "parse_open_meteo_single_run",
    "HimalayanSiteSpec",
    "HimalayanSnowpackForcing",
    "build_himalayan_snowpack_forcing",
    "precipitation_phase_fraction",
    "write_himalayan_smet",
]


def __getattr__(name):
    """PEP 562: lazily load physics adapter exports on first attribute access."""
    if name in _LAZY_IMPORTS:
        import importlib
        module_path, attr_name = _LAZY_IMPORTS[name]
        module = importlib.import_module(module_path, __name__)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """PEP 562: list both eager and lazy exports for discoverability."""
    return sorted(list(__all__) + list(_LAZY_IMPORTS.keys()))
