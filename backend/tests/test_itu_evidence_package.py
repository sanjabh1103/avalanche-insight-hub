"""Focused contract tests for the ITU evidence-package generator."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.generate_itu_evidence_package import (
    EVIDENCE_LANE,
    EvidencePackageError,
    SCIENCE_ARTIFACTS,
    compare_pro_files,
    load_source_attestation,
    parse_runtime_log,
    proof_card_rows,
    recompute_repeatability,
    validate_toolchain_manifest,
    write_proof_card_csv,
)


class ItuEvidencePackageTests(unittest.TestCase):
    def test_pro_timestamp_only_difference_is_normalized_and_proven(self) -> None:
        first = b"[HEADER]\n#2026-08-13T10:00:33, Snowpack DEFAULT version 3.7.0\nDATA\n1\n"
        second = b"[HEADER]\n#2026-08-13T10:46:54, Snowpack DEFAULT version 3.7.0\nDATA\n1\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_path = root / "first.pro"
            second_path = root / "second.pro"
            first_path.write_bytes(first)
            second_path.write_bytes(second)
            result = compare_pro_files(first_path, second_path)
        self.assertFalse(result["exact_match"])
        self.assertTrue(result["physics_content_identical"])
        self.assertIn("exactly one", result["normalization"])

    def test_same_size_non_timestamp_difference_is_rejected(self) -> None:
        first = b"[HEADER]\n#2026-08-13T10:00:33, Snowpack DEFAULT version 3.7.0\nDATA=1\n"
        second = b"[HEADER]\n#2026-08-13T10:46:54, Snowpack DEFAULT version 3.7.0\nDATA=2\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_path = root / "first.pro"
            second_path = root / "second.pro"
            first_path.write_bytes(first)
            second_path.write_bytes(second)
            result = compare_pro_files(first_path, second_path)
        self.assertFalse(result["physics_content_identical"])
        self.assertEqual(result["note"], "normalized profile content differs")

    def test_repeatability_requires_all_four_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run"
            repeat = root / "repeat"
            run.mkdir()
            repeat.mkdir()
            for filename, _ in SCIENCE_ARTIFACTS[:-1]:
                (run / filename).write_bytes(b"same")
                (repeat / filename).write_bytes(b"same")
            result = recompute_repeatability(run, repeat)
        self.assertIn(SCIENCE_ARTIFACTS[-1][0], result["missing_artifacts"])
        self.assertEqual(result["repeatability_result"], "FAIL_MISSING_ARTIFACTS")

    def test_runtime_log_counts_explicit_levels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.log"
            path.write_text(
                "[stdout]\ncompleted\n[stderr]\n[W] advisory\n[E] failure\n",
                encoding="utf-8",
            )
            result = parse_runtime_log(path)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["warning_count"], 1)

    def test_source_attestation_mismatch_and_dirty_state_fail_closed(self) -> None:
        source_sha = subprocess.check_output(
            ["git", "rev-parse", "--verify", "HEAD^{commit}"],
            text=True,
        ).strip()
        different_sha = subprocess.check_output(
            ["git", "rev-parse", "--verify", "HEAD^"],
            text=True,
        ).strip()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run-source-attestation.json"
            base = {
                "schema_version": "itu_run_source_attestation_v1",
                "captured_before_native_execution": True,
                "capture_method": "runner_preflight_git_identity",
                "run_source_sha": source_sha,
                "worktree_dirty_at_capture": False,
            }
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(EvidencePackageError, "mismatch"):
                load_source_attestation(path, different_sha)
            base["worktree_dirty_at_capture"] = True
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(EvidencePackageError, "dirty"):
                load_source_attestation(path, source_sha)

    def test_toolchain_manifest_values_are_cross_bound(self) -> None:
        manifest = {
            "binary_sha256": "a" * 64,
            "binary_version": "Snowpack 3.7.0",
            "image_id": "sha256:" + "b" * 64,
            "image_archive_sha256": "c" * 64,
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "toolchain-manifest-v16.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            native = {
                "binary_sha256": manifest["binary_sha256"],
                "binary_version": "Snowpack   3.7.0",
                "image_id": manifest["image_id"],
                "image_archive_sha256": manifest["image_archive_sha256"],
                "toolchain_manifest_path": "/run/input-manifests/toolchain-manifest-v16.json",
                "toolchain_manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "toolchain_manifest": manifest,
            }
            self.assertEqual(validate_toolchain_manifest(path, native), manifest)
            native["image_id"] = "sha256:" + "d" * 64
            with self.assertRaisesRegex(ValueError, "mismatch"):
                validate_toolchain_manifest(path, native)

    def test_proof_card_rows_are_structured_without_markdown_separator(self) -> None:
        summary = {
            "evidence_lane": EVIDENCE_LANE,
            "run_source_sha": "a" * 64,
            "package_generation_sha": "b" * 64,
            "provenance_status": {"run_source_sha": "verified"},
            "decision_record_sha256": "c" * 64,
            "run_id": "run",
            "status": "completed",
            "evidence_class": "pipeline-proof-only",
            "native_execution": {
                "end_date": "2024-02-23T23:00",
                "runtime_error_count": 0,
                "runtime_warning_count": 0,
                "exit_code": 0,
                "binary_sha256": "d" * 64,
                "image_id": "sha256:" + "e" * 64,
                "image_archive_sha256": "f" * 64,
            },
            "source": {
                "source_id": "source",
                "model_id": "model",
                "sample_count": 1,
                "source_sample_count": 1,
                "warmup_hours": 0,
                "core_null_count": 0,
            },
            "profile_summary": {
                "snow_height_m": 1,
                "layer_count": 1,
                "weak_layer_depth_m": 0,
                "bulk_density_kgm3": 1,
                "snowpack_stability_index": 1,
                "weak_layer_grain_type": "none",
                "weak_layer_shear_strength_kpa": 1,
            },
            "forcing_manifest_sha256": "1" * 64,
            "case_manifest_sha256": "2" * 64,
            "toolchain_manifest_sha256": "3" * 64,
            "repeatability": {
                "exact_hash_matches": 4,
                "total_artifacts_compared": 4,
                "result": "PASS",
                "pro_physics_content_identical": True,
            },
            "license_review_status": "pending",
            "scope": "pipeline_integrity_proof_only_not_scientific_validation",
            "non_claims": ["no_accuracy_claim"],
        }
        rows = proof_card_rows(summary)
        self.assertEqual(rows[0], ("evidence_lane", EVIDENCE_LANE))
        self.assertNotIn(("-------", "-------"), rows)

    def test_proof_card_csv_has_lf_line_endings_and_no_blank_eof(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proof-card.csv"
            write_proof_card_csv(path, [("field_name", "value")])
            content = path.read_bytes()
        self.assertNotIn(b"\r\n", content)
        self.assertTrue(content.endswith(b"\n"))
        self.assertFalse(content.endswith(b"\n\n"))
        self.assertNotIn(b"-------", content)


if __name__ == "__main__":
    unittest.main()
