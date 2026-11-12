from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.sar_release_promote import promote_from_report


def _accepted_report() -> dict:
    return {
        'decision': 'accepted_research_grade',
        'accepted_research_grade': True,
        'requires_fresh_final_holdout': False,
    }


class SarReleasePromoteTests(unittest.TestCase):
    def test_promote_from_report_rejects_baseline_only_report_without_acceptance(self) -> None:
        with self.assertRaisesRegex(ValueError, 'SnowSlide research-grade acceptance report'):
            promote_from_report(
                {'status': 'ok', 'beats_baseline': True},
                artifact_root=Path('.'),
                recent_shadow_event_ids=['evt-1'],
            )

    def test_promote_from_report_rejects_non_passing_report(self) -> None:
        with self.assertRaisesRegex(ValueError, 'beats_baseline=true'):
            promote_from_report(
                {'status': 'ok', 'beats_baseline': False},
                artifact_root=Path('.'),
                recent_shadow_event_ids=['evt-1'],
            )

    @patch('backend.sar_release_promote.run_segmentation')
    def test_promote_from_report_reruns_segmentation_in_promoted_mode(self, run_segmentation_mock) -> None:
        run_segmentation_mock.return_value = {'status': 'ok', 'persisted_events': 2}
        with tempfile.TemporaryDirectory() as tmpdir:
            result = promote_from_report(
                {'status': 'ok', 'beats_baseline': True},
                acceptance_report=_accepted_report(),
                scenes_manifest={'scenes': [{'scene_id': 'S1A_001', 'region_key': 'colorado_rockies'}]},
                model_path=Path('/tmp/model.ckpt'),
                artifact_root=Path(tmpdir),
            )

        self.assertEqual(result['promotion_mode'], 'rerun_segmentation')
        self.assertEqual(run_segmentation_mock.call_args.kwargs['promoted'], True)
        self.assertEqual(run_segmentation_mock.call_args.kwargs['persist_events'], True)

    @patch('backend.sar_release_promote.flip_to_training_eligible', return_value=2)
    def test_promote_from_report_flips_existing_shadow_rows(self, flip_mock) -> None:
        result = promote_from_report(
            {'status': 'ok', 'beats_baseline': True},
            acceptance_report=_accepted_report(),
            artifact_root=Path('.'),
            recent_shadow_event_ids=['evt-1', 'evt-2'],
        )

        self.assertEqual(result['promotion_mode'], 'flip_existing')
        self.assertEqual(result['promoted_event_ids'], 2)
        flip_mock.assert_called_once_with(['evt-1', 'evt-2'])

    @patch('backend.sar_release_promote._query_recent_shadow_event_ids', return_value=['evt-3'])
    @patch('backend.sar_release_promote.flip_to_training_eligible', return_value=1)
    def test_promote_from_report_queries_recent_shadow_rows_when_days_back_provided(
        self,
        flip_mock,
        query_mock,
    ) -> None:
        result = promote_from_report(
            {'status': 'ok', 'beats_baseline': True},
            acceptance_report=_accepted_report(),
            artifact_root=Path('.'),
            recent_days_back=14,
        )

        self.assertEqual(result['promoted_event_ids'], 1)
        query_mock.assert_called_once_with(14, hazard_type='avalanche')
        flip_mock.assert_called_once_with(['evt-3'])


if __name__ == '__main__':
    unittest.main()
