from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.scripts.run_modal_sar_prediction_materialization_direct import (
    assert_avalcd_gate_allows_materialization,
    load_materialization_request,
    main,
)


def _benchmark_report(*, gate_passed: bool) -> dict:
    return {
        'production_scoring_allowed': False,
        'promotion_gate_report': {'decision': 'blocked_shadow_only'},
        'source_reports': [{
            'source_key': 'avalcd_zenodo_v1',
            'sar_prediction_metrics': {
                'quality_gate': {
                    'passed': gate_passed,
                    'precision_floor_met': gate_passed,
                    'recall_floor_met': gate_passed,
                },
            },
        }],
    }


class RunModalSarPredictionMaterializationDirectTests(unittest.TestCase):
    def test_load_materialization_request_requires_artifact_model_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            request_path = Path(tmpdir) / 'request.json'
            request_path.write_text(json.dumps({
                'reference_set_key': 'snowslide-heldout-v1',
                'prediction_model_version': 'avalcd-v4',
                'model_path': '/tmp/sar_model.pt',
            }), encoding='utf-8')

            with self.assertRaisesRegex(ValueError, 'under /artifacts'):
                load_materialization_request(request_path)

    def test_gate_blocks_when_avalcd_quality_gate_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, 'quality gate passes'):
            assert_avalcd_gate_allows_materialization(_benchmark_report(gate_passed=False))

    def test_main_invokes_sar_segment_remote_when_gate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            request_path = root / 'request.json'
            benchmark_path = root / 'benchmark.json'
            output_path = root / 'result.json'
            request_path.write_text(json.dumps({
                'reference_set_key': 'snowslide-heldout-v1',
                'prediction_model_version': 'avalcd-v4',
                'model_family': 'swinunet_tiny_diff',
                'model_path': '/artifacts/20260516T164730Z/sar_model.pt',
                'threshold': 0.995,
            }), encoding='utf-8')
            benchmark_path.write_text(json.dumps(_benchmark_report(gate_passed=True)), encoding='utf-8')
            remote_function = Mock()
            remote_function.remote.return_value = {
                'status': 'ok',
                'mask_asset_refs': ['sar-masks/heldout/snowslide/prediction_mask.tif'],
            }
            function_namespace = SimpleNamespace(from_name=Mock(return_value=remote_function))
            fake_modal = SimpleNamespace(Function=function_namespace)

            with patch(
                'backend.scripts.run_modal_sar_prediction_materialization_direct._load_modal_module',
                return_value=fake_modal,
            ), patch.dict(os.environ, {}, clear=True):
                exit_code = main([
                    '--modal-profile', 'sanjabh1103_limit30',
                    '--request', str(request_path),
                    '--avalcd-benchmark-report', str(benchmark_path),
                    '--output', str(output_path),
                ])

            payload = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload['status'], 'ok')
            self.assertEqual(payload['modal_profile'], 'sanjabh1103_limit30')
            function_namespace.from_name.assert_called_once_with('avalanche-modal-worker', 'sar_segment_remote')
            request_payload = remote_function.remote.call_args.args[0]
            self.assertFalse(request_payload['persist_events'])
            self.assertTrue(request_payload['shadow_mode'])

    def test_main_writes_blocked_artifact_when_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            request_path = root / 'request.json'
            benchmark_path = root / 'benchmark.json'
            output_path = root / 'result.json'
            request_path.write_text(json.dumps({
                'reference_set_key': 'snowslide-heldout-v1',
                'prediction_model_version': 'avalcd-v4',
                'model_path': '/artifacts/20260516T164730Z/sar_model.pt',
            }), encoding='utf-8')
            benchmark_path.write_text(json.dumps(_benchmark_report(gate_passed=False)), encoding='utf-8')

            exit_code = main([
                '--modal-profile', 'sanjabh1103_limit30',
                '--request', str(request_path),
                '--avalcd-benchmark-report', str(benchmark_path),
                '--output', str(output_path),
            ])

            payload = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload['status'], 'blocked_prediction_materialization')
            self.assertIn('quality gate passes', payload['reason'])


if __name__ == '__main__':
    unittest.main()
