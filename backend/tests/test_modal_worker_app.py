from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault('AVALANCHE_SKIP_MODAL_IMPORT', '1')

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
)


class ModalWorkerAppTests(unittest.TestCase):
    def test_modal_pinned_runtime_packages_match_requirements(self) -> None:
        self.assertEqual(
            MODAL_PINNED_RUNTIME_PACKAGES,
            ('shap==0.51.0', 'scikit-learn==1.8.0'),
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
    @patch('backend.modal_worker_app.handle_train_mtslstm', return_value={'status': 'ok'})
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
    @patch('backend.modal_worker_app.handle_train_mtslstm', return_value={'status': 'ok'})
    def test_dispatch_modal_route_forwards_valid_request(self, handle_mock) -> None:
        payload = {'dataset_snapshot_id': 'latest'}
        status_code, body = dispatch_modal_route(
            '/train-mtslstm',
            payload,
            authorization_header='Bearer secret-token',
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(body['status'], 'ok')
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
                return {'status': 'ok', 'artifact_dir': '/artifacts/20260427T000000Z'}

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
                return {'status': 'ok', 'artifact_dir': '/artifacts/20260427T000000Z'}

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
                return {'status': 'ok', 'candidate_model_version': 'shadow-v2'}

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
                return {'status': 'ok', 'candidate_model_version': 'shadow-v2'}

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
                return {'status': 'ok', 'cells_with_shap': 400}

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
        run_train_mock.assert_called_once_with(
            {'training_manifest_path': 'sar-data/train.json'},
            artifact_root=Path('/artifacts'),
            device='cuda',
        )

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


if __name__ == '__main__':
    unittest.main()
