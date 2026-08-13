"""Adversarial regression tests for Modal audit findings M1/M4/R3."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.common.modal_execution_manifest import (
    build_execution_manifest,
    compute_artifact_digest,
    validate_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _valid_kwargs(root: Path) -> dict[str, object]:
    artifact = root / "result.json"
    artifact.write_text('{"status":"ok"}\n', encoding="utf-8")
    now = datetime.now(timezone.utc)
    return {
        "run_id": "run-pir-panjal-001",
        "compute_job_id": "compute-job-001",
        "input_manifest_id": "input-manifest-001",
        "input_manifest_hash": "a" * 64,
        "source_commit": "b" * 40,
        "model_version": "shadow-model-v1",
        "image_identity": "modal-image:sha256:" + "c" * 64,
        "image_archive_sha256": "d" * 64,
        "artifact_root": str(root),
        "artifact_paths": [artifact],
        "python_version": "3.12.12",
        "modal_sdk_version": "0.73.83",
        "torch_version": "2.5.1+cu121",
        "torchvision_version": "0.20.1+cu121",
        "torchaudio_version": "2.5.1+cu121",
        "cuda_version": "12.1",
        "function_name": "sar_segment_remote",
        "call_id": "fc-001",
        "terminal_status": "ok",
        "started_at": (now - timedelta(seconds=2)).isoformat(),
        "shadow_mode": True,
        "allow_publish": False,
        "gpu_configured": "",
        "volume_committed": True,
    }


class ModalManifestIdentityTests(unittest.TestCase):
    def test_valid_manifest_has_strict_identity_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_execution_manifest(**_valid_kwargs(Path(tmp)))
            self.assertEqual(validate_manifest(manifest), [])
            for field in (
                "run_id",
                "compute_job_id",
                "call_id",
                "input_manifest_id",
                "input_manifest_hash",
                "source_commit",
                "model_version",
                "image_identity",
                "image_archive_sha256",
                "artifact_root",
                "python_version",
                "modal_sdk_version",
                "torch_version",
                "cuda_version",
            ):
                self.assertTrue(manifest[field], field)

    def test_unknown_or_empty_identity_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_execution_manifest(**_valid_kwargs(Path(tmp)))
            for field in (
                "run_id",
                "compute_job_id",
                "input_manifest_id",
                "source_commit",
                "model_version",
                "image_identity",
                "python_version",
                "modal_sdk_version",
            ):
                candidate = dict(manifest)
                candidate[field] = "unknown" if field != "source_commit" else "unknown"
                violations = validate_manifest(candidate)
                self.assertTrue(violations, field)

    def test_cross_run_and_cross_call_expectations_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_execution_manifest(**_valid_kwargs(Path(tmp)))
            self.assertTrue(validate_manifest(manifest, expected_run_id="run-other"))
            self.assertTrue(validate_manifest(manifest, expected_call_id="fc-other"))
            self.assertTrue(validate_manifest(manifest, expected_compute_job_id="compute-other"))

    def test_invalid_hashes_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_execution_manifest(**_valid_kwargs(Path(tmp)))
            for field in ("input_manifest_hash", "image_archive_sha256"):
                candidate = dict(manifest)
                candidate[field] = "not-a-sha256"
                self.assertTrue(validate_manifest(candidate), field)

    def test_naive_reversed_and_future_timestamps_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = _valid_kwargs(Path(tmp))
            for started_at, completed_at in (
                ("2026-08-09T10:00:00", "2026-08-09T10:00:01+00:00"),
                ("2026-08-09T10:00:02+00:00", "2026-08-09T10:00:01+00:00"),
                (
                    (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                    (datetime.now(timezone.utc) + timedelta(hours=1, seconds=1)).isoformat(),
                ),
            ):
                kwargs = dict(base)
                kwargs["started_at"] = started_at
                kwargs["completed_at"] = completed_at
                manifest = build_execution_manifest(**kwargs)
                self.assertTrue(validate_manifest(manifest), (started_at, completed_at))

    def test_artifact_outside_root_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            root.mkdir()
            outside = Path(tmp) / "sibling-result.json"
            outside.write_text("outside\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                compute_artifact_digest(outside, artifact_root=root)

    def test_sibling_prefix_does_not_pass_containment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifact"
            sibling = Path(tmp) / "artifact-sibling"
            root.mkdir()
            sibling.mkdir()
            file_path = sibling / "result.json"
            file_path.write_text("sibling\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                compute_artifact_digest(file_path, artifact_root=root)

    def test_symlinked_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            root.mkdir()
            outside = Path(tmp) / "outside.json"
            outside.write_text("outside\n", encoding="utf-8")
            link = root / "linked.json"
            link.symlink_to(outside)
            with self.assertRaises(ValueError):
                compute_artifact_digest(link, artifact_root=root)

    def test_directory_symlink_member_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "artifacts"
            root.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            (outside / "result.json").write_text("outside\n", encoding="utf-8")
            link = root / "linked-dir"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                compute_artifact_digest(root, artifact_root=root)


class ModalRouteAuditTests(unittest.TestCase):
    def test_route_handlers_use_declared_modal_submission_functions(self) -> None:
        from backend.modal_worker_app import (
            _route_handlers,
            submit_evaluate_release_job,
            submit_sar_segment_job,
        )

        handlers = _route_handlers()
        self.assertIs(handlers['/sar-segment'], submit_sar_segment_job)
        self.assertIs(handlers['/evaluate-release'], submit_evaluate_release_job)

    def test_fastapi_exposes_terminal_result_routes(self) -> None:
        from backend.modal_worker_app import create_fastapi_app

        app = create_fastapi_app()
        paths = {route.path for route in app.routes}
        self.assertIn('/sar-segment/result/{call_id}', paths)
        self.assertIn('/evaluate-release/result/{call_id}', paths)

    def test_terminal_ok_without_manifest_is_downgraded(self) -> None:
        from backend.modal_worker_app import _ok_modal_job

        result = _ok_modal_job('fc-001', 'sar_segment', {'status': 'ok'})
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['reason'], 'missing_execution_manifest')

    def test_submit_sar_segment_uses_gpu_function(self) -> None:
        from backend.modal_worker_app import MODAL_APP_NAME, MODAL_REMOTE_SEGMENT_FUNCTION, submit_sar_segment_job

        calls: list[tuple[str, str]] = []

        class FakeCall:
            object_id = 'fc-segment-001'

        class FakeFunction:
            def spawn(self, payload: dict[str, object]) -> FakeCall:
                return FakeCall()

        class FakeModal:
            class Function:
                @staticmethod
                def from_name(app_name: str, function_name: str) -> FakeFunction:
                    calls.append((app_name, function_name))
                    return FakeFunction()

        with patch('backend.modal_worker_app.modal', FakeModal()):
            result = submit_sar_segment_job({'run_id': 'run-001'})
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(calls, [(MODAL_APP_NAME, MODAL_REMOTE_SEGMENT_FUNCTION)])

    def test_submit_evaluate_release_uses_declared_cpu_remote_function(self) -> None:
        from backend.modal_worker_app import MODAL_APP_NAME, MODAL_REMOTE_EVALUATE_RELEASE_FUNCTION, submit_evaluate_release_job

        calls: list[tuple[str, str]] = []

        class FakeCall:
            object_id = 'fc-eval-001'

        class FakeFunction:
            def spawn(self, payload: dict[str, object]) -> FakeCall:
                return FakeCall()

        class FakeModal:
            class Function:
                @staticmethod
                def from_name(app_name: str, function_name: str) -> FakeFunction:
                    calls.append((app_name, function_name))
                    return FakeFunction()

        with patch('backend.modal_worker_app.modal', FakeModal()):
            result = submit_evaluate_release_job({'run_id': 'run-001'})
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(calls, [(MODAL_APP_NAME, MODAL_REMOTE_EVALUATE_RELEASE_FUNCTION)])


class ModalDependencyConsistencyTests(unittest.TestCase):
    def test_modal_pin_is_consistent_across_source_lock_and_image(self) -> None:
        source = (REPO_ROOT / "backend/requirements-ci.in").read_text(encoding="utf-8")
        generated = (REPO_ROOT / "backend/requirements-ci.txt").read_text(encoding="utf-8")
        lock = (REPO_ROOT / "backend/locks/ci-py312.txt").read_text(encoding="utf-8")
        worker = (REPO_ROOT / "backend/modal_worker_app.py").read_text(encoding="utf-8")
        self.assertIn("modal==0.73.83", source)
        self.assertIn("modal==0.73.83", generated)
        self.assertIn("modal==0.73.83", lock)
        self.assertIn("MODAL_PINNED_MODAL_SDK = 'modal==0.73.83'", worker)
        self.assertNotIn("modal==0.62.25", source + generated + lock + worker)
        self.assertNotIn("modal>=", source + generated + lock + worker)
        self.assertIn("h2==4.4.1", source)
        self.assertIn("h2==4.4.1", generated)
        self.assertIn("h2==4.4.1", lock)

    def test_worker_does_not_install_torch_twice_unpinned(self) -> None:
        worker = (REPO_ROOT / "backend/modal_worker_app.py").read_text(encoding="utf-8")
        self.assertIn("backend/locks/modal-py312.txt", worker)
        self.assertNotIn("pip_install_from_requirements('backend/requirements.txt')", worker)
        self.assertNotIn("pip install --no-cache-dir torch torchvision torchaudio", worker)
        modal_lock = (REPO_ROOT / "backend/locks/modal-py312.txt").read_text(encoding="utf-8")
        self.assertIn("modal==0.73.83", modal_lock)
        self.assertIn("torch==2.5.1", modal_lock)
        self.assertIn("torchvision==0.20.1", modal_lock)
        self.assertIn("torchaudio==2.5.1", modal_lock)
        self.assertIn("pyarrow==25.0.0", modal_lock)


if __name__ == "__main__":
    unittest.main()
