from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('AVALANCHE_SKIP_MODAL_IMPORT', '1')

def _valid_test_manifest(
    *,
    run_id: str = 'run-test-001',
    compute_job_id: str = 'compute-test-001',
    call_id: str = 'test-call',
) -> dict[str, object]:
    from backend.common.modal_execution_manifest import build_execution_manifest

    return build_execution_manifest(
        function_name='test_remote_function',
        call_id=call_id,
        terminal_status='ok',
        started_at='2026-08-09T10:00:00+00:00',
        run_id=run_id,
        compute_job_id=compute_job_id,
        input_manifest_id='input-test-001',
        input_manifest_hash='a' * 64,
        source_commit='b' * 40,
        model_version='test-model-v1',
        artifact_root=tempfile.gettempdir(),
        volume_committed=True,
        python_version='3.12.12',
        modal_sdk_version='0.73.83',
        torch_version='2.5.1+cu121',
        torchvision_version='0.20.1+cu121',
        torchaudio_version='2.5.1+cu121',
        cuda_version='12.1',
        image_identity='modal-image:sha256:' + 'c' * 64,
        image_archive_sha256='d' * 64,
    )


from backend.modal_worker_app import (
    MODAL_PINNED_RUNTIME_PACKAGES,
    _request_model_path,
    _require_volume_path,
    authorize_bearer_request,
    dispatch_modal_route,
    handle_evaluate_release,
    handle_infer_mtslstm,
    handle_sar_segment,
    handle_train_sar_unet,
    handle_train_mtslstm,
    normalize_model_volume_path,
    poll_infer_mtslstm_job,
    poll_infer_mtslstm_job_async,
    poll_train_sar_unet_job,
    poll_train_sar_unet_job_async,
    poll_train_mtslstm_job,
    poll_train_mtslstm_job_async,
    run_remote_evaluate_release,
    run_remote_evaluate_sar_checkpoint,
    run_remote_sar_segment,
    run_remote_train_sar_unet,
    run_remote_infer_mtslstm,
    run_remote_train_mtslstm,
    seed_dem_directory,
    seed_model_volume_file,
    submit_infer_mtslstm_job,
    submit_infer_mtslstm_job_async,
    submit_train_sar_unet_job,
    submit_train_sar_unet_job_async,
    submit_train_mtslstm_job,
    submit_train_mtslstm_job_async,
    create_fastapi_app,
)


