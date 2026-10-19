"""Tests for the post-publication scientist evidence-case seam."""
from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import patch

if 'imblearn.over_sampling' not in sys.modules:
    imblearn_module = types.ModuleType('imblearn')
    over_sampling_module = types.ModuleType('imblearn.over_sampling')

    class _KMeansSMOTEStub:
        def __init__(self, *args, **kwargs) -> None:
            pass

    over_sampling_module.KMeansSMOTE = _KMeansSMOTEStub
    imblearn_module.over_sampling = over_sampling_module
    sys.modules['imblearn'] = imblearn_module
    sys.modules['imblearn.over_sampling'] = over_sampling_module

import backend.daily_inference as daily


class TestPublishedEvidenceCaseMaterialization(unittest.TestCase):
    @patch.dict(os.environ, {'SCIENTIST_EVIDENCE_CASES_ENABLED': 'true'}, clear=False)
    @patch.object(daily, 'VERIFICATION_SPINE_ENABLED', True)
    @patch('backend.daily_inference.materialize_published_evidence_cases')
    def test_materializes_only_after_a_published_run_id(self, materialize_mock) -> None:
        materialize_mock.return_value = {'status': 'ok', 'cases_total': 1, 'cases_synced': 1}

        result = daily._materialize_published_evidence_cases_best_effort(
            forecast_run_id='11111111-1111-1111-1111-111111111111',
            region_key='great_himalaya',
            region_name='Great Himalaya',
            forecast_date='2026-01-15',
            rows=[{'row': 4, 'col': 7}],
            model_metadata={'model_version': 'rf-2026.01'},
        )

        self.assertEqual(result['status'], 'ok')
        materialize_mock.assert_called_once_with(
            forecast_run_id='11111111-1111-1111-1111-111111111111',
            region_key='great_himalaya',
            region_name='Great Himalaya',
            forecast_date='2026-01-15',
            forecast_grid_id=None,
            rows=[{'row': 4, 'col': 7}],
            model_metadata={'model_version': 'rf-2026.01'},
            enabled=True,
        )

    @patch.dict(os.environ, {'SCIENTIST_EVIDENCE_CASES_ENABLED': 'false'}, clear=False)
    @patch.object(daily, 'VERIFICATION_SPINE_ENABLED', True)
    @patch('backend.daily_inference.materialize_published_evidence_cases')
    def test_disabled_or_nonpublished_run_does_not_materialize(self, materialize_mock) -> None:
        disabled = daily._materialize_published_evidence_cases_best_effort(
            forecast_run_id='11111111-1111-1111-1111-111111111111',
            region_key='great_himalaya',
            region_name='Great Himalaya',
            forecast_date='2026-01-15',
            rows=[],
            model_metadata={},
        )
        blocked = daily._materialize_published_evidence_cases_best_effort(
            forecast_run_id='uq_blocked',
            region_key='great_himalaya',
            region_name='Great Himalaya',
            forecast_date='2026-01-15',
            rows=[],
            model_metadata={},
        )

        self.assertEqual(disabled['status'], 'disabled')
        self.assertEqual(blocked['status'], 'not_published')
        materialize_mock.assert_not_called()

    @patch.dict(os.environ, {'SCIENTIST_EVIDENCE_CASES_ENABLED': 'true'}, clear=False)
    @patch.object(daily, 'VERIFICATION_SPINE_ENABLED', True)
    @patch('backend.daily_inference.materialize_published_evidence_cases', side_effect=RuntimeError('network unavailable'))
    def test_materialization_failure_cannot_interrupt_publication(self, _materialize_mock) -> None:
        result = daily._materialize_published_evidence_cases_best_effort(
            forecast_run_id='11111111-1111-1111-1111-111111111111',
            region_key='great_himalaya',
            region_name='Great Himalaya',
            forecast_date='2026-01-15',
            rows=[],
            model_metadata={},
        )

        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error_class'], 'RuntimeError')


if __name__ == '__main__':
    unittest.main()
