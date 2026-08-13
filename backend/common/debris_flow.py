"""F14-detail: Debris Flow and GLOF Trigger Models.

Debris flow triggers use rainfall intensity-duration thresholds based on
Caine (1980), revised for Himalayan conditions. GLOF triggers use ice dam
stability and temperature anomaly indicators.

Caine (1980) threshold: I = 14.82 * D^(-0.39)
where I = intensity (mm/hr), D = duration (hours)

Himalayan revision factors:
- Pir Panjal (maritime): 0.8 (lower threshold, more susceptible)
- Shamshabari (transition): 0.9
- Great Himalaya: 1.0
- Karakoram (polar-dry): 1.2 (higher threshold, less susceptible)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.common.multi_hazard import (
    HAZARD_FLOOD,
    HazardAssessment,
    risk_level_from_score,
)


# Caine (1980) global threshold coefficients
CAINE_COEFF_A = 14.82
CAINE_COEFF_B = -0.39

# Himalayan regional revision factors
REGIONAL_FACTORS = {
    'pir_panjal': 0.8,
    'shamshabari': 0.9,
    'great_himalaya': 1.0,
    'karakoram': 1.2,
    'default': 1.0,
}

# GLOF trigger thresholds
DEFAULT_TEMP_ANOMALY_THRESHOLD = 5.0  # °C above 7-day mean
DEFAULT_DAM_STABILITY_THRESHOLD = 0.3  # Below this = unstable
DEFAULT_GLACIAL_LAKE_AREA_MIN = 0.01  # km² — minimum lake area to consider


@dataclass(frozen=True)
class DebrisFlowConfig:
    """Configuration for debris flow trigger model."""
    caine_a: float = CAINE_COEFF_A
    caine_b: float = CAINE_COEFF_B
    regional_factor: float = 1.0
    min_slope_deg: float = 15.0
    min_rainfall_mm: float = 10.0


@dataclass(frozen=True)
class GLOFConfig:
    """Configuration for GLOF trigger model."""
    temp_anomaly_threshold_c: float = DEFAULT_TEMP_ANOMALY_THRESHOLD
    dam_stability_threshold: float = DEFAULT_DAM_STABILITY_THRESHOLD
    min_lake_area_km2: float = DEFAULT_GLACIAL_LAKE_AREA_MIN
    lookback_days: int = 7


@dataclass
class DebrisFlowInput:
    """Input for debris flow assessment."""
    rainfall_intensity_mmhr: float  # Current rainfall intensity
    rainfall_duration_hr: float  # Duration of rainfall event
    slope_deg: float
    sediment_availability: float = 0.5  # 0-1, fraction of available sediment
    burn_scar: bool = False  # Recent fire/burn scar increases susceptibility
    region_key: str = 'default'


@dataclass
class GLOFInput:
    """Input for GLOF assessment."""
    glacial_lake_present: bool
    lake_area_km2: float = 0.0
    temperature_2m_c: float = 0.0
    temp_7d_mean_c: float = 0.0
    ice_dam_stability: float = 1.0  # 0-1, 1=stable
    lake_elevation_m: float = 4000.0
    downstream_population: int = 0


def caine_threshold(duration_hr: float, *, config: DebrisFlowConfig | None = None) -> float:
    """Compute Caine (1980) rainfall intensity threshold for debris flow.

    Args:
        duration_hr: Rainfall duration in hours
        config: Optional configuration with regional factor

    Returns:
        Threshold intensity in mm/hr. Rainfall above this triggers debris flow.
    """
    cfg = config or DebrisFlowConfig()
    if duration_hr <= 0:
        return 999.0  # No duration = no threshold
    base_threshold = cfg.caine_a * (duration_hr ** cfg.caine_b)
    return base_threshold * cfg.regional_factor


def assess_debris_flow_risk(
    cell_input: DebrisFlowInput,
    *,
    config: DebrisFlowConfig | None = None,
) -> HazardAssessment:
    """Assess debris flow risk for a single grid cell.

    Args:
        cell_input: Cell rainfall and terrain parameters
        config: Optional custom configuration

    Returns:
        HazardAssessment with computed risk
    """
    # Apply regional factor
    regional = REGIONAL_FACTORS.get(cell_input.region_key, REGIONAL_FACTORS['default'])
    cfg = config or DebrisFlowConfig(regional_factor=regional)

    # Compute Caine threshold
    threshold = caine_threshold(cell_input.rainfall_duration_hr, config=cfg)

    # Check if rainfall exceeds threshold
    exceeds_threshold = cell_input.rainfall_intensity_mmhr > threshold

    # Check trigger conditions
    trigger_met = (
        exceeds_threshold
        and cell_input.slope_deg >= cfg.min_slope_deg
        and cell_input.rainfall_intensity_mmhr >= cfg.min_rainfall_mm
    )

    # Compute risk score
    if not exceeds_threshold:
        base_risk = 0.0
    else:
        # Ratio of actual to threshold intensity
        ratio = cell_input.rainfall_intensity_mmhr / max(threshold, 0.1)
        base_risk = min(ratio * 2.5, 5.0)

    # Amplification factors
    if cell_input.slope_deg > 30:
        base_risk *= 1.2
    if cell_input.sediment_availability > 0.7:
        base_risk *= 1.15
    if cell_input.burn_scar:
        base_risk *= 1.3

    risk_score = min(base_risk, 5.0)
    risk_level = risk_level_from_score(risk_score)

    # Confidence
    confidence = 0.7  # Moderate confidence — rainfall intensity can be uncertain
    if cell_input.rainfall_duration_hr > 0:
        confidence = 0.85

    contributing: dict[str, float] = {}
    contributing['rainfall_intensity'] = min(cell_input.rainfall_intensity_mmhr / 50.0, 1.0)
    contributing['caine_threshold'] = min(threshold / 50.0, 1.0)
    contributing['slope_angle'] = min(cell_input.slope_deg / 60.0, 1.0)
    contributing['sediment_availability'] = cell_input.sediment_availability
    if cell_input.burn_scar:
        contributing['burn_scar'] = 1.0

    return HazardAssessment(
        hazard_type='debris_flow',
        risk_score=round(risk_score, 3),
        risk_level=risk_level,
        confidence=round(confidence, 3),
        trigger_met=trigger_met,
        contributing_factors=contributing,
        metadata={
            'caine_threshold': round(threshold, 2),
            'intensity_ratio': round(cell_input.rainfall_intensity_mmhr / max(threshold, 0.1), 3),
            'model': 'caine_1980',
            'regional_factor': cfg.regional_factor,
        },
    )


def assess_glof_risk(
    cell_input: GLOFInput,
    *,
    config: GLOFConfig | None = None,
) -> HazardAssessment:
    """Assess GLOF (Glacial Lake Outburst Flood) risk for a single grid cell.

    Args:
        cell_input: Cell glacial lake and temperature parameters
        config: Optional custom configuration

    Returns:
        HazardAssessment with computed risk
    """
    cfg = config or GLOFConfig()

    # No lake = no GLOF risk
    if not cell_input.glacial_lake_present or cell_input.lake_area_km2 < cfg.min_lake_area_km2:
        return HazardAssessment(
            hazard_type=HAZARD_FLOOD,
            risk_score=0.0,
            risk_level=0,
            confidence=0.9,
            trigger_met=False,
            contributing_factors={},
            metadata={'model': 'glof', 'reason': 'no_glacial_lake'},
        )

    # Temperature anomaly
    temp_anomaly = cell_input.temperature_2m_c - cell_input.temp_7d_mean_c
    temp_exceeds = temp_anomaly > cfg.temp_anomaly_threshold_c

    # Dam stability
    dam_unstable = cell_input.ice_dam_stability < cfg.dam_stability_threshold

    # Trigger: temperature spike + unstable dam
    trigger_met = temp_exceeds and dam_unstable

    # Risk score
    base_risk = 0.0

    # Lake area contribution (larger lake = higher risk)
    area_factor = min(cell_input.lake_area_km2 / 1.0, 1.0)  # Normalize to 1 km²
    base_risk += area_factor * 1.5

    # Temperature anomaly contribution
    if temp_anomaly > 0:
        temp_factor = min(temp_anomaly / (cfg.temp_anomaly_threshold_c * 2), 1.0)
        base_risk += temp_factor * 1.5

    # Dam stability contribution
    if cell_input.ice_dam_stability < 1.0:
        dam_factor = (1.0 - cell_input.ice_dam_stability) * 2.0
        base_risk += dam_factor

    # Downstream population amplification
    if cell_input.downstream_population > 1000:
        base_risk *= 1.2

    # Trigger bonus
    if trigger_met:
        base_risk += 1.0

    risk_score = min(base_risk, 5.0)
    risk_level = risk_level_from_score(risk_score)

    contributing: dict[str, float] = {}
    contributing['lake_area'] = area_factor
    contributing['temp_anomaly'] = min(temp_anomaly / 10.0, 1.0)
    contributing['dam_stability'] = 1.0 - cell_input.ice_dam_stability
    if cell_input.downstream_population > 0:
        contributing['downstream_exposure'] = min(cell_input.downstream_population / 10000.0, 1.0)

    confidence = 0.75  # GLOF prediction is inherently uncertain

    return HazardAssessment(
        hazard_type=HAZARD_FLOOD,
        risk_score=round(risk_score, 3),
        risk_level=risk_level,
        confidence=round(confidence, 3),
        trigger_met=trigger_met,
        contributing_factors=contributing,
        metadata={
            'model': 'glof',
            'temp_anomaly_c': round(temp_anomaly, 2),
            'dam_stability': round(cell_input.ice_dam_stability, 3),
            'lake_area_km2': cell_input.lake_area_km2,
        },
    )


def assess_debris_flow_grid(
    cells: list[dict[str, Any]],
    *,
    config: DebrisFlowConfig | None = None,
) -> list[dict[str, Any]]:
    """Assess debris flow risk for a grid of cells.

    Args:
        cells: List of cell dicts with rainfall and terrain parameters
        config: Optional custom configuration

    Returns:
        List of cells with debris_flow_risk field added
    """
    results: list[dict[str, Any]] = []
    for cell in cells:
        cell_input = DebrisFlowInput(
            rainfall_intensity_mmhr=float(cell.get('rainfall_intensity_mmhr', 0.0)),
            rainfall_duration_hr=float(cell.get('rainfall_duration_hr', 0.0)),
            slope_deg=float(cell.get('slope_deg', 0.0)),
            sediment_availability=float(cell.get('sediment_availability', 0.5)),
            burn_scar=bool(cell.get('burn_scar', False)),
            region_key=str(cell.get('region_key', 'default')),
        )
        assessment = assess_debris_flow_risk(cell_input, config=config)

        cell_out = dict(cell)
        cell_out['debris_flow_risk'] = {
            'risk_score': assessment.risk_score,
            'risk_level': assessment.risk_level,
            'confidence': assessment.confidence,
            'trigger_met': assessment.trigger_met,
            'caine_threshold': assessment.metadata.get('caine_threshold', 0.0),
            'contributing_factors': assessment.contributing_factors,
        }
        results.append(cell_out)

    return results
