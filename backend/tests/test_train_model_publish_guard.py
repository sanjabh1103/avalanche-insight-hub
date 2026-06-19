from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

try:
    from backend.train_model import (
        build_model_status_truth,
        persist_phase2_evaluation_plane,
        publish_guard_reason,
    )
    _IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional training deps
    build_model_status_truth = None
    persist_phase2_evaluation_plane = None
    publish_guard_reason = None
    _IMPORT_ERROR = exc


@unittest.skipIf(publish_guard_reason is None, f'train_model import unavailable: {_IMPORT_ERROR}')
class TrainModelPublishGuardTests(unittest.TestCase):
    def _phase2_bundle(self) -> dict[str, object]:
        return {
            'metrics': {'pss_reported': 0.52, 'pss_gate_passed': True},
            'dataset_manifest': {
                'training_dataset_version': 'real_event_join_v1',
                'positive_count': 12,
                'negative_count': 28,
                'training_row_count': 40,
                'event_source_counts': {'field_report': 3, 'sar_unet': 9},
                'source_training_weight_sums': {'field_report': 2.1, 'sar_unet': 6.4},
                'source_region_counts': {'field_report': 1, 'sar_unet': 3},
                'region_keys': ['davos', 'kargil'],
                'newest_timestamp_by_source': {'field_report': '2026-04-20T00:00:00+00:00'},
            },
            'dataset_snapshot_id': 'real_event_join_v1:2026-04-25T00:00:00+00:00',
            'training_dataset_version': 'real_event_join_v1',
            'dynamic_model_version': 'mts-lstm-shadow-1',
            'surrogate_model_version': 'rf-surrogate-1',
            'lstm_head_meta': {
                'enabled': True,
                'dynamic_model_version': 'mts-lstm-shadow-1',
                'calibration_method': 'isotonic',
                'calibration_applied': True,
                'pss_holdout': 0.55,
                'pss_holdout_uncalibrated': 0.48,
                'brier_score': 0.17,
                'brier_score_uncalibrated': 0.22,
                'rf_pss_holdout': 0.46,
                'rf_brier_score': 0.19,
                'shadow_quality_gate_passed': True,
                'promotion_gate_passed': False,
                'production_eligibility_gate_passed': False,
                'sar_unet_promoted_count': 9,
                'sar_unet_promoted_region_count': 3,
                'sar_unet_promoted_scene_date_count': 6,
            },
            'lstm_evaluation': {
                'test_prob_uncalibrated': np.asarray([0.2, 0.3, 0.6, 0.8], dtype=np.float32),
                'test_prob_calibrated': np.asarray([0.1, 0.25, 0.72, 0.9], dtype=np.float32),
                'test_labels': np.asarray([0, 0, 1, 1], dtype=int),
            },
        }

    def _phase2_test_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            'timestamp': pd.date_range('2026-04-20', periods=4, freq='D', tz='UTC'),
            'region_key': ['davos', 'davos', 'kargil', 'kargil'],
            'label': [0, 0, 1, 1],
        })

    def test_synthetic_artifacts_are_never_published(self) -> None:
        reason = publish_guard_reason(is_synthetic=True, allow_publish=True)
        self.assertEqual(reason, 'synthetic_bootstrap_not_published')

    def test_shadow_only_remote_training_skips_publish(self) -> None:
        reason = publish_guard_reason(is_synthetic=False, allow_publish=False)
        self.assertEqual(reason, 'shadow_only_remote_training')

    def test_publish_allowed_when_real_data_and_flag_enabled(self) -> None:
        reason = publish_guard_reason(is_synthetic=False, allow_publish=True)
        self.assertIsNone(reason)

    def test_publish_guard_blocks_low_pss(self) -> None:
        reason = publish_guard_reason(
            is_synthetic=False,
            allow_publish=True,
            pss_reported=0.44,
            brier_score=0.10,
            pss_floor=0.45,
            brier_ceiling=0.15,
        )
        self.assertEqual(reason, 'pss_gate_failed')

    def test_publish_guard_blocks_poor_brier_calibration(self) -> None:
        reason = publish_guard_reason(
            is_synthetic=False,
            allow_publish=True,
            pss_reported=0.52,
            brier_score=0.16,
            pss_floor=0.45,
            brier_ceiling=0.15,
        )
        self.assertEqual(reason, 'brier_score_gate_failed')

    def test_build_model_status_truth_keeps_rf_active_until_promotion_gate(self) -> None:
        truth = build_model_status_truth({
            'created_at': '2026-04-25T00:00:00+00:00',
            'surrogate_model_version': 'rf_surrogate_v1',
            'metrics': {'pss_reported': 0.52, 'pss_gate_passed': True},
            'stability_summary': {'classification': 'stable', 'seed_count': 3},
            'latest_benchmark_summary': {'benchmark_kind': 'training', 'total_seconds': 18.2},
            'dataset_manifest': {
                'training_dataset_version': 'real_event_join_v1',
                'positive_count': 10,
                'negative_count': 30,
                'training_row_count': 40,
                'event_source_counts': {'field_report': 2, 'sar_unet': 8},
                'source_training_weight_sums': {'field_report': 1.8, 'sar_unet': 5.6},
                'source_region_counts': {'field_report': 1, 'sar_unet': 3},
                'newest_timestamp_by_source': {'field_report': '2026-04-20T00:00:00+00:00'},
                'region_keys': ['davos', 'drass', 'kargil'],
                'mean_training_weight': 0.74,
            },
            'lstm_head_meta': {
                'enabled': True,
                'promotion_gate_passed': False,
                'shadow_quality_gate_passed': True,
                'sar_release_gate_passed': False,
                'sar_volume_gate_passed': False,
                'production_eligibility_gate_passed': False,
                'dynamic_model_type': 'mts_lstm_v1',
                'dynamic_model_version': 'mts-lstm-shadow-1',
                'sar_unet_promoted_count': 8,
                'sar_unet_promoted_region_count': 3,
                'sar_unet_promoted_scene_date_count': 5,
            },
        })
        self.assertEqual(truth['dynamic_model_candidate']['dynamic_model_type'], 'mts_lstm_v1')
        self.assertEqual(truth['dynamic_model_candidate']['blocked_gate'], 'sar_release_gate')
        self.assertFalse(truth['dynamic_model_candidate']['ready_for_activation'])
        self.assertEqual(truth['autonomous_evidence_summary']['manual_positive_count'], 2)
        self.assertEqual(truth['autonomous_evidence_summary']['autonomous_positive_count'], 8)
        self.assertEqual(truth['stability_summary']['classification'], 'stable')
        self.assertEqual(truth['drift_mode_state'], 'blocked_by_gate')
        self.assertEqual(truth['latest_benchmark_summary']['benchmark_kind'], 'training')

    def test_persist_phase2_evaluation_plane_writes_artifacts_without_supabase_credentials(self) -> None:
        artifact_dir_path: Path
        with TemporaryDirectory() as tmpdir:
            artifact_dir_path = Path(tmpdir)
            summary = persist_phase2_evaluation_plane(
                artifact_dir=artifact_dir_path,
                bundle=self._phase2_bundle(),
                metadata={'published_at': '2026-05-03T00:00:00+00:00'},
                test_df=self._phase2_test_df(),
            )
            self.assertEqual(summary['db_write_status'], 'skipped_no_credentials')
            self.assertTrue((artifact_dir_path / 'label_snapshot.json').exists())
            self.assertTrue((artifact_dir_path / 'hindcast_run.json').exists())
            self.assertTrue((artifact_dir_path / 'calibration_reports.json').exists())

    @patch('backend.train_model.rest_insert')
    @patch('backend.train_model.rest_upsert')
    @patch('backend.train_model.has_supabase_credentials', return_value=True)
    def test_persist_phase2_evaluation_plane_writes_db_rows_when_credentials_exist(
        self,
        _has_supabase_credentials_mock,
        rest_upsert_mock,
        rest_insert_mock,
    ) -> None:
        rest_upsert_mock.return_value = [{'id': 'label-snapshot-1'}]
        rest_insert_mock.side_effect = [
            [{'id': 'hindcast-run-1'}],
            [{'id': 'calibration-report-1'}],
        ]

        with TemporaryDirectory() as tmpdir:
            summary = persist_phase2_evaluation_plane(
                artifact_dir=Path(tmpdir),
                bundle=self._phase2_bundle(),
                metadata={'published_at': '2026-05-03T00:00:00+00:00'},
                test_df=self._phase2_test_df(),
            )

        self.assertEqual(summary['db_write_status'], 'ok')
        self.assertEqual(summary['label_snapshot_id'], 'label-snapshot-1')
        self.assertEqual(summary['hindcast_run_id'], 'hindcast-run-1')
        self.assertTrue(summary['calibration_report_ids'])


if __name__ == '__main__':
    unittest.main()
