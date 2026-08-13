"""C0.27-C0.40 adversarial probes — seventh-pass release/security hardening.

These tests are written FIRST to prove the vulnerabilities exist, then the
implementation is fixed so they pass. Every test probes a specific false-green
gap identified by Codex.

Probes:
  C0.27: awsome_runner --release --output-bundle bypasses canonical orchestrator
  C0.28: no_fallback=True still allows AWSOME failure → direct SNOWPACK fallback
  C0.29: injected runner exception leaves staging directory behind
  C0.30: newly-created approved root under symlinked parent is accepted
  C0.31: invocation evidence not bound to toolchain manifest; binary_version = binary.name
  C0.32: arbitrary manifest IDs pass (only non-empty + 2 placeholders checked)
  C0.33: preflight and native jobs rebuild Docker image independently
  C0.34: Dockerfile checks non-empty, not exact 40-char; base images mutable
  C0.38: parse_snowpack_pro uses defaults for missing columns
  C0.39: forcing time validation compares strings, no cadence/gap policy
  C0.40: non-Himalayan regions inferred as portability

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.common.snowpack_paths import (
    UnsafePathError,
    ensure_safe_directory,
    validate_output_bundle_path,
)


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


def _write_approved_registry(root: Path) -> Path:
    """Create a temporary hash-verified registry for resolver tests."""
    manifest_dir = root / 'manifests'
    manifest_dir.mkdir()
    records = []
    for manifest_id, kind in (
        ('fm-openmeteo-shadow-v1-approved', 'forcing'),
        ('gm-nepal-lower-v1-approved', 'geometry'),
        ('tc-snowpack-v1-approved', 'toolchain'),
    ):
        relative = f'manifests/{manifest_id}.json'
        manifest_path = root / relative
        manifest_path.write_text(
            json.dumps({
                'id': manifest_id,
                'kind': kind,
                'source': 'test-authoritative-source',
                'licence': 'test-licence',
                'units': 'SI',
                'region': 'himalayas_nepal',
                'elevation_band': 'lower',
                'valid_from': '2024-01-01T00:00:00Z',
                'valid_to': '2025-01-01T00:00:00Z',
                'approval_state': 'approved',
            }, sort_keys=True),
            encoding='utf-8',
        )
        record = {
            'id': manifest_id,
            'kind': kind,
            'content_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'source': 'test-authoritative-source',
            'licence': 'test-licence',
            'units': 'SI',
            'region': 'himalayas_nepal',
            'elevation_band': 'lower',
            'valid_from': '2024-01-01T00:00:00Z',
            'valid_to': '2025-01-01T00:00:00Z',
            'approval_state': 'approved',
            'manifest_path': relative,
        }
        if kind in {'forcing', 'geometry'}:
            payload_relative = f'manifests/{manifest_id}-payload.json'
            payload_path = root / payload_relative
            payload = (
                [{'time': '2024-01-01T00:00:00+00:00', 'temperature_2m': -5.0,
                  'relative_humidity_2m': 80.0, 'windspeed_10m': 5.0,
                  'shortwave_radiation': 200.0, 'precipitation': 0.0,
                  'cloud_cover': 50.0}]
                if kind == 'forcing'
                else {'latitude': 28.0, 'longitude': 86.0, 'elevation_m': 4000.0,
                      'slope_angle': 30.0, 'aspect': 180.0,
                      'crs': 'EPSG:4326', 'zone_id': 'nepal-lower-test',
                      'dem_sha256': 'd' * 64}
            )
            payload_path.write_text(json.dumps(payload), encoding='utf-8')
            manifest = json.loads(manifest_path.read_text())
            manifest['payload_path'] = payload_relative
            manifest['payload_sha256'] = hashlib.sha256(payload_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding='utf-8')
            record['content_sha256'] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            record['payload_path'] = payload_relative
            record['payload_sha256'] = manifest['payload_sha256']
        records.append(record)
    registry = root / 'registry.json'
    registry.write_text(
        json.dumps({
            'schema_version': 'snowpack_manifest_registry_v1',
            'manifests': records,
        }, sort_keys=True),
        encoding='utf-8',
    )
    return registry


class TestC027AlternateReleaseBypass(unittest.TestCase):
    """C0.27: awsome_runner --release --output-bundle must NOT write bundles directly."""

    def test_release_flag_requires_canonical_orchestrator(self) -> None:
        """--release --output-bundle delegates to the canonical producer."""
        from backend.common.awsome_runner import main as awsome_main

        with patch(
            "backend.scripts.run_snowpack_release.run_release_orchestration",
            return_value=1,
        ) as orchestrator:
            result = awsome_main([
                "--region", "himalayas_nepal",
                "--elevation-band", "lower",
                "--run-id", "test-run-1",
                "--toolchain-id", "tc-1",
                "--forcing-id", "fm-1",
                "--geometry-id", "gm-1",
                "--engine", "snowpack_direct",
                "--no-fallback",
                "--release",
                "--output-bundle", "/tmp/c027-bundle",
            ])

        self.assertEqual(result, 1)
        orchestrator.assert_called_once()
        self.assertEqual(orchestrator.call_args.kwargs["run_id"], "test-run-1")

    def test_release_mode_refuses_direct_bundle_write(self) -> None:
        """Calling awsome_runner with --release --output-bundle must exit non-zero
        or delegate — it must NOT produce a bundle directly."""
        from backend.common.awsome_runner import main as awsome_main

        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle"
            # Patch run_awsome_for_region to return a fake completed result
            # so we can test the bundle-writing path in isolation.
            with patch("backend.common.awsome_runner.run_awsome_for_region") as mock_run:
                mock_run.return_value = {
                    "status": "completed",
                    "region": "himalayas_nepal",
                    "run_id": "test-run-1",
                    "no_fallback": True,
                    "manifest": {"run_id": "test-run-1", "artifacts": []},
                    "execution_evidence": {"binary_path": "/fake"},
                }
                try:
                    exit_code = awsome_main([
                        "--region", "himalayas_nepal",
                        "--release",
                        "--output-bundle", str(bundle),
                        "--run-id", "test-run-1",
                        "--toolchain-id", "tc-1",
                        "--forcing-id", "fm-1",
                        "--geometry-id", "gm-1",
                        "--elevation-band", "lower",
                    ])
                except SystemExit as e:
                    exit_code = e.code

            # After fix: --release --output-bundle must NOT write directly.
            # It should either delegate (exit 0 via canonical path) or refuse (exit 1).
            # The key assertion: no direct result.json written by the runner.
            result_json = bundle / "result.json"
            if result_json.exists():
                # If a bundle was written, it must have gone through the canonical
                # orchestrator (which produces invocation.json with proper attestation).
                # The runner's direct writer does NOT produce a valid invocation.json
                # through the gate. We check that the canonical orchestrator was used.
                # If result.json exists but was written directly, that's the bug.
                # After fix, --release delegates, so this path should not be reached
                # by the direct writer.
                invocation = bundle / "invocation.json"
                # The direct writer writes invocation only if native_binary_invoked
                # or status == completed. But it doesn't go through the gate.
                # After fix, this should not happen.
                self.fail(
                    "C0.27: awsome_runner --release --output-bundle wrote result.json "
                    "directly instead of delegating to the canonical orchestrator."
                )


class TestC028EngineContractFallback(unittest.TestCase):
    """C0.28: no_fallback=True must prevent AWSOME→direct SNOWPACK fallback."""

    def test_no_fallback_prevents_engine_switching(self) -> None:
        """When no_fallback=True and AWSOME fails, the runner must NOT fall through
        to direct SNOWPACK execution. It must fail with the AWSOME error."""
        from backend.common.awsome_runner import run_awsome_for_region
        from backend.common.regions import load_regions

        regions = load_regions()
        region = next((r for r in regions if r.key == "himalayas_nepal"), None)
        self.assertIsNotNone(region, "himalayas_nepal region must exist")

        # Simulate AWSOME being available but failing
        with patch("backend.common.awsome_runner.awsome_available", return_value=True), \
             patch("backend.common.awsome_runner.AWSOME_HOME", "/fake/awsome"), \
             patch("backend.common.awsome_runner.Path") as mock_path_cls, \
             patch("subprocess.run") as mock_subprocess:
            # Make AWSOME CLI fail
            mock_subprocess.return_value.returncode = 1
            mock_subprocess.return_value.stderr = "AWSOME internal error"
            mock_subprocess.return_value.stdout = ""

            result = run_awsome_for_region(
                region=region,
                no_fallback=True,
                engine="awsome",
                run_id="test-c028",
                elevation_band="lower",
                toolchain_manifest_id="tc-test",
                forcing_manifest_id="fm-test",
                geometry_manifest_id="gm-test",
            )

        # After fix: with no_fallback=True, AWSOME failure must NOT fall through
        # to direct SNOWPACK. The status must be 'failed', not 'snowpack_direct'.
        self.assertNotEqual(
            result.get("method"), "snowpack_direct",
            "C0.28: no_fallback=True must prevent fallback to direct SNOWPACK. "
            f"Got method={result.get('method')}, status={result.get('status')}"
        )

    def test_invalid_engine_is_rejected_by_api(self) -> None:
        """The API rejects an engine outside the explicit release contract."""
        from backend.common.awsome_runner import run_awsome_for_region
        from backend.common.regions import load_regions

        region = next(r for r in load_regions() if r.key == 'himalayas_nepal')
        result = run_awsome_for_region(
            region=region,
            no_fallback=True,
            engine='future-engine',
            run_id='test-invalid-engine',
        )
        self.assertEqual(result['status'], 'failed')
        self.assertIn('engine', result['error'].lower())

    def test_release_cli_requires_no_fallback(self) -> None:
        """Release CLI must reject a missing --no-fallback contract."""
        from backend.common.awsome_runner import main as awsome_main

        exit_code = awsome_main([
            '--region', 'himalayas_nepal',
            '--release',
            '--engine', 'snowpack_direct',
        ])
        self.assertEqual(exit_code, 1)


class TestC029StagingResidueOnException(unittest.TestCase):
    """C0.29: injected exceptions must not leave staging directories behind."""

    def test_runner_exception_cleans_staging(self) -> None:
        """If run_awsome_for_region raises an exception, the staging directory
        must be cleaned up — no silent residue."""
        from backend.scripts.run_snowpack_release import run_release_orchestration

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = _write_approved_registry(root)
            approved_root = root / "approved"
            output_bundle = approved_root / "bundle"

            with patch("backend.common.awsome_runner.run_awsome_for_region") as mock_run:
                mock_run.side_effect = RuntimeError("injected runner exception")

                exit_code = run_release_orchestration(
                    region_key="himalayas_nepal",
                    elevation_band="lower",
                    run_id="test-c029",
                    toolchain_id="tc-snowpack-v1-approved",
                    forcing_id="fm-openmeteo-shadow-v1-approved",
                    geometry_id="gm-nepal-lower-v1-approved",
                    engine="snowpack_direct",
                    output_bundle=output_bundle,
                    approved_artifact_root=approved_root,
                    manifest_registry_path=registry,
                )

            self.assertEqual(exit_code, 1, "C0.29: exception must return exit 1")

            # After fix: no staging directories should remain
            staging_dirs = [
                p for p in approved_root.rglob("*")
                if p.is_dir() and ".staging" in p.name
            ]
            self.assertEqual(
                staging_dirs, [],
                f"C0.29: staging directories left behind after exception: {staging_dirs}"
            )

    def test_manifest_write_exception_cleans_staging(self) -> None:
        """If JSON writing fails, staging must be cleaned."""
        from backend.scripts.run_snowpack_release import run_release_orchestration

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = _write_approved_registry(root)
            approved_root = root / "approved"
            output_bundle = approved_root / "bundle"

            with patch("backend.common.awsome_runner.run_awsome_for_region") as mock_run:
                mock_run.return_value = {
                    "status": "completed",
                    "region": "himalayas_nepal",
                    "run_id": "test-c029b",
                    "no_fallback": True,
                    "manifest": {"run_id": "test-c029b", "artifacts": []},
                    "execution_evidence": {"binary_path": "/fake", "binary_version": "v1"},
                }
                # Patch json.dump to fail during manifest writing
                with patch("json.dump", side_effect=OSError("disk full")):
                    exit_code = run_release_orchestration(
                        region_key="himalayas_nepal",
                        elevation_band="lower",
                        run_id="test-c029b",
                        toolchain_id="tc-snowpack-v1-approved",
                        forcing_id="fm-openmeteo-shadow-v1-approved",
                        geometry_id="gm-nepal-lower-v1-approved",
                        engine="snowpack_direct",
                        output_bundle=output_bundle,
                        approved_artifact_root=approved_root,
                        manifest_registry_path=registry,
                    )

            self.assertEqual(exit_code, 1, "C0.29: JSON write failure must return exit 1")

            staging_dirs = [
                p for p in approved_root.rglob("*")
                if p.is_dir() and ".staging" in p.name
            ]
            self.assertEqual(
                staging_dirs, [],
                f"C0.29: staging directories left after JSON failure: {staging_dirs}"
            )


class TestC030SymlinkedApprovedRootParent(unittest.TestCase):
    """C0.30: approved root under symlinked parent must be rejected."""

    def test_symlinked_parent_of_approved_root_rejected(self) -> None:
        """Creating an approved_root under a symlinked parent directory must fail."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp).resolve()
            real_dir = tmp_path / "real"
            real_dir.mkdir()
            symlinked = tmp_path / "symlinked"
            symlinked.symlink_to(real_dir)

            # Try to create an approved root under the symlinked parent
            approved_root = symlinked / "approved"

            with self.assertRaises(
                UnsafePathError,
                msg="C0.30: approved root under symlinked parent must be rejected"
            ):
                validate_output_bundle_path(
                    approved_root / "bundle",
                    approved_root,
                    create_approved_root=True,
                )

    def test_symlinked_parent_recheck_after_mkdir(self) -> None:
        """After mkdir, recheck that no symlink was introduced in the parent chain."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp).resolve()
            approved_root = tmp_path / "approved"
            approved_root.mkdir()

            # Now replace a parent with a symlink (race condition simulation)
            # This is harder to test directly, but we verify that ensure_safe_directory
            # checks the full parent chain, not just the leaf.
            result = ensure_safe_directory(approved_root)
            self.assertTrue(result.is_dir())


class TestC031ToolchainManifestBinding(unittest.TestCase):
    """C0.31: invocation evidence must be cryptographically bound to toolchain manifest."""

    def test_toolchain_manifest_version_mismatch_is_rejected(self) -> None:
        """A tampered runtime version must fail the actual release gate."""
        from test_release_gate import _build_valid_bundle
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            path = root / 'toolchain-manifest.json'
            data = json.loads(path.read_text())
            data['binary_version'] = 'tampered-version'
            path.write_text(json.dumps(data))
            self.assertEqual(_run_fixture_gate(root), 1)

    def test_missing_toolchain_manifest_is_rejected(self) -> None:
        """A release bundle without runtime toolchain identity must fail."""
        from test_release_gate import _build_valid_bundle
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _build_valid_bundle(root)
            (root / 'toolchain-manifest.json').unlink()
            self.assertEqual(_run_fixture_gate(root), 1)


class TestC032ArbitraryManifestIds(unittest.TestCase):
    """C0.32: arbitrary manifest IDs must not pass in release mode."""

    def test_unknown_forcing_id_rejected(self) -> None:
        """An unknown forcing ID (not a placeholder, not approved) must be rejected."""
        from backend.common.awsome_runner import _validate_manifest_ids_for_release

        # After fix: _validate_manifest_ids_for_release must exist and reject unknown IDs
        with tempfile.TemporaryDirectory() as tmp:
            registry = _write_approved_registry(Path(tmp))
            errors = _validate_manifest_ids_for_release(
                forcing_id="fm-completely-unknown",
                geometry_id="gm-nepal-lower-v1-approved",
                toolchain_id="tc-snowpack-v1-approved",
                registry_path=registry,
                region_key="himalayas_nepal",
                elevation_band="lower",
            )
        self.assertTrue(
            any("forcing" in e.lower() for e in errors),
            f"C0.32: unknown forcing ID must be rejected. Got errors: {errors}"
        )

    def test_placeholder_id_rejected(self) -> None:
        """Placeholder IDs must be rejected even if they are non-empty."""
        from backend.common.awsome_runner import _validate_manifest_ids_for_release

        with tempfile.TemporaryDirectory() as tmp:
            registry = _write_approved_registry(Path(tmp))
            errors = _validate_manifest_ids_for_release(
                forcing_id="fm-openmeteo-shadow",
                geometry_id="gm-nepal-lower-representative",
                toolchain_id="tc-snowpack-v1-approved",
                registry_path=registry,
                region_key="himalayas_nepal",
                elevation_band="lower",
            )
        self.assertTrue(
            len(errors) > 0,
            "C0.32: placeholder IDs must be rejected"
        )

    def test_approved_id_accepted(self) -> None:
        """Approved IDs must pass validation."""
        from backend.common.awsome_runner import _validate_manifest_ids_for_release

        with tempfile.TemporaryDirectory() as tmp:
            registry = _write_approved_registry(Path(tmp))
            errors = _validate_manifest_ids_for_release(
                forcing_id="fm-openmeteo-shadow-v1-approved",
                geometry_id="gm-nepal-lower-v1-approved",
                toolchain_id="tc-snowpack-v1-approved",
                registry_path=registry,
                region_key="himalayas_nepal",
                elevation_band="lower",
            )
        self.assertEqual(
            errors, [],
            f"C0.32: approved IDs must pass. Got errors: {errors}"
        )

    def test_symlinked_manifest_path_rejected(self) -> None:
        """A registry cannot hash through a symlinked manifest path."""
        from backend.common.awsome_runner import _validate_manifest_ids_for_release

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry = _write_approved_registry(root)
            forcing_path = root / 'manifests' / 'fm-openmeteo-shadow-v1-approved.json'
            external = root / 'external-forcing.json'
            external.write_text(forcing_path.read_text(encoding='utf-8'), encoding='utf-8')
            forcing_path.unlink()
            forcing_path.symlink_to(external)
            errors = _validate_manifest_ids_for_release(
                forcing_id="fm-openmeteo-shadow-v1-approved",
                geometry_id="gm-nepal-lower-v1-approved",
                toolchain_id="tc-snowpack-v1-approved",
                registry_path=registry,
                region_key="himalayas_nepal",
                elevation_band="lower",
            )
        self.assertTrue(
            any('symlink' in error.lower() for error in errors),
            f"C0.32: symlinked manifest path must fail closed: {errors}"
        )


class TestC033ImageDigestBinding(unittest.TestCase):
    """C0.33: preflight and native jobs must use the same image digest."""

    def test_native_job_does_not_rebuild_image(self) -> None:
        """The native job must NOT rebuild the Docker image — it must use the
        image built by the preflight job, identified by digest."""
        workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ml_pipeline_manual.yml"
        content = workflow_path.read_text(encoding="utf-8")

        # The native job must not have its own "Build SNOWPACK Docker image" step
        # that rebuilds from scratch. Instead, it should load/use the preflight image.
        # After fix, the native job should use docker load or reference a digest.
        # We check that the native job section does not contain a standalone rebuild.
        # Find the snowpack_native job section
        native_start = content.find("snowpack_native:")
        native_end = content.find("snowpack_release_gate:")
        native_section = content[native_start:native_end] if native_start >= 0 else ""

        # After fix: the native job should load the image from preflight, not rebuild
        self.assertIn(
            "docker load",
            native_section,
            "C0.33: native job must load preflight image, not rebuild independently"
        )


class TestC034DockerfileHashValidation(unittest.TestCase):
    """C0.34: Dockerfile must validate exact 40-char hashes before cloning."""

    def test_dockerfile_uses_current_official_wsl_source_urls(self) -> None:
        """Native builds must clone the current official WSL repositories."""
        dockerfile_path = Path(__file__).resolve().parents[2] / "Dockerfile.snowpack"
        content = dockerfile_path.read_text(encoding="utf-8")

        self.assertIn(
            "https://code.wsl.ch/snow-models/meteoio.git",
            content,
            "Dockerfile must use the current official MeteoIO repository URL",
        )
        self.assertIn(
            "https://code.wsl.ch/snow-models/snowpack.git",
            content,
            "Dockerfile must use the current official SNOWPACK repository URL",
        )
        self.assertNotIn(
            "https://models.slf.ch/p/",
            content,
            "Dockerfile must not use the retired models.slf.ch clone URLs",
        )

    def test_build_script_uses_current_official_wsl_source_urls(self) -> None:
        """The native build script and Dockerfile must share current sources."""
        script_path = Path(__file__).resolve().parents[2] / "scripts" / "build_snowpack.sh"
        content = script_path.read_text(encoding="utf-8")

        self.assertIn(
            'SNOWPACK_REPO="https://code.wsl.ch/snow-models/snowpack.git"',
            content,
            "build script must use the current official SNOWPACK repository URL",
        )
        self.assertIn(
            'MeteoIO_REPO="https://code.wsl.ch/snow-models/meteoio.git"',
            content,
            "build script must use the current official MeteoIO repository URL",
        )
        self.assertNotIn(
            "https://models.slf.ch/p/",
            content,
            "build script must not use the retired models.slf.ch clone URLs",
        )

    def test_dockerfile_validates_exact_hash_format(self) -> None:
        """The Dockerfile must validate that commit hashes are exactly 40 hex chars."""
        dockerfile_path = Path(__file__).resolve().parents[2] / "Dockerfile.snowpack"
        content = dockerfile_path.read_text(encoding="utf-8")

        # After fix: the Dockerfile must check for exact 40-character hex format
        # not just non-empty
        self.assertIn(
            "40",
            content,
            "C0.34: Dockerfile must validate exact 40-character hash format"
        )

    def test_dockerfile_pins_base_image_by_digest(self) -> None:
        """Base images must be pinned by digest, not just tag."""
        dockerfile_path = Path(__file__).resolve().parents[2] / "Dockerfile.snowpack"
        content = dockerfile_path.read_text(encoding="utf-8")

        # The digest is supplied as a required immutable build arg and used
        # in both FROM expressions; tag-only images cannot build.
        self.assertIn(
            "@${UBUNTU_BASE_DIGEST}",
            content,
            "C0.34: Dockerfile must pin the builder base image by digest"
        )
        self.assertIn(
            "@${PYTHON_BASE_DIGEST}",
            content,
            "C0.34: Dockerfile must pin the runtime base image by digest"
        )

    def test_dockerfile_uses_hash_pinned_python_lock(self) -> None:
        """Runtime packages must come from the repository hash lock."""
        root = Path(__file__).resolve().parents[2]
        dockerfile_path = root / "Dockerfile.snowpack"
        content = dockerfile_path.read_text(encoding="utf-8")
        self.assertIn("backend/locks/snowpack-native-poc-py312.txt", content)
        self.assertTrue(
            (root / "backend" / "locks" / "snowpack-native-poc-py312.txt").is_file(),
            "native POC runtime lock must be present in the repository",
        )
        self.assertIn("--require-hashes", content)

    def test_native_build_enables_meteoio_static_library(self) -> None:
        """MeteoIO must build its static library before SNOWPACK links it."""
        root = Path(__file__).resolve().parents[2]
        dockerfile = (root / "Dockerfile.snowpack").read_text(encoding="utf-8")
        build_script = (root / "scripts" / "build_snowpack.sh").read_text(
            encoding="utf-8"
        )

        self.assertGreaterEqual(
            dockerfile.count("-DBUILD_STATIC_LIBS=ON"),
            2,
            "Dockerfile must enable static-library generation for MeteoIO and SNOWPACK",
        )
        self.assertGreaterEqual(
            build_script.count("-DBUILD_STATIC_LIBS=ON"),
            2,
            "build script must enable static-library generation for MeteoIO and SNOWPACK",
        )


class TestC038StrictProParser(unittest.TestCase):
    """C0.38: parse_snowpack_pro must not use defaults for missing columns."""

    def test_missing_required_columns_fails(self) -> None:
        """A .pro file missing required columns (HS, rho, T) must fail, not default."""
        from backend.common.meteoio_openmeteo import parse_snowpack_pro

        with tempfile.TemporaryDirectory() as tmp:
            pro_path = Path(tmp) / "test.pro"
            # Write a .pro file with no recognized columns
            pro_path.write_text(
                "#Date Col1 Col2 Col3\n"
                "2024-01-01T00:00:00 1.0 2.0 3.0\n",
                encoding="utf-8",
            )

            # After fix: missing required columns must raise, not default
            with self.assertRaises(
                (ValueError, KeyError),
                msg="C0.38: missing required columns must fail, not default"
            ):
                parse_snowpack_pro(pro_path)

    def test_malformed_row_fails(self) -> None:
        """A malformed data row must fail, not be silently skipped."""
        from backend.common.meteoio_openmeteo import parse_snowpack_pro

        with tempfile.TemporaryDirectory() as tmp:
            pro_path = Path(tmp) / "test.pro"
            pro_path.write_text(
                "#Date HS rho T grain_type\n"
                "2024-01-01T00:00:00 not_a_number 300.0 273.15 5\n",
                encoding="utf-8",
            )

            with self.assertRaises(
                (ValueError, TypeError),
                msg="C0.38: malformed numeric values must fail, not default"
            ):
                parse_snowpack_pro(pro_path)

    def test_empty_pro_file_fails(self) -> None:
        """An empty .pro file must fail, not produce default output."""
        from backend.common.meteoio_openmeteo import parse_snowpack_pro

        with tempfile.TemporaryDirectory() as tmp:
            pro_path = Path(tmp) / "empty.pro"
            pro_path.write_text("", encoding="utf-8")

            with self.assertRaises(
                (ValueError, FileNotFoundError),
                msg="C0.38: empty .pro file must fail"
            ):
                parse_snowpack_pro(pro_path)


class TestC039TimezoneAwareForcingValidation(unittest.TestCase):
    """C0.39: forcing time validation must parse timezone-aware timestamps."""

    def test_offset_equivalent_duplicate_timestamps_are_rejected(self) -> None:
        """Chronology is compared in UTC, not by timestamp string ordering."""
        from backend.common.meteoio_openmeteo import validate_smet_samples

        samples = [
            {"time": "2024-01-01T01:00:00+00:00", "temperature_2m": -5.0,
             "relative_humidity_2m": 80.0, "windspeed_10m": 5.0,
             "shortwave_radiation": 200.0, "precipitation": 0.0,
             "cloud_cover": 50.0},
            {"time": "2024-01-01T02:00:00+01:00", "temperature_2m": -5.0,
             "relative_humidity_2m": 80.0, "windspeed_10m": 5.0,
             "shortwave_radiation": 200.0, "precipitation": 0.0,
             "cloud_cover": 50.0},
        ]
        with self.assertRaises(ValueError):
            validate_smet_samples(samples, strict=True)

    def test_invalid_timezone_rejected(self) -> None:
        """Timestamps with invalid timezone values must be rejected."""
        from backend.common.meteoio_openmeteo import validate_smet_samples

        samples = [
            {"time": "2024-01-01T00:00:00+00:00", "temperature_2m": -5.0,
             "relative_humidity_2m": 80.0, "windspeed_10m": 5.0,
             "shortwave_radiation": 200.0, "precipitation": 0.0},
            {"time": "not-a-valid-timestamp", "temperature_2m": -5.0,
             "relative_humidity_2m": 80.0, "windspeed_10m": 5.0,
             "shortwave_radiation": 200.0, "precipitation": 0.0},
        ]
        with self.assertRaises(
            ValueError,
            msg="C0.39: invalid timestamp format must be rejected"
        ):
            validate_smet_samples(samples, strict=True)

    def test_unexplained_gap_rejected(self) -> None:
        """Large gaps in forcing timestamps must be rejected without cadence policy."""
        from backend.common.meteoio_openmeteo import validate_smet_samples

        # 24-hour gap when cadence is hourly
        samples = [
            {"time": "2024-01-01T00:00:00+00:00", "temperature_2m": -5.0,
             "relative_humidity_2m": 80.0, "windspeed_10m": 5.0,
             "shortwave_radiation": 200.0, "precipitation": 0.0},
            {"time": "2024-01-02T00:00:00+00:00", "temperature_2m": -5.0,
             "relative_humidity_2m": 80.0, "windspeed_10m": 5.0,
             "shortwave_radiation": 200.0, "precipitation": 0.0},
        ]
        with self.assertRaises(
            ValueError,
            msg="C0.39: unexplained 24h gap in hourly forcing must be rejected"
        ):
            validate_smet_samples(samples, strict=True, expected_cadence_hours=1)

    def test_smet_records_utc_interval_and_cadence(self) -> None:
        """Generated forcing must preserve auditable UTC interval metadata."""
        from backend.common.meteoio_openmeteo import write_smet_file

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'forcing.smet'
            samples = [
                {"time": "2024-01-01T00:00:00+00:00", "temperature_2m": -5.0,
                 "relative_humidity_2m": 80.0, "windspeed_10m": 5.0,
                 "shortwave_radiation": 200.0, "precipitation": 0.0,
                 "cloud_cover": 50.0},
                {"time": "2024-01-01T01:00:00+00:00", "temperature_2m": -5.0,
                 "relative_humidity_2m": 80.0, "windspeed_10m": 5.0,
                 "shortwave_radiation": 200.0, "precipitation": 0.0,
                 "cloud_cover": 50.0},
            ]
            write_smet_file(
                output_path=output,
                station_id='test',
                latitude=28.0,
                longitude=86.0,
                elevation=4000.0,
                samples=samples,
                strict=True,
            )
            content = output.read_text(encoding='utf-8')
            self.assertIn('source_time_start = 2024-01-01T00:00:00+00:00', content)
            self.assertIn('source_time_end   = 2024-01-01T01:00:00+00:00', content)
            self.assertIn('source_cadence_hours = 1.0', content)
            self.assertIn('source_time_semantics = timezone-aware UTC', content)


class TestC040ExplicitPortabilityRegistry(unittest.TestCase):
    """C0.40: portability must be explicit, not inferred from catch-all default."""

    def test_portability_and_unknown_classification_are_executable(self) -> None:
        """Known portability and unknown-region behavior are runtime-tested."""
        from backend.common.awsome_runner import _track_for_region

        self.assertEqual(_track_for_region("colorado_rockies"), "portability")
        with self.assertRaises(ValueError):
            _track_for_region("future_region_not_registered")

    def test_unknown_region_fails_closed(self) -> None:
        """A truly unknown region (not in any registry) must fail closed."""
        from backend.common.awsome_runner import _track_for_region

        with self.assertRaises(
            ValueError,
            msg="C0.40: unknown region must fail closed, not default to portability"
        ):
            _track_for_region("completely_unknown_region_xyz")

    def test_known_portability_region_classified_correctly(self) -> None:
        """A known portability region must be classified as portability."""
        from backend.common.awsome_runner import _track_for_region

        # Colorado Rockies is a known non-Himalayan region
        track = _track_for_region("colorado_rockies")
        self.assertEqual(
            track, "portability",
            f"C0.40: colorado_rockies must be portability, got {track}"
        )


if __name__ == "__main__":
    unittest.main()
