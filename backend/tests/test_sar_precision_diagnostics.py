from __future__ import annotations

import unittest

from backend.common.sar_precision_diagnostics import build_sar_precision_diagnostics


class SarPrecisionDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_rank_scene_burdens_and_precision_failure(self) -> None:
        payload = {
            'candidate_model_version': 'avalcd-test-v1',
            'model_family': 'swinunet_tiny_diff',
            'dataset_audit': {'dataset_version': 'avalcd-test-sar'},
            'validation_metrics': {
                'threshold': 0.995,
                'precision': 0.38,
                'recall': 0.72,
                'f1': 0.50,
                'fp': 422,
                'tp': 257,
            },
            'threshold_metrics': [
                {'threshold': 0.95, 'precision': 0.35, 'recall': 0.75, 'f1': 0.47, 'fp': 500, 'tp': 270},
                {'threshold': 0.995, 'precision': 0.38, 'recall': 0.72, 'f1': 0.50, 'fp': 422, 'tp': 257},
            ],
            'scene_breakdown': [
                {
                    'scene_id': 'livigno_20250318',
                    'region_key': 'italian_alps',
                    'precision': 0.18,
                    'recall': 0.66,
                    'f1': 0.28,
                    'false_positive_rate': 0.0024,
                    'fp': 82,
                    'tp': 18,
                    'fn': 9,
                    'tn': 3300,
                },
                {
                    'scene_id': 'nuuk_20210411',
                    'region_key': 'greenland_nuuk',
                    'precision': 0.41,
                    'recall': 0.73,
                    'f1': 0.53,
                    'false_positive_rate': 0.0061,
                    'fp': 340,
                    'tp': 239,
                    'fn': 88,
                    'tn': 5484,
                },
            ],
        }

        diagnostics = build_sar_precision_diagnostics(payload, precision_floor=0.60)

        self.assertFalse(diagnostics['precision_floor_met'])
        self.assertEqual(diagnostics['failure_reason'], 'no_threshold_met_precision_floor')
        self.assertEqual(diagnostics['max_precision'], 0.38)
        self.assertEqual(diagnostics['flags']['weakest_precision_scene_id'], 'livigno_20250318')
        self.assertEqual(diagnostics['flags']['largest_fp_volume_scene_id'], 'nuuk_20210411')
        self.assertEqual(diagnostics['scene_diagnostics']['weakest_precision_scene']['precision'], 0.18)
        self.assertEqual(diagnostics['scene_diagnostics']['largest_fp_volume_scene']['fp'], 340)
        self.assertFalse(diagnostics['threshold_curve'][0]['precision_floor_met'])


if __name__ == '__main__':
    unittest.main()
