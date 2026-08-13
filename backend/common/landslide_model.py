"""F14-detail: Landslide Susceptibility Model.

Operational landslide susceptibility using the infinite slope stability model
and rainfall thresholds. Produces risk scores from terrain and rainfall inputs.

The infinite slope model computes a Factor of Safety (FS):
    FS = (c' + γ'·h·cos²β·tanφ') / (γ·h·sinβ·cosβ)

When FS < 1.0, the slope is unstable. When FS < 1.25 and rainfall exceeds
threshold, landslide risk is high.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.common.multi_hazard import (
    HAZARD_LANDSLIDE,
    HazardAssessment,
    risk_level_from_score,
)


# Default soil parameters for Himalayan conditions
DEFAULT_COHESION_KPA = 15.0  # kPa — typical for colluvium
DEFAULT_FRICTION_ANGLE_DEG = 30.0  # degrees — typical for mountain soil
DEFAULT_SOIL_DEPTH_M = 3.0  # meters — typical regolith depth
DEFAULT_SOIL_UNIT_WEIGHT = 18.0  # kN/m³ — typical moist soil
DEFAULT_SATURATED_UNIT_WEIGHT = 20.0  # kN/m³ — saturated
DEFAULT_SLOPE_THRESHOLD_DEG = 15.0  # minimum slope for landslide
DEFAULT_RAINFALL_THRESHOLD_MM = 50.0  # 24h rainfall threshold


@dataclass(frozen=True)
class LandslideConfig:
    """Configuration for landslide susceptibility model."""
    cohesion_kpa: float = DEFAULT_COHESION_KPA
    friction_angle_deg: float = DEFAULT_FRICTION_ANGLE_DEG
    soil_depth_m: float = DEFAULT_SOIL_DEPTH_M
    soil_unit_weight: float = DEFAULT_SOIL_UNIT_WEIGHT
    saturated_unit_weight: float = DEFAULT_SATURATED_UNIT_WEIGHT
    min_slope_deg: float = DEFAULT_SLOPE_THRESHOLD_DEG
    min_rainfall_24h_mm: float = DEFAULT_RAINFALL_THRESHOLD_MM
    # Critical FS threshold below which slope is definitely unstable
    fs_critical: float = 1.0
    # Warning FS threshold
    fs_warning: float = 1.25


@dataclass
class LandslideCellInput:
    """Input parameters for a single grid cell."""
    slope_deg: float
    rainfall_24h_mm: float
    soil_depth_m: float = DEFAULT_SOIL_DEPTH_M
    cohesion_kpa: float = DEFAULT_COHESION_KPA
    friction_angle_deg: float = DEFAULT_FRICTION_ANGLE_DEG
    soil_saturation: float = 0.0  # 0-1 fraction
    lithology_factor: float = 0.5  # 0-1, higher = more susceptible
    seismic_amplification: float = 0.0  # 0-1


def compute_factor_of_safety(
    *,
    slope_deg: float,
    soil_depth_m: float,
    cohesion_kpa: float,
    friction_angle_deg: float,
    soil_unit_weight: float,
    saturated_unit_weight: float,
    saturation: float = 0.0,
) -> float:
    """Compute Factor of Safety using infinite slope model.

    Args:
        slope_deg: Slope angle in degrees
        soil_depth_m: Soil depth in meters
        cohesion_kpa: Soil cohesion in kPa
        friction_angle_deg: Friction angle in degrees
        soil_unit_weight: Unsaturated unit weight (kN/m³)
        saturated_unit_weight: Saturated unit weight (kN/m³)
        saturation: Saturation fraction (0=dry, 1=fully saturated)

    Returns:
        Factor of Safety (FS). FS < 1.0 = unstable, FS < 1.25 = warning.
    """
    if slope_deg <= 0 or soil_depth_m <= 0:
        return 10.0  # Flat ground or no soil = very stable

    beta = math.radians(slope_deg)
    phi = math.radians(friction_angle_deg)

    # Effective unit weight based on saturation
    gamma = soil_unit_weight + (saturated_unit_weight - soil_unit_weight) * saturation
    gamma_prime = saturated_unit_weight - 9.81  # Submerged unit weight for saturated portion

    # Normal stress on slip plane
    sigma_n = gamma * soil_depth_m * math.cos(beta) ** 2

    # Shear stress
    tau = gamma * soil_depth_m * math.sin(beta) * math.cos(beta)

    # Resistive force: cohesion + friction
    resistive = cohesion_kpa + sigma_n * math.tan(phi)

    if tau < 1e-10:
        return 10.0

    fs = resistive / tau
    return max(min(fs, 10.0), 0.0)


def assess_landslide_risk(
    cell_input: LandslideCellInput,
    *,
    config: LandslideConfig | None = None,
) -> HazardAssessment:
    """Assess landslide risk for a single grid cell.

    Args:
        cell_input: Cell terrain and rainfall parameters
        config: Optional custom configuration

    Returns:
        HazardAssessment with computed risk
    """
    cfg = config or LandslideConfig()

    # Check trigger thresholds
    trigger_met = (
        cell_input.slope_deg >= cfg.min_slope_deg
        and cell_input.rainfall_24h_mm >= cfg.min_rainfall_24h_mm
    )

    # Compute Factor of Safety
    saturation = min(max(cell_input.soil_saturation, 0.0), 1.0)
    fs = compute_factor_of_safety(
        slope_deg=cell_input.slope_deg,
        soil_depth_m=cell_input.soil_depth_m,
        cohesion_kpa=cell_input.cohesion_kpa,
        friction_angle_deg=cell_input.friction_angle_deg,
        soil_unit_weight=cfg.soil_unit_weight,
        saturated_unit_weight=cfg.saturated_unit_weight,
        saturation=saturation,
    )

    # Convert FS to risk score (0-5 scale)
    # FS > 2.0 → very safe (risk 0)
    # FS 1.25-2.0 → moderate (risk 1-2)
    # FS 1.0-1.25 → high (risk 3-4)
    # FS < 1.0 → very high (risk 5)
    if fs >= 2.0:
        base_risk = 0.0
    elif fs >= 1.25:
        base_risk = 2.0 * (2.0 - fs) / 0.75
    elif fs >= 1.0:
        base_risk = 2.0 + 2.0 * (1.25 - fs) / 0.25
    else:
        base_risk = 4.0 + min((1.0 - fs) * 2.0, 1.0)

    # Rainfall amplification
    if cell_input.rainfall_24h_mm > cfg.min_rainfall_24h_mm:
        rain_factor = min(cell_input.rainfall_24h_mm / (cfg.min_rainfall_24h_mm * 3), 1.5)
        base_risk *= (1.0 + rain_factor * 0.3)

    # Seismic amplification
    if cell_input.seismic_amplification > 0:
        base_risk *= (1.0 + cell_input.seismic_amplification * 0.2)

    # Lithology factor
    base_risk *= (0.7 + cell_input.lithology_factor * 0.6)

    risk_score = min(base_risk, 5.0)
    risk_level = risk_level_from_score(risk_score)

    # Confidence based on data completeness
    factors_present = sum([
        cell_input.slope_deg > 0,
        cell_input.rainfall_24h_mm > 0,
        cell_input.soil_depth_m > 0,
        cell_input.cohesion_kpa > 0,
        cell_input.friction_angle_deg > 0,
        cell_input.soil_saturation > 0 or True,  # Always present (default 0)
    ])
    confidence = factors_present / 6.0

    contributing: dict[str, float] = {}
    if cell_input.slope_deg > 0:
        contributing['slope_angle'] = min(cell_input.slope_deg / 60.0, 1.0)
    if cell_input.rainfall_24h_mm > 0:
        contributing['rainfall_24h'] = min(cell_input.rainfall_24h_mm / 150.0, 1.0)
    contributing['factor_of_safety'] = max(0, 1.0 - fs / 2.0)
    if cell_input.soil_saturation > 0:
        contributing['soil_saturation'] = cell_input.soil_saturation
    if cell_input.seismic_amplification > 0:
        contributing['seismic_amplification'] = cell_input.seismic_amplification
    contributing['lithology'] = cell_input.lithology_factor

    return HazardAssessment(
        hazard_type=HAZARD_LANDSLIDE,
        risk_score=round(risk_score, 3),
        risk_level=risk_level,
        confidence=round(confidence, 3),
        trigger_met=trigger_met,
        contributing_factors=contributing,
        metadata={
            'factor_of_safety': round(fs, 3),
            'model': 'infinite_slope',
        },
    )


def assess_landslide_grid(
    cells: list[dict[str, Any]],
    *,
    config: LandslideConfig | None = None,
) -> list[dict[str, Any]]:
    """Assess landslide risk for a grid of cells.

    Args:
        cells: List of cell dicts with slope_deg, rainfall_24h_mm, etc.
        config: Optional custom configuration

    Returns:
        List of cells with landslide_risk field added
    """
    results: list[dict[str, Any]] = []
    for cell in cells:
        cell_input = LandslideCellInput(
            slope_deg=float(cell.get('slope_deg', 0.0)),
            rainfall_24h_mm=float(cell.get('rainfall_24h_mm', 0.0)),
            soil_depth_m=float(cell.get('soil_depth_m', DEFAULT_SOIL_DEPTH_M)),
            cohesion_kpa=float(cell.get('cohesion_kpa', DEFAULT_COHESION_KPA)),
            friction_angle_deg=float(cell.get('friction_angle_deg', DEFAULT_FRICTION_ANGLE_DEG)),
            soil_saturation=float(cell.get('soil_saturation', 0.0)),
            lithology_factor=float(cell.get('lithology_factor', 0.5)),
            seismic_amplification=float(cell.get('seismic_amplification', 0.0)),
        )
        assessment = assess_landslide_risk(cell_input, config=config)

        cell_out = dict(cell)
        cell_out['landslide_risk'] = {
            'risk_score': assessment.risk_score,
            'risk_level': assessment.risk_level,
            'confidence': assessment.confidence,
            'trigger_met': assessment.trigger_met,
            'factor_of_safety': assessment.metadata.get('factor_of_safety', 0.0),
            'contributing_factors': assessment.contributing_factors,
        }
        results.append(cell_out)

    return results
