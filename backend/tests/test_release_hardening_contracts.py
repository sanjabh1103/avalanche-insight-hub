"""Static release-boundary contracts for the dual-repository publish path."""

from pathlib import Path
import re
import unittest
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReleaseHardeningContractTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    def test_seed_baselines_has_no_embedded_database_fallback(self) -> None:
        source = self.read("backend/scripts/seed_baselines.py")

        self.assertNotIn("eyyellmffzzujyssaayb", source)
        self.assertNotRegex(
            source,
            r"SUPABASE_DB_PASSWORD\s*['\"]?\s*,\s*['\"]",
        )
        self.assertIn("PGPASSWORD", source)
        self.assertIn("SUPABASE_DB_HOST", source)

    def test_synthetic_seed_requires_a_configured_supabase_url(self) -> None:
        source = self.read("scripts/seed_synthetic_events.py")

        self.assertNotIn("eyyellmffzzujyssaayb", source)
        self.assertIn("SUPABASE_URL is required", source)

    def test_orphan_scanner_uses_standard_supabase_database_host(self) -> None:
        source = self.read("backend/scripts/nuke_orphaned_s3.py")

        self.assertIn("SUPABASE_DB_HOST", source)
        self.assertIn("SUPABASE_DB_USER", source)
        self.assertIn("db.{project_ref}.supabase.co", source)

    def test_sync_requires_lease_protection_and_expected_public_sha(self) -> None:
        source = self.read("scripts/sync_to_public.sh")

        self.assertIn("--expected-public-sha", source)
        self.assertIn("--force-with-lease", source)
        self.assertIn("credential.helper=", source)
        self.assertIn("http.https://github.com/.extraheader", source)
        self.assertIn("PUBLIC_GIT_TOKEN", source)
        self.assertIn("git ls-remote", source)
        self.assertIn("git ls-remote origin", source)
        self.assertIn("Private origin main does not match", source)
        self.assertIn("--attestation-out", source)
        self.assertIn("expected_pre_push_public_commit", source)
        self.assertIn("verified_post_push_public_commit", source)
        self.assertNotIn("git push public \"${ORPHAN}:main\" --force", source)
        self.assertNotIn("sed -i ''", source)
        self.assertNotIn("for f in $(find", source)

    def test_public_sync_rewrites_workflows_without_yaml_boolean_on_key(self) -> None:
        source = self.read("scripts/sync_to_public.sh")

        self.assertIn("root_on = next", source)
        self.assertIn('path.write_text(text, encoding="utf-8")', source)
        self.assertIn("workflow_dispatch: {}", source)
        self.assertIn("boolean workflow key emitted", source)
        self.assertNotIn("yaml.dump(data", source)

    def test_public_sync_removes_private_poc_workflow(self) -> None:
        source = self.read("scripts/sync_to_public.sh")

        self.assertGreaterEqual(
            source.count(".github/workflows/poc_snowpack_pipeline.yml"),
            3,
        )
        self.assertIn("Private path remains in public tree", source)

    def test_ml_pipeline_dispatch_input_budget_and_literal_on_contract(self) -> None:
        source = self.read(".github/workflows/ml_pipeline.yml")

        self.assertRegex(source, r"(?m)^on:\s*$")
        self.assertNotRegex(source, r"(?m)^(?:true|True):\s*$")
        self.assertNotIn("anomaly_input_path:", source)
        self.assertIn("vars.ANOMALY_INPUT_PATH", source)

        import yaml

        workflow = yaml.safe_load(source)
        on_data = workflow.get(True, workflow.get("on", {})) or {}
        dispatch = on_data.get("workflow_dispatch") or {}
        self.assertLessEqual(len(dispatch.get("inputs") or {}), 25)

    def test_ml_pipeline_does_not_reference_undefined_dispatch_inputs(self) -> None:
        source = self.read(".github/workflows/ml_pipeline.yml")
        import yaml

        workflow = yaml.safe_load(source)
        on_data = workflow.get(True, workflow.get("on", {})) or {}
        dispatch = on_data.get("workflow_dispatch") or {}
        defined = set((dispatch.get("inputs") or {}).keys())
        referenced = set(re.findall(r"github\\.event\\.inputs\\.([A-Za-z0-9_-]+)", source))
        self.assertEqual(referenced - defined, set())

    def test_forward_migration_repairs_cron_url_resolution(self) -> None:
        migration_dir = REPO_ROOT / "supabase/migrations"
        migrations = list(migration_dir.glob("*_repair_cron_url_resolution.sql"))

        self.assertEqual(len(migrations), 1)
        source = migrations[0].read_text(encoding="utf-8")
        self.assertIn("get_supabase_url", source)
        self.assertIn("eyyellmffzzujyssaayb", source)

    def test_additive_migration_targets_canonical_project_and_poc_scope(self) -> None:
        migration = REPO_ROOT / (
            "supabase/migrations/20260810150000_repair_active_project_and_poc_scope.sql"
        )
        source = migration.read_text(encoding="utf-8")
        self.assertIn("https://eyyellmffzzujyssaayb.supabase.co", source)
        self.assertIn("decision_record_sha256", source)
        self.assertIn("ensemble_members", source)
        self.assertIn("pir_panjal_nw_himalaya", source)
        self.assertIn("horizon_hours = 48", source)

    def test_poc_workflow_uses_recursive_supabase_bundle_round_trip(self) -> None:
        source = self.read(".github/workflows/poc_snowpack_pipeline.yml")

        self.assertIn("python3 -m backend.scripts.supabase_bundle upload", source)
        self.assertIn("--source-dir \"/app/workspace/${BUNDLE_DIR}\"", source)
        self.assertIn("python3 -m backend.scripts.supabase_bundle download", source)
        self.assertIn("--output-dir supabase-native-artifacts", source)
        self.assertIn("--artifacts-dir supabase-native-artifacts", source)
        self.assertIn("--expected-decision-record-sha256", source)
        self.assertNotIn("STORAGE_BASE=", source)
        self.assertNotIn("for artifact_file in result.json", source)

    def test_retention_preserves_published_forecast_run_records(self) -> None:
        migration = REPO_ROOT / (
            "supabase/migrations/20260810170000_preserve_published_runs_in_retention.sql"
        )
        source = migration.read_text(encoding="utf-8")
        delete_start = source.index("  DELETE FROM public.forecast_runs")
        delete_block = source[delete_start:source.index("\n  GET DIAGNOSTICS deleted_runs", delete_start)]

        self.assertIn("active = FALSE", delete_block)
        self.assertIn("publication_status NOT IN ('validated', 'published')", delete_block)
        self.assertIn("status <> 'ready'", delete_block)

    def test_retention_batches_forecast_run_deletes(self) -> None:
        migration = REPO_ROOT / (
            "supabase/migrations/20260810171000_bound_forecast_run_retention.sql"
        )
        source = migration.read_text(encoding="utf-8")
        delete_start = source.index("  WITH eligible_runs AS (")
        delete_block = source[delete_start:source.index("\n  GET DIAGNOSTICS deleted_runs", delete_start)]

        self.assertIn("LIMIT 500", delete_block)
        self.assertIn("DELETE FROM public.forecast_runs AS r", delete_block)

    def test_poc_consumer_job_does_not_spend_minutes_after_native_failure(self) -> None:
        source = self.read(".github/workflows/poc_snowpack_pipeline.yml")
        gate_start = source.index("  snowpack_release_gate:")
        gate_block = source[gate_start:]

        self.assertIn("if: needs.snowpack_native.result == 'success'", gate_block)

    def test_retention_sweeps_stale_snowpack_runs(self) -> None:
        migration = REPO_ROOT / (
            "supabase/migrations/20260810172000_schedule_stale_snowpack_cleanup.sql"
        )
        source = migration.read_text(encoding="utf-8")

        self.assertIn("PERFORM public.cleanup_stale_snowpack_runs();", source)
        self.assertIn("CREATE OR REPLACE FUNCTION public.cleanup_stale_snowpack_runs()", source)
        self.assertIn("updated_at < now() - INTERVAL '30 days'", source)

    def test_retention_functions_are_private_and_storage_safe(self) -> None:
        migration = REPO_ROOT / (
            "supabase/migrations/20260810173000_lock_down_retention_and_storage_order.sql"
        )
        source = migration.read_text(encoding="utf-8")

        for function_name in (
            "get_capacity_snapshot()",
            "cleanup_stale_snowpack_runs()",
            "cleanup_forecast_retention(interval, integer, integer)",
        ):
            self.assertIn(
                f"REVOKE ALL ON FUNCTION public.{function_name} FROM PUBLIC, anon, authenticated;",
                source,
            )
        self.assertIn("GRANT EXECUTE ON FUNCTION public.cleanup_forecast_retention", source)
        self.assertIn("FROM storage.objects AS o", source)
        self.assertIn("public.forecast_run_hours", source)
        self.assertIn("Storage references remain", source)

    def test_active_supabase_examples_use_canonical_target(self) -> None:
        for relative_path in ('.env.local.example', 'SUPABASE_SETUP_GUIDE.md'):
            source = self.read(relative_path)
            self.assertIn('eyyellmffzzujyssaayb', source)
            self.assertNotIn('eyyellmffzzujyssaayb', source)
            self.assertNotIn('eyyellmffzzujyssaayb', source)

    def test_orphan_scan_is_not_scheduled_without_s3_credentials(self) -> None:
        source = self.read(".github/workflows/ml_pipeline.yml")

        self.assertNotIn("orphan-scan:", source)
        self.assertNotIn("orphan_scan", source)

    def test_backend_requirements_declare_the_audit_dependencies(self) -> None:
        source = self.read("backend/requirements.txt")
        core = self.read("backend/requirements-core.in")
        lock = self.read("backend/locks/core-py312.txt")

        self.assertIn("pdfplumber==0.11.9", source)
        self.assertRegex(source, r"(?m)^pyshp==")
        self.assertRegex(source, r"(?m)^timm==")
        self.assertIn("torch==2.13.0", core)
        self.assertIn("torch==2.13.0 \\", lock)
        self.assertIn("torchvision==0.28.0 \\", lock)
        self.assertNotIn("torch==2.12.1 \\", lock)
        self.assertIn("setuptools==83.0.0", core)
        self.assertIn("setuptools==83.0.0", lock)
        self.assertNotIn("setuptools==81.0.0", lock)

    def test_public_release_validation_has_zero_input_dispatch(self) -> None:
        source = self.read(".github/workflows/public_release_validation.yml")

        self.assertIn("workflow_dispatch:", source)
        self.assertNotIn("inputs:", source)
        self.assertIn("public-release-manifest.json", source)
        self.assertIn("schema_version", source)
        self.assertIn("migration_tree_sha256", source)
        self.assertIn("workflow_tree_sha256", source)
        self.assertIn("removed_paths", source)
        self.assertIn("hashlib.sha256", source)

    def test_public_release_preserves_pre_remote_gate_contract(self) -> None:
        source = self.read(".github/workflows/public_release_validation.yml")

        self.assertIn("verify_mvp4_pre_remote_gate.py", source)
        self.assertIn("mvp4_pre_remote_approval.template.json", source)
        self.assertIn("mvp4_pre_remote_gate_v1", source)
        self.assertIn("blocked_pre_remote_gate", source)
        self.assertIn("scope_manifest_sha256", source)
        self.assertIn("must resolve under the repository root", source)
        self.assertIn("prepare_mvp4_pre_remote_approval.py", source)
        self.assertIn("non-empty name or approval_ref", source)
        self.assertIn('"approval_ref"', source)
        self.assertIn("MVP4_PRE_REMOTE_SCOPE_MANIFEST", source)
        self.assertIn("MVP4_PRE_REMOTE_APPROVAL_MANIFEST", source)
        self.assertIn("ml_pipeline_manual.yml", source)

    def test_public_release_preserves_shadow_scope_contract(self) -> None:
        validator = self.read("scripts/verify_mvp4_shadow_scope_approval.py")
        template = self.read("schemas/mvp4_shadow_scope_approval.template.json")
        release_validator = self.read(".github/workflows/public_release_validation.yml")

        self.assertIn('SCHEMA_VERSION = "mvp4_shadow_scope_approval_v1"', validator)
        self.assertIn("APPROVED_SHADOW_ONLY", validator)
        self.assertIn("required_false = (", validator)
        for required_false_field in (
            '"model_fit_allowed"',
            '"training_eligible"',
            '"production_scoring_eligible"',
            '"remote_pilot_allowed"',
        ):
            self.assertIn(required_false_field, validator)
        self.assertIn("policy.get(field) is not False", validator)
        self.assertIn('"decision": "PENDING"', template)
        self.assertIn('"shadow_only": true', template)
        self.assertIn('"model_fit_allowed": false', template)
        self.assertIn('"source_rights_and_api_scope": "PENDING"', template)
        self.assertIn("source_rights_and_api_scope", release_validator)
        self.assertIn("shadow-scope validator is missing", release_validator)
        self.assertIn("mvp4_shadow_scope_approval_v1", release_validator)

    def test_public_release_validation_enforces_legacy_training_fail_closed(self) -> None:
        source = self.read(".github/workflows/public_release_validation.yml")

        self.assertIn('train-avalanche-model.yml', source)
        self.assertIn('Block ungoverned legacy retraining', source)
        self.assertIn('reviewed MVP4 snapshot/preflight input', source)
        self.assertIn('Use ml_pipeline.yml or public_ml_pilot.yml', source)
        self.assertIn('legacy_guard < legacy_trigger', source)
        self.assertIn('exit 1', source)

    def test_ml_pilot_is_bounded_to_one_region(self) -> None:
        source = self.read(".github/workflows/public_ml_pilot.yml")

        self.assertIn("workflow_dispatch:", source)
        self.assertIn("TRAINING_REGION_KEYS: himalayas_nepal", source)
        self.assertIn("SAMPLES_PER_REGION: '100'", source)
        self.assertIn("TRAINING_SNOWPACK_PROXY_MODE: regional_day", source)
        self.assertIn("model-artifacts/${run_id}", source)
        self.assertIn("MIN_EVENTS_FOR_TRAINING: '30'", source)
        self.assertNotIn("MIN_EVENTS_FOR_TRAINING: '10'", source)
        self.assertNotIn("pir_panjal_nw_himalaya", source)

    def test_ml_pilot_verifies_remote_artifact_restore(self) -> None:
        source = self.read(".github/workflows/public_ml_pilot.yml")

        self.assertIn("Download and verify remote pilot artifact", source)
        self.assertIn("sha256sum", source)
        self.assertIn("joblib.load", source)
        self.assertIn("json.loads", source)

    def test_ml_pilot_requires_explicit_reviewed_snapshot_inputs(self) -> None:
        source = self.read(".github/workflows/public_ml_pilot.yml")

        self.assertIn("snapshot_manifest:", source)
        self.assertIn("snapshot_events:", source)
        self.assertIn("snapshot_overlap_report:", source)
        self.assertIn("snapshot_source_key:", source)
        self.assertIn("snapshot_role:", source)
        self.assertIn("snapshot_license_review_id:", source)
        self.assertIn("SNAPSHOT_MANIFEST: ${{ github.event.inputs.snapshot_manifest }}", source)
        self.assertIn("OPEN_SOURCE_LABEL_SNAPSHOT: ${{ github.event.inputs.snapshot_events }}", source)
        self.assertIn("SNAPSHOT_OVERLAP_REPORT: ${{ github.event.inputs.snapshot_overlap_report }}", source)
        self.assertIn("snapshot manifest events_path does not match dispatch input", source)
        self.assertIn("snapshot manifest overlap report does not match dispatch input", source)
        self.assertIn("snapshot manifest source_key does not match dispatch input", source)

    def test_ml_pilot_requires_pre_remote_attestation_before_training(self) -> None:
        source = self.read(".github/workflows/public_ml_pilot.yml")

        self.assertIn("pre_remote_scope_manifest:", source)
        self.assertIn("pre_remote_approval_manifest:", source)
        self.assertIn("PRE_REMOTE_SCOPE_MANIFEST: ${{ github.event.inputs.pre_remote_scope_manifest }}", source)
        self.assertIn("PRE_REMOTE_APPROVAL_MANIFEST: ${{ github.event.inputs.pre_remote_approval_manifest }}", source)
        gate = source.index("Fail-closed pre-remote MVP4 gate")
        train = source.index("python -m backend.train_model")
        self.assertLess(gate, train)
        self.assertIn("--scope-manifest", source[gate:train])
        self.assertIn("--approval-manifest", source[gate:train])

    def test_ml_pilot_containment_covers_pre_remote_attestations(self) -> None:
        source = self.read(".github/workflows/public_ml_pilot.yml")

        self.assertIn(
            'pre_remote_scope_manifest_path = resolve_repo_file(sys.argv[10], "pre-remote scope manifest")',
            source,
        )
        self.assertIn(
            'pre_remote_approval_manifest_path = resolve_repo_file(sys.argv[11], "pre-remote approval manifest")',
            source,
        )
        self.assertIn('"${PRE_REMOTE_SCOPE_MANIFEST}" "${PRE_REMOTE_APPROVAL_MANIFEST}"', source)
        self.assertIn("pre-remote scope manifest", source)
        self.assertIn("pre-remote approval manifest", source)

    def test_surrogate_training_paths_require_pre_remote_gate(self) -> None:
        sections = {
            ".github/workflows/ml_pipeline.yml": self.read(
                ".github/workflows/ml_pipeline.yml"
            ).split("  train:", 1)[1].split("  infer:", 1)[0],
            ".github/workflows/ml_pipeline_manual.yml": self.read(
                ".github/workflows/ml_pipeline_manual.yml"
            ).split("  backfill:", 1)[1].split("  sar_backfill:", 1)[0],
        }
        for workflow_path, section in sections.items():
            gate = section.index("Fail-closed pre-remote MVP4 gate")
            train = section.index("python -m backend.train_model")
            self.assertLess(gate, train, workflow_path)
            self.assertLess(gate, section.index("Install Python dependencies"), workflow_path)
            for required_value in (
                "PRE_REMOTE_SCOPE_MANIFEST",
                "PRE_REMOTE_APPROVAL_MANIFEST",
                "SOURCE_REQUEST_MANIFEST",
                "SOURCE_REQUEST_PAYLOAD",
                "SOURCE_REQUEST_EVENTS_JSONL",
                "--scope-manifest",
                "--approval-manifest",
            ):
                self.assertIn(required_value, section[gate:train], workflow_path)

    def test_every_local_train_model_entrypoint_has_metadata_preflight(self) -> None:
        workflow_paths = (
            ".github/workflows/ml_pipeline.yml",
            ".github/workflows/ml_pipeline_manual.yml",
            ".github/workflows/public_ml_pilot.yml",
        )
        for workflow_path in workflow_paths:
            source = self.read(workflow_path)
            preflight = source.index("Metadata-only training preflight")
            train = source.index("python -m backend.train_model")
            self.assertLess(preflight, train, workflow_path)
            if workflow_path.endswith("public_ml_pilot.yml"):
                self.assertIn('--artifact-root "${PILOT_ARTIFACT_ROOT}"', source[preflight:train], workflow_path)
            else:
                self.assertIn("--artifact-root backend/artifacts", source[preflight:train], workflow_path)
            self.assertIn('--snapshot-manifest "${SNAPSHOT_MANIFEST}"', source[preflight:train], workflow_path)
            self.assertIn('--region-keys "${TRAINING_REGION_KEYS}"', source[preflight:train], workflow_path)
            self.assertIn("--strict", source[preflight:train], workflow_path)

    def test_mts_lstm_shadow_training_has_metadata_preflight_before_dispatch(self) -> None:
        source = self.read(".github/workflows/ml_pipeline.yml")
        section = source.split("  train_mtslstm:", 1)[1].split("  infer_mtslstm:", 1)[0]

        preflight = section.index("Metadata-only training preflight")
        dispatch = section.index("Dispatch MTS-LSTM training worker")
        self.assertLess(preflight, dispatch)
        self.assertIn("--snapshot-manifest \"${SNAPSHOT_MANIFEST}\"", section[preflight:dispatch])
        self.assertIn("--region-keys \"${TRAINING_REGION_KEYS}\"", section[preflight:dispatch])
        self.assertIn("--strict", section[preflight:dispatch])
        self.assertIn('"snapshot_manifest": "${SNAPSHOT_MANIFEST}"', section[dispatch:])
        self.assertIn('"training_region_keys": "${TRAINING_REGION_KEYS}"', section[dispatch:])
        self.assertIn('"shadow_mode": true', section[dispatch:])
        self.assertIn('"allow_publish": false', section[dispatch:])

    def test_mts_lstm_shadow_training_requires_pre_remote_gate(self) -> None:
        source = self.read(".github/workflows/ml_pipeline.yml")
        section = source.split("  train_mtslstm:", 1)[1].split("  infer_mtslstm:", 1)[0]

        gate = section.index("Fail-closed pre-remote MVP4 gate")
        dispatch = section.index("Dispatch MTS-LSTM training worker")
        self.assertLess(gate, dispatch)
        for required_value in (
            "PRE_REMOTE_SCOPE_MANIFEST",
            "PRE_REMOTE_APPROVAL_MANIFEST",
            "SOURCE_REQUEST_MANIFEST",
            "SOURCE_REQUEST_PAYLOAD",
            "SOURCE_REQUEST_EVENTS_JSONL",
            "--scope-manifest",
            "--approval-manifest",
        ):
            self.assertIn(required_value, section[gate:dispatch])

    def test_sar_training_requires_explicit_mvp4_enablement(self) -> None:
        source = self.read(".github/workflows/ml_pipeline.yml")
        section = source.split("  train_sar_unet:", 1)[1].split("  train_mtslstm:", 1)[0]

        self.assertIn("vars.MVP4_TRAINING_ENABLED == 'true'", section)
        self.assertIn("vars.MVP4_SAR_TRAINING_ENABLED == 'true'", section)

    def test_train_model_entrypoint_rechecks_reviewed_snapshot_gate(self) -> None:
        import backend.train_model as train_model

        with patch.object(train_model, 'TRAINING_PREFLIGHT_STRICT', True), \
             patch.object(train_model, 'TRAINING_RESEARCH_OVERRIDE', False), \
             patch.dict('os.environ', {'SNAPSHOT_MANIFEST': ''}, clear=False):
            result = train_model._reviewed_snapshot_preflight()

        self.assertFalse(result['passed'])
        self.assertIn('required', ' '.join(result['errors']))

    def test_scheduled_ml_paths_are_artifact_first_and_region_day_bounded(self) -> None:
        source = self.read(".github/workflows/ml_pipeline.yml")

        self.assertIn("TRAINING_SNOWPACK_PROXY_MODE: regional_day", source)
        self.assertIn("No model.joblib found and no model_artifact_version specified", source)
        self.assertNotIn("Train model if inference artifact is unavailable", source)
        self.assertIn("--approximate-tree-shap", source)
        self.assertIn("tree_shap_approximate", self.read("backend/daily_inference.py"))


if __name__ == "__main__":
    unittest.main()
