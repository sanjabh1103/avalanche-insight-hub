"""Tests for the Modal execution manifest contract and polling hardening.

Covers:
  - Manifest builder produces all required fields
  - GPU evidence collection (mocked)
  - Artifact digest computation (file and directory)
  - Secret redaction detection
  - Manifest validation (rejects non-terminal, allow_publish, official_warning)
  - Polling rejects accepted/pending body status even with HTTP 200
  - Negative tests for all Modal failure modes
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


class TestModalExecutionManifestBuilder(unittest.TestCase):
    """Test the manifest builder produces all required fields."""

    def test_build_execution_manifest_has_all_required_fields(self) -> None:
        from backend.common.modal_execution_manifest import build_execution_manifest

        manifest = build_execution_manifest(
            function_name='train_sar_unet_remote',
            call_id='call-123',
            terminal_status='ok',
            started_at=datetime.now(timezone.utc).isoformat(),
            gpu_configured='T4',
            shadow_mode=True,
            allow_publish=False,
        )
        required = [
            'manifest_version', 'app_name', 'function_name', 'call_id',
            'source_commit', 'input_manifest_hash', 'model_version',
            'shadow_mode', 'allow_publish', 'terminal_status',
            'started_at', 'completed_at', 'duration_seconds',
            'python_version', 'modal_sdk_version', 'image_identity',
            'volume_name', 'volume_committed', 'gpu_evidence',
            'artifacts', 'cost_estimate', 'cold_start_seconds',
            'secret_redaction_status', 'official_warning_eligible',
            'error_message',
        ]
        for field in required:
            self.assertIn(field, manifest, f'Missing required field: {field}')

    def test_manifest_defaults_to_shadow_mode(self) -> None:
        from backend.common.modal_execution_manifest import build_execution_manifest

        manifest = build_execution_manifest(
            function_name='test_fn',
            call_id='call-1',
            terminal_status='ok',
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.assertTrue(manifest['shadow_mode'])
        self.assertFalse(manifest['allow_publish'])
        self.assertFalse(manifest['official_warning_eligible'])

    def test_manifest_duration_is_positive(self) -> None:
        from backend.common.modal_execution_manifest import build_execution_manifest

        started = datetime.now(timezone.utc).isoformat()
        time.sleep(0.01)
        manifest = build_execution_manifest(
            function_name='test_fn',
            call_id='call-1',
            terminal_status='ok',
            started_at=started,
        )
        self.assertGreater(manifest['duration_seconds'], 0.0)


class TestGPUEvidence(unittest.TestCase):
    """Test GPU evidence collection."""

    def test_collect_gpu_evidence_without_torch(self) -> None:
        from backend.common.modal_execution_manifest import collect_gpu_evidence

        with patch.dict(sys.modules, {'torch': None}):
            evidence = collect_gpu_evidence('T4')
        self.assertEqual(evidence.gpu_configured, 'T4')
        # cuda_available should be False when torch is not available
        self.assertFalse(evidence.cuda_available)

    def test_collect_gpu_evidence_with_mocked_torch(self) -> None:
        from backend.common.modal_execution_manifest import collect_gpu_evidence

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 1
        mock_torch.cuda.get_device_name.return_value = 'Tesla T4'
        mock_torch.version.cuda = '12.1'

        with patch.dict(sys.modules, {'torch': mock_torch}):
            evidence = collect_gpu_evidence('T4')
        self.assertTrue(evidence.cuda_available)
        self.assertEqual(evidence.gpu_device_name, 'Tesla T4')
        self.assertEqual(evidence.cuda_version, '12.1')
        self.assertEqual(evidence.device_count, 1)

    def test_collect_gpu_evidence_no_gpu_configured(self) -> None:
        from backend.common.modal_execution_manifest import collect_gpu_evidence

        evidence = collect_gpu_evidence('')
        self.assertEqual(evidence.gpu_configured, '')


class TestArtifactDigest(unittest.TestCase):
    """Test artifact digest computation."""

    def test_compute_file_digest(self) -> None:
        from backend.common.modal_execution_manifest import compute_artifact_digest

        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as f:
            f.write(b'{"test": "data"}')
            f.flush()
            path = Path(f.name)
        try:
            digest = compute_artifact_digest(path)
            self.assertEqual(digest.sha256, hashlib.sha256(b'{"test": "data"}').hexdigest())
            self.assertFalse(digest.is_directory)
            self.assertGreater(digest.size_bytes, 0)
        finally:
            path.unlink()

    def test_compute_directory_digest(self) -> None:
        from backend.common.modal_execution_manifest import compute_artifact_digest

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir)
            (d / 'file1.txt').write_text('hello')
            (d / 'file2.txt').write_text('world')
            digest = compute_artifact_digest(d)
            self.assertTrue(digest.is_directory)
            self.assertEqual(digest.size_bytes, 10)  # 'hello' + 'world'

    def test_compute_digest_missing_file_raises(self) -> None:
        from backend.common.modal_execution_manifest import compute_artifact_digest

        with self.assertRaises(FileNotFoundError):
            compute_artifact_digest('/nonexistent/path/file.txt')


class TestSecretRedaction(unittest.TestCase):
    """Test secret redaction detection in manifests."""

    def test_redaction_passes_clean_payload(self) -> None:
        from backend.common.modal_execution_manifest import build_execution_manifest

        manifest = build_execution_manifest(
            function_name='test_fn',
            call_id='call-1',
            terminal_status='ok',
            started_at=datetime.now(timezone.utc).isoformat(),
            extra_payload={'status': 'ok', 'model_version': 'v1'},
        )
        self.assertTrue(manifest['secret_redaction_status'].startswith('passed'))

    def test_redaction_fails_on_modal_token_pattern(self) -> None:
        from backend.common.modal_execution_manifest import build_execution_manifest

        manifest = build_execution_manifest(
            function_name='test_fn',
            call_id='call-1',
            terminal_status='ok',
            started_at=datetime.now(timezone.utc).isoformat(),
            extra_payload={'some_field': 'mod-abcdefghijklmnopqrst1234567890'},
        )
        self.assertTrue(manifest['secret_redaction_status'].startswith('failed'))

    def test_redaction_fails_on_sensitive_key(self) -> None:
        from backend.common.modal_execution_manifest import build_execution_manifest

        manifest = build_execution_manifest(
            function_name='test_fn',
            call_id='call-1',
            terminal_status='ok',
            started_at=datetime.now(timezone.utc).isoformat(),
            extra_payload={'api_key': 'some-value'},
        )
        self.assertTrue(manifest['secret_redaction_status'].startswith('failed'))


class TestManifestValidation(unittest.TestCase):
    """Test the manifest validator."""

    def test_validate_minimal_manifest_fails_closed(self) -> None:
        from backend.common.modal_execution_manifest import build_execution_manifest, validate_manifest

        manifest = build_execution_manifest(
            function_name='test_fn',
            call_id='call-1',
            terminal_status='ok',
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        violations = validate_manifest(manifest)
        self.assertTrue(violations)
        self.assertTrue(any('run_id' in violation for violation in violations))

    def test_validate_rejects_non_terminal_status(self) -> None:
        from backend.common.modal_execution_manifest import validate_manifest

        manifest = {
            'manifest_version': '1.0',
            'app_name': 'test',
            'function_name': 'fn',
            'call_id': 'call-1',
            'source_commit': 'abc',
            'terminal_status': 'accepted',
            'started_at': '2026-01-01T00:00:00+00:00',
            'completed_at': '2026-01-01T00:01:00+00:00',
            'python_version': '3.12',
            'modal_sdk_version': '0.73.83',
            'shadow_mode': True,
            'allow_publish': False,
            'gpu_evidence': {},
            'secret_redaction_status': 'passed',
            'official_warning_eligible': False,
        }
        violations = validate_manifest(manifest)
        self.assertTrue(any('non-terminal' in v for v in violations))

    def test_validate_rejects_allow_publish_true(self) -> None:
        from backend.common.modal_execution_manifest import validate_manifest

        manifest = {
            'manifest_version': '1.0',
            'app_name': 'test',
            'function_name': 'fn',
            'call_id': 'call-1',
            'source_commit': 'abc',
            'terminal_status': 'ok',
            'started_at': '2026-01-01T00:00:00+00:00',
            'completed_at': '2026-01-01T00:01:00+00:00',
            'python_version': '3.12',
            'modal_sdk_version': '0.73.83',
            'shadow_mode': True,
            'allow_publish': True,
            'gpu_evidence': {},
            'secret_redaction_status': 'passed',
            'official_warning_eligible': False,
        }
        violations = validate_manifest(manifest)
        self.assertTrue(any('allow_publish' in v for v in violations))

    def test_validate_rejects_official_warning_eligible_true(self) -> None:
        from backend.common.modal_execution_manifest import validate_manifest

        manifest = {
            'manifest_version': '1.0',
            'app_name': 'test',
            'function_name': 'fn',
            'call_id': 'call-1',
            'source_commit': 'abc',
            'terminal_status': 'ok',
            'started_at': '2026-01-01T00:00:00+00:00',
            'completed_at': '2026-01-01T00:01:00+00:00',
            'python_version': '3.12',
            'modal_sdk_version': '0.73.83',
            'shadow_mode': True,
            'allow_publish': False,
            'gpu_evidence': {},
            'secret_redaction_status': 'passed',
            'official_warning_eligible': True,
        }
        violations = validate_manifest(manifest)
        self.assertTrue(any('official_warning_eligible' in v for v in violations))

    def test_validate_rejects_gpu_configured_without_cuda(self) -> None:
        from backend.common.modal_execution_manifest import validate_manifest

        manifest = {
            'manifest_version': '1.0',
            'app_name': 'test',
            'function_name': 'fn',
            'call_id': 'call-1',
            'source_commit': 'abc',
            'terminal_status': 'ok',
            'started_at': '2026-01-01T00:00:00+00:00',
            'completed_at': '2026-01-01T00:01:00+00:00',
            'python_version': '3.12',
            'modal_sdk_version': '0.73.83',
            'shadow_mode': True,
            'allow_publish': False,
            'gpu_evidence': {'gpu_configured': 'T4', 'cuda_available': False},
            'secret_redaction_status': 'passed',
            'official_warning_eligible': False,
        }
        violations = validate_manifest(manifest)
        self.assertTrue(any('cuda_available' in v for v in violations))

    def test_validate_rejects_bad_artifact_hash(self) -> None:
        from backend.common.modal_execution_manifest import validate_manifest

        manifest = {
            'manifest_version': '1.0',
            'app_name': 'test',
            'function_name': 'fn',
            'call_id': 'call-1',
            'source_commit': 'abc',
            'terminal_status': 'ok',
            'started_at': '2026-01-01T00:00:00+00:00',
            'completed_at': '2026-01-01T00:01:00+00:00',
            'python_version': '3.12',
            'modal_sdk_version': '0.73.83',
            'shadow_mode': True,
            'allow_publish': False,
            'gpu_evidence': {},
            'secret_redaction_status': 'passed',
            'official_warning_eligible': False,
            'artifacts': [{'path': '/tmp/file.txt', 'sha256': 'bad-hash', 'size_bytes': 10}],
        }
        violations = validate_manifest(manifest)
        self.assertTrue(any('sha256' in v for v in violations))


class TestStatusHelpers(unittest.TestCase):
    """Test the status helper functions."""

    def test_is_terminal_success(self) -> None:
        from backend.common.modal_execution_manifest import is_terminal_success
        self.assertTrue(is_terminal_success('ok'))
        self.assertTrue(is_terminal_success('completed_with_validation_gate_failure'))
        self.assertFalse(is_terminal_success('accepted'))
        self.assertFalse(is_terminal_success('pending'))
        self.assertFalse(is_terminal_success('error'))

    def test_is_non_terminal(self) -> None:
        from backend.common.modal_execution_manifest import is_non_terminal
        self.assertTrue(is_non_terminal('accepted'))
        self.assertTrue(is_non_terminal('pending'))
        self.assertTrue(is_non_terminal('running'))
        self.assertFalse(is_non_terminal('ok'))
        self.assertFalse(is_non_terminal('error'))


class TestPollingRejectsAcceptedAsTerminal(unittest.TestCase):
    """Test that _poll_until_terminal rejects accepted/pending body status."""

    def test_poll_rejects_accepted_body_with_http_200(self) -> None:
        """Even with HTTP 200, an accepted body status should continue polling."""
        from backend.scripts.trigger_and_poll_training import _poll_until_terminal

        call_count = [0]

        def mock_poller(**kwargs: Any) -> tuple[int, dict[str, Any]]:
            call_count[0] += 1
            if call_count[0] == 1:
                return 200, {'status': 'accepted', 'call_id': 'test-call'}
            return 200, {'status': 'ok', 'call_id': 'test-call', 'result': 'done'}

        result = _poll_until_terminal(
            job_name='test-job',
            poller=mock_poller,
            worker_url='',
            worker_token='',
            call_id='test-call',
            poll_interval_seconds=0,
            timeout_seconds=10,
        )
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(call_count[0], 2)

    def test_poll_rejects_pending_body_with_http_200(self) -> None:
        """Even with HTTP 200, a pending body status should continue polling."""
        from backend.scripts.trigger_and_poll_training import _poll_until_terminal

        call_count = [0]

        def mock_poller(**kwargs: Any) -> tuple[int, dict[str, Any]]:
            call_count[0] += 1
            if call_count[0] <= 2:
                return 200, {'status': 'pending', 'call_id': 'test-call'}
            return 200, {'status': 'ok', 'call_id': 'test-call'}

        result = _poll_until_terminal(
            job_name='test-job',
            poller=mock_poller,
            worker_url='',
            worker_token='',
            call_id='test-call',
            poll_interval_seconds=0,
            timeout_seconds=10,
        )
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(call_count[0], 3)

    def test_poll_rejects_running_body_with_http_200(self) -> None:
        """Even with HTTP 200, a running body status should continue polling."""
        from backend.scripts.trigger_and_poll_training import _poll_until_terminal

        call_count = [0]

        def mock_poller(**kwargs: Any) -> tuple[int, dict[str, Any]]:
            call_count[0] += 1
            if call_count[0] == 1:
                return 200, {'status': 'running', 'call_id': 'test-call'}
            return 200, {'status': 'ok', 'call_id': 'test-call'}

        result = _poll_until_terminal(
            job_name='test-job',
            poller=mock_poller,
            worker_url='',
            worker_token='',
            call_id='test-call',
            poll_interval_seconds=0,
            timeout_seconds=10,
        )
        self.assertEqual(result['status'], 'ok')

    def test_poll_202_still_works(self) -> None:
        """HTTP 202 should still be treated as pending."""
        from backend.scripts.trigger_and_poll_training import _poll_until_terminal

        call_count = [0]

        def mock_poller(**kwargs: Any) -> tuple[int, dict[str, Any]]:
            call_count[0] += 1
            if call_count[0] == 1:
                return 202, {'status': 'pending', 'call_id': 'test-call'}
            return 200, {'status': 'ok', 'call_id': 'test-call'}

        result = _poll_until_terminal(
            job_name='test-job',
            poller=mock_poller,
            worker_url='',
            worker_token='',
            call_id='test-call',
            poll_interval_seconds=0,
            timeout_seconds=10,
        )
        self.assertEqual(result['status'], 'ok')


class TestSARPollingRejectsAcceptedAsTerminal(unittest.TestCase):
    """Test that SAR training _poll_until_terminal rejects accepted/pending."""

    def test_sar_poll_rejects_accepted_body_with_http_200(self) -> None:
        from backend.scripts.trigger_and_poll_sar_training import _poll_until_terminal

        call_count = [0]

        def mock_poller(**kwargs: Any) -> tuple[int, dict[str, Any]]:
            call_count[0] += 1
            if call_count[0] == 1:
                return 200, {'status': 'accepted', 'call_id': 'test-call'}
            return 200, {'status': 'ok', 'call_id': 'test-call'}

        result = _poll_until_terminal(
            poller=mock_poller,
            worker_url='',
            worker_token='',
            call_id='test-call',
            poll_interval_seconds=0,
            timeout_seconds=10,
        )
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(call_count[0], 2)


class TestModalImagePinConsistency(unittest.TestCase):
    """Test that the Modal image pins are consistent and not lower-bounds."""

    def test_modal_sdk_is_exact_pin_not_lower_bound(self) -> None:
        from backend.modal_worker_app import MODAL_PINNED_MODAL_SDK
        self.assertIn('==', MODAL_PINNED_MODAL_SDK)
        self.assertNotIn('>=', MODAL_PINNED_MODAL_SDK)

    def test_modal_python_version_is_312(self) -> None:
        from backend.modal_worker_app import MODAL_IMAGE_PYTHON_VERSION
        self.assertEqual(MODAL_IMAGE_PYTHON_VERSION, '3.12')

    def test_torch_is_pinned(self) -> None:
        from backend.modal_worker_app import MODAL_PINNED_TORCH
        self.assertIn('==', MODAL_PINNED_TORCH)

    def test_torchvision_is_pinned(self) -> None:
        from backend.modal_worker_app import MODAL_PINNED_TORCHVISION
        self.assertIn('==', MODAL_PINNED_TORCHVISION)

    def test_fastapi_is_pinned(self) -> None:
        from backend.modal_worker_app import MODAL_PINNED_FASTAPI
        self.assertIn('==', MODAL_PINNED_FASTAPI)

    def test_pyarrow_is_pinned(self) -> None:
        from backend.modal_worker_app import MODAL_PINNED_PYARROW
        self.assertIn('==', MODAL_PINNED_PYARROW)

    def test_function_runtime_manifest_has_all_functions(self) -> None:
        from backend.modal_worker_app import (
            MODAL_FUNCTION_RUNTIME_MANIFEST,
            MODAL_REMOTE_EVALUATE_RELEASE_FUNCTION,
            MODAL_REMOTE_EVALUATE_SAR_CHECKPOINT_FUNCTION,
            MODAL_REMOTE_INFER_FUNCTION,
            MODAL_REMOTE_SEGMENT_FUNCTION,
            MODAL_REMOTE_TRAIN_FUNCTION,
            MODAL_REMOTE_TRAIN_SAR_FUNCTION,
        )
        expected = {
            MODAL_REMOTE_SEGMENT_FUNCTION,
            MODAL_REMOTE_TRAIN_SAR_FUNCTION,
            MODAL_REMOTE_EVALUATE_SAR_CHECKPOINT_FUNCTION,
            MODAL_REMOTE_EVALUATE_RELEASE_FUNCTION,
            MODAL_REMOTE_TRAIN_FUNCTION,
            MODAL_REMOTE_INFER_FUNCTION,
        }
        self.assertEqual(set(MODAL_FUNCTION_RUNTIME_MANIFEST.keys()), expected)

    def test_gpu_functions_have_gpu_type(self) -> None:
        from backend.modal_worker_app import MODAL_FUNCTION_RUNTIME_MANIFEST
        for name, manifest in MODAL_FUNCTION_RUNTIME_MANIFEST.items():
            if manifest['device'] == 'gpu':
                self.assertIn('gpu_type', manifest, f'GPU function {name} missing gpu_type')
                self.assertTrue(manifest['gpu_type'], f'GPU function {name} has empty gpu_type')

    def test_cpu_functions_have_cpu_allocation(self) -> None:
        from backend.modal_worker_app import MODAL_FUNCTION_RUNTIME_MANIFEST
        for name, manifest in MODAL_FUNCTION_RUNTIME_MANIFEST.items():
            if manifest['device'] == 'cpu':
                self.assertIn('cpu', manifest, f'CPU function {name} missing cpu allocation')
                self.assertGreater(manifest['cpu'], 0, f'CPU function {name} has zero cpu')


class TestCIRequirementsPin(unittest.TestCase):
    """Test that CI requirements pin modal to the same version as the worker."""

    def test_ci_requirements_pin_modal_073_82(self) -> None:
        req_path = Path(__file__).parent.parent / 'requirements-ci.txt'
        content = req_path.read_text()
        self.assertIn('modal==0.73.83', content)
        self.assertNotIn('modal==0.62.25', content)
        self.assertNotIn('modal>=', content)


class TestExecutionManifestAttachment(unittest.TestCase):
    """Test that _attach_execution_manifest correctly wraps results."""

    def test_attach_manifest_to_ok_result(self) -> None:
        from backend.modal_worker_app import _attach_execution_manifest

        result = {'status': 'ok', 'model_version': 'v1', 'shadow_mode': True}
        attached = _attach_execution_manifest(
            result,
            function_name='test_fn',
            call_id='call-1',
            started_at=datetime.now(timezone.utc).isoformat(),
            gpu_configured='T4',
        )
        self.assertIn('execution_manifest', attached)
        manifest = attached['execution_manifest']
        self.assertEqual(manifest['function_name'], 'test_fn')
        self.assertEqual(manifest['call_id'], 'call-1')
        self.assertEqual(manifest['terminal_status'], 'ok')
        self.assertTrue(manifest['shadow_mode'])
        self.assertFalse(manifest['allow_publish'])
        self.assertFalse(manifest['official_warning_eligible'])

    def test_attach_manifest_preserves_original_fields(self) -> None:
        from backend.modal_worker_app import _attach_execution_manifest

        result = {'status': 'ok', 'model_version': 'v1', 'custom_field': 'value'}
        attached = _attach_execution_manifest(
            result,
            function_name='test_fn',
            call_id='call-1',
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self.assertEqual(attached['custom_field'], 'value')
        self.assertEqual(attached['model_version'], 'v1')

    def test_attach_manifest_with_error_status(self) -> None:
        from backend.modal_worker_app import _attach_execution_manifest

        result = {'status': 'error', 'error': 'GPU not available', 'shadow_mode': True}
        attached = _attach_execution_manifest(
            result,
            function_name='test_fn',
            call_id='call-1',
            started_at=datetime.now(timezone.utc).isoformat(),
            gpu_configured='T4',
        )
        manifest = attached['execution_manifest']
        self.assertEqual(manifest['terminal_status'], 'error')
        self.assertEqual(manifest['error_message'], 'GPU not available')


if __name__ == '__main__':
    unittest.main()
