"""Dual-narrative explainability: couples TreeSHAP with physics-based snowpack narratives.

This module produces a :class:`PhysicsNarrative` from snowpack physics results and
seismic amplification data, providing a human-readable physics explanation that
complements the existing SHAP-based ML explanation.

The narrative is zone-aware: different Himalayan zones (Pir Panjal, Shamshabari,
Great Himalaya, Karakoram) get zone-specific phrasing for their dominant
avalanche problems.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.common.seismic_integrator import SeismicAmplification
from backend.common.snowpack_physics import SnowpackPhysicsResult


# ---------------------------------------------------------------------------
# Zone-specific narrative context
# ---------------------------------------------------------------------------

ZONE_NARRATIVE_CONTEXT: dict[str, dict[str, str]] = {
    'pir_panjal': {
        'dominant_concern': 'wet-snow and wind-loading',
        'zone_label': 'Pir Panjal (maritime)',
        'typical_grain': 'melt_form',
    },
    'shamshabari': {
        'dominant_concern': 'persistent weak layers',
        'zone_label': 'Shamshabari (transition)',
        'typical_grain': 'faceted',
    },
    'great_himalaya': {
        'dominant_concern': 'temperature gradient metamorphism and depth hoar',
        'zone_label': 'Great Himalaya (continental)',
        'typical_grain': 'depth_hoar',
    },
    'karakoram_ladakh': {
        'dominant_concern': 'cold, dry snowpack dynamics',
        'zone_label': 'Karakoram/Ladakh (polar-dry)',
        'typical_grain': 'depth_hoar',
    },
}

GRAIN_TYPE_LABELS: dict[str, str] = {
    'faceted': 'faceted grains',
    'depth_hoar': 'depth hoar',
    'surface_hoar': 'surface hoar',
    'melt_form': 'melt forms',
    'rounded': 'rounded grains',
}

STABILITY_LABELS = [
    (1.0, 'below the critical threshold', 'Unstable', 'low'),
    (1.5, 'near the critical threshold', 'Marginal', 'medium'),
    (float('inf'), 'well above the critical threshold', 'Stable', 'high'),
]


def _stability_label(index: float) -> tuple[str, str, str]:
    """Return (description, label, confidence) for a stability index."""
    for threshold, desc, label, conf in STABILITY_LABELS:
        if index < threshold:
            return desc, label, conf
    return 'well above the critical threshold', 'Stable', 'high'


def _shear_label(kpa: float) -> str:
    if kpa < 3.0:
        return 'Weak'
    if kpa < 5.0:
        return 'Moderate'
    return 'Strong'


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PhysicsNarrative:
    """Physics-based narrative result coupling snowpack + seismic data."""

    summary: str
    shear_strength_kpa: float | None
    stability_index: float | None
    grain_type: str | None
    temperature_gradient_per_m: float | None
    liquid_water_content_pct: float | None
    snow_height_m: float | None
    method: str
    confidence: str  # 'high' | 'medium' | 'low'
    seismic_summary: str | None = None


# ---------------------------------------------------------------------------
# Narrative builder
# ---------------------------------------------------------------------------

def build_physics_narrative(
    snowpack_physics: SnowpackPhysicsResult | None,
    seismic_amplification: SeismicAmplification | None,
    zone_type: str | None,
    risk_score: int,
) -> PhysicsNarrative:
    """Build a physics-based narrative from snowpack + seismic data.

    Args:
        snowpack_physics: Physics simulation result (COSIPY/SNOWPACK or heuristic fallback).
        seismic_amplification: Active seismic amplification, or None if no event.
        zone_type: Microclimate zone key (e.g. 'pir_panjal'), or None.
        risk_score: Final risk score (1-5) after all amplifications.

    Returns:
        PhysicsNarrative with structured fields + human-readable summary.
    """
    zone_ctx = ZONE_NARRATIVE_CONTEXT.get(zone_type or '', {})
    zone_label = zone_ctx.get('zone_label', 'this zone')
    zone_concern = zone_ctx.get('dominant_concern', 'avalanche hazard')

    # Seismic narrative fragment
    seismic_summary = None
    if seismic_amplification is not None:
        seismic_summary = (
            f"Seismic cascade active: M{seismic_amplification.magnitude:.1f} event "
            f"{seismic_amplification.epicenter_distance_km:.0f}km away, "
            f"{seismic_amplification.hours_since_event:.1f}h ago, "
            f"amplification factor {seismic_amplification.factor:.2f}x "
            f"in window phase {seismic_amplification.window_phase}."
        )

    # No physics data — fallback narrative
    if snowpack_physics is None:
        summary = (
            f"Physics simulation unavailable for this cell in {zone_label}. "
            f"The forecast relies on weather-derived proxy estimates for {zone_concern}. "
            f"Snowpack terms are proxy-based, not from full thermodynamic simulation."
        )
        if seismic_summary:
            summary = f"{summary} {seismic_summary}"
        return PhysicsNarrative(
            summary=summary,
            shear_strength_kpa=None,
            stability_index=None,
            grain_type=None,
            temperature_gradient_per_m=None,
            liquid_water_content_pct=None,
            snow_height_m=None,
            method='unavailable',
            confidence='low',
            seismic_summary=seismic_summary,
        )

    # Extract physics fields
    shear = snowpack_physics.weak_layer_shear_strength_kpa
    stability = snowpack_physics.snowpack_stability_index
    grain = snowpack_physics.weak_layer_grain_type
    temp_grad = snowpack_physics.temperature_gradient_per_m
    lwc = snowpack_physics.liquid_water_content_pct
    snow_height = snowpack_physics.snow_height_m
    method = snowpack_physics.method
    depth = snowpack_physics.weak_layer_depth_m

    grain_label = GRAIN_TYPE_LABELS.get(grain, grain or 'unknown grains')
    stab_desc, stab_label, confidence = _stability_label(stability)
    shear_label = _shear_label(shear)

    # Build narrative based on risk level
    if risk_score >= 4:
        summary = (
            f"Weak layer at {depth:.2f}m with {grain_label} in {zone_label}. "
            f"Shear strength {shear:.1f} kPa ({shear_label}) is "
            f"{'below' if stability < 1.0 else 'near' if stability < 1.5 else 'above'} "
            f"the stability threshold (index {stability:.2f}). "
            f"Temperature gradient {temp_grad:.3f} K/m "
            f"{'supports weak-layer faceting' if temp_grad > 0.1 else 'is moderate'}. "
            f"Snowpack is {stab_label.lower()} — {stab_desc}."
        )
    elif risk_score <= 2:
        summary = (
            f"Snowpack is {stab_label.lower()} in {zone_label}. "
            f"Stability index {stability:.2f} is {stab_desc}. "
            f"{grain_label.capitalize()} present at {depth:.2f}m but shear strength "
            f"({shear:.1f} kPa, {shear_label}) provides sufficient resistance. "
            f"Temperature gradient {temp_grad:.3f} K/m "
            f"{'is low, limiting metamorphism' if temp_grad < 0.1 else 'is moderate'}."
        )
    else:
        summary = (
            f"Snowpack is marginally stable in {zone_label}. "
            f"Stability index {stability:.2f} is {stab_desc}. "
            f"{grain_label.capitalize()} at {depth:.2f}m with shear strength "
            f"{shear:.1f} kPa ({shear_label}). "
            f"Temperature gradient {temp_grad:.3f} K/m. "
            f"Primary concern: {zone_concern}."
        )

    if seismic_summary:
        summary = f"{summary} {seismic_summary}"

    return PhysicsNarrative(
        summary=summary,
        shear_strength_kpa=shear,
        stability_index=stability,
        grain_type=grain,
        temperature_gradient_per_m=temp_grad,
        liquid_water_content_pct=lwc,
        snow_height_m=snow_height,
        method=method,
        confidence=confidence,
        seismic_summary=seismic_summary,
    )


def physics_narrative_to_dict(narrative: PhysicsNarrative) -> dict[str, Any]:
    """Convert PhysicsNarrative to a JSON-serializable dict for cell payload."""
    return {
        'summary': narrative.summary,
        'shear_strength_kpa': narrative.shear_strength_kpa,
        'stability_index': narrative.stability_index,
        'grain_type': narrative.grain_type,
        'temperature_gradient_per_m': narrative.temperature_gradient_per_m,
        'liquid_water_content_pct': narrative.liquid_water_content_pct,
        'snow_height_m': narrative.snow_height_m,
        'method': narrative.method,
        'confidence': narrative.confidence,
        'seismic_summary': narrative.seismic_summary,
    }
