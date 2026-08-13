"""Executable G0.1-G0.6/G0.14 re-verification probes.

These tests exercise public/API and release-gate behavior rather than relying
on source-text assertions. They are intentionally written before the repairs.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.common.snowpack_paths import UnsafePathError
from backend.scripts.release_gate import _validate_relative_path


def _run_fixture_gate(root: Path, *, expected_run_id: str = '') -> int:
    from backend.scripts.release_gate import run_release_gate
    # G5: Compute the expected registry hash from the actual bundle bytes.
    # No mutable global — the hash is derived from the registry file that
    # was written by the fixture builder.
    registry_path = root / 'input-manifests' / 'approval-registry.json'
    expected_registry_sha256 = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    return run_release_gate(
        root,
        expected_run_id=expected_run_id,
        expected_registry_sha256=expected_registry_sha256,
    )


class TestG01RelativePathContract(unittest.TestCase):
    """G0.1: all absolute/path escape forms fail closed."""

    def test_absolute_and_cross_platform_paths_rejected(self) -> None:
        for value in (
            "/etc/passwd",
            "//server/share/artifact.smet",
            "C:/Windows/system32/artifact.smet",
            "C:\\Windows\\system32\\artifact.smet",
            "native-output/../outside.smet",
            "native-output//artifact.smet",
        ):
            with self.subTest(value=value):
                self.assertIsNone(_validate_relative_path(value))

    def test_safe_relative_path_accepted(self) -> None:
        self.assertEqual(
            _validate_relative_path("native-output/run.pro"),
            "native-output/run.pro",
        )


class TestG02RunIdContract(unittest.TestCase):
    """G0.2: release IDs are explicit, bounded, and path-safe."""

    def test_release_run_id_validator_rejects_empty_unsafe_and_oversized(self) -> None:
        from backend.common.snowpack_contracts import validate_release_run_id

        for value in ("", "   ", "../escape", "run/id", "run\\id", "run\x00id", "é" * 5, "x" * 129):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_release_run_id(value)

    def test_release_run_id_validator_accepts_safe_ascii(self) -> None:
        from backend.common.snowpack_contracts import validate_release_run_id

        self.assertEqual(
            validate_release_run_id("snowpack-123-1-nepal-lower"),
            "snowpack-123-1-nepal-lower",
        )

    def test_release_api_does_not_generate_identity(self) -> None:
        from backend.common.awsome_runner import run_awsome_for_region
        from backend.common.regions import load_regions

        region = next(r for r in load_regions() if r.key == "himalayas_nepal")
        result = run_awsome_for_region(
            region=region,
            no_fallback=True,
            engine="snowpack_direct",
            run_id="",
            toolchain_manifest_id="tc",
            forcing_manifest_id="fm",
            geometry_manifest_id="gm",
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("run_id", result.get("error", "").lower())


class TestG03EngineContract(unittest.TestCase):
    """G0.3: the Python API must match the release CLI contract."""

    def test_acceptance_api_rejects_auto_engine(self) -> None:
        from backend.common.awsome_runner import run_awsome_for_region
        from backend.common.regions import load_regions

        region = next(r for r in load_regions() if r.key == "himalayas_nepal")
        result = run_awsome_for_region(
            region=region,
            no_fallback=True,
            engine="auto",
            run_id="run-g03",
            toolchain_manifest_id="tc",
            forcing_manifest_id="fm",
            geometry_manifest_id="gm",
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("engine", result.get("error", "").lower())


class TestG04ExecutableDelegation(unittest.TestCase):
    """G0.4: release delegation is proven by an executable call."""

    def test_runner_release_calls_canonical_orchestrator(self) -> None:
        from backend.common.awsome_runner import main as runner_main

        with patch(
            "backend.scripts.run_snowpack_release.run_release_orchestration",
            return_value=1,
        ) as orchestrator:
            result = runner_main([
                "--region", "himalayas_nepal",
                "--elevation-band", "lower",
                "--run-id", "run-g04",
                "--toolchain-id", "tc",
                "--forcing-id", "fm",
                "--geometry-id", "gm",
                "--engine", "snowpack_direct",
                "--no-fallback",
                "--release",
                "--output-bundle", "/tmp/g04-bundle",
            ])

        self.assertEqual(result, 1)
        orchestrator.assert_called_once()
        self.assertEqual(orchestrator.call_args.kwargs["run_id"], "run-g04")
        self.assertEqual(orchestrator.call_args.kwargs["engine"], "snowpack_direct")


class TestG05ToolchainSchemaBinding(unittest.TestCase):
    """G0.5: runtime schema and toolchain identity are exact, not truthy."""

    @staticmethod
    def _build_bundle(root: Path) -> None:
        from test_release_gate import _build_valid_bundle

        _build_valid_bundle(root)

    def test_wrong_toolchain_schema_version_fails_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build_bundle(root)
            path = root / "toolchain-manifest.json"
            data = json.loads(path.read_text())
            data["schema_version"] = "wrong-schema"
            path.write_text(json.dumps(data))
            self.assertEqual(_run_fixture_gate(root), 1)

    def test_result_toolchain_id_must_match_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build_bundle(root)
            result_path = root / "result.json"
            result = json.loads(result_path.read_text())
            result["toolchain_manifest_id"] = "different-toolchain"
            result_path.write_text(json.dumps(result))
            self.assertEqual(_run_fixture_gate(root), 1)

    def test_invalid_toolchain_commit_fails_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build_bundle(root)
            path = root / "toolchain-manifest.json"
            data = json.loads(path.read_text())
            data["meteoio_commit"] = "not-a-commit"
            path.write_text(json.dumps(data))
            self.assertEqual(_run_fixture_gate(root), 1)

    def test_tampered_approval_snapshot_context_fails_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build_bundle(root)
            snapshot_path = root / 'input-manifests' / 'approval-registry-snapshot.json'
            snapshot = json.loads(snapshot_path.read_text())
            snapshot['records']['forcing']['region'] = 'wrong-region'
            snapshot_path.write_text(json.dumps(snapshot, sort_keys=True, indent=2))
            result_path = root / 'result.json'
            result = json.loads(result_path.read_text())
            result['registry_snapshot']['sha256'] = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
            result_path.write_text(json.dumps(result))
            self.assertEqual(_run_fixture_gate(root), 1)


class TestG06SemanticManifestRegistry(unittest.TestCase):
    """G0.6: referenced manifest bytes must be semantic objects matching records."""

    def test_registry_rejects_semantic_kind_mismatch(self) -> None:
        from backend.common.snowpack_manifest_registry import (
            validate_release_manifest_ids,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = root / "manifests"
            manifests.mkdir()
            forcing = manifests / "forcing.json"
            forcing.write_text(
                json.dumps({
                    "id": "fm-1",
                    "kind": "geometry",
                    "source": "source",
                    "licence": "licence",
                    "units": "SI",
                    "region": "himalayas_nepal",
                    "elevation_band": "lower",
                    "valid_from": "2024-01-01T00:00:00Z",
                    "valid_to": "2025-01-01T00:00:00Z",
                    "approval_state": "approved",
                }),
                encoding="utf-8",
            )
            records = []
            for manifest_id, kind, filename in (
                ("fm-1", "forcing", "forcing.json"),
                ("gm-1", "geometry", "geometry.json"),
                ("tc-1", "toolchain", "toolchain.json"),
            ):
                path = manifests / filename
                if not path.exists():
                    path.write_text(
                        json.dumps({
                            "id": manifest_id,
                            "kind": kind,
                            "source": "source",
                            "licence": "licence",
                            "units": "SI",
                            "region": "himalayas_nepal",
                            "elevation_band": "lower",
                            "valid_from": "2024-01-01T00:00:00Z",
                            "valid_to": "2025-01-01T00:00:00Z",
                            "approval_state": "approved",
                        }),
                        encoding="utf-8",
                    )
                records.append({
                    "id": manifest_id,
                    "kind": kind,
                    "content_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "source": "source",
                    "licence": "licence",
                    "units": "SI",
                    "region": "himalayas_nepal",
                    "elevation_band": "lower",
                    "valid_from": "2024-01-01T00:00:00Z",
                    "valid_to": "2025-01-01T00:00:00Z",
                    "approval_state": "approved",
                    "manifest_path": f"manifests/{filename}",
                })
            registry = root / "registry.json"
            registry.write_text(json.dumps({
                "schema_version": "snowpack_manifest_registry_v1",
                "manifests": records,
            }), encoding="utf-8")
            errors = validate_release_manifest_ids(
                forcing_id="fm-1",
                geometry_id="gm-1",
                toolchain_id="tc-1",
                registry_path=registry,
                region_key="himalayas_nepal",
                elevation_band="lower",
            )
            self.assertTrue(any("kind" in error for error in errors), errors)


class TestG014PostprocessorStatus(unittest.TestCase):
    """G0.14: postprocessor input absence is not legacy execution skipped."""

    def test_legacy_skipped_normalizes_to_inputs_unavailable(self) -> None:
        from backend.common.postprocessor_adapters import normalize_postprocessor_status

        self.assertEqual(normalize_postprocessor_status("skipped"), "inputs_unavailable")

    def test_unknown_status_rejected(self) -> None:
        from backend.common.postprocessor_adapters import normalize_postprocessor_status

        with self.assertRaises(ValueError):
            normalize_postprocessor_status("completed")


if __name__ == "__main__":
    unittest.main()
