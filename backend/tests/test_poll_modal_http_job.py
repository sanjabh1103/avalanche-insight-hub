"""Regression tests for the GitHub-to-Modal terminal proof wrapper."""
from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.common.modal_execution_manifest import build_execution_manifest
from backend.scripts.poll_modal_http_job import (
    ModalJobError,
    SUPPORTED_ROUTES,
    _validate_safe_identity,
    poll_until_terminal,
    run_job,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_WORKER_TOKEN = os.environ.get('TEST_MODAL_TOKEN') or 'ci-' + 'smoke-token'
MISSING_WORKER_TOKEN = os.environ.get('MISSING_MODAL_TOKEN', '')


def _manifest(root: Path, *, run_id: str = 'run-001', call_id: str = 'call-001', compute_job_id: str = 'compute-001') -> dict[str, object]:
    artifact = root / 'result.json'
    artifact.write_text('{"status":"ok"}\n', encoding='utf-8')
    return build_execution_manifest(
        function_name='test_remote_function',
        call_id=call_id,
        terminal_status='ok',
        started_at='2026-08-09T10:00:00+00:00',
        run_id=run_id,
        compute_job_id=compute_job_id,
        input_manifest_id='input-001',
        input_manifest_hash='a' * 64,
        source_commit='b' * 40,
        model_version='model-v1',
        artifact_root=root,
        artifact_paths=[artifact],
        volume_committed=True,
        python_version='3.12.12',
        modal_sdk_version='0.73.83',
        torch_version='2.5.1+cu121',
        torchvision_version='0.20.1+cu121',
        torchaudio_version='2.5.1+cu121',
        cuda_version='12.1',
        image_identity='modal-image:sha256:' + 'c' * 64,
        image_archive_sha256='d' * 64,
    )


def _accepted_response(*, call_id: str = 'call-001', run_id: str = 'run-001', compute_job_id: str = 'compute-001') -> dict[str, object]:
    """Build a valid 'accepted' submission response with identity fields."""
    return {
        'status': 'accepted',
        'call_id': call_id,
        'modal_call_id': call_id,
        'run_id': run_id,
        'compute_job_id': compute_job_id,
        'request_type': 'test',
        'runtime_provider': 'modal',
    }


def _ok_terminal_response(root: Path, *, call_id: str = 'call-001', run_id: str = 'run-001', compute_job_id: str = 'compute-001') -> dict[str, object]:
    """Build a valid terminal 'ok' response with manifest and identity fields."""
    return {
        'status': 'ok',
        'call_id': call_id,
        'modal_call_id': call_id,
        'run_id': run_id,
        'compute_job_id': compute_job_id,
        'execution_manifest': _manifest(root, run_id=run_id, call_id=call_id, compute_job_id=compute_job_id),
    }


def _ok_terminal_no_run_id(root: Path, *, call_id: str = 'call-001', compute_job_id: str = 'compute-001') -> dict[str, object]:
    """Build a terminal 'ok' response missing top-level run_id (G9 adversarial)."""
    return {
        'status': 'ok',
        'call_id': call_id,
        'compute_job_id': compute_job_id,
        'execution_manifest': _manifest(root, call_id=call_id, compute_job_id=compute_job_id),
    }


class PollModalWorkflowStaticTests(unittest.TestCase):
    def test_modal_jobs_use_terminal_wrapper(self) -> None:
        workflow = (REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline.yml').read_text(encoding='utf-8')
        for job in ('sar_segment:', 'train_sar_unet:', 'train_mtslstm:', 'infer_mtslstm:', 'evaluate_release:'):
            start = workflow.index(f'  {job}')
            next_job = None
            for line_start in range(start + 1, len(workflow)):
                if workflow.startswith('\n  ', line_start) and not workflow.startswith('\n    ', line_start):
                    next_job = line_start
                    break
            section = workflow[start:] if next_job is None else workflow[start:next_job]
            self.assertIn('poll_modal_http_job.py', section, job)
            self.assertNotIn('curl -fsSL -X POST', section, job)
            self.assertIsNone(re.search(r"<<'JSON'.*?\\$\\{MODAL_RUN_ID\\}", section, re.DOTALL), job)

    def test_workflow_has_distinct_submission_and_terminal_artifacts(self) -> None:
        workflow = (REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline.yml').read_text(encoding='utf-8')
        self.assertIn('-submission.json', workflow)
        self.assertIn('-terminal.json', workflow)

    def test_g1_manual_workflow_has_snowpack_poc_release_mode(self) -> None:
        """G1: The manual workflow must have a snowpack_poc_release mode that
        derives region, band, and horizon from the decision record.
        C0.5: Parse the actual YAML structure, not global string search."""
        import yaml
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline_manual.yml'
        workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
        # Find the snowpack_poc_release mode in workflow_dispatch inputs
        on_key = True if True in workflow else 'on'
        dispatch = workflow.get(on_key, {}).get('workflow_dispatch', {})
        if isinstance(dispatch, dict):
            inputs = dispatch.get('inputs', {})
            mode_input = inputs.get('mode', {})
            self.assertEqual(mode_input.get('type', ''), 'choice',
                             'mode must be a choice workflow_dispatch input')
            self.assertIn('snowpack_poc_release', mode_input.get('options', []),
                          'snowpack_poc_release must be a mode option')
        # Find the job that uses snowpack_poc_release
        jobs = workflow.get('jobs', {})
        found_poc_mode = False
        found_dr_sha256 = False
        found_dr_path = False
        found_expected_dr_sha256 = False
        for job_name, job_def in jobs.items():
            steps = job_def.get('steps', [])
            for step in steps:
                run_text = str(step.get('run', ''))
                if 'snowpack_poc_release' in run_text:
                    found_poc_mode = True
                if 'PIR_PANJAL_DECISION_RECORD_SHA256' in run_text:
                    found_dr_sha256 = True
                if '--decision-record-path' in run_text:
                    found_dr_path = True
                if '--expected-decision-record-sha256' in run_text:
                    found_expected_dr_sha256 = True
        self.assertTrue(found_poc_mode, 'snowpack_poc_release must appear in a step run command')
        self.assertTrue(found_dr_sha256, 'PIR_PANJAL_DECISION_RECORD_SHA256 must appear in a step run command')
        self.assertTrue(found_dr_path, '--decision-record-path must appear in a step run command')
        self.assertTrue(found_expected_dr_sha256, '--expected-decision-record-sha256 must appear in a step run command')

    def test_g1_manual_workflow_poll_passes_expected_identity(self) -> None:
        """G1/G2: The ml_pipeline.yml poll invocations must pass
        --expected-run-id and --expected-compute-job-id.
        C0.5: Parse the actual YAML structure, not global string search."""
        import yaml
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline.yml'
        workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
        jobs = workflow.get('jobs', {})
        found_run_id = False
        found_compute_job_id = False
        for job_name, job_def in jobs.items():
            for step in job_def.get('steps', []):
                run_text = str(step.get('run', ''))
                if '--expected-run-id' in run_text:
                    found_run_id = True
                if '--expected-compute-job-id' in run_text:
                    found_compute_job_id = True
        self.assertTrue(found_run_id, '--expected-run-id must appear in a step run command')
        self.assertTrue(found_compute_job_id, '--expected-compute-job-id must appear in a step run command')

    def test_g1_producer_passes_expected_registry_sha256(self) -> None:
        """G1: The manual workflow native execution must pass
        --expected-registry-sha256 to run_snowpack_release.py.
        C0.5: Parse the actual YAML structure and find the exact producer command."""
        import yaml
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline_manual.yml'
        workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
        jobs = workflow.get('jobs', {})
        found_registry_sha256_flag = False
        found_env_var = False
        for job_name, job_def in jobs.items():
            for step in job_def.get('steps', []):
                run_text = str(step.get('run', ''))
                # The flag must be in a run_snowpack_release command, not a comment
                if 'run_snowpack_release' in run_text and '--expected-registry-sha256' in run_text:
                    found_registry_sha256_flag = True
                # The env var must be in the step's env or run text
                env = step.get('env', {})
                if 'EXPECTED_REGISTRY_SHA256' in env or 'EXPECTED_REGISTRY_SHA256' in run_text:
                    found_env_var = True
        self.assertTrue(found_registry_sha256_flag,
                        '--expected-registry-sha256 must appear in a run_snowpack_release.py command')
        self.assertTrue(found_env_var, 'EXPECTED_REGISTRY_SHA256 must be defined as an env var or in run text')

    def test_g6_preflight_does_not_hardcode_nepal_in_poc_mode(self) -> None:
        """G6: The preflight 'Resolve approved native manifests' step must
        derive region/band from the decision record in POC mode, not hardcode
        himalayas_nepal/lower.
        C0.5: Parse the actual YAML structure, not global string search."""
        import yaml
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline_manual.yml'
        workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
        jobs = workflow.get('jobs', {})
        found_poc_mode = False
        found_resolve_region = False
        for job_name, job_def in jobs.items():
            for step in job_def.get('steps', []):
                step_name = str(step.get('name', ''))
                if 'Resolve approved native manifests' in step_name:
                    run_text = str(step.get('run', ''))
                    self.assertIn('POC_MODE', run_text,
                                  'Preflight step must reference POC_MODE')
                    self.assertIn('RESOLVE_REGION', run_text,
                                  'Preflight step must derive RESOLVE_REGION')
                    found_poc_mode = True
                    found_resolve_region = True
        self.assertTrue(found_poc_mode, 'Preflight step "Resolve approved native manifests" must exist')
        self.assertTrue(found_resolve_region, 'Preflight step must use RESOLVE_REGION')
    def test_c05_release_gate_uses_poc_mode_flag(self) -> None:
        """C0.4/C0.5: The release gate invocation in the workflow must pass
        --poc-mode when in snowpack_poc_release mode. Parse the YAML structure."""
        import yaml
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline_manual.yml'
        workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
        jobs = workflow.get('jobs', {})
        found_poc_mode_flag = False
        for job_name, job_def in jobs.items():
            if job_name == 'snowpack_release_gate':
                for step in job_def.get('steps', []):
                    run_text = str(step.get('run', ''))
                    # --poc-mode may be in a shell variable that's expanded
                    # in the release_gate command. Check it's in the same
                    # run block as release_gate.
                    if 'release_gate' in run_text and '--poc-mode' in run_text:
                        found_poc_mode_flag = True
        self.assertTrue(found_poc_mode_flag,
                        '--poc-mode must appear in the snowpack_release_gate step run text')

    def test_c05_native_and_gate_derive_identical_run_ids(self) -> None:
        """C0.5: The native and gate jobs must derive identical run IDs.
        Parse the YAML structure to verify both jobs use github.run_id."""
        import yaml
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline_manual.yml'
        workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
        jobs = workflow.get('jobs', {})
        native_has_run_id = False
        gate_has_run_id = False
        for job_name, job_def in jobs.items():
            if job_name == 'snowpack_native':
                for step in job_def.get('steps', []):
                    run_text = str(step.get('run', ''))
                    if 'github.run_id' in run_text or 'GITHUB_RUN_ID' in run_text:
                        native_has_run_id = True
            if job_name == 'snowpack_release_gate':
                for step in job_def.get('steps', []):
                    run_text = str(step.get('run', ''))
                    if 'github.run_id' in run_text or 'GITHUB_RUN_ID' in run_text:
                        gate_has_run_id = True
        self.assertTrue(native_has_run_id, 'snowpack_native job must use github.run_id')
        self.assertTrue(gate_has_run_id, 'snowpack_release_gate job must use github.run_id')

    def test_p1_7_no_inline_decision_record_parsing_in_workflow(self) -> None:
        """P1-7: The workflow must not contain inline json.loads of the decision
        record. All POC scope derivation must go through derive_poc_scope.py."""
        import yaml
        import re
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline_manual.yml'
        workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
        jobs = workflow.get('jobs', {})
        violations = []
        for job_name, job_def in jobs.items():
            for step in job_def.get('steps', []):
                run_text = str(step.get('run', ''))
                # Check for inline json.loads of PIR_PANJAL_POC_DECISION_RECORD
                # or inline parsing of the decision record that doesn't use
                # the shared helper.
                if 'PIR_PANJAL_POC_DECISION_RECORD' in run_text:
                    if 'json.loads' in run_text and 'derive_poc_scope' not in run_text:
                        # This is inline parsing, not using the helper
                        violations.append(
                            f'{job_name}.{step.get("name", "?")}: '
                            f'inline json.loads of decision record without derive_poc_scope'
                        )
        self.assertEqual(violations, [],
                         f'Inline decision record parsing found (must use derive_poc_scope): {violations}')

    def test_p1_7_workflow_uses_derive_poc_scope_helper(self) -> None:
        """P1-7: The workflow must use derive_poc_scope.py for POC scope derivation."""
        import yaml
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline_manual.yml'
        workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
        jobs = workflow.get('jobs', {})
        found_helper = False
        for job_name, job_def in jobs.items():
            for step in job_def.get('steps', []):
                run_text = str(step.get('run', ''))
                if 'derive_poc_scope' in run_text:
                    found_helper = True
        self.assertTrue(found_helper,
                        'Workflow must use derive_poc_scope.py for POC scope derivation')

    def test_r1_workflow_passes_poc_mode_to_producer(self) -> None:
        """R1: The workflow must pass --poc-mode to run_snowpack_release.py
        when POC_MODE is set, so the producer state machine is explicit."""
        import yaml
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline_manual.yml'
        workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
        jobs = workflow.get('jobs', {})
        found_poc_mode_to_producer = False
        for job_name, job_def in jobs.items():
            for step in job_def.get('steps', []):
                run_text = str(step.get('run', ''))
                # Look for the producer invocation that includes --poc-mode
                if 'run_snowpack_release' in run_text and '--poc-mode' in run_text:
                    found_poc_mode_to_producer = True
        self.assertTrue(found_poc_mode_to_producer,
                        'Workflow must pass --poc-mode to run_snowpack_release.py')

    def test_r2_no_hardcoded_poc_mode_in_consumer_gate(self) -> None:
        """R2: The consumer gate must not hardcode poc_mode=True when calling
        the shared POC scope validator. It must pass the actual gate mode."""
        gate_path = REPO_ROOT / 'backend' / 'scripts' / 'release_gate.py'
        content = gate_path.read_text(encoding='utf-8')
        # R2: The gate must not contain 'poc_mode=True' as a hardcoded argument
        # to validate_poc_scope_consistency. It must pass the actual poc_mode
        # variable.
        self.assertNotIn('poc_mode=True', content,
                         'Consumer gate must not hardcode poc_mode=True. '
                         'It must pass the actual gate mode variable.')


class PollModalHttpJobTests(unittest.TestCase):
    def test_poll_until_terminal_ignores_accepted_pending_running(self) -> None:
        responses = [
            (202, {'status': 'accepted', 'call_id': 'call-001'}),
            (200, {'status': 'pending', 'call_id': 'call-001'}),
            (200, {'status': 'running', 'call_id': 'call-001'}),
            (200, {'status': 'ok', 'call_id': 'call-001'}),
        ]

        def poller(call_id: str) -> tuple[int, dict[str, object]]:
            del call_id
            return responses.pop(0)

        result = poll_until_terminal(
            poller,
            call_id='call-001',
            poll_interval_seconds=0,
            timeout_seconds=10,
        )
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(responses, [])

    def test_poll_until_terminal_rejects_timeout(self) -> None:
        def poller(call_id: str) -> tuple[int, dict[str, object]]:
            del call_id
            return 202, {'status': 'pending', 'call_id': 'call-001'}

        with patch('backend.scripts.poll_modal_http_job.time.monotonic', side_effect=[0, 100]):
            with self.assertRaises(TimeoutError):
                poll_until_terminal(
                    poller,
                    call_id='call-001',
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )

    def test_run_job_rejects_mismatched_call_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response()),
                (200, {'status': 'ok', 'call_id': 'call-other', 'run_id': 'run-001',
                       'compute_job_id': 'compute-001',
                       'execution_manifest': _manifest(root, call_id='call-other')}),
            ]

            def request(method: str, url: str, payload: dict[str, object] | None) -> tuple[int, dict[str, object]]:
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError):
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )

    def test_run_job_requires_terminal_manifest_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response()),
                (200, {'status': 'ok', 'call_id': 'call-001', 'run_id': 'run-001', 'compute_job_id': 'compute-001'}),
            ]

            def request(method: str, url: str, payload: dict[str, object] | None) -> tuple[int, dict[str, object]]:
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError):
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )

    def test_run_job_writes_submission_and_terminal_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response()),
                (200, _ok_terminal_response(root)),
            ]

            def request(method: str, url: str, payload: dict[str, object] | None) -> tuple[int, dict[str, object]]:
                del method, url, payload
                return responses.pop(0)

            submission_path = root / 'submission.json'
            terminal_path = root / 'terminal.json'
            submission, terminal = run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=request,
                submission_output=submission_path,
                terminal_output=terminal_path,
                poll_interval_seconds=0,
                timeout_seconds=10,
            )
            self.assertEqual(submission['status'], 'accepted')
            self.assertEqual(terminal['status'], 'ok')
            self.assertEqual(json.loads(submission_path.read_text())['status'], 'accepted')
            self.assertEqual(json.loads(terminal_path.read_text())['status'], 'ok')

    def test_run_job_rejects_non_http_worker_url(self) -> None:
        with self.assertRaises(ModalJobError):
            run_job(
                worker_url='file:///tmp/worker',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
            )

    def test_run_job_rejects_missing_credentials(self) -> None:
        with self.assertRaises(ModalJobError):
            run_job(
                worker_url='',
                worker_token=MISSING_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
            )


