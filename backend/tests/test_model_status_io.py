from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.common.supabase_io import fetch_latest_model_status_row, patch_latest_model_status_row
from backend.daily_inference import _fetch_current_model_status
from backend.scripts.activate_dynamic_model_candidate import _fetch_model_status_row


LATEST_MODEL_STATUS_PARAMS = {
    'select': '*',
    'order': 'last_inference.desc.nullslast,last_trained.desc.nullslast',
    'limit': '1',
}


class LatestModelStatusIoTests(unittest.TestCase):
    @patch('backend.common.supabase_io.rest_get')
    def test_fetch_latest_model_status_row_orders_by_latest_inference_then_training(
        self,
        rest_get_mock,
    ) -> None:
        rest_get_mock.return_value = [{'id': 'row-1', 'version': 'forecast-1'}]

        row = fetch_latest_model_status_row()

        self.assertEqual(row, {'id': 'row-1', 'version': 'forecast-1'})
        rest_get_mock.assert_called_once_with('model_status', LATEST_MODEL_STATUS_PARAMS)

    @patch('backend.common.supabase_io.patch_row_by_id')
    @patch('backend.common.supabase_io.rest_get')
    def test_patch_latest_model_status_row_updates_latest_row_id(
        self,
        rest_get_mock,
        patch_row_by_id_mock,
    ) -> None:
        rest_get_mock.return_value = [{'id': 'row-99'}]
        patch_row_by_id_mock.return_value = {'id': 'row-99', 'version': 'next'}

        result = patch_latest_model_status_row({'version': 'next'})

        self.assertEqual(result, {'id': 'row-99', 'version': 'next'})
        rest_get_mock.assert_called_once_with(
            'model_status',
            {
                'select': 'id',
                'order': 'last_inference.desc.nullslast,last_trained.desc.nullslast',
                'limit': '1',
            },
        )
        patch_row_by_id_mock.assert_called_once_with(
            'model_status',
            'row-99',
            {'version': 'next'},
            returning='representation',
            timeout_seconds=30,
        )


class ModelStatusReaderDelegationTests(unittest.TestCase):
    @patch('backend.daily_inference.fetch_latest_model_status_row')
    @patch('backend.daily_inference.has_supabase_credentials', return_value=True)
    def test_daily_inference_fetch_current_model_status_uses_latest_helper(
        self,
        _has_credentials_mock,
        fetch_latest_model_status_row_mock,
    ) -> None:
        fetch_latest_model_status_row_mock.return_value = {'id': 'row-1'}

        row = _fetch_current_model_status()

        self.assertEqual(row, {'id': 'row-1'})
        fetch_latest_model_status_row_mock.assert_called_once_with()

    @patch('backend.scripts.activate_dynamic_model_candidate.fetch_latest_model_status_row')
    @patch('backend.scripts.activate_dynamic_model_candidate.has_supabase_credentials', return_value=True)
    def test_activate_dynamic_model_candidate_fetches_latest_row_via_helper(
        self,
        _has_credentials_mock,
        fetch_latest_model_status_row_mock,
    ) -> None:
        fetch_latest_model_status_row_mock.return_value = {'id': 'row-2'}

        row = _fetch_model_status_row()

        self.assertEqual(row, {'id': 'row-2'})
        fetch_latest_model_status_row_mock.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
