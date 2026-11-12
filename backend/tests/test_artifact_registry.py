"""Tests for artifact namespace isolation (P6).

Tests verify that:
- Artifacts can be registered and verified for their bound track
- Cross-lane artifact swaps are rejected
- Namespace mismatches are rejected
- Lineage mismatches are rejected
- Unregistered artifacts are rejected
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from backend.common.track_contracts.artifact_registry import (
    ArtifactBindingV1,
    ArtifactRegistry,
    ArtifactNamespaceError,
)
from backend.common.track_contracts.content_resolver import ContentResolver


_HEX = "a" * 64


def _valid_binding(track="t2a", artifact_id="model_001") -> ArtifactBindingV1:
    return ArtifactBindingV1(
        artifact_id=artifact_id,
        artifact_type="model",
        track=track,
        feature_hash=_HEX,
        source_hash=_HEX,
        split_hash=_HEX,
        namespace=f"{track}_training",
        created_at="2026-08-18T06:00:00+00:00",
    )


class TestArtifactBinding(unittest.TestCase):

    def test_valid_binding_passes(self):
        _valid_binding().validate()

    def test_invalid_track_rejected(self):
        binding = ArtifactBindingV1(
            artifact_id="m1", artifact_type="model", track="track3",
            feature_hash=_HEX, source_hash=_HEX, split_hash=_HEX,
            namespace="track3_training", created_at="2026-01-01T00:00:00+00:00",
        )
        with self.assertRaises(ArtifactNamespaceError):
            binding.validate()

    def test_namespace_must_match_track(self):
        binding = ArtifactBindingV1(
            artifact_id="m1", artifact_type="model", track="t2a",
            feature_hash=_HEX, source_hash=_HEX, split_hash=_HEX,
            namespace="track1_training",  # wrong track in namespace
            created_at="2026-01-01T00:00:00+00:00",
        )
        with self.assertRaises(ArtifactNamespaceError):
            binding.validate()

    def test_non_hex_lineage_rejected(self):
        binding = ArtifactBindingV1(
            artifact_id="m1", artifact_type="model", track="t2a",
            feature_hash="g" * 64, source_hash=_HEX, split_hash=_HEX,
            namespace="t2a_training", created_at="2026-01-01T00:00:00+00:00",
        )
        with self.assertRaises(ArtifactNamespaceError):
            binding.validate()

    def test_malformed_created_at_rejected(self):
        binding = replace(_valid_binding(), created_at="not-a-timestamp+00:00")
        with self.assertRaises(ArtifactNamespaceError):
            binding.validate()


class TestArtifactRegistry(unittest.TestCase):

    def test_registered_artifact_verified(self):
        reg = ArtifactRegistry()
        binding = _valid_binding(track="t2a")
        reg.register(binding)
        result = reg.verify_artifact_for_track(
            "model_001", "t2a", "t2a_training"
        )
        self.assertEqual(result.artifact_id, "model_001")

    def test_cross_lane_swap_rejected(self):
        """CRITICAL: T2A artifact cannot be used for Track 1."""
        reg = ArtifactRegistry()
        binding = _valid_binding(track="t2a", artifact_id="t2a_model")
        reg.register(binding)
        with self.assertRaises(ArtifactNamespaceError) as ctx:
            reg.verify_artifact_for_track(
                "t2a_model", "track1", "track1_training"  # wrong track
            )
        self.assertIn("cross-lane", str(ctx.exception).lower())

    def test_track1_artifact_cannot_load_for_t2a(self):
        """Track 1 artifact cannot be loaded for T2A."""
        reg = ArtifactRegistry()
        binding = _valid_binding(track="track1", artifact_id="track1_model")
        reg.register(binding)
        with self.assertRaises(ArtifactNamespaceError):
            reg.verify_artifact_for_track(
                "track1_model", "t2a", "t2a_training"
            )

    def test_namespace_mismatch_rejected(self):
        reg = ArtifactRegistry()
        binding = _valid_binding(track="t2a", artifact_id="m1")
        reg.register(binding)
        with self.assertRaises(ArtifactNamespaceError):
            reg.verify_artifact_for_track(
                "m1", "t2a", "t2a_serving"  # wrong namespace
            )

    def test_lineage_mismatch_rejected(self):
        reg = ArtifactRegistry()
        binding = _valid_binding(track="t2a", artifact_id="m1")
        reg.register(binding)
        with self.assertRaises(ArtifactNamespaceError):
            reg.verify_artifact_for_track(
                "m1", "t2a", "t2a_training",
                feature_hash="b" * 64,  # different feature hash
                source_hash="a" * 64,
                split_hash="a" * 64,
            )

    def test_unregistered_artifact_rejected(self):
        reg = ArtifactRegistry()
        with self.assertRaises(ArtifactNamespaceError):
            reg.verify_artifact_for_track(
                "nonexistent", "t2a", "t2a_training"
            )

    def test_list_artifacts_for_track(self):
        reg = ArtifactRegistry()
        reg.register(_valid_binding(track="t2a", artifact_id="m1"))
        reg.register(_valid_binding(track="t2a", artifact_id="m2"))
        reg.register(_valid_binding(track="track1", artifact_id="m3"))
        t2a_artifacts = reg.list_artifacts_for_track("t2a")
        self.assertEqual(len(t2a_artifacts), 2)
        track1_artifacts = reg.list_artifacts_for_track("track1")
        self.assertEqual(len(track1_artifacts), 1)

    def test_content_bound_artifact_requires_matching_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            content = b"model-bytes"
            path = Path(tmpdir) / "model.bin"
            path.write_bytes(content)
            binding = ArtifactBindingV1(
                artifact_id="content-model",
                artifact_type="model",
                track="t2a",
                feature_hash=_HEX,
                source_hash=_HEX,
                split_hash=_HEX,
                namespace="t2a_evaluation",
                created_at="2026-01-01T00:00:00+00:00",
                content_hash=hashlib.sha256(content).hexdigest(),
                content_path="model.bin",
            )
            registry = ArtifactRegistry()
            registry.register(binding)
            result = registry.verify_artifact_for_track(
                "content-model",
                "t2a",
                "t2a_evaluation",
                feature_hash=_HEX,
                source_hash=_HEX,
                split_hash=_HEX,
                content_resolver=ContentResolver(Path(tmpdir)),
                require_content=True,
            )
            self.assertEqual(result.artifact_id, "content-model")

    def test_content_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model.bin"
            path.write_bytes(b"original")
            declared = hashlib.sha256(path.read_bytes()).hexdigest()
            binding = ArtifactBindingV1(
                artifact_id="content-model",
                artifact_type="model",
                track="t2a",
                feature_hash=_HEX,
                source_hash=_HEX,
                split_hash=_HEX,
                namespace="t2a_evaluation",
                created_at="2026-01-01T00:00:00+00:00",
                content_hash=declared,
                content_path="model.bin",
            )
            registry = ArtifactRegistry()
            registry.register(binding)
            path.write_bytes(b"mutated")
            with self.assertRaises(ArtifactNamespaceError):
                registry.verify_artifact_for_track(
                    "content-model", "t2a", "t2a_evaluation",
                    feature_hash=_HEX, source_hash=_HEX, split_hash=_HEX,
                    content_resolver=ContentResolver(Path(tmpdir)),
                    require_content=True,
                )


if __name__ == "__main__":
    unittest.main()
