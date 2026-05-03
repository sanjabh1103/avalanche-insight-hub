from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = REPO_ROOT / '.github' / 'workflows'
FULL_SHA_ACTION = re.compile(r'uses:\s+actions/[A-Za-z0-9._-]+@[0-9a-f]{40}\b')


class GitHubRolloutPolicyTests(unittest.TestCase):
    def test_actions_are_pinned_to_full_commit_shas(self) -> None:
        unpinned: list[str] = []
        for path in sorted(WORKFLOW_ROOT.glob('*.yml')):
            for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
                stripped = line.strip()
                if not stripped.startswith('uses: actions/'):
                    continue
                if not FULL_SHA_ACTION.search(stripped):
                    unpinned.append(f'{path.name}:{lineno}:{stripped}')

        self.assertFalse(
            unpinned,
            msg='Unpinned GitHub-hosted actions found:\n' + '\n'.join(unpinned),
        )

    def test_production_environment_guards_release_jobs(self) -> None:
        modal_deploy = (WORKFLOW_ROOT / 'modal_deploy.yml').read_text(encoding='utf-8')
        ml_pipeline = (WORKFLOW_ROOT / 'ml_pipeline.yml').read_text(encoding='utf-8')
        bootstrap_gate = (WORKFLOW_ROOT / 'bootstrap_pinned_gate.yml').read_text(encoding='utf-8')

        self.assertRegex(
            modal_deploy,
            r'jobs:\n  deploy:\n(?:    .*\n)*?    environment: production\n',
        )
        for job_name in ('sar_segment', 'train_mtslstm', 'infer_mtslstm', 'evaluate_release'):
            self.assertRegex(
                ml_pipeline,
                rf'  {job_name}:\n(?:    .*\n)*?    environment: production\n',
            )
        self.assertIn('reference_set_key is required for the official evaluate_release gate.', ml_pipeline)
        self.assertIn('if [ -n "${REFERENCE_SET_KEY}" ]; then', ml_pipeline)
        self.assertIn('"reference_set_key": "${REFERENCE_SET_KEY}"', ml_pipeline)
        self.assertIn('"prediction_model_version": "${PREDICTION_MODEL_VERSION}"', ml_pipeline)
        self.assertIn('"persist_events": false', ml_pipeline)
        self.assertRegex(
            bootstrap_gate,
            r'jobs:\n  bootstrap:\n(?:    .*\n)*?    environment: production\n',
        )

    def test_ml_infer_is_manual_only_after_batch_precompute_cutover(self) -> None:
        ml_pipeline = (WORKFLOW_ROOT / 'ml_pipeline.yml').read_text(encoding='utf-8')

        self.assertNotIn("- cron: '0 2 * * *'", ml_pipeline)
        self.assertIn("if: github.event_name == 'workflow_dispatch' && github.event.inputs.mode == 'infer'", ml_pipeline)

    def test_bootstrap_pinned_gate_is_manual_only_and_allowlisted(self) -> None:
        bootstrap_gate = (WORKFLOW_ROOT / 'bootstrap_pinned_gate.yml').read_text(encoding='utf-8')

        self.assertIn('workflow_dispatch:', bootstrap_gate)
        self.assertNotIn('pull_request:', bootstrap_gate)
        self.assertNotIn('\npush:\n', bootstrap_gate)
        self.assertIn('group: bootstrap-pinned-gate', bootstrap_gate)
        self.assertIn('DATASET_URL:', bootstrap_gate)
        self.assertIn('SAR_RASTER_URL:', bootstrap_gate)
        self.assertIn('BOOTSTRAP_MODE:', bootstrap_gate)
        self.assertIn("default: 'authoritative'", bootstrap_gate)
        self.assertIn("- authoritative", bootstrap_gate)
        self.assertIn("- canary", bootstrap_gate)
        self.assertIn('Direct truth/vector held-out archive URL on an allowlisted academic or trusted cloud mirror host', bootstrap_gate)
        self.assertIn(
            'Direct Sentinel-1 VV/VH GeoTIFF archive URL on an allowlisted cloud or EO host; use the same URL as DATASET_URL only for a bundled AvalCD-style archive that already contains truth plus bi-temporal SAR members',
            bootstrap_gate,
        )
        self.assertIn("wget \"${DATASET_URL}\" -O truth_archive.zip", bootstrap_gate)
        self.assertIn('if [ "${DATASET_URL}" = "${SAR_RASTER_URL}" ]; then', bootstrap_gate)
        self.assertIn('cp truth_archive.zip sar_rasters.zip', bootstrap_gate)
        self.assertIn("wget \"${SAR_RASTER_URL}\" -O sar_rasters.zip", bootstrap_gate)
        for host in (
            'envidat.ch',
            'www.envidat.ch',
            'zenodo.org',
            'www.zenodo.org',
            'slf.ch',
            'www.slf.ch',
            'storage.googleapis.com',
            's3.amazonaws.com',
            'dataspace.copernicus.eu',
            ".s3.amazonaws.com",
        ):
            self.assertIn(host, bootstrap_gate)
        self.assertIn("validate_url('DATASET_URL', exact_hosts=truth_allowed_hosts, host_suffixes=truth_allowed_suffixes)", bootstrap_gate)
        self.assertIn("if os.environ['DATASET_URL'] == os.environ['SAR_RASTER_URL']:", bootstrap_gate)
        self.assertIn('backend.scripts.assemble_seed_archive', bootstrap_gate)
        self.assertIn('backend.scripts.seed_snowslide_truth', bootstrap_gate)
        self.assertIn('--validate-only', bootstrap_gate)
        self.assertIn('--source-dir assembled_seed_dir', bootstrap_gate)
        self.assertIn('--non-authoritative', bootstrap_gate)
        self.assertIn('Preflight assembled Sentinel-1 SAR dataset', bootstrap_gate)
        self.assertIn('backend.scripts.materialize_release_baseline_masks', bootstrap_gate)
        self.assertIn('--no-activate', bootstrap_gate)
        self.assertIn('canary mode must not target the production reference set key snowslide-heldout-v1', bootstrap_gate)
        self.assertIn("expected_status = 'active' if mode == 'authoritative' else 'draft'", bootstrap_gate)
        self.assertIn("expected_authoritative = mode == 'authoritative'", bootstrap_gate)

    def test_trigger_job_admin_path_requires_supabase_auth_and_allowlists(self) -> None:
        trigger_job = (REPO_ROOT / 'supabase' / 'functions' / 'trigger-job' / 'index.ts').read_text(encoding='utf-8')

        self.assertIn('auth.getUser(token)', trigger_job)
        self.assertIn('ADMIN_USER_IDS', trigger_job)
        self.assertIn('ADMIN_USER_EMAILS', trigger_job)
        self.assertIn('ad hoc evaluation manifests require admin privileges', trigger_job)
        self.assertIn("gate_source: evaluateReleaseContext?.evaluationManifest", trigger_job)
        self.assertIn('"admin_manifest"', trigger_job)
        self.assertIn('"reference_set_key"', trigger_job)

    def test_codeowners_covers_sensitive_release_paths(self) -> None:
        codeowners = (REPO_ROOT / 'CODEOWNERS').read_text(encoding='utf-8')

        for required_entry in (
            '/.github/workflows/',
            '/backend/modal_worker_app.py',
            '/backend/sar_unet_worker.py',
            '/backend/sar_release_manifest.py',
            '/backend/sar_release_promote.py',
            '/backend/common/sar_release_refs.py',
            '/backend/scripts/assemble_seed_archive.py',
            '/backend/scripts/seed_snowslide_truth.py',
            '/backend/scripts/materialize_release_baseline_masks.py',
            '/supabase/functions/trigger-job/',
        ):
            self.assertIn(required_entry, codeowners)


if __name__ == '__main__':
    unittest.main()
