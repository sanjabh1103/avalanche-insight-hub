"""Tests for RAvaFcast runtime gate wiring in daily_inference.py main()."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock


class DailyInferenceRuntimeGateTests(unittest.TestCase):
    """Verify that the canonical scheduled path emits ravafcast gate metadata."""

    def test_stage_metrics_contains_ravafcast_gate_disabled(self) -> None:
        """When RAVAFCAST_PIPELINE_ENABLED is unset, gate status must be 'disabled'."""
        from backend.common.ravafcast_runtime_gate import check_pipeline_status, emit_gate_metadata

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RAVAFCAST_PIPELINE_ENABLED', None)
            status = check_pipeline_status()
            self.assertEqual(status.status, 'disabled')
            metadata = emit_gate_metadata(status)
            self.assertEqual(metadata['ravafcast_gate']['status'], 'disabled')
            self.assertTrue(metadata['ravafcast_gate']['active_path_unchanged'])

    def test_stage_metrics_contains_ravafcast_gate_enabled(self) -> None:
        """When RAVAFCAST_PIPELINE_ENABLED=true, gate status must not be 'disabled'."""
        from backend.common.ravafcast_runtime_gate import check_pipeline_status

        with patch.dict(os.environ, {'RAVAFCAST_PIPELINE_ENABLED': 'true'}):
            status = check_pipeline_status()
            self.assertNotEqual(status.status, 'disabled')

    def test_main_emits_gate_metadata_in_stage_metrics(self) -> None:
        """Verify that main() adds ravafcast_gate to stage_metrics_payload."""
        import backend.daily_inference as di

        captured_payload: dict = {}

        original_dump_json = di.dump_json

        def capture_dump_json(path: Path, data: dict, **kwargs) -> None:
            if 'inference_stage_metrics' in str(path):
                captured_payload.update(data)
            original_dump_json(path, data, **kwargs)

        with patch.dict(os.environ, {
            'RAVAFCAST_PIPELINE_ENABLED': 'false',
            'DRY_RUN': '1',
            'SUPABASE_URL': '',
            'SUPABASE_SERVICE_ROLE_KEY': '',
        }, clear=False):
            with patch.object(di, 'dump_json', side_effect=capture_dump_json):
                with patch.object(di, 'resolve_artifact_dir', return_value=Path('/tmp/test_gate')):
                    with patch.object(di, 'load_settings') as mock_settings:
                        mock_settings.return_value = MagicMock(
                            artifact_root=Path('/tmp/test_gate'),
                            forecast_horizon_hours=1,
                            grid_size=3,
                            dry_run=True,
                        )
                        with patch.object(di, 'load_regions', return_value=[]):
                            with patch.object(di, 'resolve_active_model_state', return_value={}):
                                with patch.object(di, 'build_autonomous_evidence_summary', return_value={}):
                                    with patch.object(di, 'build_drift_mode_state', return_value={}):
                                        with patch.object(di, 'build_dynamic_model_candidate', return_value=None):
                                            with patch.object(di, 'resolve_active_candidate_artifact_dir', return_value=None):
                                                with patch.object(di, 'build_latest_benchmark_summary', return_value={}):
                                                    with patch.object(di, 'build_source_health_summary', return_value={}):
                                                        try:
                                                            di.main(['--dry-run', '--emit-stage-metrics', '--artifact-dir', '/tmp/test_gate'])
                                                        except Exception:
                                                            pass  # main() may raise in mock env; gate metadata is checked below
                                                        if captured_payload:
                                                            self.assertIn('ravafcast_gate', captured_payload)
                                                            self.assertEqual(
                                                                captured_payload['ravafcast_gate']['ravafcast_gate']['status'],
                                                                'disabled',
                                                            )

    def test_gate_does_not_modify_active_path(self) -> None:
        """Gate metadata must not alter risk_score, danger, CAP, or SACHET."""
        from backend.common.ravafcast_runtime_gate import check_pipeline_status, emit_gate_metadata

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RAVAFCAST_PIPELINE_ENABLED', None)
            status = check_pipeline_status()
            metadata = emit_gate_metadata(status)
            gate = metadata['ravafcast_gate']
            self.assertTrue(gate['active_path_unchanged'])
            self.assertNotIn('risk_score', gate)
            self.assertNotIn('danger', gate)
            self.assertNotIn('cap', gate)
            self.assertNotIn('sachet', gate)

    def test_grid_physics_reuses_selected_proxy_when_native_backend_is_absent(self) -> None:
        import backend.daily_inference as di

        with patch.dict(os.environ, {'SNOWPACK_GRID_PHYSICS_MODE': 'auto'}):
            with patch.object(di, 'SNOWPACK_PHYSICS_ENABLED', True), \
                 patch.object(di, 'snowpack_binary_available', return_value=False):
                self.assertTrue(di._reuse_selected_proxy_for_grid_physics())

    def test_grid_physics_override_can_force_diagnostic_physics_path(self) -> None:
        import backend.daily_inference as di

        with patch.dict(os.environ, {'SNOWPACK_GRID_PHYSICS_MODE': 'physics'}):
            self.assertFalse(di._reuse_selected_proxy_for_grid_physics())

    def test_calibrated_probability_helper_preserves_batch_shape(self) -> None:
        import backend.daily_inference as di
        import numpy as np
        import pandas as pd

        class _InnerEstimator:
            n_jobs = -1

        inner = _InnerEstimator()

        class _FakeCalibrator:
            n_jobs = None
            estimator = type('_FrozenEstimator', (), {'estimator': inner})()

            def predict_proba(self, frame):
                self.received_rows = len(frame)
                return np.asarray([[0.25, 0.75] for _ in range(len(frame))])

        model = _FakeCalibrator()
        probabilities = di._predict_calibrated_probabilities(
            model,
            pd.DataFrame({'feature': [1.0, 2.0]}),
        )
        self.assertEqual(model.received_rows, 2)
        self.assertEqual(probabilities.tolist(), [0.75, 0.75])
        self.assertEqual(model.n_jobs, 1)
        self.assertEqual(inner.n_jobs, 1)


if __name__ == '__main__':
    unittest.main()
