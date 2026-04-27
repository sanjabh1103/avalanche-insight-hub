from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault('AVALANCHE_SKIP_MODAL_IMPORT', '1')

from backend.modal_worker_app import (
    authorize_bearer_request,
    dispatch_modal_route,
    handle_evaluate_release,
    handle_infer_mtslstm,
    handle_sar_segment,
    handle_train_mtslstm,
    normalize_model_volume_path,
    poll_train_mtslstm_job,
    run_remote_train_mtslstm,
    seed_dem_directory,
    seed_model_volume_file,
    submit_train_mtslstm_job,
)


class ModalWorkerAppTests(unittest.TestCase):
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

        class _FakeFunction:
            def __init__(self) -> None:
                self.payload = None

            def spawn(self, payload):
                self.payload = payload
                return _FakeCall()

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
        self.assertEqual(fake_function.payload, {'dataset_snapshot_id': 'latest'})

    def test_poll_train_mtslstm_job_returns_pending_on_timeout(self) -> None:
        class _FakeFunctionCall:
            def get(self, timeout: int = 0):
                raise TimeoutError()

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = poll_train_mtslstm_job('fc-123')

        self.assertEqual(status_code, 202)
        self.assertEqual(body['status'], 'pending')

    def test_poll_train_mtslstm_job_returns_result_when_complete(self) -> None:
        class _FakeFunctionCall:
            def get(self, timeout: int = 0):
                return {'status': 'ok', 'artifact_dir': '/artifacts/20260427T000000Z'}

        fake_modal = SimpleNamespace(
            FunctionCall=SimpleNamespace(from_id=lambda call_id: _FakeFunctionCall()),
            exception=SimpleNamespace(OutputExpiredError=RuntimeError),
        )

        with patch('backend.modal_worker_app.modal', fake_modal):
            status_code, body = poll_train_mtslstm_job('fc-123')

        self.assertEqual(status_code, 200)
        self.assertEqual(body['status'], 'ok')

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
