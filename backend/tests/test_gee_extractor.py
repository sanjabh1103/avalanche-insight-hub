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
                    'ascending_scene_count': 3,
                    'descending_scene_count': 2,
                    'sar_coverage_state': 'full_coverage',
                },
            },
            {
                'training_eligible': False,
                'training_eligible_reason': 'sar_low_coverage',
                'features': {
                    'ascending_scene_count': 3,
                    'descending_scene_count': 2,
                    'sar_coverage_state': 'full_coverage',
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
        self.assertEqual(summary['fused_detections'], 2)
        self.assertEqual(summary['low_coverage_rejects'], 1)
        self.assertEqual(summary['eligible_detections'], 1)
        self.assertEqual(summary['sar_coverage_state'], 'full_coverage')
        self.assertEqual(summary['fusion_method'], 'quality_mosaic_latest_pixel_v1')


if __name__ == '__main__':
    unittest.main()
