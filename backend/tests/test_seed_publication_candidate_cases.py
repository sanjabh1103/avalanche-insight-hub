from unittest.mock import patch

import pytest

from backend.scripts.seed_publication_candidate_cases import (
    CLAIM_BOUNDARY,
    REGION_KEY,
    build_candidate_pack,
    sync_candidate_pack,
)


def test_publication_candidate_pack_is_not_grounded_or_training_eligible():
    pack = build_candidate_pack()

    assert pack['summary']['region_key'] == REGION_KEY
    assert pack['summary']['claim_boundary'] == CLAIM_BOUNDARY
    assert pack['summary']['training_eligible'] is False
    assert pack['summary']['production_eligible'] is False
    assert pack['summary']['grounded_himalayan_evidence'] is False
    assert pack['summary']['case_count'] >= 10

    for case in pack['cases']:
        assert case['region_key'] == REGION_KEY
        assert case['region_key'] != 'himalayas_nepal'
        assert case['claim_boundary'] == CLAIM_BOUNDARY
        assert case['requires_two_reviewers'] is True
        assert case['signoff_scope'] == 'candidate_confirmation_only'
        assert case['forecast_run_id'] is None
        assert case['cell_row'] is None
        assert case['cell_col'] is None
        evidence = case['evidence']
        assert evidence['source_type'] == 'publication_or_open_data'
        assert evidence['needs_scientist_confirmation'] is True
        assert evidence['training_eligible'] is False
        assert evidence['production_eligible'] is False
        assert evidence['grounded_himalayan_evidence'] is False
        assert evidence['synthetic_demo'] is False
        assert evidence['source_citation']


@patch('backend.scripts.seed_publication_candidate_cases.has_supabase_credentials', return_value=False)
def test_sync_requires_explicit_credentials(_credentials_mock):
    with pytest.raises(RuntimeError, match='SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY'):
        sync_candidate_pack(build_candidate_pack())


@patch('backend.scripts.seed_publication_candidate_cases.rest_upsert')
@patch('backend.scripts.seed_publication_candidate_cases.has_supabase_credentials', return_value=True)
def test_sync_keeps_candidate_boundaries(_credentials_mock, upsert_mock):
    pack = build_candidate_pack()

    summary = sync_candidate_pack(pack)

    assert summary['sync_status'] == 'ok'
    assert summary['cases_synced'] == pack['summary']['case_count']
    assert summary['claim_boundary'] == CLAIM_BOUNDARY
    assert summary['training_eligible'] is False
    assert summary['production_eligible'] is False
    assert summary['grounded_himalayan_evidence'] is False
    upsert_mock.assert_called_once()
    records = upsert_mock.call_args.args[1]
    assert all(record['claim_boundary'] == CLAIM_BOUNDARY for record in records)