class ModalWorkerAppTests(unittest.TestCase):
    def test_health_route_reports_gpu_function_names(self) -> None:
        # G9: fastapi is an optional dependency — skip if not installed
        try:
            import fastapi  # noqa: F401
        except ImportError:
            self.skipTest('fastapi not installed')
        app = create_fastapi_app()
        routes = {route.path for route in app.routes}

        self.assertIn('/health', routes)
        health_route = next(route for route in app.routes if route.path == '/health')
        body = asyncio.run(health_route.endpoint())

        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['runtime_provider'], 'modal')
        self.assertIn('sar_segment_remote', body['gpu_functions'])
        self.assertIn('train_sar_unet_remote', body['gpu_functions'])
        self.assertIn('evaluate_sar_checkpoint_remote', body['gpu_functions'])
        self.assertIn('train_mts_lstm_remote', body['gpu_functions'])
        self.assertIn('/train-mtslstm', body['routes'])

    def test_modal_pinned_runtime_packages_match_requirements(self) -> None:
        self.assertEqual(
            MODAL_PINNED_RUNTIME_PACKAGES,
            ('shap==0.51.0', 'scikit-learn==1.9.0'),
        )
        requirements = (Path(__file__).resolve().parents[1] / 'requirements.txt').read_text(encoding='utf-8').splitlines()
        for package in MODAL_PINNED_RUNTIME_PACKAGES:
            self.assertIn(package, requirements)

    @patch('backend.modal_worker_app._dispatch_worker_request', return_value={'status': 'ok'})
    def test_handle_sar_segment_forwards_payload(self, dispatch_mock) -> None:
        payload = {'hazard_type': 'avalanche', 'scenes': [{'scene_id': 'S1A_001'}]}
        result = handle_sar_segment(payload)

        self.assertEqual(result['status'], 'ok')
        dispatch_mock.assert_called_once_with('sar-segment', payload)

    @patch('backend.modal_worker_app._dispatch_worker_request', return_value={'status': 'ok'})
    def test_handle_train_mtslstm_forwards_payload(self, dispatch_mock) -> None:
        payload = {'hazard_type': 'avalanche', 'dataset_snapshot_id': 'latest'}
        handle_train_mtslstm(payload)
        dispatch_mock.assert_called_once_with('train-mtslstm', payload)

    @patch('backend.modal_worker_app._dispatch_worker_request', return_value={'status': 'accepted'})
    def test_handle_train_sar_unet_forwards_payload(self, dispatch_mock) -> None:
        payload = {'training_manifest_path': 'sar-data/train.json', 'candidate_model_version': 'shadow-v2'}
        handle_train_sar_unet(payload)
        dispatch_mock.assert_called_once_with('train-sar-unet', payload)

    @patch('backend.modal_worker_app._dispatch_worker_request', return_value={'status': 'ok'})
    def test_handle_infer_mtslstm_forwards_payload(self, dispatch_mock) -> None:
        payload = {'hazard_type': 'avalanche', 'forecast_hours': 72}
        handle_infer_mtslstm(payload)
        dispatch_mock.assert_called_once_with('infer-mtslstm', payload)

    @patch('backend.modal_worker_app._dispatch_worker_request', return_value={'status': 'ok'})
    def test_handle_evaluate_release_forwards_payload(self, dispatch_mock) -> None:
        payload = {'hazard_type': 'avalanche', 'scenes': [{'scene_id': 'S1A_001'}]}
        handle_evaluate_release(payload)
        dispatch_mock.assert_called_once_with('evaluate-release', payload)

    @patch('backend.modal_worker_app.run_worker_request', return_value={'status': 'ok', 'beats_baseline': False})
    def test_run_remote_evaluate_release_forces_dry_run(self, worker_mock) -> None:
        reload_mock = Mock()
        commit_mock = Mock()
        with TemporaryDirectory() as tmpdir:
            result = run_remote_evaluate_release(
                {'reference_set_key': 'snowslide-heldout-v1', 'dry_run': False},
                artifact_root=Path(tmpdir),
                volume_reload=reload_mock,
                volume_commit=commit_mock,
            )

        self.assertEqual(result['status'], 'ok')
        reload_mock.assert_called_once()
        commit_mock.assert_called_once()
        call_args = worker_mock.call_args
        self.assertEqual(call_args.args[0], 'evaluate-release')
        self.assertTrue(call_args.args[1]['dry_run'])
        self.assertTrue(call_args.kwargs['dry_run'])

    def test_request_model_path_requires_artifact_volume_path(self) -> None:
        self.assertEqual(_request_model_path({'model_path': '/artifacts/20260516T164730Z/sar_model.pt'}), Path('/artifacts/20260516T164730Z/sar_model.pt'))
        with self.assertRaisesRegex(ValueError, 'under /artifacts'):
            _request_model_path({'model_path': '/tmp/sar_model.pt'})

    def test_require_volume_path_rejects_non_artifact_path(self) -> None:
        self.assertEqual(
            _require_volume_path({'checkpoint_path': '/artifacts/run/sar_model.pt'}, ('checkpoint_path',)),
            Path('/artifacts/run/sar_model.pt'),
        )
        with self.assertRaisesRegex(ValueError, 'under /artifacts'):
            _require_volume_path({'checkpoint_path': '/tmp/sar_model.pt'}, ('checkpoint_path',))

    @patch.dict('os.environ', {'MODAL_WORKER_TOKEN': 'secret-token'}, clear=False)
    def test_authorize_bearer_request_rejects_missing_token(self) -> None:
        with self.assertRaisesRegex(PermissionError, 'missing or invalid'):
            authorize_bearer_request(None)

    @patch.dict('os.environ', {'MODAL_WORKER_TOKEN': 'secret-token'}, clear=False)
    @patch('backend.modal_worker_app.submit_train_mtslstm_job', return_value={'status': 'accepted', 'call_id': 'fc-test'})
    def test_dispatch_modal_route_enforces_bearer_auth(self, handle_mock) -> None:
        status_code, body = dispatch_modal_route(
            '/train-mtslstm',
            {'dataset_snapshot_id': 'latest'},
            authorization_header='Bearer wrong-token',
        )

        self.assertEqual(status_code, 401)
        self.assertEqual(body['status'], 'unauthorized')
        handle_mock.assert_not_called()

    @patch.dict('os.environ', {'MODAL_WORKER_TOKEN': 'secret-token'}, clear=False)
    @patch('backend.modal_worker_app.submit_train_mtslstm_job', return_value={'status': 'accepted', 'call_id': 'fc-test'})
    def test_dispatch_modal_route_forwards_valid_request(self, handle_mock) -> None:
        payload = {'dataset_snapshot_id': 'latest'}
        status_code, body = dispatch_modal_route(
            '/train-mtslstm',
            payload,
            authorization_header='Bearer secret-token',
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(body['status'], 'accepted')
        handle_mock.assert_called_once_with(payload)

    def test_submit_train_mtslstm_job_returns_call_id(self) -> None:
        class _FakeCall:
            object_id = 'fc-123'

        class _FakeSpawn:
            def __init__(self) -> None:
                self.payload = None

            def __call__(self, payload):
                self.payload = payload
                return _FakeCall()

            async def aio(self, payload):
                return self(payload)

        class _FakeFunction:
            def __init__(self) -> None:
                self.spawn = _FakeSpawn()

        fake_function = _FakeFunction()
        fake_modal = SimpleNamespace(
            Function=SimpleNamespace(
                from_name=lambda app_name, fn_name: fake_function,
            ),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            result = submit_train_mtslstm_job({'dataset_snapshot_id': 'latest'})

        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['call_id'], 'fc-123')
        self.assertEqual(fake_function.spawn.payload, {'dataset_snapshot_id': 'latest'})

    def test_submit_train_sar_unet_job_returns_call_id(self) -> None:
        class _FakeCall:
            object_id = 'fc-sar-123'

        class _FakeSpawn:
            def __init__(self) -> None:
                self.payload = None

            def __call__(self, payload):
                self.payload = payload
                return _FakeCall()

            async def aio(self, payload):
                return self(payload)

        class _FakeFunction:
            def __init__(self) -> None:
                self.spawn = _FakeSpawn()

        fake_function = _FakeFunction()
        fake_modal = SimpleNamespace(
            Function=SimpleNamespace(
                from_name=lambda app_name, fn_name: fake_function,
            ),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            result = submit_train_sar_unet_job({'training_manifest_path': 'sar-data/train.json'})

        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['call_id'], 'fc-sar-123')
        self.assertEqual(fake_function.spawn.payload, {'training_manifest_path': 'sar-data/train.json'})

    def test_submit_train_sar_unet_job_async_returns_call_id(self) -> None:
        class _FakeCall:
            object_id = 'fc-sar-123'

        class _FakeSpawn:
            def __init__(self) -> None:
                self.payload = None

            def __call__(self, payload):
                self.payload = payload
                return _FakeCall()

            async def aio(self, payload):
                return self(payload)

        class _FakeFunction:
            def __init__(self) -> None:
                self.spawn = _FakeSpawn()

        fake_function = _FakeFunction()
        fake_modal = SimpleNamespace(
            Function=SimpleNamespace(
                from_name=lambda app_name, fn_name: fake_function,
            ),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            result = asyncio.run(submit_train_sar_unet_job_async({'training_manifest_path': 'sar-data/train.json'}))

        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['call_id'], 'fc-sar-123')
        self.assertEqual(fake_function.spawn.payload, {'training_manifest_path': 'sar-data/train.json'})

    def test_submit_train_mtslstm_job_async_returns_call_id(self) -> None:
        class _FakeCall:
            object_id = 'fc-123'

        class _FakeSpawn:
            def __init__(self) -> None:
                self.payload = None

            def __call__(self, payload):
                self.payload = payload
                return _FakeCall()

            async def aio(self, payload):
                return self(payload)

        class _FakeFunction:
            def __init__(self) -> None:
                self.spawn = _FakeSpawn()

        fake_function = _FakeFunction()
        fake_modal = SimpleNamespace(
            Function=SimpleNamespace(
                from_name=lambda app_name, fn_name: fake_function,
            ),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            result = asyncio.run(submit_train_mtslstm_job_async({'dataset_snapshot_id': 'latest'}))

        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['call_id'], 'fc-123')
        self.assertEqual(fake_function.spawn.payload, {'dataset_snapshot_id': 'latest'})

    def test_poll_train_mtslstm_job_returns_pending_on_timeout(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                raise TimeoutError()

            async def aio(self, timeout: int = 0):
                raise TimeoutError()

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = poll_train_mtslstm_job('fc-123')

        self.assertEqual(status_code, 202)
        self.assertEqual(body['status'], 'pending')

    def test_poll_train_sar_unet_job_returns_pending_on_timeout(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                raise TimeoutError()

            async def aio(self, timeout: int = 0):
                raise TimeoutError()

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = poll_train_sar_unet_job('fc-sar-123')

        self.assertEqual(status_code, 202)
        self.assertEqual(body['status'], 'pending')

    def test_poll_train_sar_unet_job_async_returns_pending_on_timeout(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                raise TimeoutError()

            async def aio(self, timeout: int = 0):
                raise TimeoutError()

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = asyncio.run(poll_train_sar_unet_job_async('fc-sar-123'))

        self.assertEqual(status_code, 202)
        self.assertEqual(body['status'], 'pending')

    def test_poll_train_mtslstm_job_async_returns_pending_on_timeout(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                raise TimeoutError()

            async def aio(self, timeout: int = 0):
                raise TimeoutError()

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = asyncio.run(poll_train_mtslstm_job_async('fc-123'))

        self.assertEqual(status_code, 202)
        self.assertEqual(body['status'], 'pending')

    def test_poll_train_mtslstm_job_returns_result_when_complete(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                return {'status': 'ok', 'artifact_dir': '/artifacts/20260427T000000Z', 'execution_manifest': _valid_test_manifest(call_id='fc-123')}

            async def aio(self, timeout: int = 0):
                return self(timeout)

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = poll_train_mtslstm_job('fc-123')

        self.assertEqual(status_code, 200)
        self.assertEqual(body['status'], 'ok')

    def test_poll_train_mtslstm_job_async_returns_result_when_complete(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                return {'status': 'ok', 'artifact_dir': '/artifacts/20260427T000000Z', 'execution_manifest': _valid_test_manifest(call_id='fc-123')}

            async def aio(self, timeout: int = 0):
                return self(timeout)

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = asyncio.run(poll_train_mtslstm_job_async('fc-123'))

        self.assertEqual(status_code, 200)
        self.assertEqual(body['status'], 'ok')

    def test_poll_train_sar_unet_job_returns_result_when_complete(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                return {'status': 'ok', 'candidate_model_version': 'shadow-v2', 'execution_manifest': _valid_test_manifest(call_id='fc-sar-123')}

            async def aio(self, timeout: int = 0):
                return self(timeout)

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = poll_train_sar_unet_job('fc-sar-123')

        self.assertEqual(status_code, 200)
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['candidate_model_version'], 'shadow-v2')

    def test_poll_train_sar_unet_job_async_returns_result_when_complete(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                return {'status': 'ok', 'candidate_model_version': 'shadow-v2', 'execution_manifest': _valid_test_manifest(call_id='fc-sar-123')}

            async def aio(self, timeout: int = 0):
                return self(timeout)

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = asyncio.run(poll_train_sar_unet_job_async('fc-sar-123'))

        self.assertEqual(status_code, 200)
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['candidate_model_version'], 'shadow-v2')

    def test_submit_infer_mtslstm_job_returns_call_id(self) -> None:
        class _FakeCall:
            object_id = 'fc-456'

        class _FakeSpawn:
            def __init__(self) -> None:
                self.payload = None

            def __call__(self, payload):
                self.payload = payload
                return _FakeCall()

            async def aio(self, payload):
                return self(payload)

        class _FakeFunction:
            def __init__(self) -> None:
                self.spawn = _FakeSpawn()

        fake_function = _FakeFunction()
        fake_modal = SimpleNamespace(
            Function=SimpleNamespace(
                from_name=lambda app_name, fn_name: fake_function,
            ),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            result = submit_infer_mtslstm_job({
                'forecast_hours': 72,
                'dry_run': True,
                'compute_job_id': 'job-123',
                'artifact_dir': '/artifacts/20260427T000000Z',
            })

        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['call_id'], 'fc-456')
        self.assertEqual(result['modal_call_id'], 'fc-456')
        self.assertEqual(result['compute_job_id'], 'job-123')
        self.assertEqual(result['artifact_dir'], '/artifacts/20260427T000000Z')
        self.assertEqual(
            fake_function.spawn.payload,
            {
                'forecast_hours': 72,
                'dry_run': True,
                'compute_job_id': 'job-123',
                'artifact_dir': '/artifacts/20260427T000000Z',
            },
        )

    def test_submit_infer_mtslstm_job_async_returns_call_id(self) -> None:
        class _FakeCall:
            object_id = 'fc-456'

        class _FakeSpawn:
            def __init__(self) -> None:
                self.payload = None

            def __call__(self, payload):
                self.payload = payload
                return _FakeCall()

            async def aio(self, payload):
                return self(payload)

        class _FakeFunction:
            def __init__(self) -> None:
                self.spawn = _FakeSpawn()

        fake_function = _FakeFunction()
        fake_modal = SimpleNamespace(
            Function=SimpleNamespace(
                from_name=lambda app_name, fn_name: fake_function,
            ),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            result = asyncio.run(submit_infer_mtslstm_job_async({'forecast_hours': 72, 'dry_run': True}))

        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['call_id'], 'fc-456')
        self.assertEqual(fake_function.spawn.payload, {'forecast_hours': 72, 'dry_run': True})

    def test_poll_infer_mtslstm_job_returns_pending_on_timeout(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                raise TimeoutError()

            async def aio(self, timeout: int = 0):
                raise TimeoutError()

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = poll_infer_mtslstm_job('fc-456')

        self.assertEqual(status_code, 202)
        self.assertEqual(body['status'], 'pending')

    def test_poll_infer_mtslstm_job_async_returns_pending_on_timeout(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                raise TimeoutError()

            async def aio(self, timeout: int = 0):
                raise TimeoutError()

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = asyncio.run(poll_infer_mtslstm_job_async('fc-456'))

        self.assertEqual(status_code, 202)
        self.assertEqual(body['status'], 'pending')

    def test_poll_infer_mtslstm_job_async_returns_pending_on_deadline_exceeded_connection_error(self) -> None:
        class _FakeConnectionError(Exception):
            pass

        class _FakeGet:
            def __call__(self, timeout: int = 0):
                raise _FakeConnectionError('Deadline exceeded')

            async def aio(self, timeout: int = 0):
                raise _FakeConnectionError('Deadline exceeded')

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(
                OutputExpiredError=RuntimeError,
                ConnectionError=_FakeConnectionError,
            ),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = asyncio.run(poll_infer_mtslstm_job_async('fc-456'))

        self.assertEqual(status_code, 202)
        self.assertEqual(body['status'], 'pending')

    def test_poll_infer_mtslstm_job_returns_cancelled_on_remote_error(self) -> None:
        class _FakeRemoteError(Exception):
            pass

        class _FakeGet:
            def __call__(self, timeout: int = 0):
                raise _FakeRemoteError('Function call was cancelled by user.')

            async def aio(self, timeout: int = 0):
                raise _FakeRemoteError('Function call was cancelled by user.')

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(
                OutputExpiredError=RuntimeError,
                RemoteError=_FakeRemoteError,
            ),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = poll_infer_mtslstm_job('fc-456')

        self.assertEqual(status_code, 409)
        self.assertEqual(body['status'], 'cancelled')
        self.assertEqual(body['reason'], 'cancelled_by_user')

    def test_poll_infer_mtslstm_job_async_returns_cancelled_on_remote_error(self) -> None:
        class _FakeRemoteError(Exception):
            pass

        class _FakeGet:
            def __call__(self, timeout: int = 0):
                raise _FakeRemoteError('Function call was cancelled by user.')

            async def aio(self, timeout: int = 0):
                raise _FakeRemoteError('Function call was cancelled by user.')

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(
                OutputExpiredError=RuntimeError,
                RemoteError=_FakeRemoteError,
            ),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = asyncio.run(poll_infer_mtslstm_job_async('fc-456'))

        self.assertEqual(status_code, 409)
        self.assertEqual(body['status'], 'cancelled')
        self.assertEqual(body['reason'], 'cancelled_by_user')

    def test_poll_infer_mtslstm_job_returns_result_when_complete(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                return {
                    'status': 'ok',
                    'cells_with_shap': 400,
                    'artifact_dir': '/artifacts/20260427T000000Z',
                    'compute_job_id': 'job-123',
                    'forecast_run_id': 'run-123',
                    'execution_manifest': _valid_test_manifest(run_id='run-123', compute_job_id='job-123', call_id='fc-456'),
                }

            async def aio(self, timeout: int = 0):
                return self(timeout)

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal), \
             patch('backend.modal_worker_app._sync_modal_job_linkage_best_effort') as sync_mock:
            status_code, body = poll_infer_mtslstm_job('fc-456')

        self.assertEqual(status_code, 200)
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['cells_with_shap'], 400)
        self.assertEqual(body['modal_call_id'], 'fc-456')
        self.assertEqual(body['artifact_dir'], '/artifacts/20260427T000000Z')
        self.assertEqual(body['forecast_run_id'], 'run-123')
        sync_mock.assert_called_once()

    def test_poll_infer_mtslstm_job_async_returns_result_when_complete(self) -> None:
        class _FakeGet:
            def __call__(self, timeout: int = 0):
                return {'status': 'ok', 'cells_with_shap': 400, 'execution_manifest': _valid_test_manifest(call_id='fc-456')}

            async def aio(self, timeout: int = 0):
                return self(timeout)

        class _FakeFunctionCall:
            def __init__(self) -> None:
                self.get = _FakeGet()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = asyncio.run(poll_infer_mtslstm_job_async('fc-456'))

        self.assertEqual(status_code, 200)
        self.assertEqual(body['status'], 'ok')
        self.assertEqual(body['cells_with_shap'], 400)

    @patch('backend.modal_worker_app.run_train_mtslstm', return_value={'status': 'ok'})
    def test_run_remote_train_mtslstm_reloads_and_commits_volume(self, run_train_mock) -> None:
        calls: list[str] = []

        def _reload() -> None:
            calls.append('reload')

        def _commit() -> None:
            calls.append('commit')

        result = run_remote_train_mtslstm(
            {'dataset_snapshot_id': 'latest'},
            artifact_root=Path('/artifacts'),
            volume_reload=_reload,
            volume_commit=_commit,
        )

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(calls, ['reload', 'commit'])
        run_train_mock.assert_called_once_with({'dataset_snapshot_id': 'latest'}, artifact_root=Path('/artifacts'))

    @patch('backend.modal_worker_app.run_train_sar_unet', return_value={'status': 'ok', 'candidate_model_version': 'shadow-v2'})
    def test_run_remote_train_sar_unet_reloads_and_commits_volume(self, run_train_mock) -> None:
        calls: list[str] = []

        def _reload() -> None:
            calls.append('reload')

        def _commit() -> None:
            calls.append('commit')

        result = run_remote_train_sar_unet(
            {'training_manifest_path': 'sar-data/train.json'},
            artifact_root=Path('/artifacts'),
            device='cuda',
            volume_reload=_reload,
            volume_commit=_commit,
        )

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['candidate_model_version'], 'shadow-v2')
        self.assertEqual(calls, ['reload', 'commit'])
        run_train_mock.assert_called_once()
        _, kwargs = run_train_mock.call_args
        self.assertEqual(kwargs['artifact_root'], Path('/artifacts'))
        self.assertEqual(kwargs['device'], 'cuda')
        self.assertTrue(callable(kwargs['progress_callback']))

    def test_run_remote_train_sar_unet_commits_volume_on_progress_callback(self) -> None:
        calls: list[str] = []

        def _reload() -> None:
            calls.append('reload')

        def _commit() -> None:
            calls.append('commit')

        def _run_train(payload: dict[str, object], **kwargs: object) -> dict[str, object]:
            progress_callback = kwargs.get('progress_callback')
            self.assertTrue(callable(progress_callback))
            progress_callback({'phase': 'initializing'})
            progress_callback({'phase': 'materializing_dataset'})
            return {'status': 'ok', 'candidate_model_version': 'shadow-progress'}

        with patch('backend.modal_worker_app.run_train_sar_unet', side_effect=_run_train):
            result = run_remote_train_sar_unet(
                {'training_manifest_path': 'sar-data/train.json'},
                artifact_root=Path('/artifacts'),
                device='cuda',
                volume_reload=_reload,
                volume_commit=_commit,
            )

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(calls, ['reload', 'commit', 'commit', 'commit'])

    @patch('backend.modal_worker_app.evaluate_sar_checkpoint', return_value={'status': 'ok', 'quality_gate': {'passed': True}})
    def test_run_remote_evaluate_sar_checkpoint_reloads_and_commits_volume(self, evaluate_mock) -> None:
        calls: list[str] = []
        payload = {
            'training_manifest_path': '/artifacts/european-shadow-sar/manifest.json',
            'checkpoint_path': '/artifacts/20260516T164730Z/sar_model.pt',
        }

        def _reload() -> None:
            calls.append('reload')

        def _commit() -> None:
            calls.append('commit')

        result = run_remote_evaluate_sar_checkpoint(
            payload,
            artifact_root=Path('/artifacts'),
            device='cuda',
            volume_reload=_reload,
            volume_commit=_commit,
        )

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(calls, ['reload', 'commit'])
        evaluate_mock.assert_called_once_with(payload, artifact_root=Path('/artifacts'), device='cuda')

    @patch('backend.modal_worker_app.build_sar_validation_error_diagnostics', return_value={'status': 'ok'})
    def test_run_remote_evaluate_sar_checkpoint_diagnostics_branch(self, diagnostics_mock) -> None:
        payload = {
            'training_manifest_path': '/artifacts/european-shadow-sar/manifest.json',
            'checkpoint_path': '/artifacts/20260516T164730Z/sar_model.pt',
            'diagnostics': True,
        }

        result = run_remote_evaluate_sar_checkpoint(payload, artifact_root=Path('/artifacts'), device='cuda')

        self.assertEqual(result['status'], 'ok')
        diagnostics_mock.assert_called_once_with(payload, artifact_root=Path('/artifacts'), device='cuda')

    @patch('backend.modal_worker_app.evaluate_sar_checkpoint_scene_blended', return_value={'status': 'ok', 'evaluation_mode': 'scene_blended'})
    def test_run_remote_evaluate_sar_checkpoint_scene_blended_branch(self, scene_blended_mock) -> None:
        payload = {
            'training_manifest_path': '/artifacts/european-shadow-sar/manifest.json',
            'checkpoint_path': '/artifacts/20260516T164730Z/sar_model.pt',
            'evaluation_mode': 'scene_blended',
        }

        result = run_remote_evaluate_sar_checkpoint(payload, artifact_root=Path('/artifacts'), device='cuda')

        self.assertEqual(result['status'], 'ok')
        scene_blended_mock.assert_called_once_with(payload, artifact_root=Path('/artifacts'), device='cuda')

    @patch('backend.modal_worker_app.handle_infer_mtslstm', return_value={'status': 'ok', 'cells_with_shap': 5})
    def test_run_remote_infer_mtslstm_reloads_and_commits_volume(self, handle_infer_mock) -> None:
        calls: list[str] = []

        def _reload() -> None:
            calls.append('reload')

        def _commit() -> None:
            calls.append('commit')

        result = run_remote_infer_mtslstm(
            {'forecast_hours': 72, 'dry_run': True},
            artifact_root=Path('/artifacts'),
            volume_reload=_reload,
            volume_commit=_commit,
        )

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['cells_with_shap'], 5)
        self.assertEqual(calls, ['reload', 'commit'])
        handle_infer_mock.assert_called_once_with({'forecast_hours': 72, 'dry_run': True})

    @patch('backend.modal_worker_app.run_worker_request', return_value={'status': 'ok', 'scene_count': 7})
    def test_run_remote_sar_segment_reloads_and_commits_volume(self, run_worker_request_mock) -> None:
        calls: list[str] = []

        def _reload() -> None:
            calls.append('reload')

        def _commit() -> None:
            calls.append('commit')

        result = run_remote_sar_segment(
            {'reference_set_key': 'snowslide-heldout-v1', 'shadow_mode': True},
            artifact_root=Path('/artifacts'),
            device='cuda',
            volume_reload=_reload,
            volume_commit=_commit,
        )

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['scene_count'], 7)
        self.assertEqual(calls, ['reload', 'commit'])
        run_worker_request_mock.assert_called_once()
        self.assertEqual(run_worker_request_mock.call_args.args[0], 'sar-segment')
        self.assertEqual(run_worker_request_mock.call_args.args[1], {'reference_set_key': 'snowslide-heldout-v1', 'shadow_mode': True})
        self.assertEqual(run_worker_request_mock.call_args.kwargs['device'], 'cuda')

    @patch(
        'backend.modal_worker_app.run_worker_request',
        return_value={
            'status': 'ok',
            'prediction_mask_dtype': 'float32',
            'scene_count': 2,
            'detections_count': 2,
            'mask_asset_refs': ['sar-masks/a.tif', 'sar-masks/b.tif'],
            'detections': [{'large': 'geometry'}],
        },
    )
    def test_run_remote_sar_segment_compact_response_omits_detection_payload(self, run_worker_request_mock) -> None:
        result = run_remote_sar_segment(
            {'reference_set_key': 'snowslide-heldout-v1', 'compact_response': True},
            artifact_root=Path('/artifacts'),
            device='cuda',
        )

        self.assertEqual(result['status'], 'ok')
        self.assertTrue(result['compact_response'])
        self.assertEqual(result['prediction_mask_dtype'], 'float32')
        self.assertEqual(result['mask_asset_ref_count'], 2)
        self.assertEqual(result['mask_asset_refs'], ['sar-masks/a.tif', 'sar-masks/b.tif'])
        self.assertNotIn('detections', result)
        run_worker_request_mock.assert_called_once()

    def test_seed_dem_directory_copies_missing_dems_only(self) -> None:
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'source'
            destination = Path(tmpdir) / 'dest'
            source.mkdir()
            destination.mkdir()
            (source / 'colorado_rockies.tif').write_bytes(b'1234')
            (source / 'README.md').write_text('dem docs', encoding='utf-8')

            first = seed_dem_directory(source, destination)
            second = seed_dem_directory(source, destination)

        self.assertEqual(first['copied'], 1)
        self.assertEqual(second['skipped'], 1)

    def test_normalize_model_volume_path_rejects_paths_outside_models(self) -> None:
        with self.assertRaisesRegex(ValueError, 'expected an absolute path under /models/'):
            normalize_model_volume_path('/tmp/swin.pt')

    def test_seed_model_volume_file_uses_models_remote_path(self) -> None:
        class _FakeBatch:
            def __init__(self) -> None:
                self.uploads: list[tuple[Path, str]] = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def put_file(self, source_path, remote_path) -> None:
                self.uploads.append((Path(source_path), remote_path))

        class _FakeVolume:
            def __init__(self) -> None:
                self.batch = _FakeBatch()

            def batch_upload(self, force: bool = False):
                self.force = force
                return self.batch

        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / 'swin.pt'
            source.write_bytes(b'checkpoint')
            volume = _FakeVolume()

            result = seed_model_volume_file(
                volume,
                source,
                remote_model_path='/models/swin_transformer_v2_tiny.pt',
            )

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['remote_model_path'], '/models/swin_transformer_v2_tiny.pt')
        self.assertEqual(result['runtime_model_path'], '/artifacts/models/swin_transformer_v2_tiny.pt')
        self.assertEqual(volume.batch.uploads, [(source.resolve(), '/models/swin_transformer_v2_tiny.pt')])


class ModalWorkerAdversarialTests(unittest.TestCase):
    """Adversarial tests for G5: no manifest attestation rewriting."""

    def test_g5_manifest_call_id_mismatch_rejected_not_rewritten(self) -> None:
        """G5: When the manifest's call_id does not match the provider call_id,
        the job is rejected with manifest_call_id_mismatch, NOT silently rewritten."""
        from backend.modal_worker_app import _ok_modal_job

        # The manifest has call_id='wrong-call' but the provider says call_id='fc-real'
        result = {
            'status': 'ok',
            'execution_manifest': _valid_test_manifest(call_id='wrong-call'),
        }
        body = _ok_modal_job('fc-real', 'infer_mtslstm', result)
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['reason'], 'manifest_call_id_mismatch')
        self.assertIn('manifest_errors', body)
        # The manifest call_id must NOT have been rewritten
        self.assertEqual(body['execution_manifest']['call_id'], 'wrong-call')

    def test_g5_manifest_with_matching_call_id_passes(self) -> None:
        """G5: When the manifest's call_id matches the provider call_id, the job passes."""
        from backend.modal_worker_app import _ok_modal_job

        result = {
            'status': 'ok',
            'execution_manifest': _valid_test_manifest(call_id='fc-real'),
        }
        body = _ok_modal_job('fc-real', 'infer_mtslstm', result)
        self.assertEqual(body['status'], 'ok')

    def test_g5_manifest_without_call_id_fails_validation(self) -> None:
        """G5: When the manifest has an empty call_id, the validator rejects it
        (it's a required identity field). This is NOT a mismatch rejection."""
        from backend.modal_worker_app import _ok_modal_job

        manifest = _valid_test_manifest(call_id='')
        result = {
            'status': 'ok',
            'execution_manifest': manifest,
        }
        body = _ok_modal_job('fc-real', 'infer_mtslstm', result)
        # Empty call_id should fail validation, not mismatch
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['reason'], 'invalid_execution_manifest')
        self.assertNotEqual(body.get('reason'), 'manifest_call_id_mismatch')


if __name__ == '__main__':
    unittest.main()
