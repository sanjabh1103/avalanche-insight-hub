import json
from pathlib import Path
from unittest.mock import patch

from backend.scripts.build_scientist_validation_case_pack import build_case_pack, sync_case_pack_to_supabase


def write_json(path: Path, payload):
    path.write_text(json.dumps(payload), encoding='utf-8')


def test_build_case_pack_seeds_cell_and_gate_reviews(tmp_path):
    write_json(
        tmp_path / 'forecast_grids.json',
        [
            {
                'region_key': 'colorado_rockies',
                'region_name': 'Colorado Rockies',
                'forecast_date': '2026-05-20',
                'model_metadata': {
                    'forecast_run_id': '11111111-1111-1111-1111-111111111111',
                    'compatibility_forecast_grid_id': '22222222-2222-2222-2222-222222222222',
                },
                'grid_geojson': [
                    {
                        'row': 1,
                        'col': 2,
                        'risk_score': 4,
                        'probability': 0.72,
                        'uncertainty_class': 'high',
                        'runout_seed': True,
                        'public_eligible': True,
                        'snowpack_proxy': {'estimated_shear_strength': 2.1},
                        'explainability_mode': 'heuristic_fallback',
                    },
                    {
                        'row': 3,
                        'col': 4,
                        'risk_score': 0,
                        'public_eligible': False,
                        'public_mask_reasons': ['slope_outside_30_to_50_deg'],
                    },
                ],
            }
        ],
    )
    write_json(
        tmp_path / 'dynamic_model_candidate.json',
        {
            'dynamic_model_type': 'mts_lstm_v1',
            'ready_for_activation': False,
            'gates': {'sar_release_gate_passed': False},
        },
    )
    write_json(
        tmp_path / 'publication_proof.json',
        {
            'forecast_run_id': '11111111-1111-1111-1111-111111111111',
            'region_key': 'colorado_rockies',
            'region_name': 'Colorado Rockies',
        },
    )

    pack = build_case_pack(tmp_path, max_per_type=2)

    assert pack['schema_version'] == 'scientist-validation-case-pack/v1'
    case_types = {case['case_type'] for case in pack['cases']}
    assert {'runout', 'weak_layer', 'masked_terrain', 'model_gate', 'sar_candidate'} <= case_types
    assert pack['summary']['claim_boundary'] == 'review_evidence_only_not_scientist_validation_closure'
    runout_case = next(case for case in pack['cases'] if case['case_type'] == 'runout')
    assert runout_case['forecast_run_id'] == '11111111-1111-1111-1111-111111111111'
    assert runout_case['priority'] == 5
    assert runout_case['requires_two_reviewers'] is True


def test_build_case_pack_seeds_false_positive_and_false_negative(tmp_path):
    write_json(tmp_path / 'forecast_grids.json', [])
    write_json(
        tmp_path / 'forecast_outcomes.json',
        [
            {
                'forecast_run_id': 'run-a',
                'forecast_grid_id': 'grid-a',
                'forecast_hour': 6,
                'cell_row': 1,
                'cell_col': 1,
                'predicted_risk_score': 4,
                'event_observed': False,
            },
            {
                'forecast_run_id': 'run-b',
                'forecast_grid_id': 'grid-b',
                'forecast_hour': 12,
                'cell_row': 2,
                'cell_col': 2,
                'predicted_risk_score': 1,
                'event_observed': True,
            },
        ],
    )

    pack = build_case_pack(tmp_path, max_per_type=2)

    case_types = {case['case_type'] for case in pack['cases']}
    assert {'false_positive', 'false_negative'} <= case_types


