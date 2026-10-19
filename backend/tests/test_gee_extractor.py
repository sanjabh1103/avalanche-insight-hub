from __future__ import annotations

import unittest

from backend.gee_extractor import build_region_sar_summary


class GeeExtractorSummaryTests(unittest.TestCase):
    def test_region_summary_counts_provenance_fields(self) -> None:
        events = [
            {
                'training_eligible': True,
                'training_eligible_reason': None,
                'features': {
                    'training_bucket': 'core_training',
                    'ascending_scene_count': 3,
                    'descending_scene_count': 2,
                    'sar_coverage_state': 'full_coverage',
                },
            },
            {
                'training_eligible': True,
                'training_eligible_reason': 'sar_low_coverage_weak_training',
                'features': {
                    'training_bucket': 'weak_training',
                    'ascending_scene_count': 3,
                    'descending_scene_count': 2,
                    'sar_coverage_state': 'low_coverage',
                },
            },
            {
                'training_eligible': False,
                'training_eligible_reason': 'sar_single_pass_audit_only',
                'features': {
                    'training_bucket': 'audit_only',
                    'ascending_scene_count': 1,
                    'descending_scene_count': 0,
                    'sar_coverage_state': 'low_coverage',
                },
            },
        ]

        summary = build_region_sar_summary(
            region_key='colorado_rockies',
            ascending_count=3,
            descending_count=2,
            coverage_state='full_coverage',
            events=events,
        )

        self.assertEqual(summary['region'], 'colorado_rockies')
        self.assertEqual(summary['ascending_scene_count'], 3)
        self.assertEqual(summary['descending_scene_count'], 2)
        self.assertEqual(summary['fused_detections'], 3)
        self.assertEqual(summary['low_coverage_rejects'], 1)
        self.assertEqual(summary['eligible_detections'], 2)
        self.assertEqual(summary['core_training_detections'], 1)
        self.assertEqual(summary['weak_training_detections'], 1)
        self.assertEqual(summary['audit_only_detections'], 1)
        self.assertEqual(summary['sar_coverage_state'], 'full_coverage')
        self.assertEqual(summary['fusion_method'], 'quality_mosaic_latest_pixel_v1')


if __name__ == '__main__':
    unittest.main()
