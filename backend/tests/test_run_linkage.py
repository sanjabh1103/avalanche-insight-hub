from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.common.run_linkage import merge_compute_job_terminal_result


class RunLinkageTests(unittest.TestCase):
    @patch('backend.common.run_linkage.patch_row_by_id')
    @patch('backend.common.run_linkage.rest_get')
    def test_merge_compute_job_terminal_result_marks_completed_and_records_worker_result(
        self,
        rest_get_mock,
        patch_row_by_id_mock,
    ) -> None:
        rest_get_mock.return_value = [{'result': {'modal_call_id': 'fc-123'}}]
        worker_result = {
            'status': 'ok',
            'completed_at': '2026-05-01T14:16:56.601562+00:00',
            'skip_tree_shap': False,
            'skip_shap_cache': True,
            'skip_runout_generation': False,
            'skip_compatibility_write': True,
            'emit_stage_metrics': True,
            'stage_metrics_summary': {
                'region_count': 1,
            },
        }

        merge_compute_job_terminal_result(
            compute_job_id='job-123',
            linkage={
                'artifact_dir': '/artifacts/20260430T165639Z',
                'forecast_run_id': 'run-123',
                'forecast_run_ids_by_region': {'himalayas_nepal': 'run-123'},
            },
            worker_result=worker_result,
        )

        patch_row_by_id_mock.assert_called_once_with(
            'compute_jobs',
            'job-123',
            {
                'status': 'completed',
                'result': {
                    'modal_call_id': 'fc-123',
                    'artifact_dir': '/artifacts/20260430T165639Z',
                    'forecast_run_id': 'run-123',
                    'forecast_run_ids_by_region': {'himalayas_nepal': 'run-123'},
                    'workerResult': worker_result,
                    'workerCompletedAt': '2026-05-01T14:16:56.601562+00:00',
                },
                'error': None,
            },
            returning='minimal',
            timeout_seconds=120,
        )

    @patch('backend.common.run_linkage.patch_row_by_id')
    @patch('backend.common.run_linkage.rest_get')
    def test_merge_compute_job_terminal_result_marks_failed_and_extracts_error(
        self,
        rest_get_mock,
        patch_row_by_id_mock,
    ) -> None:
        rest_get_mock.return_value = [{'result': {'modal_call_id': 'fc-456'}}]
        worker_result = {
            'status': 'failed',
            'completed_at': '2026-05-01T15:00:00+00:00',
            'stderr_tail': ['forecast publish failed'],
        }

        merge_compute_job_terminal_result(
            compute_job_id='job-456',
            linkage={
                'artifact_dir': '/artifacts/20260430T165639Z',
                'forecast_run_id': None,
            },
            worker_result=worker_result,
        )

        patch_row_by_id_mock.assert_called_once_with(
            'compute_jobs',
            'job-456',
            {
                'status': 'failed',
                'result': {
                    'modal_call_id': 'fc-456',
                    'artifact_dir': '/artifacts/20260430T165639Z',
                    'workerResult': worker_result,
                    'workerCompletedAt': '2026-05-01T15:00:00+00:00',
                },
                'error': 'forecast publish failed',
            },
            returning='minimal',
            timeout_seconds=120,
        )


if __name__ == '__main__':
    unittest.main()