def test_build_case_pack_filters_to_grounded_region_sources(tmp_path):
    write_json(
        tmp_path / 'forecast_grids.json',
        [
            {
                'region_key': 'himalayas_nepal',
                'region_name': 'Himalayas Nepal',
                'forecast_date': '2026-05-20',
                'model_metadata': {'forecast_run_id': 'run-himalayas'},
                'grid_geojson': [
                    {
                        'row': 8,
                        'col': 9,
                        'risk_score': 4,
                        'uncertainty_class': 'high',
                        'runout_seed': True,
                        'public_eligible': True,
                    },
                ],
            },
            {
                'region_key': 'colorado_rockies',
                'region_name': 'Colorado Rockies',
                'forecast_date': '2026-05-20',
                'model_metadata': {'forecast_run_id': 'run-colorado'},
                'grid_geojson': [
                    {
                        'row': 1,
                        'col': 1,
                        'risk_score': 4,
                        'uncertainty_class': 'high',
                        'runout_seed': True,
                        'public_eligible': True,
                    },
                ],
            },
        ],
    )
    write_json(
        tmp_path / 'forecast_outcomes.json',
        [
            {
                'region_key': 'himalayas_nepal',
                'region_name': 'Himalayas Nepal',
                'forecast_run_id': 'run-himalayas',
                'forecast_hour': 6,
                'cell_row': 8,
                'cell_col': 9,
                'predicted_risk_score': 1,
                'event_observed': True,
            },
            {
                'region_key': 'colorado_rockies',
                'region_name': 'Colorado Rockies',
                'forecast_run_id': 'run-colorado',
                'forecast_hour': 6,
                'cell_row': 1,
                'cell_col': 1,
                'predicted_risk_score': 1,
                'event_observed': True,
            },
        ],
    )
    write_json(
        tmp_path / 'field_reports.json',
        [
            {
                'id': 'field-himalayas-1',
                'region_key': 'himalayas_nepal',
                'region_name': 'Himalayas Nepal',
                'forecast_run_id': 'run-himalayas',
                'cell_row': 8,
                'cell_col': 9,
                'problem_type': 'persistent weak layers',
            },
            {
                'id': 'field-colorado-1',
                'region_key': 'colorado_rockies',
                'region_name': 'Colorado Rockies',
            },
        ],
    )
    write_json(
        tmp_path / 'publication_proof.json',
        {
            'region_key': 'himalayas_nepal',
            'region_name': 'Himalayas Nepal',
        },
    )
    write_json(
        tmp_path / 'dynamic_model_candidate.json',
        {
            'ready_for_activation': False,
            'gates': {'sar_release_gate_passed': False},
        },
    )

    pack = build_case_pack(tmp_path, max_per_type=3, region_keys={'himalayas_nepal'})

    assert pack['summary']['requested_region_keys'] == ['himalayas_nepal']
    assert pack['summary']['warnings'] == []
    assert all(case['region_key'] == 'himalayas_nepal' for case in pack['cases'])
    assert 'field_report_validation' in {case['gate_key'] for case in pack['cases']}
    assert pack['summary']['grounded_source_counts']['forecast_grids'] == 1
    assert pack['summary']['grounded_source_counts']['forecast_outcomes'] == 1
    assert pack['summary']['grounded_source_counts']['field_reports'] == 1


def test_build_case_pack_reports_when_region_has_no_grounded_cases(tmp_path):
    write_json(tmp_path / 'forecast_grids.json', [])
    write_json(tmp_path / 'forecast_outcomes.json', [])
    write_json(tmp_path / 'field_reports.json', [])
    write_json(
        tmp_path / 'publication_proof.json',
        {
            'region_key': 'colorado_rockies',
            'region_name': 'Colorado Rockies',
        },
    )
    write_json(
        tmp_path / 'dynamic_model_candidate.json',
        {
            'ready_for_activation': False,
            'gates': {'sar_release_gate_passed': False},
        },
    )

    pack = build_case_pack(tmp_path, region_keys={'himalayas_nepal'})

    assert pack['cases'] == []
    assert pack['summary']['warnings'] == ['not_enough_grounded_cases_for_requested_regions']


@patch('backend.scripts.build_scientist_validation_case_pack.rest_upsert')
@patch('backend.scripts.build_scientist_validation_case_pack.rest_get')
@patch('backend.scripts.build_scientist_validation_case_pack.has_supabase_credentials')
def test_sync_case_pack_inserts_missing_cases_without_overwriting_existing(
    has_credentials_mock,
    rest_get_mock,
    rest_upsert_mock,
):
    has_credentials_mock.return_value = True
    rest_get_mock.return_value = [{'id': 'existing-case'}]
    pack = {
        'cases': [
            {'id': 'existing-case', 'case_type': 'runout', 'title': 'Existing'},
            {'id': 'new-case', 'case_type': 'weak_layer', 'title': 'New'},
        ],
    }

    summary = sync_case_pack_to_supabase(pack)

    assert summary['cases_total'] == 2
    assert summary['cases_existing'] == 1
    assert summary['cases_synced'] == 1
    rest_upsert_mock.assert_called_once()
    synced_records = rest_upsert_mock.call_args.args[1]
    assert synced_records == [{'id': 'new-case', 'case_type': 'weak_layer', 'title': 'New'}]
    assert rest_upsert_mock.call_args.kwargs['on_conflict'] == 'id'


@patch('backend.scripts.build_scientist_validation_case_pack.has_supabase_credentials')
def test_sync_case_pack_requires_service_role_credentials(has_credentials_mock):
    has_credentials_mock.return_value = False

    try:
        sync_case_pack_to_supabase({'cases': []})
    except RuntimeError as exc:
        assert 'SUPABASE_URL' in str(exc)
    else:
        raise AssertionError('Expected RuntimeError when service-role credentials are missing')
