from pathlib import Path
from unittest.mock import patch

from backend.scripts.run_scientist_demo_workflow import CLAIM_BOUNDARY, run_scientist_demo_workflow


@patch('backend.scripts.run_scientist_demo_workflow._patch_case_in_review')
@patch('backend.scripts.run_scientist_demo_workflow._post_rows')
@patch('backend.scripts.run_scientist_demo_workflow._get_rows')
@patch('backend.scripts.run_scientist_demo_workflow._sign_in')
def test_scientist_demo_workflow_writes_redacted_export(
    sign_in_mock,
    get_rows_mock,
    post_rows_mock,
    patch_case_mock,
    tmp_path: Path,
):
    sign_in_mock.return_value = {
        'supabase_url': 'https://exampleprojectref.supabase.co',
        'publishable_key': 'publishable-fixture',
        'access_token': 'access-token-fixture',
        'user_id': 'scientist-user-id',
        'email': 'scientist@insight-hub.local',
    }
    get_rows_mock.side_effect = [
        [{
            'id': 'case-id',
            'region_key': 'demo_himalayas_synthetic',
            'claim_boundary': CLAIM_BOUNDARY,
            'disagreement_count': 0,
        }],
        [{
            'id': 'review-id',
            'reviewer_id': 'scientist-user-id',
            'evidence_refs': {'attached_publications': [{'id': 'him-strat-2020'}]},
        }],
        [{
            'id': 'action-id',
            'action_type': 'evidence_request',
        }],
    ]
    post_rows_mock.return_value = []
    export_path = tmp_path / 'scientist-export.json'

    summary = run_scientist_demo_workflow(output_path=export_path)

    assert summary['workflow_status'] == 'ok'
    assert summary['password_printed'] is False
    assert summary['claim_boundary'] == CLAIM_BOUNDARY
    assert export_path.exists()
    export_text = export_path.read_text(encoding='utf-8')
    assert 'access-token-fixture' not in export_text
    assert 'SCIENTIST_DEMO_PASSWORD' not in export_text
    assert 'attached_publications' in export_text
    patch_case_mock.assert_called_once()
