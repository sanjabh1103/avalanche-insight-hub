"""Research-only open-forcing lane.

This package is intentionally separate from the existing RF/TreeSHAP runtime.
It can build and validate open gridded forcing inputs, but it cannot publish
forecasts or produce authoritative danger labels.
"""

from .contracts import (
    OPEN_FORCING_LANE,
    OpenForcingContractError,
    OpenForcingPolicy,
    SourceSnapshot,
)
from .cosipy_adapter import (
    CosipyForcingSeries,
    CosipyNativeResult,
    build_cosipy_dataset,
    load_cosipy_api,
    run_cosipy_coupled_reference,
    run_cosipy_reference,
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
from .snowpack_adapter import (
    HimalayanSiteSpec,
    HimalayanSnowpackForcing,
    build_himalayan_snowpack_forcing,
    precipitation_phase_fraction,
    write_himalayan_smet,
)

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
