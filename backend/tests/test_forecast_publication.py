from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.common.forecast_publication import promote_forecast_run, publish_forecast_run


class ForecastPublicationTests(unittest.TestCase):
    @patch('backend.common.forecast_publication.patch_row_by_id')
    @patch('backend.common.forecast_publication.storage_upsert_json')
    @patch('backend.common.forecast_publication.storage_upload_bytes')
    @patch('backend.common.forecast_publication.rest_insert')
    def test_publish_forecast_run_persists_bulletin_in_row_and_manifest(
        self,
        rest_insert_mock,
        storage_upload_bytes_mock,
        storage_upsert_json_mock,
        patch_row_by_id_mock,
    ) -> None:
        bulletin = {
            'schema_version': 'forecast-bulletin/v1',
            'standard': 'EAWS-style experimental',
            'danger_level': 4,
            'danger_label': 'High',
            'primary_problem': 'wind_slab',
            'problems': ['wind_slab'],
            'critical_elevations': {'min_m': 2400, 'max_m': 3400, 'band_step_m': 200},
            'critical_aspects': ['W', 'NW', 'N', 'NE'],
            'coverage': 'ready',
            'derived_from': {
                'aggregation': 'highest_regional_level_by_cumulative_frequency',
                'source_field': 'risk_score',
                'base_metric': 'probability_risk_score',
                'terrain_filter_profile': 'apt_30_50_v1',
                'frequency_basis': 'cumulative_ge_threshold',
                'frequency_class': 'some',
                'ready_cell_count': 381,
                'eligible_cell_count': 92,
                'selected_level_cell_count': 47,
                'selected_level_cell_share': 0.1234,
                'max_danger_cell_count': 47,
                'problem_counts': {'wind_slab': 47},
            },
        }
        rest_insert_mock.side_effect = [
            [{'id': 'run-1'}],
            [],
            [],
            [],
            [],
        ]
        storage_upload_bytes_mock.side_effect = (
            lambda *, bucket, object_path, payload, content_type: f'{bucket}/{object_path}'
        )
        storage_upsert_json_mock.side_effect = (
            lambda *, bucket, object_path, payload: f'{bucket}/{object_path}'
        )

        publish_forecast_run(
            hazard_type='avalanche',
            region_key='himalayas_nepal',
            region_name='Himalayas (Nepal)',
            forecast_date='2026-05-01',
            horizon_hours=72,
            grid_size=20,
            bbox=[27.5, 86.0, 28.5, 87.0],
            status='ready',
            weather_summary={'snowfall_24h': '18.0'},
            forecast_bulletins=bulletin,
            model_metadata={'model_version': '2026-05-01T00:00:00+00:00'},
            hourly_grids=[[{'row': 0, 'col': 0, 'status': 'ready'}]],
            runout_polygons=[],
        )

        inserted_row = rest_insert_mock.call_args_list[0].args[1][0]
        self.assertEqual(inserted_row['forecast_bulletins'], bulletin)
        manifest_payload = storage_upsert_json_mock.call_args.kwargs['payload']
        self.assertEqual(manifest_payload['forecastBulletin'], bulletin)
        patch_row_payload = patch_row_by_id_mock.call_args.args[2]
        self.assertEqual(patch_row_payload['forecast_bulletins'], bulletin)

    @patch('backend.common.forecast_publication._record_event')
    @patch('backend.common.forecast_publication.rest_rpc')
    def test_promote_forecast_run_returns_promoted_row(self, rest_rpc_mock, _record_event_mock) -> None:
        rest_rpc_mock.return_value = {
            'id': 'run-1',
            'published_at': '2026-05-08T02:00:00+00:00',
            'active': True,
        }

        promoted = promote_forecast_run(forecast_run_id='run-1')

        self.assertEqual(promoted['id'], 'run-1')
        self.assertEqual(promoted['published_at'], '2026-05-08T02:00:00+00:00')


if __name__ == '__main__':
    unittest.main()
