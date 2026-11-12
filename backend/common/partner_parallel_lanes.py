"""Partner parallel lane preparation — P9.

Defines two parallel preparation lanes for parallel engineering preparation.
Feature generation is independently gated; neither lane is training-ready:

1. Track 2A (T2A): Open-forcing and terrain shadow analysis
   - Uses public ERA5/IMD reanalysis forcing data
   - Computes terrain shadowing and aspect-related features
   - Engineering preparation is station-free; feature generation still requires
     verified source bytes, schema, rights, and lineage
   - Output: Feature packets for future model training

2. Track 1: Station and SNOWPACK simulation packets
   - Uses public weather station data where available
   - Runs SNOWPACK model simulations for Himalayan stations
   - Requires Partner-approved station/anchor evidence, not a public substitute
   - Output: Snowpack profile features for future model training

P9 exit gate: Both lanes are defined with their data sources, dependencies,
outputs, and blocking conditions. T2A permits engineering preparation only;
Track 1 requires Partner-approved station/anchor data and cannot generate features
without it. Neither lane can train, evaluate, promote, or serve at this stage.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParallelLaneV1:
    """A single parallel preparation lane.

    P9 contract: lane_id, track, data_sources, dependencies, outputs,
    blocking_conditions, and granular operation permissions.

    G12: Granular permission fields replace the coarse can_proceed/Partner_approval_required.
    Each phase of preparation has its own permission flag.
    """

    lane_id: str
    track: str  # 'T2A' or 'Track1'
    description: str
    data_sources: list[str]
    dependencies: list[str]
    outputs: list[str]
    blocking_conditions: list[str]
    # Legacy fields are retained for packet compatibility. They are checked
    # against the granular permissions and are never used as the authority.
    Partner_approval_required: bool = False
    can_proceed: bool = False
    is_specification: bool = True  # True = description only, False = executable pipeline
    # G12: Granular permission fields — each phase has its own gate
    engineering_preparation_allowed: bool = True
    feature_generation_allowed: bool = False
    training_allowed: bool = False
    evaluation_allowed: bool = False
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.can_proceed != self.feature_generation_allowed:
            raise ValueError(
                'legacy can_proceed must equal feature_generation_allowed; '
                'granular permissions are authoritative'
            )
        if self.track == 'Track1' and not self.Partner_approval_required:
            raise ValueError('Track 1 must require Partner approval for station/anchor evidence')

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Track 2A: Open-forcing and terrain shadow analysis
# NOTE: This is a SPECIFICATION, not an implementation. No executable code
# connects to ERA5/IMD/OSM data sources yet. Data source connections must
# be implemented before this lane can produce features.
T2A_LANE = ParallelLaneV1(
    lane_id='T2A_open_forcing_terrain_shadow',
    track='T2A',
    description=(
        'SPECIFICATION (not yet implemented): Open-forcing and terrain shadow analysis '
        'using public reanalysis data. Computes terrain features (aspect, slope, shadowing) '
        'and forcing variables (temperature, wind, precipitation) from ERA5/IMD reanalysis. '
        'Does NOT require Partner station data or labels. '
        'WARNING: No executable data pipeline exists for ERA5/IMD/OSM sources.'
    ),
    data_sources=[
        'ERA5 reanalysis (public, ECMWF/Copernicus)',
        'IMD gridded temperature and rainfall (public, Indian Met Dept)',
        'SRTM/ASTER DEM (public, NASA/USGS) for terrain features',
        'OpenStreetMap for geographic boundaries',
    ],
    dependencies=[
        'ERA5 API access (Copernicus Climate Data Store)',
        'xarray and netCDF4 for gridded data processing',
        'SRTM/ASTER DEM data for Himalayan region',
    ],
    outputs=[
        'Terrain feature packets: aspect, slope, shadowing per grid cell',
        'Forcing feature packets: temperature, wind, precipitation time series',
        'Combined feature matrix ready for future model training',
        'Feature provenance manifest with data source hashes',
    ],
    blocking_conditions=[
        'ERA5 API access not configured',
        'DEM data not downloaded for Himalayan region',
        'source rights and content hashes not verified',
    ],
    Partner_approval_required=False,
    can_proceed=False,
    notes=(
        'Engineering preparation only. The listed sources may be public, but '
        'rights, source bytes, schemas, and lineage must be verified before '
        'feature generation. Outputs are inputs, never labels.'
    ),
)


# Track 1: Station and SNOWPACK simulation packets
# NOTE: This is a SPECIFICATION, not an implementation. The SNOWPACK physics
# model exists at backend/common/snowpack_physics.py but is not validated for
# Himalayan conditions. No executable data pipeline connects to station
# data sources yet.
# G11: Track 1 REQUIRES Partner-approved station/anchor data and the approved
# reference lane. It does NOT use "any public station source" as a substitute.
TRACK1_LANE = ParallelLaneV1(
    lane_id='Track1_station_snowpack',
    track='Track1',
    description=(
        'SPECIFICATION (not yet implemented): Station data collection and SNOWPACK model '
        'simulation for Himalayan stations. REQUIRES Partner-approved station/anchor data '
        'and the approved reference lane — does NOT substitute public station sources. '
        'Runs SNOWPACK physics model to generate snowpack profile features. '
        'WARNING: SNOWPACK model exists but is not validated for Himalayan conditions. '
        'No executable data pipeline connects to station data sources yet. '
        'This lane is BLOCKED until Partner provides approved station data.'
    ),
    data_sources=[
        'Partner-approved station data from 70 surface observatories (REQUIRED)',
        'ERA5 reanalysis as forcing for SNOWPACK at station locations',
        'Published station coordinates from Partner research papers (P8 literature matrix)',
        'SNOWPACK model (already in codebase)',
    ],
    dependencies=[
        'SNOWPACK physics model (backend/common/snowpack_physics.py)',
        'Partner-approved station/anchor data (REQUIRED — no public substitute)',
        'Approved reference lane (from Partner)',
        'ERA5 forcing data (shared with T2A)',
    ],
    outputs=[
        'Snowpack profile feature packets per station',
        'Station metadata manifest with coordinates and data sources',
        'SNOWPACK simulation output: snow stratigraphy, temperature gradient, etc.',
        'Feature provenance manifest with simulation parameters',
    ],
    blocking_conditions=[
        'Partner-approved station data not provided',
        'Approved reference lane not established',
        'SNOWPACK model not validated for Himalayan conditions',
    ],
    Partner_approval_required=True,
    can_proceed=False,
    engineering_preparation_allowed=True,
    feature_generation_allowed=False,
    training_allowed=False,
    evaluation_allowed=False,
    notes=(
        'G11: This lane REQUIRES Partner-approved station/anchor data. '
        'Public station data (NOAA/ISD) is NOT a substitute for Partner-approved data. '
        'This lane is BLOCKED until Partner provides approved station data and '
        'establishes the approved reference lane. '
        'Engineering preparation (SNOWPACK validation, coordinate extraction) '
        'can proceed, but feature generation cannot.'
    ),
)


def get_parallel_lanes() -> list[ParallelLaneV1]:
    """Return both parallel preparation lanes.

    P9 exit gate: Both lanes are defined with their data sources, dependencies,
    outputs, blocking conditions, and granular permissions. Track 1 requires
    Partner-approved station/anchor evidence; T2A is station-free but remains
    specification-only until source contracts pass.
    """
    return [T2A_LANE, TRACK1_LANE]


def build_lane_summary() -> dict[str, Any]:
    """Build a summary of parallel lanes for the Partner decision packet.

    P9 exit gate: The summary confirms which lanes can proceed and which are blocked.
    G12: Reports granular permission fields for each lane.
    """
    lanes = get_parallel_lanes()
    from backend.common.Partner_lane_sources import build_lane_source_contracts

    source_contracts = {
        lane.track.lower(): [
            contract.to_dict() for contract in build_lane_source_contracts(lane.track.lower())
        ]
        for lane in lanes
    }
    all_specification = all(lane.is_specification for lane in lanes)
    can_proceed_count = sum(1 for lane in lanes if lane.feature_generation_allowed)
    blocked_count = sum(1 for lane in lanes if not lane.feature_generation_allowed)
    return {
        'schema_version': 'Partner_parallel_lanes_v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'total_lanes': len(lanes),
        'lanes_can_proceed': can_proceed_count,
        'lanes_blocked': blocked_count,
        'all_can_proceed': all(lane.feature_generation_allowed for lane in lanes),
        'none_require_Partner_approval': not any(lane.Partner_approval_required for lane in lanes),
        'all_are_specification_only': all_specification,
        'implemented_lane_count': sum(1 for lane in lanes if not lane.is_specification),
        # G12: Granular permission summary
        'engineering_preparation_allowed_count': sum(1 for lane in lanes if lane.engineering_preparation_allowed),
        'engineering_only_count': sum(
            1 for lane in lanes
            if lane.engineering_preparation_allowed and not lane.feature_generation_allowed
        ),
        'feature_generation_allowed_count': sum(1 for lane in lanes if lane.feature_generation_allowed),
        'training_allowed_count': sum(1 for lane in lanes if lane.training_allowed),
        'evaluation_allowed_count': sum(1 for lane in lanes if lane.evaluation_allowed),
        'source_contracts': source_contracts,
        'lanes': [lane.to_dict() for lane in lanes],
        'key_finding': (
            f'{len(lanes)} parallel preparation lanes defined. '
            f'{can_proceed_count} can proceed without Partner approval, '
            f'{blocked_count} are BLOCKED (require Partner-approved data). '
            f'WARNING: All lanes are SPECIFICATION ONLY — no executable data pipeline exists. '
            f'Output features (not labels) will be combined with Partner-approved '
            f'labels in P11 conditional training.'
            if all_specification else
            f'{len(lanes)} parallel preparation lanes defined. '
            f'{sum(1 for lane in lanes if not lane.is_specification)} have executable pipelines. '
            f'{can_proceed_count} can proceed, {blocked_count} are blocked.'
        ),
    }


def save_lane_summary(summary: dict[str, Any], path: Path) -> None:
    """Save lane summary to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))


def load_lane_summary(path: Path) -> dict[str, Any] | None:
    """Load a previously saved lane summary fail-closed."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('E030_malformed_evidence: lane summary must be a JSON object')
        return payload
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'lane summary load failed: {exc}') from exc
