from __future__ import annotations

import unittest

from backend.common.risk_math import (
    DangerAggregationConfig,
    build_hazard_vector,
    build_impact_vector,
    chebyshev_ipa,
    compute_danger_level,
    impact_risk_level,
    impact_risk_score,
    legacy_max_risk_level,
    risk_level,
)


class ChebyshevIPATests(unittest.TestCase):
    def test_chebyshev_reports_dominant_criterion(self) -> None:
        vector = build_hazard_vector(
            probability=0.22,
            slope_deg=41.0,
            aspect_risk=0.25,
            snowpack_shear_strength=2.0,
        )

        result = chebyshev_ipa(vector)

        self.assertEqual(result.dominant_criterion, 'slope_deviation_from_38deg')
        self.assertAlmostEqual(result.score, 1.0)
        self.assertEqual(risk_level(result.score), 5)

    def test_default_ipa_floor_does_not_reduce_legacy_probability_or_slope_risk(self) -> None:
        replay_cells = [
            {'probability': 0.10, 'slope_deg': 10.0, 'aspect_risk': 0.1, 'shear': 10.0},
            {'probability': 0.35, 'slope_deg': 28.0, 'aspect_risk': 0.2, 'shear': 8.0},
            {'probability': 0.62, 'slope_deg': 34.0, 'aspect_risk': 0.5, 'shear': 3.0},
            {'probability': 0.12, 'slope_deg': 44.0, 'aspect_risk': 0.3, 'shear': 5.0},
        ]

        for cell in replay_cells:
            vector = build_hazard_vector(
                probability=cell['probability'],
                slope_deg=cell['slope_deg'],
                aspect_risk=cell['aspect_risk'],
                snowpack_shear_strength=cell['shear'],
            )
            ipa_risk = max(risk_level(chebyshev_ipa(vector).score), legacy_max_risk_level(cell['probability'], cell['slope_deg'])[0])
            self.assertGreaterEqual(ipa_risk, legacy_max_risk_level(cell['probability'], cell['slope_deg'])[0])


class HazardImpactSeparationTests(unittest.TestCase):
    def test_hazard_vector_excludes_exposure(self) -> None:
        vector = build_hazard_vector(
            probability=0.5, slope_deg=38.0, aspect_risk=0.5,
            snowpack_shear_strength=6.0, exposure=0.9,
        )
        self.assertNotIn('exposure', vector)
        self.assertEqual(len(vector), 4)

    def test_impact_vector_contains_exposure_and_vulnerability(self) -> None:
        vector = build_impact_vector(exposure=0.7, vulnerability=0.5)
        self.assertIn('exposure', vector)
        self.assertIn('vulnerability', vector)
        self.assertAlmostEqual(vector['exposure'], 0.7)
        self.assertAlmostEqual(vector['vulnerability'], 0.5)

    def test_impact_risk_score_basic(self) -> None:
        vector = build_impact_vector(exposure=0.8, vulnerability=0.4)
        score = impact_risk_score(vector)
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_impact_risk_level_thresholds(self) -> None:
        self.assertEqual(impact_risk_level(0.10), 1)
        self.assertEqual(impact_risk_level(0.25), 2)
        self.assertEqual(impact_risk_level(0.45), 3)
        self.assertEqual(impact_risk_level(0.65), 4)
        self.assertEqual(impact_risk_level(0.80), 5)

    def test_chebyshev_ipa_ignores_exposure(self) -> None:
        vector = build_hazard_vector(
            probability=0.3, slope_deg=30.0, aspect_risk=0.2,
            snowpack_shear_strength=8.0,
        )
        result = chebyshev_ipa(vector)
        self.assertNotIn('exposure', result.weighted_criteria)


class DangerAggregationTests(unittest.TestCase):
    def test_danger_aggregation_default_matches_risk_level(self) -> None:
        config = DangerAggregationConfig()
        self.assertEqual(compute_danger_level(config, score=0.10), risk_level(0.10))
        self.assertEqual(compute_danger_level(config, score=0.40), risk_level(0.40))
        self.assertEqual(compute_danger_level(config, score=0.80), risk_level(0.80))

    def test_danger_aggregation_custom_config(self) -> None:
        config = DangerAggregationConfig(
            profile='custom',
            thresholds=(0.20, 0.40, 0.60, 0.80),
        )
        self.assertEqual(compute_danger_level(config, score=0.15), 1)
        self.assertEqual(compute_danger_level(config, score=0.35), 2)
        self.assertEqual(compute_danger_level(config, score=0.55), 3)
        self.assertEqual(compute_danger_level(config, score=0.75), 4)
        self.assertEqual(compute_danger_level(config, score=0.85), 5)

    def test_danger_aggregation_multi_factor(self) -> None:
        config = DangerAggregationConfig(
            profile='custom',
            factor_weights={'stability': 0.5, 'frequency': 0.3, 'size': 0.2},
        )
        level = compute_danger_level(config, stability=0.6, frequency=0.4, size=0.3)
        self.assertGreaterEqual(level, 1)
        self.assertLessEqual(level, 5)


if __name__ == '__main__':
    unittest.main()
