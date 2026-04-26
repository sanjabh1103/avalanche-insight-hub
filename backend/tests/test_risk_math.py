from __future__ import annotations

import unittest

from backend.common.risk_math import build_hazard_vector, chebyshev_ipa, legacy_max_risk_level, risk_level


class ChebyshevIPATests(unittest.TestCase):
    def test_chebyshev_reports_dominant_criterion(self) -> None:
        vector = build_hazard_vector(
            probability=0.22,
            slope_deg=41.0,
            aspect_risk=0.25,
            snowpack_shear_strength=2.0,
            exposure=0.35,
        )

        result = chebyshev_ipa(vector)

        self.assertEqual(result.dominant_criterion, 'slope_deviation_from_38deg')
        self.assertAlmostEqual(result.score, 1.0)
        self.assertEqual(risk_level(result.score), 5)

    def test_default_ipa_floor_does_not_reduce_legacy_probability_or_slope_risk(self) -> None:
        replay_cells = [
            {'probability': 0.10, 'slope_deg': 10.0, 'aspect_risk': 0.1, 'shear': 10.0, 'exposure': 0.1},
            {'probability': 0.35, 'slope_deg': 28.0, 'aspect_risk': 0.2, 'shear': 8.0, 'exposure': 0.4},
            {'probability': 0.62, 'slope_deg': 34.0, 'aspect_risk': 0.5, 'shear': 3.0, 'exposure': 0.6},
            {'probability': 0.12, 'slope_deg': 44.0, 'aspect_risk': 0.3, 'shear': 5.0, 'exposure': 0.2},
        ]

        for cell in replay_cells:
            vector = build_hazard_vector(
                probability=cell['probability'],
                slope_deg=cell['slope_deg'],
                aspect_risk=cell['aspect_risk'],
                snowpack_shear_strength=cell['shear'],
                exposure=cell['exposure'],
            )
            ipa_risk = max(risk_level(chebyshev_ipa(vector).score), legacy_max_risk_level(cell['probability'], cell['slope_deg'])[0])
            self.assertGreaterEqual(ipa_risk, legacy_max_risk_level(cell['probability'], cell['slope_deg'])[0])


if __name__ == '__main__':
    unittest.main()