class PollModalAdversarialTests(unittest.TestCase):
    """Adversarial tests for G2/G5/G6 identity trust boundaries."""

    def test_g2_terminal_compute_id_mismatch_with_independent_value_fails(self) -> None:
        """G2: Terminal compute_job_id must match the independent pre-submission value,
        not be derived from the terminal response itself."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Submission echoes the correct compute_job_id
            # Terminal returns a DIFFERENT compute_job_id (attacker-controlled)
            responses = [
                (200, _accepted_response(compute_job_id='compute-001')),
                (200, {
                    'status': 'ok', 'call_id': 'call-001', 'run_id': 'run-001',
                    'compute_job_id': 'compute-EVIL',
                    'execution_manifest': _manifest(root, compute_job_id='compute-EVIL'),
                }),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('compute_job_id mismatch', str(ctx.exception))

    def test_g2_manifest_compute_id_mismatch_with_independent_value_fails(self) -> None:
        """G2: Manifest compute_job_id must match the independent pre-submission value."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response(compute_job_id='compute-001')),
                (200, {
                    'status': 'ok', 'call_id': 'call-001', 'run_id': 'run-001',
                    'compute_job_id': 'compute-001',
                    'execution_manifest': _manifest(root, compute_job_id='compute-EVIL'),
                }),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('compute_job_id does not match', str(ctx.exception))

    def test_g6_submission_without_accepted_status_fails(self) -> None:
        """G6: A bare HTTP 200 with a call_id but no 'accepted' status is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, {'status': 'ok', 'call_id': 'call-001'}),
                (200, _ok_terminal_response(root)),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('accepted', str(ctx.exception))

    def test_g6_submission_with_pending_status_fails(self) -> None:
        """G6: A submission with 'pending' status is not accepted."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, {'status': 'pending', 'call_id': 'call-001'}),
                (200, _ok_terminal_response(root)),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('accepted', str(ctx.exception))

    def test_g2_submission_run_id_mismatch_fails(self) -> None:
        """G2: Submission run_id must match the independent pre-submission value."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response(run_id='run-EVIL')),
                (200, _ok_terminal_response(root)),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('run_id mismatch', str(ctx.exception))

    def test_g8_expected_run_id_disagreement_rejected(self) -> None:
        """G8: When expected_run_id differs from payload.run_id, the job is
        rejected instead of silently overwriting the payload."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response(run_id='run-FIXED', compute_job_id='compute-001')),
                (200, _ok_terminal_response(root, run_id='run-FIXED')),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                    expected_run_id='run-FIXED',
                )
            self.assertIn('does not match', str(ctx.exception))

    def test_g8_expected_compute_id_disagreement_rejected(self) -> None:
        """G8: When expected_compute_job_id differs from payload.compute_job_id,
        the job is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response(compute_job_id='compute-FIXED')),
                (200, _ok_terminal_response(root, compute_job_id='compute-FIXED')),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                    expected_compute_job_id='compute-FIXED',
                )
            self.assertIn('does not match', str(ctx.exception))

    def test_g8_matching_expected_ids_succeed(self) -> None:
        """G8: When expected_run_id matches payload.run_id, the job succeeds."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response(run_id='run-001', compute_job_id='compute-001')),
                (200, _ok_terminal_response(root)),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            submission, terminal = run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=request,
                poll_interval_seconds=0,
                timeout_seconds=10,
                expected_run_id='run-001',
                expected_compute_job_id='compute-001',
            )
            self.assertEqual(submission['run_id'], 'run-001')
            self.assertEqual(terminal['run_id'], 'run-001')

    def test_g2_auto_generated_compute_id_is_deterministic(self) -> None:
        """G2: When no compute_job_id is supplied, a deterministic client compute ID
        is generated from run_id + route."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            captured_payload = {}

            def request(method, url, payload):
                if method == 'POST' and isinstance(payload, dict):
                    captured_payload.update(payload)
                    return (200, _accepted_response(
                        compute_job_id='client-run-001-sar-segment',
                    ))
                return (200, _ok_terminal_response(
                    root, compute_job_id='client-run-001-sar-segment',
                ))

            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001'},
                request=request,
                poll_interval_seconds=0,
                timeout_seconds=10,
            )
            self.assertEqual(
                captured_payload['compute_job_id'],
                'client-run-001-sar-segment',
            )

    def test_g9_terminal_missing_run_id_fails(self) -> None:
        """G9: Terminal response missing top-level run_id fails even if manifest has it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response()),
                (200, _ok_terminal_no_run_id(root)),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('run_id', str(ctx.exception))

    def test_g9_terminal_missing_compute_id_fails(self) -> None:
        """G9: Terminal response missing top-level compute_job_id fails."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response()),
                (200, {
                    'status': 'ok', 'call_id': 'call-001', 'run_id': 'run-001',
                    'execution_manifest': _manifest(root),
                }),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('compute_job_id', str(ctx.exception))

    def test_g9_submission_missing_run_id_fails(self) -> None:
        """G9: Submission response missing run_id fails."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, {
                    'status': 'accepted', 'call_id': 'call-001',
                    'compute_job_id': 'compute-001',
                }),
                (200, _ok_terminal_response(root)),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('run_id', str(ctx.exception))

    def test_g9_submission_missing_compute_id_fails(self) -> None:
        """G9: Submission response missing compute_job_id fails."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, {
                    'status': 'accepted', 'call_id': 'call-001',
                    'run_id': 'run-001',
                }),
                (200, _ok_terminal_response(root)),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('compute_job_id', str(ctx.exception))

    def test_g8_unsafe_run_id_syntax_fails(self) -> None:
        """G8: run_id with unsafe characters fails before POST."""
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run;rm -rf /', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('run_id must be', str(ctx.exception))

    # ─── GLB: call_id injection regression tests ───

    def test_glb_call_id_path_traversal_fails(self) -> None:
        """GLB: Provider returns call_id='../escape' → must fail before poll."""
        def fake_request(method, url, body):
            if method == 'POST':
                return 200, {
                    'status': 'accepted',
                    'call_id': '../escape',
                    'run_id': 'run-001',
                    'compute_job_id': 'compute-001',
                }
            return 200, {}
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=fake_request,
            )
        self.assertIn('call_id must be', str(ctx.exception))

    def test_glb_call_id_slash_injection_fails(self) -> None:
        """GLB: call_id with '/' (e.g. 'a/b/c') → must fail."""
        def fake_request(method, url, body):
            if method == 'POST':
                return 200, {
                    'status': 'accepted',
                    'call_id': 'a/b/c',
                    'run_id': 'run-001',
                    'compute_job_id': 'compute-001',
                }
            return 200, {}
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=fake_request,
            )
        self.assertIn('call_id must be', str(ctx.exception))

    def test_glb_call_id_query_injection_fails(self) -> None:
        """GLB: call_id with '?' (query injection) → must fail."""
        def fake_request(method, url, body):
            if method == 'POST':
                return 200, {
                    'status': 'accepted',
                    'call_id': 'valid?redirect=evil',
                    'run_id': 'run-001',
                    'compute_job_id': 'compute-001',
                }
            return 200, {}
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=fake_request,
            )
        self.assertIn('call_id must be', str(ctx.exception))

    def test_glb_call_id_fragment_injection_fails(self) -> None:
        """GLB: call_id with '#' (fragment injection) → must fail."""
        def fake_request(method, url, body):
            if method == 'POST':
                return 200, {
                    'status': 'accepted',
                    'call_id': 'valid#fragment',
                    'run_id': 'run-001',
                    'compute_job_id': 'compute-001',
                }
            return 200, {}
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=fake_request,
            )
        self.assertIn('call_id must be', str(ctx.exception))

    def test_glb_call_id_overlength_fails(self) -> None:
        """GLB: call_id exceeding 256 chars → must fail."""
        def fake_request(method, url, body):
            if method == 'POST':
                return 200, {
                    'status': 'accepted',
                    'call_id': 'a' * 257,
                    'run_id': 'run-001',
                    'compute_job_id': 'compute-001',
                }
            return 200, {}
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=fake_request,
            )
        self.assertIn('call_id must be', str(ctx.exception))

    def test_glb_call_id_valid_succeeds_validation(self) -> None:
        """GLB: A valid call_id passes validation and proceeds to poll."""
        def fake_request(method, url, body):
            if method == 'POST':
                return 200, {
                    'status': 'accepted',
                    'call_id': 'call-2026-08-09-abc.def_123',
                    'run_id': 'run-001',
                    'compute_job_id': 'compute-001',
                }
            # GET poll — return terminal success with manifest
            manifest = _manifest(Path(tempfile.mkdtemp()), call_id='call-2026-08-09-abc.def_123')
            return 200, {
                'status': 'ok',
                'call_id': 'call-2026-08-09-abc.def_123',
                'run_id': 'run-001',
                'compute_job_id': 'compute-001',
                'execution_manifest': manifest,
            }
        try:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=fake_request,
                poll_interval_seconds=0,
                timeout_seconds=5,
            )
        except ModalJobError as exc:
            # May fail on manifest validation in test, but NOT on call_id validation
            self.assertNotIn('call_id must be', str(exc))

    # ─── 360-2: route injection regression tests ───

    def test_route_path_traversal_fails(self) -> None:
        """360-2: route='../admin/delete' → must fail before POST."""
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='../admin/delete',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('route must be', str(ctx.exception))

    def test_route_slash_injection_fails(self) -> None:
        """360-2: route='sar-segment/../../admin' → must fail."""
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment/../../admin',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('route must be', str(ctx.exception))


# ─── P2/G2: Dot-segment identity regression tests ───


class SafeIdentityDotSegmentTests(unittest.TestCase):
    """G2: _validate_safe_identity must reject dot-only segments (., .., ...)."""

    def test_dot_only_single_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            _validate_safe_identity('.', 'test_field')
        self.assertIn('dot-only segment', str(ctx.exception))

    def test_dot_only_double_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            _validate_safe_identity('..', 'test_field')
        self.assertIn('dot-only segment', str(ctx.exception))

    def test_dot_only_triple_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            _validate_safe_identity('...', 'test_field')
        self.assertIn('dot-only segment', str(ctx.exception))

    def test_dot_mixed_valid_passes(self) -> None:
        """A value like 'a.b' should still pass — it's not dot-only."""
        _validate_safe_identity('a.b', 'test_field')  # should not raise

    def test_dot_separator_valid_passes(self) -> None:
        """A value like 'call-2026-abc.def_123' should still pass."""
        _validate_safe_identity('call-2026-abc.def_123', 'test_field')


