from __future__ import annotations

import json
import hashlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.prepare_mvp4_pre_remote_approval import build_draft_approval
from scripts.verify_mvp4_pre_remote_gate import ROOT, _path_matches, evaluate_pre_remote_gate


class Mvp4PreRemoteGateTests(unittest.TestCase):
    def test_relative_approval_paths_bind_to_repository_root(self) -> None:
        previous_cwd = os.getcwd()
        try:
            with TemporaryDirectory() as tmpdir:
                os.chdir(tmpdir)
                self.assertTrue(
                    _path_matches(
                        "schemas/mvp4_pre_remote_approval.template.json",
                        ROOT / "schemas/mvp4_pre_remote_approval.template.json",
                    )
                )
        finally:
            os.chdir(previous_cwd)

    def test_missing_inputs_fail_closed(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            report = evaluate_pre_remote_gate(
                scope_manifest=root / "scope.json",
                approval_manifest=root / "approval.json",
                snapshot_manifest=root / "snapshot.json",
                artifact_root=root / "artifacts",
                source_request_manifest=root / "source.json",
                source_request_payload=root / "payload.bin",
                source_request_events=root / "events.jsonl",
                selected_region_keys=["himalayas_nepal"],
            )

        self.assertFalse(report["passed"])
        self.assertEqual(report["decision"], "blocked_pre_remote_gate")
        self.assertGreaterEqual(len(report["blockers"]), 4)
        self.assertTrue(any("scope manifest" in value for value in report["blockers"]))
        self.assertTrue(any("approval manifest" in value for value in report["blockers"]))
        self.assertTrue(any("snapshot manifest" in value for value in report["blockers"]))

    def test_evidence_inputs_must_resolve_inside_repository(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact_root = root / "artifacts"
            artifact_root.mkdir()
            report = evaluate_pre_remote_gate(
                scope_manifest=root / "scope.json",
                approval_manifest=root / "approval.json",
                snapshot_manifest=root / "snapshot.json",
                artifact_root=artifact_root,
                source_request_manifest=root / "source.json",
                source_request_payload=root / "payload.bin",
                source_request_events=root / "events.jsonl",
                selected_region_keys=["himalayas_nepal"],
            )

        self.assertFalse(report["passed"])
        self.assertGreaterEqual(
            sum("must resolve under the repository root" in value for value in report["blockers"]),
            7,
        )

    def test_scope_and_approval_hashes_are_bound(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            scope = root / "scope.json"
            snapshot = root / "snapshot.json"
            approval = root / "approval.json"
            scope.write_text(
                json.dumps({
                    "release_candidate_ready": True,
                    "decision": "GO",
                    "selection_hash": "a" * 64,
                }),
                encoding="utf-8",
            )
            snapshot.write_text(
                json.dumps({
                    "training_eligible": True,
                    "production_scoring_eligible": False,
                    "label_time_contract": "exact_time_core_v1",
                }),
                encoding="utf-8",
            )
            approval.write_text(
                json.dumps({
                    "schema_version": "mvp4_pre_remote_approval_v1",
                    "decision": "GO",
                    "scope_manifest_path": str(scope),
                    "scope_manifest_sha256": "0" * 64,
                    "snapshot_manifest_path": str(snapshot),
                    "snapshot_manifest_sha256": "0" * 64,
                    "approved_candidate_selection_hash": "b" * 64,
                    "selected_region_keys": ["himalayas_nepal"],
                    "approved_by": [
                        {"role": "scientist", "name": "redacted"},
                        {"role": "customer", "name": "redacted"},
                    ],
                    "approved_at": "2026-08-04T00:00:00Z",
                }),
                encoding="utf-8",
            )
            report = evaluate_pre_remote_gate(
                scope_manifest=scope,
                approval_manifest=approval,
                snapshot_manifest=snapshot,
                artifact_root=root / "artifacts",
                source_request_manifest=root / "source.json",
                source_request_payload=root / "payload.bin",
                source_request_events=root / "events.jsonl",
                selected_region_keys=["himalayas_nepal"],
            )

        self.assertFalse(report["passed"])
        self.assertTrue(any("scope manifest hash" in value for value in report["blockers"]))
        self.assertTrue(any("snapshot manifest hash" in value for value in report["blockers"]))
        self.assertTrue(any("selection hash" in value for value in report["blockers"]))

    def test_approval_requires_attributable_reviewer_identity(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            scope = root / "scope.json"
            snapshot = root / "snapshot.json"
            approval = root / "approval.json"
            artifact_root = root / "artifacts"
            artifact_root.mkdir()
            scope.write_text(
                json.dumps({
                    "release_candidate_ready": True,
                    "decision": "GO",
                    "selection_hash": "a" * 64,
                    "selected_paths": ["scripts/example.py"],
                }),
                encoding="utf-8",
            )
            snapshot.write_text(
                json.dumps({
                    "training_eligible": True,
                    "production_scoring_eligible": False,
                    "label_time_contract": "exact_time_core_v1",
                }),
                encoding="utf-8",
            )

            def digest(path: Path) -> str:
                return hashlib.sha256(path.read_bytes()).hexdigest()

            approval.write_text(
                json.dumps({
                    "schema_version": "mvp4_pre_remote_approval_v1",
                    "decision": "GO",
                    "scope_manifest_path": str(scope),
                    "scope_manifest_sha256": digest(scope),
                    "snapshot_manifest_path": str(snapshot),
                    "snapshot_manifest_sha256": digest(snapshot),
                    "approved_candidate_selection_hash": "a" * 64,
                    "selected_region_keys": ["himalayas_nepal"],
                    "approved_by": [
                        {"role": "scientist", "name": None},
                        {"role": "customer", "name": ""},
                    ],
                    "approved_at": "2026-08-04T00:00:00Z",
                }),
                encoding="utf-8",
            )
            report = evaluate_pre_remote_gate(
                scope_manifest=scope,
                approval_manifest=approval,
                snapshot_manifest=snapshot,
                artifact_root=artifact_root,
                source_request_manifest=root / "source.json",
                source_request_payload=root / "payload.bin",
                source_request_events=root / "events.jsonl",
                selected_region_keys=["himalayas_nepal"],
            )

        self.assertFalse(report["passed"])
        self.assertTrue(
            any("non-empty name or approval_ref" in value for value in report["blockers"])
        )

    def test_approval_draft_is_pending_and_hash_bound(self) -> None:
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            scope = root / "scope.json"
            snapshot = root / "snapshot.json"
            scope.write_text(
                json.dumps({"selection_hash": "a" * 64, "selected_paths": ["scripts/example.py"]}),
                encoding="utf-8",
            )
            snapshot.write_text(json.dumps({"snapshot_schema_version": "test_fixture_v1"}), encoding="utf-8")
            draft = build_draft_approval(
                scope_manifest=scope,
                snapshot_manifest=snapshot,
                selected_region_keys=["himalayas_nepal"],
            )

        self.assertEqual(draft["decision"], "PENDING")
        self.assertTrue(draft["scope_manifest_path"].endswith("/scope.json"))
        self.assertTrue(draft["snapshot_manifest_path"].endswith("/snapshot.json"))
        self.assertEqual(draft["selected_region_keys"], ["himalayas_nepal"])
        self.assertEqual(len(draft["scope_manifest_sha256"]), 64)
        self.assertEqual(len(draft["snapshot_manifest_sha256"]), 64)
        self.assertEqual(len(draft["approved_candidate_selection_hash"]), 64)
        self.assertIsNone(draft["approved_at"])

    def test_approval_draft_rejects_paths_outside_repository(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scope = root / "scope.json"
            snapshot = root / "snapshot.json"
            scope.write_text(json.dumps({"selection_hash": "a" * 64}), encoding="utf-8")
            snapshot.write_text(json.dumps({}), encoding="utf-8")
            with self.assertRaises(ValueError):
                build_draft_approval(
                    scope_manifest=scope,
                    snapshot_manifest=snapshot,
                    selected_region_keys=["himalayas_nepal"],
                )


class ShadowBundleVerifierIntegrationTests(unittest.TestCase):
    """Integration tests proving the shadow-bundle verifier is wired into the gate.

    These tests verify that:
    1. A valid shadow bundle does not enable training (training remains blocked)
    2. A tampered bundle blocks the gate
    3. A missing bundle directory blocks the gate
    4. A shadow pass cannot be mistaken for a training GO
    """

    def _build_shadow_artifact(self, tmpdir: Path) -> Path:
        """Build a minimal valid shadow artifact and return its directory."""
        import sys
        sys.path.insert(0, str(ROOT))
        from backend.tests.test_preflight_shadow_nepal import _build_artifact, _label

        labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:2")]
        artifact_dir, _ = _build_artifact(tmpdir, labels)
        return artifact_dir

    def test_valid_shadow_bundle_does_not_enable_training(self) -> None:
        """A valid shadow bundle must pass the verifier but NOT enable training."""
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            shadow_dir = self._build_shadow_artifact(root)

            # Run just the shadow-bundle verifier (not the full pre-remote gate,
            # which requires approval manifests etc.)
            from backend.scripts.preflight_shadow_nepal import run_preflight
            report = run_preflight(shadow_dir, repo_root=ROOT)

            self.assertTrue(report["structural_pass"])
            self.assertTrue(report["coverage_pass"])
            self.assertTrue(report["training_blocked"])
            self.assertTrue(report["overall_pass"])
            # A shadow pass must NOT set training_eligible
            self.assertFalse(report["training_blocked"] is False)

    def test_tampered_shadow_bundle_blocks_gate(self) -> None:
        """A tampered shadow bundle must block the pre-remote gate."""
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            shadow_dir = self._build_shadow_artifact(root)

            # Tamper: modify features.jsonl
            features_path = shadow_dir / "features.jsonl"
            content = features_path.read_text()
            features_path.write_text(content + json.dumps({"tampered": True}) + "\n")

            from backend.scripts.preflight_shadow_nepal import run_preflight
            report = run_preflight(shadow_dir, repo_root=ROOT)

            self.assertFalse(report["structural_pass"])
            self.assertFalse(report["overall_pass"])

    def test_shadow_bundle_verifier_in_pre_remote_gate(self) -> None:
        """The shadow-bundle verifier is invoked when --shadow-bundle-dir is provided."""
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            shadow_dir = self._build_shadow_artifact(root)

            # Create minimal placeholder files for required gate inputs
            for fname in ["scope.json", "approval.json", "snapshot.json",
                          "source.json", "payload.bin", "events.jsonl"]:
                (root / fname).write_text("{}")
            (root / "artifacts").mkdir(exist_ok=True)

            report = evaluate_pre_remote_gate(
                scope_manifest=root / "scope.json",
                approval_manifest=root / "approval.json",
                snapshot_manifest=root / "snapshot.json",
                artifact_root=root / "artifacts",
                source_request_manifest=root / "source.json",
                source_request_payload=root / "payload.bin",
                source_request_events=root / "events.jsonl",
                selected_region_keys=["himalayas_nepal"],
                shadow_bundle_dir=shadow_dir,
            )

            # The gate should be blocked (because the placeholder files are invalid),
            # but the shadow_bundle_verifier field should be present in the report
            self.assertIn("shadow_bundle_verifier", report)
            # The shadow verifier itself should have been invoked
            self.assertIsNotNone(report["shadow_bundle_verifier"])
            # The shadow verifier should report training_blocked=True
            self.assertTrue(report["shadow_bundle_verifier"].get("training_blocked"))

    def test_tampered_shadow_bundle_adds_blocker_to_gate(self) -> None:
        """A tampered shadow bundle must add a blocker to the pre-remote gate."""
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            shadow_dir = self._build_shadow_artifact(root)

            # Tamper: modify features.jsonl
            features_path = shadow_dir / "features.jsonl"
            content = features_path.read_text()
            features_path.write_text(content + json.dumps({"tampered": True}) + "\n")

            # Create minimal placeholder files
            for fname in ["scope.json", "approval.json", "snapshot.json",
                          "source.json", "payload.bin", "events.jsonl"]:
                (root / fname).write_text("{}")
            (root / "artifacts").mkdir(exist_ok=True)

            report = evaluate_pre_remote_gate(
                scope_manifest=root / "scope.json",
                approval_manifest=root / "approval.json",
                snapshot_manifest=root / "snapshot.json",
                artifact_root=root / "artifacts",
                source_request_manifest=root / "source.json",
                source_request_payload=root / "payload.bin",
                source_request_events=root / "events.jsonl",
                selected_region_keys=["himalayas_nepal"],
                shadow_bundle_dir=shadow_dir,
            )

            self.assertFalse(report["passed"])
            # The shadow-bundle verifier should have added a blocker
            self.assertTrue(
                any("shadow-bundle" in b for b in report["blockers"]),
                f"Expected shadow-bundle blocker in: {report['blockers']}",
            )


class AttestationValidationTests(unittest.TestCase):
    """Tests for attestation validation in the pre-remote gate (G3, G9)."""

    def _build_shadow_artifact(self, tmpdir: Path) -> Path:
        import sys
        sys.path.insert(0, str(ROOT))
        from backend.tests.test_preflight_shadow_nepal import _build_artifact, _label
        labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:2")]
        artifact_dir, _ = _build_artifact(tmpdir, labels)
        return artifact_dir

    def _generate_valid_attestation(self, artifact_dir: Path) -> Path:
        """Generate a valid attestation and return its path."""
        from backend.scripts.generate_release_attestation import generate_attestation
        # Run preflight first so a report exists
        from backend.scripts.preflight_shadow_nepal import run_preflight
        run_preflight(artifact_dir, repo_root=ROOT)
        attestation = generate_attestation(artifact_dir, repo_root=ROOT)
        att_path = artifact_dir / "release_attestation.json"
        att_path.write_text(
            json.dumps(attestation, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return att_path

    def test_missing_attestation_blocks_gate(self) -> None:
        """Omitting --attestation must block the gate (fail-closed)."""
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            shadow_dir = self._build_shadow_artifact(root)
            for fname in ["scope.json", "approval.json", "snapshot.json",
                          "source.json", "payload.bin", "events.jsonl"]:
                (root / fname).write_text("{}")
            (root / "artifacts").mkdir(exist_ok=True)

            report = evaluate_pre_remote_gate(
                scope_manifest=root / "scope.json",
                approval_manifest=root / "approval.json",
                snapshot_manifest=root / "snapshot.json",
                artifact_root=root / "artifacts",
                source_request_manifest=root / "source.json",
                source_request_payload=root / "payload.bin",
                source_request_events=root / "events.jsonl",
                selected_region_keys=["himalayas_nepal"],
                shadow_bundle_dir=shadow_dir,
                # attestation_path omitted — should block
            )

            self.assertFalse(report["passed"])
            self.assertTrue(
                any("attestation path is required" in b for b in report["blockers"]),
                f"Expected attestation required blocker in: {report['blockers']}",
            )

    def test_stale_attestation_blocks_gate(self) -> None:
        """A stale attestation (bundle hash mismatch) must block the gate (G9)."""
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            shadow_dir = self._build_shadow_artifact(root)
            att_path = self._generate_valid_attestation(shadow_dir)

            # Tamper with the attestation: change the bundle_sha256
            att = json.loads(att_path.read_text())
            att["bundle_sha256"] = "0" * 64  # Wrong hash
            # Recompute attestation_sha256 so it's internally consistent
            att_bytes = json.dumps(
                {k: v for k, v in att.items() if k != "attestation_sha256"},
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")
            att["attestation_sha256"] = hashlib.sha256(att_bytes).hexdigest()
            att_path.write_text(json.dumps(att, indent=2, sort_keys=True) + "\n")

            for fname in ["scope.json", "approval.json", "snapshot.json",
                          "source.json", "payload.bin", "events.jsonl"]:
                (root / fname).write_text("{}")
            (root / "artifacts").mkdir(exist_ok=True)

            report = evaluate_pre_remote_gate(
                scope_manifest=root / "scope.json",
                approval_manifest=root / "approval.json",
                snapshot_manifest=root / "snapshot.json",
                artifact_root=root / "artifacts",
                source_request_manifest=root / "source.json",
                source_request_payload=root / "payload.bin",
                source_request_events=root / "events.jsonl",
                selected_region_keys=["himalayas_nepal"],
                shadow_bundle_dir=shadow_dir,
                attestation_path=att_path,
            )

            self.assertFalse(report["passed"])
            self.assertTrue(
                any("bundle_sha256_matches_verifier" in b for b in report["blockers"]),
                f"Expected bundle hash mismatch blocker in: {report['blockers']}",
            )

    def test_tampered_attestation_hash_blocks_gate(self) -> None:
        """An attestation with a wrong attestation_sha256 must block the gate."""
        with TemporaryDirectory(dir=ROOT) as tmpdir:
            root = Path(tmpdir)
            shadow_dir = self._build_shadow_artifact(root)
            att_path = self._generate_valid_attestation(shadow_dir)

            # Tamper with the attestation hash directly
            att = json.loads(att_path.read_text())
            att["attestation_sha256"] = "0" * 64  # Wrong hash
            att_path.write_text(json.dumps(att, indent=2, sort_keys=True) + "\n")

            for fname in ["scope.json", "approval.json", "snapshot.json",
                          "source.json", "payload.bin", "events.jsonl"]:
                (root / fname).write_text("{}")
            (root / "artifacts").mkdir(exist_ok=True)

            report = evaluate_pre_remote_gate(
                scope_manifest=root / "scope.json",
                approval_manifest=root / "approval.json",
                snapshot_manifest=root / "snapshot.json",
                artifact_root=root / "artifacts",
                source_request_manifest=root / "source.json",
                source_request_payload=root / "payload.bin",
                source_request_events=root / "events.jsonl",
                selected_region_keys=["himalayas_nepal"],
                shadow_bundle_dir=shadow_dir,
                attestation_path=att_path,
            )

            self.assertFalse(report["passed"])
            self.assertTrue(
                any("attestation_sha256_matches_recomputed" in b for b in report["blockers"]),
                f"Expected attestation hash mismatch blocker in: {report['blockers']}",
            )


class PreflightSiblingPrefixTests(unittest.TestCase):
    """G7: Path containment must use Path.relative_to(), not string prefix."""

    def test_sibling_prefix_not_accepted(self) -> None:
        """A path like /repo_evil/file must not be accepted as within /repo."""
        from backend.scripts.preflight_shadow_nepal import _is_within
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "repo"
            base.mkdir()
            sibling = Path(tmpdir) / "repo_evil"
            sibling.mkdir()
            target = sibling / "file.json"
            target.write_text("{}")

            # _is_within must reject the sibling
            self.assertFalse(_is_within(target, base))

    def test_child_path_accepted(self) -> None:
        """A path within base must be accepted."""
        from backend.scripts.preflight_shadow_nepal import _is_within
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "repo"
            base.mkdir()
            child = base / "subdir" / "file.json"
            child.parent.mkdir(parents=True)
            child.write_text("{}")

            self.assertTrue(_is_within(child, base))


class PreflightArgparseTests(unittest.TestCase):
    """G8: Preflight CLI must use argparse with proper --help and error handling."""

    def test_help_does_not_crash(self) -> None:
        """--help should print usage and exit 0."""
        from backend.scripts.preflight_shadow_nepal import main
        try:
            main(["--help"])
        except SystemExit as e:
            self.assertEqual(e.code, 0)

    def test_unknown_arg_rejected(self) -> None:
        """Unknown arguments should be rejected by argparse."""
        from backend.scripts.preflight_shadow_nepal import main
        with self.assertRaises(SystemExit) as ctx:
            main(["--unknown-flag"])
        self.assertEqual(ctx.exception.code, 2)

    def test_missing_artifact_dir_rejected(self) -> None:
        """Missing artifact_dir positional should be rejected."""
        from backend.scripts.preflight_shadow_nepal import main
        with self.assertRaises(SystemExit) as ctx:
            main([])
        self.assertEqual(ctx.exception.code, 2)


class WorkflowStaticTests(unittest.TestCase):
    """G1: All workflow files must pass --shadow-bundle-dir and --attestation to the gate."""

    def test_ml_pipeline_yml_has_shadow_bundle_dir(self) -> None:
        workflow = ROOT / ".github" / "workflows" / "ml_pipeline.yml"
        content = workflow.read_text()
        self.assertIn("--shadow-bundle-dir", content)
        self.assertIn("--attestation", content)
        self.assertIn("SHADOW_BUNDLE_DIR", content)
        self.assertIn("SHADOW_ATTESTATION", content)

    def test_ml_pipeline_manual_yml_has_shadow_bundle_dir(self) -> None:
        workflow = ROOT / ".github" / "workflows" / "ml_pipeline_manual.yml"
        content = workflow.read_text()
        self.assertIn("--shadow-bundle-dir", content)
        self.assertIn("--attestation", content)
        self.assertIn("SHADOW_BUNDLE_DIR", content)
        self.assertIn("SHADOW_ATTESTATION", content)

    def test_public_ml_pilot_yml_has_shadow_bundle_dir(self) -> None:
        workflow = ROOT / ".github" / "workflows" / "public_ml_pilot.yml"
        content = workflow.read_text()
        self.assertIn("--shadow-bundle-dir", content)
        self.assertIn("--attestation", content)
        self.assertIn("SHADOW_BUNDLE_DIR", content)
        self.assertIn("SHADOW_ATTESTATION", content)

    def test_public_ml_pilot_yml_has_required_inputs(self) -> None:
        """public_ml_pilot.yml must declare shadow_bundle_dir and shadow_attestation as required inputs."""
        workflow = ROOT / ".github" / "workflows" / "public_ml_pilot.yml"
        content = workflow.read_text()
        self.assertIn("shadow_bundle_dir:", content)
        self.assertIn("shadow_attestation:", content)
        self.assertIn("required: true", content)

    def test_snowpack_preflight_reaches_native_and_release_modes(self) -> None:
        """C0.17: Native/release modes must be covered by toolchain preflight."""
        workflow = (ROOT / ".github" / "workflows" / "ml_pipeline_manual.yml").read_text()
        preflight = workflow.split('  snowpack_toolchain_preflight:', 1)[1].split('  snowpack_native:', 1)[0]
        self.assertIn("github.event.inputs.mode == 'snowpack_physics'", preflight)
        self.assertIn("github.event.inputs.mode == 'snowpack_native'", preflight)
        self.assertIn("github.event.inputs.mode == 'snowpack_release'", preflight)
        native = workflow.split('  snowpack_native:', 1)[1].split('  snowpack_release_gate:', 1)[0]
        self.assertIn('needs: snowpack_toolchain_preflight', native)

    def test_runtime_toolchain_manifest_is_verified_not_builder_paths(self) -> None:
        """C0.18: Runtime verification must use embedded manifest, not /build paths."""
        workflow = (ROOT / ".github" / "workflows" / "ml_pipeline_manual.yml").read_text()
        native = workflow.split('  snowpack_native:', 1)[1].split('  snowpack_release_gate:', 1)[0]
        self.assertIn('toolchain-manifest.json', native)
        self.assertNotIn('/build/meteoio', native)
        self.assertNotIn('/build/snowpack', native)
        dockerfile = (ROOT / 'Dockerfile.snowpack').read_text()
        self.assertIn('/opt/snowpack/toolchain-manifest.json', dockerfile)
        self.assertIn("tr '\\r\\n\\t'", dockerfile)


if __name__ == "__main__":
    unittest.main()
