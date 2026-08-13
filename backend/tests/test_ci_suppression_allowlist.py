"""G-17: Machine-checkable allowlist for CI continue-on-error suppressions.

Verifies that only explicitly allowlisted step IDs in ml_pipeline.yml have
continue-on-error: true. Any new continue-on-error must be added to the
ALLOWLIST below with a justification.
"""
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ML_PIPELINE = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline.yml'

ALLOWLIST = {
    'download_train_artifacts_1': 'Optional artifact download — recovery step handles failure',
    'download_train_artifacts_2': 'Optional artifact download — recovery step handles failure',
}


class TestCISuppressionAllowlist(unittest.TestCase):
    """G-17: Only allowlisted steps may have continue-on-error: true."""

    def test_no_unallowlisted_continue_on_error(self) -> None:
        self.assertTrue(ML_PIPELINE.exists(), f'{ML_PIPELINE} not found')
        content = ML_PIPELINE.read_text()
        lines = content.splitlines()

        current_step_id = None
        current_step_name = None
        violations: list[str] = []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('- name:'):
                current_step_name = stripped.removeprefix('- name:').strip()
                current_step_id = None
            if stripped.startswith('id:'):
                current_step_id = stripped.removeprefix('id:').strip()
            if stripped == 'continue-on-error: true':
                step_key = current_step_id or current_step_name or f'line_{i}'
                if step_key not in ALLOWLIST:
                    violations.append(
                        f'Line {i}: continue-on-error: true on step '
                        f"'{step_key}' (name: {current_step_name}) "
                        f'is not in the allowlist. '
                        f'Add it to ALLOWLIST in this test with justification.'
                    )

        self.assertEqual(
            violations,
            [],
            f'Unallowlisted continue-on-error found:\n' + '\n'.join(violations),
        )

    def test_allowlist_entries_exist_in_workflow(self) -> None:
        content = ML_PIPELINE.read_text()
        manual_pipeline = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline_manual.yml'
        manual_content = manual_pipeline.read_text() if manual_pipeline.exists() else ''
        for step_id, justification in ALLOWLIST.items():
            self.assertTrue(
                f'id: {step_id}' in content or f'id: {step_id}' in manual_content,
                f'Allowlisted step ID {step_id!r} not found in {ML_PIPELINE.name} or {manual_pipeline.name}. '
                f'Remove it from ALLOWLIST or add it to the workflow.',
            )