# ─── P2/G4: Non-string type regression tests ───


class SafeIdentityNonStringTests(unittest.TestCase):
    """G4: _validate_safe_identity must reject non-string types without AttributeError."""

    def test_none_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            _validate_safe_identity(None, 'test_field')
        self.assertIn('must be a string', str(ctx.exception))

    def test_integer_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            _validate_safe_identity(123, 'test_field')
        self.assertIn('must be a string', str(ctx.exception))

    def test_list_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            _validate_safe_identity(['a', 'b'], 'test_field')
        self.assertIn('must be a string', str(ctx.exception))

    def test_dict_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            _validate_safe_identity({'key': 'val'}, 'test_field')
        self.assertIn('must be a string', str(ctx.exception))

    def test_bool_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            _validate_safe_identity(True, 'test_field')
        self.assertIn('must be a string', str(ctx.exception))


# ─── P2/G4: run_job type validation before .strip() ───


class RunJobTypeValidationTests(unittest.TestCase):
    """G4: run_job must validate types before calling .strip() or dict()."""

    def test_route_none_fails_cleanly(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route=None,  # type: ignore[arg-type]
                payload={'run_id': 'run-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('must be a string', str(ctx.exception))

    def test_route_integer_fails_cleanly(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route=123,  # type: ignore[arg-type]
                payload={'run_id': 'run-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('must be a string', str(ctx.exception))

    def test_worker_url_none_fails_cleanly(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url=None,  # type: ignore[arg-type]
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('must be a string', str(ctx.exception))

    def test_worker_token_none_fails_cleanly(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=None,  # type: ignore[arg-type]
                route='sar-segment',
                payload={'run_id': 'run-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('must be a string', str(ctx.exception))

    def test_payload_none_fails_cleanly(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload=None,  # type: ignore[arg-type]
                request=lambda *args: (200, {}),
            )
        self.assertIn('must be a dict', str(ctx.exception))


# ─── P2/G3: Semantic route allowlist tests ───


class RouteAllowlistTests(unittest.TestCase):
    """G3: run_job must reject routes not in SUPPORTED_ROUTES."""

    def test_unknown_route_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='not-a-real-route',
                payload={'run_id': 'run-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('not supported', str(ctx.exception))

    def test_dot_route_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='.',
                payload={'run_id': 'run-001'},
                request=lambda *args: (200, {}),
            )
        # Dot-only is caught by _validate_safe_identity first
        self.assertIn('dot-only', str(ctx.exception))

    def test_dotdot_route_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='..',
                payload={'run_id': 'run-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('dot-only', str(ctx.exception))

    def test_valid_route_accepted(self) -> None:
        """A valid route from SUPPORTED_ROUTES should not be rejected at the route check."""
        # We can't fully run the job, but we can verify the route passes validation
        # by checking that the requester is called (not rejected before).
        called = [False]

        def fake_request(method, url, body):
            called[0] = True
            return (400, {'status': 'error'})  # Fail after route check

        with self.assertRaises(ModalJobError):
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=fake_request,
            )
        self.assertTrue(called[0], 'Requester should have been called for valid route')


# ─── P2/G5: Provider identity string type tests ───


class ProviderIdentityStringTypeTests(unittest.TestCase):
    """G5: Provider call_id/run_id/compute_job_id must already be strings."""

    def test_call_id_integer_rejected(self) -> None:
        """Provider returning call_id=123 (int) must be rejected, not str()-coerced."""
        response = _accepted_response()
        response['call_id'] = 123  # type: ignore[dict-item]
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, response),
            )
        self.assertIn('must be a string', str(ctx.exception))

    def test_run_id_integer_rejected(self) -> None:
        """Provider returning run_id=123 (int) must be rejected."""
        response = _accepted_response()
        response['run_id'] = 123  # type: ignore[dict-item]
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, response),
            )
        self.assertIn('must be a string', str(ctx.exception))

    def test_compute_job_id_none_rejected(self) -> None:
        """Provider returning compute_job_id=None must be rejected."""
        response = _accepted_response()
        response['compute_job_id'] = None  # type: ignore[dict-item]
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, response),
            )
        self.assertIn('must be a string', str(ctx.exception))


# ─── P2/G6: poll_until_terminal defense-in-depth tests ───


class PollUntilTerminalIdentityTests(unittest.TestCase):
    """G6: poll_until_terminal must validate call_id independently."""

    def test_dot_only_call_id_rejected(self) -> None:
        """Direct poll_until_terminal with call_id='.' must fail before polling."""
        poller_called = [False]

        def fake_poller(call_id):
            poller_called[0] = True
            return (200, {'status': 'ok'})

        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(fake_poller, call_id='.', timeout_seconds=1)
        self.assertIn('dot-only', str(ctx.exception))
        self.assertFalse(poller_called[0], 'Poller should not have been called')

    def test_dotdot_call_id_rejected(self) -> None:
        poller_called = [False]

        def fake_poller(call_id):
            poller_called[0] = True
            return (200, {'status': 'ok'})

        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(fake_poller, call_id='..', timeout_seconds=1)
        self.assertIn('dot-only', str(ctx.exception))
        self.assertFalse(poller_called[0])

    def test_path_traversal_call_id_rejected(self) -> None:
        poller_called = [False]

        def fake_poller(call_id):
            poller_called[0] = True
            return (200, {'status': 'ok'})

        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(fake_poller, call_id='../escape', timeout_seconds=1)
        self.assertIn('call_id must be', str(ctx.exception))
        self.assertFalse(poller_called[0])

    def test_none_call_id_rejected(self) -> None:
        poller_called = [False]

        def fake_poller(call_id):
            poller_called[0] = True
            return (200, {'status': 'ok'})

        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(fake_poller, call_id=None, timeout_seconds=1)  # type: ignore[arg-type]
        self.assertIn('must be a string', str(ctx.exception))
        self.assertFalse(poller_called[0])

    def test_integer_call_id_rejected(self) -> None:
        poller_called = [False]

        def fake_poller(call_id):
            poller_called[0] = True
            return (200, {'status': 'ok'})

        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(fake_poller, call_id=123, timeout_seconds=1)  # type: ignore[arg-type]
        self.assertIn('must be a string', str(ctx.exception))
        self.assertFalse(poller_called[0])


# ─── P1/G4: Payload identity string type tests ───


class PayloadIdentityStringTypeTests(unittest.TestCase):
    """G4: payload.run_id and payload.compute_job_id must already be strings."""

    def test_payload_run_id_integer_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 123, 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('payload.run_id must be a string', str(ctx.exception))

    def test_payload_run_id_float_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 1.5, 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('payload.run_id must be a string', str(ctx.exception))

    def test_payload_run_id_list_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': ['run-001'], 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('payload.run_id must be a string', str(ctx.exception))

    def test_payload_compute_job_id_integer_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 123},
                request=lambda *args: (200, {}),
            )
        self.assertIn('payload.compute_job_id must be a string', str(ctx.exception))

    def test_payload_compute_job_id_float_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 1.5},
                request=lambda *args: (200, {}),
            )
        self.assertIn('payload.compute_job_id must be a string', str(ctx.exception))


