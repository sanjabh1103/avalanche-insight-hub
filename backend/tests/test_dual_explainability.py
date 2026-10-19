"""Tests for backend/common/dual_explainability.py."""
from __future__ import annotations

import pytest

from backend.common.dual_explainability import (
    PhysicsNarrative,
    build_physics_narrative,
    physics_narrative_to_dict,
)
from backend.common.seismic_integrator import SeismicAmplification
from backend.common.snowpack_physics import SnowpackPhysicsResult


def _make_physics(
    shear: float = 4.0,
    stability: float = 1.2,
    grain: str = 'faceted',
    temp_grad: float = 0.15,
    lwc: float = 1.0,
    snow_height: float = 1.5,
    depth: float = 0.45,
    method: str = 'heuristic_fallback',
) -> SnowpackPhysicsResult:
    return SnowpackPhysicsResult(
        weak_layer_depth_m=depth,
        weak_layer_grain_type=grain,
        weak_layer_shear_strength_kpa=shear,
        snowpack_stability_index=stability,
        temperature_gradient_per_m=temp_grad,
        liquid_water_content_pct=lwc,
        layer_count=1,
        snow_height_m=snow_height,
        bulk_density_kgm3=350.0,
        method=method,
        layers=[],
    )


def _make_seismic(
    factor: float = 1.3,
    phase: int = 1,
    hours: float = 5.0,
    magnitude: float = 5.5,
    distance: float = 25.0,
) -> SeismicAmplification:
    return SeismicAmplification(
        factor=factor,
        window_phase=phase,
        hours_since_event=hours,
        magnitude=magnitude,
        epicenter_distance_km=distance,
        epicenter_lat=34.5,
        epicenter_lng=76.0,
    )


class TestBuildPhysicsNarrative:
    def test_high_risk_with_physics(self):
        physics = _make_physics(shear=2.0, stability=0.8, grain='depth_hoar', temp_grad=0.25)
        narrative = build_physics_narrative(physics, None, 'great_himalaya', 5)
        assert 'depth hoar' in narrative.summary
        assert 'Great Himalaya' in narrative.summary
        assert narrative.confidence == 'low'
        assert narrative.shear_strength_kpa == 2.0
        assert narrative.stability_index == 0.8
        assert narrative.grain_type == 'depth_hoar'
        assert narrative.seismic_summary is None

    def test_low_risk_with_physics(self):
        physics = _make_physics(shear=6.0, stability=2.5, grain='rounded', temp_grad=0.05)
        narrative = build_physics_narrative(physics, None, 'karakoram_ladakh', 1)
        assert 'stable' in narrative.summary.lower()
        assert 'Karakoram/Ladakh' in narrative.summary
        assert narrative.confidence == 'high'
        assert narrative.shear_strength_kpa == 6.0

    def test_moderate_risk_with_physics(self):
        physics = _make_physics(shear=4.0, stability=1.3, grain='faceted')
        narrative = build_physics_narrative(physics, None, 'shamshabari', 3)
        assert 'marginally stable' in narrative.summary.lower()
        assert 'Shamshabari' in narrative.summary
        assert narrative.confidence == 'medium'

    def test_no_physics_data(self):
        narrative = build_physics_narrative(None, None, 'pir_panjal', 3)
        assert 'unavailable' in narrative.summary.lower()
        assert narrative.method == 'unavailable'
        assert narrative.confidence == 'low'
        assert narrative.shear_strength_kpa is None
        assert narrative.stability_index is None

    def test_no_physics_no_zone(self):
        narrative = build_physics_narrative(None, None, None, 2)
        assert 'unavailable' in narrative.summary.lower()
        assert 'this zone' in narrative.summary

    def test_with_seismic_amplification(self):
        physics = _make_physics(shear=3.0, stability=1.0, grain='faceted')
        seismic = _make_seismic(factor=1.5, magnitude=6.0, hours=4.0, distance=15.0)
        narrative = build_physics_narrative(physics, seismic, 'great_himalaya', 4)
        assert narrative.seismic_summary is not None
        assert 'M6.0' in narrative.seismic_summary
        assert '1.50x' in narrative.seismic_summary
        assert 'phase 1' in narrative.seismic_summary
        assert 'Seismic cascade active' in narrative.summary

    def test_seismic_only_no_physics(self):
        seismic = _make_seismic()
        narrative = build_physics_narrative(None, seismic, 'pir_panjal', 3)
        assert narrative.seismic_summary is not None
        assert 'Seismic cascade active' in narrative.summary
        assert narrative.method == 'unavailable'

    def test_zone_specific_phrasing(self):
        """Each zone gets different dominant concern phrasing."""
        physics = _make_physics(shear=4.0, stability=1.3, grain='faceted')
        zones = ['pir_panjal', 'shamshabari', 'great_himalaya', 'karakoram_ladakh']
        concerns = []
        for zone in zones:
            narrative = build_physics_narrative(physics, None, zone, 3)
            concerns.append(narrative.summary)
        # Each zone should have different text
        assert len(set(concerns)) == 4
        assert 'wet-snow and wind-loading' in concerns[0]
        assert 'persistent weak layers' in concerns[1]
        assert 'temperature gradient metamorphism' in concerns[2]
        assert 'cold, dry snowpack' in concerns[3]

    def test_stability_labels(self):
        # Low stability (< 1.0)
        physics = _make_physics(stability=0.5)
        narrative = build_physics_narrative(physics, None, None, 5)
        assert narrative.confidence == 'low'

        # Marginal stability (1.0-1.5)
        physics = _make_physics(stability=1.2)
        narrative = build_physics_narrative(physics, None, None, 3)
        assert narrative.confidence == 'medium'

        # High stability (>= 1.5)
        physics = _make_physics(stability=2.0)
        narrative = build_physics_narrative(physics, None, None, 1)
        assert narrative.confidence == 'high'

    def test_cosipy_method_preserved(self):
        physics = _make_physics(method='cosipy_v2')
        narrative = build_physics_narrative(physics, None, None, 3)
        assert narrative.method == 'cosipy_v2'

    def test_snowpack_native_method_preserved(self):
        physics = _make_physics(method='snowpack_native')
        narrative = build_physics_narrative(physics, None, None, 3)
        assert narrative.method == 'snowpack_native'


class TestPhysicsNarrativeToDict:
    def test_serialization(self):
        physics = _make_physics()
        narrative = build_physics_narrative(physics, None, 'pir_panjal', 3)
        d = physics_narrative_to_dict(narrative)
        assert isinstance(d, dict)
        assert 'summary' in d
        assert 'shear_strength_kpa' in d
        assert 'stability_index' in d
        assert 'grain_type' in d
        assert 'method' in d
        assert 'confidence' in d
        assert d['shear_strength_kpa'] == 4.0
        assert d['method'] == 'heuristic_fallback'
        assert d['seismic_summary'] is None

    def test_serialization_with_seismic(self):
        physics = _make_physics()
        seismic = _make_seismic()
        narrative = build_physics_narrative(physics, seismic, None, 4)
        d = physics_narrative_to_dict(narrative)
        assert d['seismic_summary'] is not None
        assert 'M5.5' in d['seismic_summary']

    def test_serialization_no_physics(self):
        narrative = build_physics_narrative(None, None, None, 2)
        d = physics_narrative_to_dict(narrative)
        assert d['shear_strength_kpa'] is None
        assert d['stability_index'] is None
        assert d['method'] == 'unavailable'
        assert d['confidence'] == 'low'
