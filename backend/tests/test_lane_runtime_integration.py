"""Production-boundary tests for explicit Partner lane requests."""

from __future__ import annotations

import tempfile
import unittest
import json
import shutil
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from backend.common.track_contracts.lane_execution_wrapper import LaneExecutionError
from backend.common.track_contracts.lane_execution_wrapper import authorize_lane_payload
from backend.common.Partner_decision_packet import build_decision_packet, save_decision_packet
from backend.common.track_contracts.artifact_registry import ArtifactRegistry
from backend.common.track_contracts.packet_loaders import StationAnchorManifestV1
from backend.common.track_contracts.lane_allowlists import TRACK1_ALLOWLIST
from backend.modal_worker_app import _dispatch_worker_request
from backend.sar_unet_worker import run_worker_request

from backend.tests.test_lane_execution_wrapper import (
    _TEST_CONTENT_ROOT,
    _utc,
    _valid_manifest,
    _valid_t2a_context,
    _valid_t2a_features,
    _registry_with_smith,
)


class TestSarWorkerBoundary(unittest.TestCase):
    @patch("backend.sar_unet_worker._run_python_module")
    def test_explicit_lane_blocks_before_worker_subprocess(self, run_module_mock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(LaneExecutionError) as caught:
                run_worker_request(
                    "train-mtslstm",
                    {
                        "Partner_lane": True,
                        "track": "t2a",
                        "operation_mode": "training",
                    },
                    artifact_root=Path(tmpdir),
                )
        self.assertIn("E024_missing_evidence_packet", str(caught.exception))
        run_module_mock.assert_not_called()

    @patch("backend.sar_unet_worker._run_python_module")
    def test_lane_operation_mode_cannot_be_relabelled_for_worker(self, run_module_mock) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(LaneExecutionError):
                run_worker_request(
                    "train-mtslstm",
                    {
                        "Partner_lane": True,
                        "track": "t2a",
                        "operation_mode": "serve",
                    },
                    artifact_root=Path(tmpdir),
                )
        run_module_mock.assert_not_called()


class TestModalBoundary(unittest.TestCase):
    @patch("backend.modal_worker_app.run_worker_request")
    def test_explicit_lane_blocks_before_modal_dispatch(self, run_worker_mock) -> None:
        with self.assertRaises(LaneExecutionError) as caught:
            _dispatch_worker_request(
                "infer-mtslstm",
                {
                    "Partner_lane": True,
                    "track": "track1",
                    "operation_mode": "serve",
                },
            )
        self.assertIn("E024_missing_evidence_packet", str(caught.exception))
        run_worker_mock.assert_not_called()


class TestSyntheticPacketLoadThroughProductionWrapper(unittest.TestCase):
    def _write_packet(self, root: Path, name: str, payload: dict) -> str:
        path = root / name
        path.write_text(json.dumps(payload, sort_keys=True, default=str), encoding="utf-8")
        return str(path)

    def test_t2a_training_and_track1_framework_packets_load_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            content_root = root / "content"
            content_root.mkdir()
            decision_packet_path = root / "Partner_decision_packet.json"
            save_decision_packet(build_decision_packet(), decision_packet_path)
            t2a_context = _valid_t2a_context()
            t2a_manifest = _valid_manifest()
            for name in (
                "label_inventory.json", "split_manifest.json", "reference_geometry.json",
                "forcing_source.json",
            ):
                shutil.copy2(_TEST_CONTENT_ROOT / name, content_root / name)

            authority = self._write_packet(root, "authority.json", _registry_with_smith().to_dict())
            artifacts = self._write_packet(root, "artifacts.json", ArtifactRegistry().to_dict())
            t2a_context_path = self._write_packet(root, "t2a_context.json", t2a_context.to_dict())
            t2a_manifest_path = self._write_packet(root, "t2a_manifest.json", t2a_manifest.to_dict())
            t2a_decision = authorize_lane_payload({
                "Partner_lane": True,
                "track": "t2a",
                "operation_mode": "training",
                "preflight_context_path": t2a_context_path,
                "experiment_manifest_path": t2a_manifest_path,
                "authority_registry_path": authority,
                "artifact_registry_path": artifacts,
                "content_base_path": str(content_root),
                "feature_names": _valid_t2a_features(),
                "decision_packet_path": str(decision_packet_path),
            })
            self.assertIsNotNone(t2a_decision)
            self.assertFalse(t2a_decision.allowed)
            self.assertIn("E026_evidence_packet_blocks_operation", t2a_decision.blocker_codes)

            station_payload = {"station": "synthetic-track1"}
            station_bytes = json.dumps(station_payload, sort_keys=True).encode("utf-8")
            (content_root / "station_source.json").write_bytes(station_bytes)
            import hashlib
            station_hash = hashlib.sha256(station_bytes).hexdigest()
            track1_context = replace(
                t2a_context,
                track="track1",
                forcing_source=None,
                station_source=StationAnchorManifestV1(
                    station_id="aws-synthetic", latitude=34.02, longitude=74.35,
                    elevation_m=3500.0, station_type="aws", source_hash=station_hash,
                    license_review_status="approved", permitted_track="track1",
                    approved_by="Dr. Smith", approved_at=_utc(2026, 8, 18, 6),
                ),
                content_paths={
                    "label_inventory": "label_inventory.json",
                    "split_manifest": "split_manifest.json",
                    "reference_geometry": "reference_geometry.json",
                    "station_source": "station_source.json",
                },
            )
            track1_manifest = replace(
                _valid_manifest(track="track1", claim_state="framework_ready"),
                track="track1",
                source_hash=station_hash,
            )
            track1_context_path = self._write_packet(root, "track1_context.json", track1_context.to_dict())
            track1_manifest_path = self._write_packet(root, "track1_manifest.json", track1_manifest.to_dict())
            track1_decision = authorize_lane_payload({
                "Partner_lane": True,
                "track": "track1",
                "operation_mode": "framework",
                "preflight_context_path": track1_context_path,
                "experiment_manifest_path": track1_manifest_path,
                "authority_registry_path": authority,
                "artifact_registry_path": artifacts,
                "content_base_path": str(content_root),
                "feature_names": list(TRACK1_ALLOWLIST),
            })
            self.assertIsNotNone(track1_decision)
            self.assertTrue(track1_decision.allowed, track1_decision.blocker_messages)

    def test_malformed_manifest_is_a_structured_runtime_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            content_root = root / "content"
            content_root.mkdir()
            context = _valid_t2a_context()
            for name in (
                "label_inventory.json", "split_manifest.json", "reference_geometry.json",
                "forcing_source.json",
            ):
                shutil.copy2(_TEST_CONTENT_ROOT / name, content_root / name)
            authority = self._write_packet(root, "authority.json", _registry_with_smith().to_dict())
            artifacts = self._write_packet(root, "artifacts.json", ArtifactRegistry().to_dict())
            context_path = self._write_packet(root, "context.json", context.to_dict())
            malformed_manifest = _valid_manifest().to_dict()
            malformed_manifest["target_hash"] = 17
            manifest_path = self._write_packet(root, "manifest.json", malformed_manifest)
            decision = authorize_lane_payload({
                "Partner_lane": True,
                "track": "t2a",
                "operation_mode": "training",
                "preflight_context_path": context_path,
                "experiment_manifest_path": manifest_path,
                "authority_registry_path": authority,
                "artifact_registry_path": artifacts,
                "content_base_path": str(content_root),
                "feature_names": _valid_t2a_features(),
            })
            self.assertIsNotNone(decision)
            self.assertFalse(decision.allowed)
            self.assertIn("E024_missing_evidence_packet", decision.blocker_codes)


if __name__ == "__main__":
    unittest.main()
