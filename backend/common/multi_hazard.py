"""F14: Multi-Hazard Framework.

Extends the avalanche forecasting system to support multiple hazard types:
- Avalanche (existing)
- Landslide (rainfall-triggered)
- Flood (glacial lake outburst / extreme precipitation)
- Rockfall (seismic + thermal stress)

Each hazard type has its own risk weights, triggers, and visualization.
The framework is designed to be extensible — new hazard types can be added
without modifying existing avalanche logic.

Env flags:
  MULTI_HAZARD_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

MULTI_HAZARD_ENABLED = os.getenv('MULTI_HAZARD_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}

HAZARD_AVALANCHE = 'avalanche'
HAZARD_LANDSLIDE = 'landslide'
HAZARD_FLOOD = 'flood'
HAZARD_ROCKFALL = 'rockfall'

SUPPORTED_HAZARDS = {HAZARD_AVALANCHE, HAZARD_LANDSLIDE, HAZARD_FLOOD, HAZARD_ROCKFALL, 'debris_flow'}


@dataclass(frozen=True)
class HazardConfig:
    """Configuration for a single hazard type."""
    hazard_type: str
    display_name: str
    risk_weights: dict[str, float]
    trigger_thresholds: dict[str, float]
    color_hex: str
    icon: str
    description: str


@dataclass
class HazardAssessment:
    """Risk assessment result for a single hazard type."""
    hazard_type: str
    risk_score: float  # 0-5 scale (matching avalanche risk levels)
    risk_level: int  # 0-5 integer
    confidence: float
    trigger_met: bool
    contributing_factors: dict[str, float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MultiHazardResult:
    """Combined multi-hazard assessment for a grid cell."""
    cell_lat: float
    cell_lng: float
    hazard_assessments: dict[str, HazardAssessment]
    dominant_hazard: str
    composite_risk: float  # Weighted combination
    composite_risk_level: int
    any_trigger_met: bool


# Default hazard configurations
DEFAULT_HAZARD_CONFIGS: dict[str, HazardConfig] = {
    HAZARD_AVALANCHE: HazardConfig(
        hazard_type=HAZARD_AVALANCHE,
        display_name='Avalanche',
        risk_weights={
            'snow_load': 0.35,
            'slope_angle': 0.25,
            'temperature_delta': 0.20,
            'wind_transport': 0.10,
            'seismic_amplification': 0.10,
        },
        trigger_thresholds={
            'min_slope': 25.0,
            'min_snow_depth': 30.0,
        },
        color_hex='#2563eb',
        icon='mountain-snow',
        description='Snow slab release on steep terrain',
    ),
    HAZARD_LANDSLIDE: HazardConfig(
        hazard_type=HAZARD_LANDSLIDE,
        display_name='Landslide',
        risk_weights={
            'rainfall_24h': 0.35,
            'slope_angle': 0.25,
            'soil_saturation': 0.20,
            'lithology': 0.10,
            'seismic_amplification': 0.10,
        },
        trigger_thresholds={
            'min_slope': 15.0,
            'min_rainfall_24h': 50.0,
        },
        color_hex='#d97706',
        icon='landslide',
        description='Rainfall-triggered slope failure',
    ),
    HAZARD_FLOOD: HazardConfig(
        hazard_type=HAZARD_FLOOD,
        display_name='Flood',
        risk_weights={
            'precipitation_72h': 0.35,
            'snowmelt_rate': 0.25,
            'river_proximity': 0.20,
            'glacial_lake_proximity': 0.10,
            'upstream_area': 0.10,
        },
        trigger_thresholds={
            'min_precipitation_72h': 100.0,
        },
        color_hex='#0891b2',
        icon='waves',
        description='Glacial lake outburst or extreme precipitation flooding',
    ),
    HAZARD_ROCKFALL: HazardConfig(
        hazard_type=HAZARD_ROCKFALL,
        display_name='Rockfall',
        risk_weights={
            'thermal_stress': 0.30,
            'slope_angle': 0.25,
            'seismic_amplification': 0.20,
            'freeze_thaw_cycles': 0.15,
            'lithology': 0.10,
        },
        trigger_thresholds={
            'min_slope': 40.0,
        },
        color_hex='#dc2626',
        icon='rock',
        description='Thermal and seismic stress-driven rock failure',
    ),
    'debris_flow': HazardConfig(
        hazard_type='debris_flow',
        display_name='Debris Flow',
        risk_weights={
            'rainfall_intensity': 0.40,
            'rainfall_duration': 0.20,
            'slope_angle': 0.20,
            'sediment_availability': 0.20,
        },
        trigger_thresholds={
            'min_rainfall_intensity': 10.0,
            'min_slope': 15.0,
        },
        color_hex='#9333ea',
        icon='activity',
        description='Rainfall intensity-duration threshold debris flow',
    ),
}


def risk_level_from_score(score: float) -> int:
    """Convert 0-5 risk score to integer risk level."""
    if score < 0.5:
        return 0
    elif score < 1.5:
        return 1
    elif score < 2.5:
        return 2
    elif score < 3.5:
        return 3
    elif score < 4.5:
        return 4
    else:
        return 5


def assess_hazard(
    hazard_type: str,
    factors: dict[str, float],
    *,
    config: HazardConfig | None = None,
) -> HazardAssessment:
    """Assess risk for a single hazard type.

    Args:
        hazard_type: Type of hazard (avalanche, landslide, flood, rockfall)
        factors: Dict of factor names to values
        config: Optional custom hazard configuration

    Returns:
        HazardAssessment with computed risk
    """
    cfg = config or DEFAULT_HAZARD_CONFIGS.get(hazard_type)
    if cfg is None:
        return HazardAssessment(
            hazard_type=hazard_type,
            risk_score=0.0,
            risk_level=0,
            confidence=0.0,
            trigger_met=False,
            contributing_factors={},
        )

    # Compute weighted risk score
    total_weight = 0.0
    weighted_sum = 0.0
    contributing: dict[str, float] = {}

    for factor_name, weight in cfg.risk_weights.items():
        value = factors.get(factor_name, 0.0)
        normalized = min(max(float(value), 0.0), 1.0)  # Normalize to 0-1
        weighted_sum += normalized * weight
        total_weight += weight
        if normalized > 0:
            contributing[factor_name] = normalized

    risk_score = (weighted_sum / total_weight * 5.0) if total_weight > 0 else 0.0
    risk_level = risk_level_from_score(risk_score)

    # Check trigger thresholds
    trigger_met = True
    for threshold_name, threshold_value in cfg.trigger_thresholds.items():
        if factors.get(threshold_name, 0.0) < threshold_value:
            trigger_met = False
            break

    # Confidence based on data completeness
    available_factors = sum(1 for f in cfg.risk_weights if f in factors)
    confidence = available_factors / len(cfg.risk_weights) if cfg.risk_weights else 0.0

    return HazardAssessment(
        hazard_type=hazard_type,
        risk_score=round(risk_score, 3),
        risk_level=risk_level,
        confidence=round(confidence, 3),
        trigger_met=trigger_met,
        contributing_factors=contributing,
    )


def assess_hazard_detailed(
    hazard_type: str,
    factors: dict[str, float],
) -> HazardAssessment:
    """Assess risk using operational models (F14-detail).

    For landslide, uses infinite slope stability model.
    For flood/GLOF, uses ice dam stability + temperature anomaly.
    For debris flow, uses Caine (1980) rainfall intensity-duration thresholds.
    For avalanche and rockfall, falls back to generic weighted scoring.

    Args:
        hazard_type: Type of hazard
        factors: Dict of factor names to values

    Returns:
        HazardAssessment with model-specific computation
    """
    if hazard_type == HAZARD_LANDSLIDE:
        from backend.common.landslide_model import (
            LandslideCellInput,
            assess_landslide_risk,
        )
        cell_input = LandslideCellInput(
            slope_deg=factors.get('slope_angle', factors.get('slope_deg', 0.0)),
            rainfall_24h_mm=factors.get('rainfall_24h', factors.get('rainfall_24h_mm', 0.0)),
            soil_saturation=factors.get('soil_saturation', 0.0),
            lithology_factor=factors.get('lithology', 0.5),
            seismic_amplification=factors.get('seismic_amplification', 0.0),
        )
        return assess_landslide_risk(cell_input)

    elif hazard_type == HAZARD_FLOOD:
        from backend.common.debris_flow import GLOFInput, assess_glof_risk
        glacial_lake = factors.get('glacial_lake_proximity', 0.0) > 0.1
        cell_input = GLOFInput(
            glacial_lake_present=glacial_lake,
            lake_area_km2=factors.get('glacial_lake_proximity', 0.0),
            temperature_2m_c=factors.get('temperature_2m', 0.0),
            temp_7d_mean_c=factors.get('temp_7d_mean', 0.0),
            ice_dam_stability=factors.get('ice_dam_stability', 1.0),
        )
        return assess_glof_risk(cell_input)

    elif hazard_type == 'debris_flow':
        from backend.common.debris_flow import DebrisFlowInput, assess_debris_flow_risk
        cell_input = DebrisFlowInput(
            rainfall_intensity_mmhr=factors.get('rainfall_intensity', 0.0),
            rainfall_duration_hr=factors.get('rainfall_duration', 0.0),
            slope_deg=factors.get('slope_angle', factors.get('slope_deg', 0.0)),
            sediment_availability=factors.get('sediment_availability', 0.5),
            region_key=factors.get('region_key', 'default'),
        )
        return assess_debris_flow_risk(cell_input)

    else:
        # Avalanche and rockfall: use generic weighted scoring
        return assess_hazard(hazard_type, factors)


def assess_multi_hazard(
    *,
    cell_lat: float,
    cell_lng: float,
    hazard_factors: dict[str, dict[str, float]],
    hazard_types: list[str] | None = None,
    configs: dict[str, HazardConfig] | None = None,
) -> MultiHazardResult:
    """Assess multiple hazard types for a single grid cell.

    Args:
        cell_lat: Cell latitude
        cell_lng: Cell longitude
        hazard_factors: Dict of hazard_type -> factors dict
        hazard_types: Which hazards to assess (default: all supported)
        configs: Custom hazard configurations

    Returns:
        MultiHazardResult with all assessments
    """
    cfgs = configs or DEFAULT_HAZARD_CONFIGS
    types_to_assess = hazard_types or list(cfgs.keys())

    assessments: dict[str, HazardAssessment] = {}
    for htype in types_to_assess:
        if htype not in SUPPORTED_HAZARDS:
            continue
        factors = hazard_factors.get(htype, {})
        cfg = cfgs.get(htype)
        if htype in {HAZARD_LANDSLIDE, HAZARD_FLOOD, 'debris_flow'}:
            assessments[htype] = assess_hazard_detailed(htype, factors)
        else:
            assessments[htype] = assess_hazard(htype, factors, config=cfg)

    # Determine dominant hazard (highest risk score)
    dominant = max(assessments, key=lambda h: assessments[h].risk_score) if assessments else HAZARD_AVALANCHE

    # Composite risk: weighted by confidence
    total_confidence = sum(a.confidence for a in assessments.values())
    if total_confidence > 0:
        composite = sum(a.risk_score * a.confidence for a in assessments.values()) / total_confidence
    else:
        composite = 0.0

    any_trigger = any(a.trigger_met for a in assessments.values())

    return MultiHazardResult(
        cell_lat=cell_lat,
        cell_lng=cell_lng,
        hazard_assessments=assessments,
        dominant_hazard=dominant,
        composite_risk=round(composite, 3),
        composite_risk_level=risk_level_from_score(composite),
        any_trigger_met=any_trigger,
    )


def assess_multi_hazard_grid(
    cells: list[dict[str, Any]],
    *,
    hazard_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Assess multi-hazard risk for a grid of cells.

    Args:
        cells: List of cell dicts with lat, lng, and hazard-specific factors
        hazard_types: Which hazards to assess

    Returns:
        List of cell dicts with multi_hazard field added
    """
    if not MULTI_HAZARD_ENABLED:
        return cells

    results: list[dict[str, Any]] = []
    for cell in cells:
        lat = float(cell.get('lat', 0.0))
        lng = float(cell.get('lng', 0.0))

        # Extract hazard-specific factors from cell
        hazard_factors: dict[str, dict[str, float]] = {}
        for htype in (hazard_types or SUPPORTED_HAZARDS):
            prefix = f'{htype}_'
            factors: dict[str, float] = {}
            for key, value in cell.items():
                if key.startswith(prefix):
                    factor_name = key[len(prefix):]
                    try:
                        factors[factor_name] = float(value)
                    except (TypeError, ValueError):
                        pass
            if factors:
                hazard_factors[htype] = factors

        if not hazard_factors:
            results.append(cell)
            continue

        mh_result = assess_multi_hazard(
            cell_lat=lat,
            cell_lng=lng,
            hazard_factors=hazard_factors,
            hazard_types=hazard_types,
        )

        cell_out = dict(cell)
        cell_out['multi_hazard'] = {
            'dominant_hazard': mh_result.dominant_hazard,
            'composite_risk': mh_result.composite_risk,
            'composite_risk_level': mh_result.composite_risk_level,
            'any_trigger_met': mh_result.any_trigger_met,
            'hazard_assessments': {
                htype: {
                    'risk_score': a.risk_score,
                    'risk_level': a.risk_level,
                    'confidence': a.confidence,
                    'trigger_met': a.trigger_met,
                    'contributing_factors': a.contributing_factors,
                }
                for htype, a in mh_result.hazard_assessments.items()
            },
        }
        cell_out['dominant_hazard'] = mh_result.dominant_hazard
        cell_out['composite_risk'] = mh_result.composite_risk
        cell_out['composite_risk_level'] = mh_result.composite_risk_level

        results.append(cell_out)

    return results


def get_hazard_metadata() -> dict[str, dict[str, Any]]:
    """Get metadata for all supported hazard types for frontend rendering.

    Returns:
        Dict of hazard_type -> metadata (display_name, color, icon, description)
    """
    return {
        htype: {
            'display_name': cfg.display_name,
            'color': cfg.color_hex,
            'icon': cfg.icon,
            'description': cfg.description,
            'risk_weights': cfg.risk_weights,
            'trigger_thresholds': cfg.trigger_thresholds,
        }
        for htype, cfg in DEFAULT_HAZARD_CONFIGS.items()
    }
