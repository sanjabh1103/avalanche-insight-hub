from __future__ import annotations

import unittest

from backend.common.shadow_danger_semantics import build_shadow_danger_candidate
from backend.common.shadow_probability_map import compare_probability_maps


class ShadowProbabilityAndDangerTests(unittest.TestCase):
    def test_direct_map_is_reference_and_gp_is_shadow_only(self) -> None:
        result = compare_probability_maps(
            anchor_points=[(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)],
            anchor_probabilities=[0.1, 0.4, 0.6, 0.9],
            query_points=[(0.0, 0.0), (0.5, 0.5)],
        )

        self.assertTrue(result['shadow_only'])
        self.assertEqual(result['direct_probabilities'][0], 0.1)
        self.assertEqual(len(result['direct_probabilities']), 2)
        self.assertIn(result['gp_status'], {'computed', 'unavailable'})
        if result['gp_status'] == 'computed':
            self.assertEqual(len(result['gp_probabilities']), 2)
            self.assertEqual(len(result['gp_std']), 2)

    def test_structured_danger_candidate_is_explicitly_non_authoritative(self) -> None:
        result = build_shadow_danger_candidate(
            probability=0.65,
            frequency=0.7,
            duration_hours=48,
            size_class=4,
            instability=0.8,
            source_attribution=['french_epa_historical', 'gee_sar'],
        )

        self.assertTrue(result['is_shadow_only'])
        self.assertEqual(result['status'], 'shadow_only')
        self.assertIn(result['candidate_level'], {1, 2, 3, 4, 5})
        self.assertEqual(result['source_attribution'], ['french_epa_historical', 'gee_sar'])
        self.assertNotIn('authoritative_level', result)


if __name__ == '__main__':
    unittest.main()
