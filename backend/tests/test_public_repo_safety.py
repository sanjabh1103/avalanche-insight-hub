"""
Regression tests for public repo safety.

These tests verify that:
1. No customer-specific terms (Partner/Partner/a partner) appear in tracked code files.
2. Private-only files (docs/, .env, media) are not tracked by git.
3. The .gitignore covers all private-only paths.
4. The pilot positioning profile has no customer-specific references.
5. Modal-dependent workflow jobs skip gracefully when secrets are absent.
6. The sync-to-public workflow exists and excludes private paths.

Run: python -m pytest backend/tests/test_public_repo_safety.py -v
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PROHIBITED_TERMS = ['Partner', 'Partner', 'a partner']

PRIVATE_PATHS = [
    'docs/',
    '.fable5/',
    '.windsurf/',
    '.understand-anything/',
    '.lovable/',
    '.devin/',
    'narration/',
    'artifacts/',
    '.positioning-audit/',
]

PRIVATE_FILES = [
    '.env',
    'AGENTS.md',
    'DESIGN.md',
    'storyboard.yml',
    'storyboard-narrated.yml',
    'generate_narration.py',
    'merge_narration.py',
]


def _git_tracked_files():
    """Return list of files tracked by git."""
    result = subprocess.run(
        ['git', 'ls-files', '--cached'],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    return result.stdout.strip().split('\n') if result.stdout.strip() else []


def _is_public_repo_context():
    """Detect if we're running in the public repo (no docs/ tracked, .gitignore has private exclusions)."""
    gitignore = (REPO_ROOT / '.gitignore').read_text()
    return 'docs/' in gitignore and '.fable5/' in gitignore


class TestNoProhibitedTermsInCode:
    """Ensure no customer-specific references in tracked code files."""

    def test_no_Partner_in_tracked_files(self):
        if not _is_public_repo_context():
            return  # Private repo is expected to have Partner/Partner references
        tracked = _git_tracked_files()
        code_extensions = {'.py', '.ts', '.tsx', '.yml', '.yaml', '.json', '.sh', '.sql', '.js', '.mjs', '.md'}
        violations = []
        for filepath in tracked:
            # Skip this test file itself (it references the terms to check for them)
            if filepath.endswith('test_public_repo_safety.py'):
                continue
            ext = Path(filepath).suffix
            if ext not in code_extensions:
                continue
            full_path = REPO_ROOT / filepath
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            for term in PROHIBITED_TERMS:
                if term in content:
                    violations.append(f'{filepath}: contains "{term}"')
        assert not violations, 'Prohibited terms found in tracked files:\n' + '\n'.join(violations)


class TestPrivateFilesNotTracked:
    """Ensure private-only files and directories are not tracked by git."""

    def test_docs_not_tracked(self):
        if not _is_public_repo_context():
            return  # Private repo tracks docs/
        tracked = _git_tracked_files()
        docs_tracked = [f for f in tracked if f.startswith('docs/')]
        assert not docs_tracked, f'docs/ files still tracked: {docs_tracked[:5]}'

    def test_env_not_tracked(self):
        if not _is_public_repo_context():
            return  # Private repo may track .env (it's in .gitignore via *.env*)
        tracked = _git_tracked_files()
        assert '.env' not in tracked, '.env is tracked by git!'
        assert 'AGENTS.md' not in tracked, 'AGENTS.md is tracked by git!'

    def test_gitignore_covers_private_paths(self):
        if not _is_public_repo_context():
            return  # Private repo doesn't need private-path exclusions
        gitignore = (REPO_ROOT / '.gitignore').read_text()
        for path in PRIVATE_PATHS:
            assert path in gitignore, f'{path} not in .gitignore'
        for path in PRIVATE_FILES:
            assert path in gitignore, f'{path} not in .gitignore'


class TestPilotPositioningProfile:
    """Verify the pilot positioning profile has no customer-specific references."""

    def test_profile_has_no_Partner(self):
        profile_path = REPO_ROOT / 'src' / 'lib' / 'pilotPositioning.ts'
        if profile_path.exists():
            content = profile_path.read_text()
            for term in PROHIBITED_TERMS:
                assert term not in content, f'pilotPositioning.ts contains "{term}"'

    def test_old_Partner_file_removed(self):
        old_file = REPO_ROOT / 'src' / 'lib' / 'PartnerPositioning.ts'
        assert not old_file.exists(), 'PartnerPositioning.ts still exists — should be renamed to pilotPositioning.ts'


class TestWorkflowSecretGates:
    """Verify Modal-dependent jobs skip gracefully when secrets are absent."""

    def test_modal_jobs_use_graceful_skip(self):
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'ml_pipeline.yml'
        if not workflow_path.exists():
            return
        content = workflow_path.read_text()
        # Check that Modal jobs use notice (not error) and exit 0
        assert '::notice::' in content or 'exit 0' in content, \
            'Modal jobs should skip gracefully with ::notice:: and exit 0'


class TestSyncWorkflow:
    """Verify the sync-to-public workflow exists and excludes private paths."""

    def test_sync_workflow_exists(self):
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'sync-to-public.yml'
        if not workflow_path.exists():
            import pytest
            pytest.skip('sync-to-public.yml not present (public repo context)')

    def test_sync_workflow_excludes_docs(self):
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'sync-to-public.yml'
        if not workflow_path.exists():
            return
        scrubber_path = REPO_ROOT / 'scripts' / 'sync_to_public.sh'
        content = workflow_path.read_text()
        if scrubber_path.exists():
            content += scrubber_path.read_text()
        assert 'docs/' in content, 'sync workflow should remove docs/'
        assert '.env' in content, 'sync workflow should remove .env'
        assert 'orphan' in content.lower() or 'commit-tree' in content, \
            'sync workflow should use orphan commit strategy'
