from pathlib import Path
import re
import unittest

from backend.common.regions import repo_root


def _workflow_text() -> str:
    return (repo_root() / '.github' / 'workflows' / 'ml_pipeline.yml').read_text(encoding='utf-8')


def _manual_workflow_text() -> str:
    return (repo_root() / '.github' / 'workflows' / 'ml_pipeline_manual.yml').read_text(encoding='utf-8')


def _legacy_training_workflow_text() -> str:
    return (repo_root() / '.github' / 'workflows' / 'train-avalanche-model.yml').read_text(encoding='utf-8')


class MlPipelineWorkflowTest(unittest.TestCase):
    def test_defaults_to_documented_himalayan_demo_regions(self) -> None:
        text = _workflow_text()
        expected_csv = 'himalayas_nepal,pir_panjal_nw_himalaya,shamshabari_nw_himalaya,great_himalaya_nw_himalaya,karakoram_&_ladakh'

        self.assertIn('Defaults to 5 Himalayan technical-reference regions; this configuration is not Himalayan validation evidence.', text)
        self.assertIn(f"default: '{expected_csv}'", text)
        self.assertIn(f"github.event.inputs.region_keys || '{expected_csv}'", text)
        self.assertIn('REQUIRE_FULL_GRID_PUBLICATION:', text)
        self.assertIn('proof_args=(--require-same-day-publication)', text)
        self.assertIn('proof_args+=(--require-full-grid-publication)', text)

    def test_inference_does_not_train_implicitly(self) -> None:
        text = _workflow_text()
        # Phase C: inference must NOT have a fallback training step
        self.assertNotIn('Train model if inference artifact is unavailable', text)
        # Extract only the infer job section to check for implicit training
        infer_section = text.split('  infer:')[1] if '  infer:' in text else text
        self.assertNotIn('python -m backend.train_model', infer_section)
        # Phase D: should have explicit pilot artifact restore instead
        self.assertIn('Restore pilot model artifact', text)
        self.assertIn('model_artifact_version', text)

    def test_preflight_asserts_project_ref(self) -> None:
        text = _workflow_text()
        # Phase E: preflight must assert project ref without printing secrets
        self.assertIn('eyyellmffzzujyssaayb', text)
        self.assertIn('PROJECT_REF', text)
        # Must not print full service role keys
        self.assertNotIn('SUPABASE_SERVICE_ROLE_KEY }}', text.replace('${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}', ''))

    def test_train_job_has_region_keys_input(self) -> None:
        text = _workflow_text()
        # Phase B: train job must accept TRAINING_REGION_KEYS env
        self.assertIn('TRAINING_REGION_KEYS', text)
        self.assertIn('training_region_keys', text)

    def test_scheduled_training_is_bounded_to_one_region(self) -> None:
        text = _workflow_text()
        self.assertIn("github.event_name == 'schedule' && '100'", text)
        self.assertIn("github.event_name == 'schedule' && 'himalayas_nepal'", text)

    def test_training_runs_metadata_only_preflight_before_model_fit(self) -> None:
        text = _workflow_text()
        preflight = text.index('Metadata-only training preflight')
        train = text.index('name: Train model')
        self.assertLess(preflight, train)
        self.assertIn('--artifact-root backend/artifacts', text[preflight:train])
        self.assertIn('--strict', text[preflight:train])

    def test_training_requires_explicit_mvp4_enablement_variable(self) -> None:
        text = _workflow_text()
        train_section = text.split('  train:', 1)[1].split('  infer:', 1)[0]
        self.assertIn("vars.MVP4_TRAINING_ENABLED == 'true'", train_section)
        self.assertIn('MVP4_TRAINING_ENABLED', train_section)

    def test_training_does_not_override_the_minimum_event_gate(self) -> None:
        text = _workflow_text()
        self.assertIn("MIN_EVENTS_FOR_TRAINING: '30'", text)
        self.assertNotIn("MIN_EVENTS_FOR_TRAINING: '10'", text)

    def test_training_cache_uses_the_exact_new_artifact_directory(self) -> None:
        text = _workflow_text()
        train_section = text.split('  infer:', 1)[0]
        cache_start = train_section.index('name: Cache model to Supabase Storage (pilot versioned path)')
        cache_section = train_section[cache_start:]

        self.assertIn('id: select_train_artifact', train_section)
        self.assertIn('ARTIFACT_DIR: ${{ steps.select_train_artifact.outputs.artifact_dir }}', cache_section)
        self.assertIn('src_path="${ARTIFACT_DIR}/${artifact_file}"', cache_section)
        self.assertNotIn('find backend/artifacts -name model.joblib -print -quit', cache_section)
        self.assertNotIn('find backend/artifacts -name "${artifact_file}" -print -quit', cache_section)

        infer_section = text.split('  infer:', 1)[1]
        infer_cache_start = infer_section.index('name: Cache model to Supabase Storage')
        infer_cache = infer_section[infer_cache_start:]
        self.assertIn('MODEL_SOURCE_DIR: backend/artifacts/${{ github.event.inputs.model_artifact_version || vars.MODEL_RECOVERY_VERSION ||', infer_cache)
        self.assertIn('src_path="${MODEL_SOURCE_DIR}/${artifact_file}"', infer_cache)
        self.assertNotIn('find backend/artifacts -name model.joblib -print -quit', infer_cache)
        self.assertNotIn('find backend/artifacts -name "${artifact_file}" -print -quit', infer_cache)

    def test_scheduled_inference_is_bounded_to_two_regions(self) -> None:
        text = _workflow_text()
        self.assertIn(
            "github.event_name == 'schedule' && 'himalayas_nepal,pir_panjal_nw_himalaya'",
            text,
        )

    def test_manual_weather_recovery_uses_declared_versioned_artifact(self) -> None:
        text = _manual_workflow_text()
        self.assertNotIn('find backend/artifacts -name model.joblib -print -quit', text)
        self.assertIn('recovery_dir="backend/artifacts/${MODEL_RECOVERY_VERSION}"', text)
        self.assertIn('if [ -f "${recovery_dir}/model.joblib" ]; then', text)
        self.assertIn('if [ -f "backend/artifacts/${MODEL_RECOVERY_VERSION}/model.joblib" ]; then', text)

    def test_training_workflows_use_the_corrected_hiaval_snapshot(self) -> None:
        for text in (_workflow_text(), _manual_workflow_text()):
            self.assertIn(
                'backend/data/open_source_labels/hiaval_hma_rebuilt_20260803/events.jsonl',
                text,
            )
            self.assertIn(
                'backend/data/open_source_labels/hiaval_hma_rebuilt_20260803/snapshot_manifest.json',
                text,
            )
            self.assertNotIn(
                'backend/data/open_source_labels/hiaval_hma/events.jsonl',
                text,
            )
            self.assertNotIn(
                'backend/data/open_source_labels/hiaval_hma/snapshot_manifest.json',
                text,
            )

    def test_legacy_edge_function_training_path_fails_closed_before_trigger(self) -> None:
        text = _legacy_training_workflow_text()
        guard = text.index('Block ungoverned legacy retraining')
        trigger = text.index('Trigger Avalanche Model Retraining')
        guard_section = text[guard:trigger]

        self.assertLess(guard, trigger)
        self.assertIn('reviewed MVP4 snapshot/preflight input', guard_section)
        self.assertIn('Use ml_pipeline.yml or public_ml_pilot.yml', guard_section)
        self.assertIn('exit 1', guard_section)
        self.assertNotIn('eyyellmffzzujyssaayb', text)


if __name__ == '__main__':
    unittest.main()
