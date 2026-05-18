from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.scripts.run_authoritative_release_gate import (
    apply_authoritative_release_env,
    record_promotion_event,
    resolve_local_model_path,
    run_authoritative_release_gate,
)


def _accepted_report() -> dict:
    return {
        'decision': 'accepted_research_grade',
        'accepted_research_grade': True,
        'requires_fresh_final_holdout': False,
    }


class RunAuthoritativeReleaseGateTests(unittest.TestCase):
    def test_resolve_local_model_path_falls_back_to_repo_checkpoint_when_artifact_mount_path_is_local_only(self) -> None:
        resolved = resolve_local_model_path('/artifacts/models/swin_transformer_v2_tiny_coldstart_v1.pt')
        self.assertEqual(resolved, Path('backend/data/models/swin_transformer_v2_tiny_coldstart_v1.pt').resolve())

    @patch('backend.scripts.run_authoritative_release_gate.load_rollout_env')
    def test_apply_authoritative_release_env_requires_model_path(self, load_rollout_env_mock) -> None:
        load_rollout_env_mock.return_value = SimpleNamespace(
            supabase_url='https://example.supabase.co',
            supabase_service_role_key='service-role',
            modal_worker_url='https://worker.modal.run',
            modal_worker_token='worker-token',
            sar_unet_model_path=None,
            sar_unet_model_version='sar_unet_resnet34_shadow_v1',
            sar_unet_model_family='resnet34_unet',
            sar_unet_device='cpu',
        )

        with self.assertRaisesRegex(ValueError, 'SAR_UNET_MODEL_PATH'):
            apply_authoritative_release_env(Path('.env'))

    @patch('backend.scripts.run_authoritative_release_gate.record_promotion_event')
    @patch('backend.scripts.run_authoritative_release_gate.promote_from_report')
    @patch('backend.scripts.run_authoritative_release_gate.post_evaluate_release')
    @patch('backend.scripts.run_authoritative_release_gate.build_authoritative_manifest')
    @patch('backend.scripts.run_authoritative_release_gate.apply_authoritative_release_env')
    def test_run_authoritative_release_gate_promotes_when_authoritative_gate_passes(
        self,
        apply_env_mock,
        build_manifest_mock,
        post_evaluate_release_mock,
        promote_from_report_mock,
        record_promotion_event_mock,
    ) -> None:
        apply_env_mock.return_value = {
            'modal_worker_url': 'https://worker.modal.run',
            'modal_worker_token': 'worker-token',
            'sar_unet_model_path': '/tmp/model.ckpt',
            'sar_unet_model_version': 'sar_unet_resnet34_shadow_v1',
            'sar_unet_device': 'cpu',
        }
        build_manifest_mock.return_value = {'reference_set_key': 'snowslide-heldout-v1', 'scenes': [{'scene_id': 'S1A_001'}]}
        post_evaluate_release_mock.return_value = {
            'status': 'ok',
            'beats_baseline': True,
            'f1': 0.81,
            'baseline_f1_floor_used': 0.74,
        }
        promote_from_report_mock.return_value = {'status': 'ok', 'promotion_mode': 'rerun_segmentation'}
        record_promotion_event_mock.return_value = {'id': 'promotion-1'}

        result = run_authoritative_release_gate(
            env_file=Path('.env'),
            reference_set_key='snowslide-heldout-v1',
            prediction_model_version='sar_unet_resnet34_shadow_v1',
            artifact_root=Path('/tmp/artifacts'),
            device='cpu',
            threshold=0.5,
            hazard_type='avalanche',
            acceptance_report=_accepted_report(),
        )

        self.assertEqual(result['decision'], 'promote')
        self.assertEqual(result['promotion_result']['promotion_mode'], 'rerun_segmentation')
        self.assertEqual(result['promotion_event']['id'], 'promotion-1')
        post_evaluate_release_mock.assert_called_once_with(
            worker_url='https://worker.modal.run',
            worker_token='worker-token',
            manifest={'reference_set_key': 'snowslide-heldout-v1', 'scenes': [{'scene_id': 'S1A_001'}]},
            request_type='authoritative_evaluate_release',
        )
        promote_from_report_mock.assert_called_once()
        promote_kwargs = promote_from_report_mock.call_args.kwargs
        self.assertEqual(promote_kwargs['scenes_manifest']['reference_set_key'], 'snowslide-heldout-v1')
        self.assertEqual(promote_kwargs['model_path'], Path('/tmp/model.ckpt'))
        self.assertEqual(promote_kwargs['acceptance_report']['decision'], 'accepted_research_grade')

    @patch('backend.scripts.run_authoritative_release_gate.record_promotion_event')
    @patch('backend.scripts.run_authoritative_release_gate.promote_from_report')
    @patch('backend.scripts.run_authoritative_release_gate.post_evaluate_release')
    @patch('backend.scripts.run_authoritative_release_gate.build_authoritative_manifest')
    @patch('backend.scripts.run_authoritative_release_gate.apply_authoritative_release_env')
    def test_run_authoritative_release_gate_prefers_local_model_path_override(
        self,
        apply_env_mock,
        build_manifest_mock,
        post_evaluate_release_mock,
        promote_from_report_mock,
        record_promotion_event_mock,
    ) -> None:
        apply_env_mock.return_value = {
            'modal_worker_url': 'https://worker.modal.run',
            'modal_worker_token': 'worker-token',
            'sar_unet_model_path': '/artifacts/models/swin_transformer_v2_tiny_coldstart_v1.pt',
            'sar_unet_model_version': 'swin_transformer_v2_tiny_coldstart_v1',
            'sar_unet_device': 'cpu',
        }
        build_manifest_mock.return_value = {'reference_set_key': 'snowslide-heldout-v1', 'scenes': [{'scene_id': 'S1A_001'}]}
        post_evaluate_release_mock.return_value = {
            'status': 'ok',
            'beats_baseline': True,
            'f1': 0.81,
            'baseline_f1_floor_used': 0.74,
        }
        promote_from_report_mock.return_value = {'status': 'ok', 'promotion_mode': 'rerun_segmentation'}
        record_promotion_event_mock.return_value = {'id': 'promotion-override'}

        result = run_authoritative_release_gate(
            env_file=Path('.env'),
            reference_set_key='snowslide-heldout-v1',
            prediction_model_version='swin_transformer_v2_tiny_coldstart_v1',
            artifact_root=Path('/tmp/artifacts'),
            device='cpu',
            threshold=0.5,
            hazard_type='avalanche',
            local_model_path=Path('/tmp/local-coldstart.pt'),
            acceptance_report=_accepted_report(),
        )

        self.assertEqual(result['decision'], 'promote')
        self.assertEqual(
            promote_from_report_mock.call_args.kwargs['model_path'],
            Path('/tmp/local-coldstart.pt').resolve(),
        )

    @patch('backend.scripts.run_authoritative_release_gate.record_promotion_event')
    @patch('backend.scripts.run_authoritative_release_gate.promote_from_report')
    @patch('backend.scripts.run_authoritative_release_gate.post_evaluate_release')
    @patch('backend.scripts.run_authoritative_release_gate.build_authoritative_manifest')
    @patch('backend.scripts.run_authoritative_release_gate.apply_authoritative_release_env')
    def test_run_authoritative_release_gate_rejects_baseline_pass_without_acceptance_report(
        self,
        apply_env_mock,
        build_manifest_mock,
        post_evaluate_release_mock,
        promote_from_report_mock,
        record_promotion_event_mock,
    ) -> None:
        apply_env_mock.return_value = {
            'modal_worker_url': 'https://worker.modal.run',
            'modal_worker_token': 'worker-token',
            'sar_unet_model_path': '/tmp/model.ckpt',
            'sar_unet_model_version': 'sar_unet_resnet34_shadow_v1',
            'sar_unet_device': 'cpu',
        }
        build_manifest_mock.return_value = {'reference_set_key': 'snowslide-heldout-v1', 'scenes': [{'scene_id': 'S1A_001'}]}
        post_evaluate_release_mock.return_value = {
            'status': 'ok',
            'beats_baseline': True,
            'f1': 0.81,
            'baseline_f1_floor_used': 0.74,
        }
        record_promotion_event_mock.return_value = {'id': 'promotion-reject'}

        result = run_authoritative_release_gate(
            env_file=Path('.env'),
            reference_set_key='snowslide-heldout-v1',
            prediction_model_version='sar_unet_resnet34_shadow_v1',
            artifact_root=Path('/tmp/artifacts'),
            device='cpu',
            threshold=0.5,
            hazard_type='avalanche',
        )

        self.assertEqual(result['decision'], 'reject')
        self.assertIn('acceptance report', result['decision_reason'])
        promote_from_report_mock.assert_not_called()

    @patch('backend.scripts.run_authoritative_release_gate.record_promotion_event')
    @patch('backend.scripts.run_authoritative_release_gate.promote_from_report')
    @patch('backend.scripts.run_authoritative_release_gate.post_evaluate_release')
    @patch('backend.scripts.run_authoritative_release_gate.build_authoritative_manifest')
    @patch('backend.scripts.run_authoritative_release_gate.apply_authoritative_release_env')
    def test_run_authoritative_release_gate_rejects_without_promotion_when_gate_fails(
        self,
        apply_env_mock,
        build_manifest_mock,
        post_evaluate_release_mock,
        promote_from_report_mock,
        record_promotion_event_mock,
    ) -> None:
        apply_env_mock.return_value = {
            'modal_worker_url': 'https://worker.modal.run',
            'modal_worker_token': 'worker-token',
            'sar_unet_model_path': '/tmp/model.ckpt',
            'sar_unet_model_version': 'sar_unet_resnet34_shadow_v1',
            'sar_unet_device': 'cpu',
        }
        build_manifest_mock.return_value = {'reference_set_key': 'snowslide-heldout-v1', 'scenes': [{'scene_id': 'S1A_001'}]}
        post_evaluate_release_mock.return_value = {
            'status': 'ok',
            'beats_baseline': False,
            'f1': 0.71,
            'baseline_f1_floor_used': 0.74,
        }
        record_promotion_event_mock.return_value = {'id': 'promotion-2'}

        result = run_authoritative_release_gate(
            env_file=Path('.env'),
            reference_set_key='snowslide-heldout-v1',
            prediction_model_version='sar_unet_resnet34_shadow_v1',
            artifact_root=Path('/tmp/artifacts'),
            device='cpu',
            threshold=0.5,
            hazard_type='avalanche',
        )

        self.assertEqual(result['decision'], 'reject')
        self.assertIsNone(result['promotion_result'])
        self.assertIn('did not beat baseline gate', result['decision_reason'])
        promote_from_report_mock.assert_not_called()
        record_promotion_event_mock.assert_called_once()

    @patch('backend.scripts.run_authoritative_release_gate.record_promotion_event')
    @patch('backend.scripts.run_authoritative_release_gate.promote_from_report')
    @patch('backend.scripts.run_authoritative_release_gate.post_evaluate_release')
    @patch('backend.scripts.run_authoritative_release_gate.build_authoritative_manifest')
    @patch('backend.scripts.run_authoritative_release_gate.apply_authoritative_release_env')
    def test_run_authoritative_release_gate_dry_run_writes_no_audit_row(
        self,
        apply_env_mock,
        build_manifest_mock,
        post_evaluate_release_mock,
        promote_from_report_mock,
        record_promotion_event_mock,
    ) -> None:
        apply_env_mock.return_value = {
            'modal_worker_url': 'https://worker.modal.run',
            'modal_worker_token': 'worker-token',
            'sar_unet_model_path': '/tmp/model.ckpt',
            'sar_unet_model_version': 'sar_unet_resnet34_shadow_v1',
            'sar_unet_device': 'cpu',
        }
        build_manifest_mock.return_value = {'reference_set_key': 'snowslide-heldout-v1', 'scenes': [{'scene_id': 'S1A_001'}]}
        post_evaluate_release_mock.return_value = {
            'status': 'ok',
            'beats_baseline': False,
            'f1': 0.71,
            'baseline_f1_floor_used': 0.74,
        }

        result = run_authoritative_release_gate(
            env_file=Path('.env'),
            reference_set_key='snowslide-heldout-v1',
            prediction_model_version='sar_unet_resnet34_shadow_v1',
            artifact_root=Path('/tmp/artifacts'),
            device='cpu',
            threshold=0.5,
            hazard_type='avalanche',
            dry_run=True,
        )

        self.assertEqual(result['decision'], 'reject')
        self.assertIsNone(result['promotion_event'])
        promote_from_report_mock.assert_not_called()
        record_promotion_event_mock.assert_not_called()

    @patch('backend.scripts.run_authoritative_release_gate.rest_insert')
    @patch('backend.scripts.run_authoritative_release_gate.has_supabase_credentials', return_value=True)
    def test_record_promotion_event_writes_audit_row(self, _has_credentials_mock, rest_insert_mock) -> None:
        rest_insert_mock.return_value = [{'id': 'promotion-3'}]

        row = record_promotion_event(
            decision='promote',
            decision_reason='gate passed',
            prediction_model_version='sar_unet_resnet34_shadow_v1',
            hazard_type='avalanche',
            report={'status': 'ok', 'beats_baseline': True, 'evaluation_run_id': 'run-1'},
        )

        self.assertEqual(row, {'id': 'promotion-3'})
        insert_kwargs = rest_insert_mock.call_args
        self.assertEqual(insert_kwargs.args[0], 'promotion_events')
        self.assertEqual(insert_kwargs.args[1][0]['decision'], 'promote')
        self.assertEqual(insert_kwargs.args[1][0]['new_version'], 'sar_unet_resnet34_shadow_v1')


if __name__ == '__main__':
    unittest.main()