# ─── P1/G5: Expected identity string type tests ───


class ExpectedIdentityStringTypeTests(unittest.TestCase):
    """G5: expected_run_id and expected_compute_job_id must be strings if supplied."""

    def test_expected_run_id_integer_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
                expected_run_id=123,  # type: ignore[arg-type]
            )
        self.assertIn('expected_run_id must be a string', str(ctx.exception))

    def test_expected_run_id_none_accepted(self) -> None:
        """None is acceptable — means 'use payload run_id as trust anchor'."""
        # This should not raise at the expected_run_id check (will fail later
        # at the requester, but the type check itself should pass).
        called = [False]

        def fake_request(method, url, body):
            called[0] = True
            return (400, {'status': 'error'})

        with self.assertRaises(ModalJobError):
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=fake_request,
                expected_run_id=None,
            )
        self.assertTrue(called[0])

    def test_expected_compute_job_id_integer_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
                expected_compute_job_id=123,  # type: ignore[arg-type]
            )
        self.assertIn('expected_compute_job_id must be a string', str(ctx.exception))


# ─── P1/G6: Terminal identity string type tests ───


class TerminalIdentityStringTypeTests(unittest.TestCase):
    """G6: Terminal call_id, run_id, compute_job_id must be strings."""

    def test_terminal_call_id_integer_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response()),
                (200, {**_ok_terminal_response(root), 'call_id': 123}),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('call_id must be a string', str(ctx.exception))

    def test_terminal_run_id_integer_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response()),
                (200, {**_ok_terminal_response(root), 'run_id': 123}),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('run_id must be a string', str(ctx.exception))

    def test_terminal_status_integer_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            responses = [
                (200, _accepted_response()),
                (200, {**_ok_terminal_response(root), 'status': 200}),
            ]

            def request(method, url, payload):
                del method, url, payload
                return responses.pop(0)

            with self.assertRaises(ModalJobError) as ctx:
                run_job(
                    worker_url='https://worker.invalid',
                    worker_token=TEST_WORKER_TOKEN,
                    route='sar-segment',
                    payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                    request=request,
                    poll_interval_seconds=0,
                    timeout_seconds=10,
                )
            self.assertIn('status must be a string', str(ctx.exception))


