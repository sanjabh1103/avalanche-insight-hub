from unittest.mock import patch

from backend.scripts.seed_scientist_demo_data import (
    CLAIM_BOUNDARY,
    DEMO_REGION_KEY,
    build_synthetic_daily_verification,
    build_synthetic_scientist_case,
    seed_synthetic_scientist_demo_data,
)


def test_synthetic_case_is_demo_only_and_not_grounded_himalayan_evidence():
    case = build_synthetic_scientist_case(created_by='scientist-user-id')

    assert case['region_key'] == DEMO_REGION_KEY
    assert case['claim_boundary'] == CLAIM_BOUNDARY
    assert case['region_key'] != 'himalayas_nepal'
    assert case['priority'] == 5
    assert case['requires_two_reviewers'] is True
    for payload_key in ('evidence', 'cell_snapshot', 'model_metadata'):
        payload = case[payload_key]
        assert payload['synthetic_demo'] is True
        assert payload['training_eligible'] is False
        assert payload['production_eligible'] is False
        assert payload['grounded_himalayan_evidence'] is False


def test_synthetic_daily_verification_is_comparison_only():
    daily = build_synthetic_daily_verification(reviewer_id='scientist-user-id')

    assert daily['region_key'] == DEMO_REGION_KEY
    assert daily['evidence_refs']['claim_boundary'] == CLAIM_BOUNDARY
    assert daily['evidence_refs']['training_eligible'] is False
    assert daily['evidence_refs']['production_eligible'] is False
    assert daily['scientist_danger_level'] != 'not_assessed'
    assert daily['model_danger_level'] != 'not_assessed'


@patch('backend.scripts.seed_scientist_demo_data._postgrest_upsert')
@patch('backend.scripts.seed_scientist_demo_data.resolve_supabase_connection')
def test_seed_summary_keeps_synthetic_boundaries(resolve_connection_mock, upsert_mock):
    from backend.scripts.provision_scientist_demo_user import SupabaseConnection

    resolve_connection_mock.return_value = SupabaseConnection(
        url='https://exampleprojectref.supabase.co',
        project_ref='exampleprojectref',
        admin_key='service-role-fixture',
        admin_key_source='local_env',
    )
    upsert_mock.side_effect = [
        [{'id': 'case-id'}],
        [{'id': 'daily-id'}],
    ]

    summary = seed_synthetic_scientist_demo_data(scientist_user_id='scientist-user-id')

    assert summary['seed_status'] == 'ok'
    assert summary['region_key'] == DEMO_REGION_KEY
    assert summary['claim_boundary'] == CLAIM_BOUNDARY
    assert summary['synthetic_demo'] is True
    assert summary['training_eligible'] is False
    assert summary['production_eligible'] is False
    assert summary['case_ids'] == ['case-id']
    assert summary['daily_verification_ids'] == ['daily-id']