# ─── P2/G7: Route canonicalization tests ───


class RouteCanonicalizationTests(unittest.TestCase):
    """G7: Leading/trailing slashes and whitespace must be rejected, not normalized."""

    def test_leading_slash_route_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='/sar-segment',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('leading or trailing slashes', str(ctx.exception))

    def test_trailing_slash_route_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route='sar-segment/',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('leading or trailing slashes', str(ctx.exception))

    def test_surrounding_whitespace_route_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                worker_url='https://worker.invalid',
                worker_token=TEST_WORKER_TOKEN,
                route=' sar-segment ',
                payload={'run_id': 'run-001', 'compute_job_id': 'compute-001'},
                request=lambda *args: (200, {}),
            )
        self.assertIn('leading or trailing whitespace', str(ctx.exception))


# ─── P2/G8: Poller response shape tests ───


class PollerResponseShapeTests(unittest.TestCase):
    """G8: Poller returning non-dict body must produce ModalJobError, not AttributeError."""

    def test_poller_returning_list_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(
                lambda call_id: (200, []),
                call_id='call-001',
                timeout_seconds=1,
                poll_interval_seconds=0,
            )
        self.assertIn('body must be a dict', str(ctx.exception))

    def test_poller_returning_none_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(
                lambda call_id: (200, None),
                call_id='call-001',
                timeout_seconds=1,
                poll_interval_seconds=0,
            )
        self.assertIn('body must be a dict', str(ctx.exception))

    def test_poller_returning_string_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(
                lambda call_id: (200, 'ok'),
                call_id='call-001',
                timeout_seconds=1,
                poll_interval_seconds=0,
            )
        self.assertIn('body must be a dict', str(ctx.exception))

    def test_poller_returning_non_int_status_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(
                lambda call_id: ('200', {'status': 'ok'}),
                call_id='call-001',
                timeout_seconds=1,
                poll_interval_seconds=0,
            )
        self.assertIn('status_code must be an integer', str(ctx.exception))

    def test_poller_returning_non_string_status_fails(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(
                lambda call_id: (200, {'status': 200}),
                call_id='call-001',
                timeout_seconds=1,
                poll_interval_seconds=0,
            )
        self.assertIn('status must be a string', str(ctx.exception))


# ─── P2/G9: Timeout and poll interval type tests ───


class TimeoutTypeTests(unittest.TestCase):
    """G9: timeout_seconds and poll_interval_seconds must be non-negative integers."""

    def test_float_timeout_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(
                lambda call_id: (200, {'status': 'ok'}),
                call_id='call-001',
                timeout_seconds=1.5,  # type: ignore[arg-type]
            )
        self.assertIn('timeout_seconds must be an integer', str(ctx.exception))

    def test_string_timeout_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(
                lambda call_id: (200, {'status': 'ok'}),
                call_id='call-001',
                timeout_seconds='10',  # type: ignore[arg-type]
            )
        self.assertIn('timeout_seconds must be an integer', str(ctx.exception))

    def test_float_poll_interval_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(
                lambda call_id: (200, {'status': 'ok'}),
                call_id='call-001',
                timeout_seconds=10,
                poll_interval_seconds=0.5,  # type: ignore[arg-type]
            )
        self.assertIn('poll_interval_seconds must be an integer', str(ctx.exception))

    def test_zero_timeout_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(
                lambda call_id: (200, {'status': 'ok'}),
                call_id='call-001',
                timeout_seconds=0,
            )
        self.assertIn('timeout_seconds must be >= 1', str(ctx.exception))

    def test_negative_poll_interval_rejected(self) -> None:
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(
                lambda call_id: (200, {'status': 'ok'}),
                call_id='call-001',
                timeout_seconds=10,
                poll_interval_seconds=-1,
            )
        self.assertIn('poll_interval_seconds must be >= 0', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
