from __future__ import annotations

import unittest

from backend.common.forecast_bulletins import build_daypart_forecast_bulletin, build_forecast_bulletin


def _cell(
    *,
    probability_risk_score: int,
    problem_type: str,
    probability: float = 0.5,
    aspect_deg: float = 0.0,
    elevation_m: float = 2500.0,
    slope_angle_deg: float = 38.0,
    status: str = 'ready',
    risk_score: int | None = None,
    apt_eligible: bool | None = True,
    public_eligible: bool | None = None,
    problem_slug: str | None = None,
):
    return {
        'status': status,
        'risk_score': probability_risk_score if risk_score is None else risk_score,
        'probability_risk_score': probability_risk_score,
        'apt_eligible': apt_eligible,
        'public_eligible': public_eligible if public_eligible is not None else apt_eligible,
        'problem_type': problem_type,
        'problem_slug': problem_slug,
        'probability': probability,
        'terrain_inputs': {
            'aspect_deg': aspect_deg,
            'elevation_m': elevation_m,
            'slope_angle_deg': slope_angle_deg,
        },
    }


class ForecastBulletinTests(unittest.TestCase):
    def test_returns_none_when_no_ready_cells_exist(self) -> None:
        bulletin = build_forecast_bulletin(
            rows=[
                _cell(probability_risk_score=4, problem_type='Wind Slab', status='unavailable_weather'),
                _cell(probability_risk_score=1, problem_type='Unavailable terrain', status='unavailable_terrain'),
            ],
            region_status='stale',
        )

        self.assertIsNone(bulletin)

    def test_uses_unified_public_risk_score_with_apt_gate(self) -> None:
        bulletin = build_forecast_bulletin(
            rows=[
                _cell(probability_risk_score=5, risk_score=5, problem_type='Storm Slab', probability=0.82, apt_eligible=False, slope_angle_deg=18.0),
                _cell(probability_risk_score=1, risk_score=1, problem_type='Storm Slab', probability=0.20),
                _cell(probability_risk_score=4, risk_score=4, problem_type='Wind Slab', probability=0.61, aspect_deg=315.0, elevation_m=2875.0),
            ],
            region_status='ready',
        )

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertEqual(bulletin['danger_level'], 4)
        self.assertEqual(bulletin['danger_label'], 'High')
        self.assertEqual(bulletin['primary_problem'], 'wind_slab')
        self.assertEqual(bulletin['derived_from']['source_field'], 'risk_score')
        self.assertEqual(bulletin['derived_from']['base_metric'], 'probability_risk_score')
        self.assertEqual(bulletin['derived_from']['terrain_filter_profile'], 'apt_30_50_v1')
        self.assertEqual(bulletin['derived_from']['eligible_cell_count'], 2)

    def test_partial_coverage_still_returns_bulletin(self) -> None:
        bulletin = build_forecast_bulletin(
            rows=[
                _cell(probability_risk_score=4, problem_type='Persistent Slab', probability=0.67),
                _cell(probability_risk_score=1, problem_type='Unavailable weather', status='unavailable_weather'),
            ],
            region_status='partial',
        )

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertEqual(bulletin['coverage'], 'partial')
        self.assertEqual(bulletin['confidence_state'], 'reduced')
        self.assertEqual(bulletin['confidence_reasons'], ['partial_coverage'])
        self.assertEqual(bulletin['primary_problem'], 'persistent_weak_layers')

    def test_reduces_confidence_for_high_uncertainty_and_low_sar_coverage(self) -> None:
        bulletin = build_forecast_bulletin(
            rows=[
                {
                    **_cell(probability_risk_score=4, problem_type='Wind Slab', probability=0.62),
                    'confidence_lower': 0.2,
                    'confidence_upper': 0.7,
                    'coverage_flags': {'sar_coverage_state': 'low_coverage'},
                },
                _cell(probability_risk_score=4, problem_type='Wind Slab', probability=0.58),
                _cell(probability_risk_score=2, problem_type='Wind Slab', probability=0.41),
                _cell(probability_risk_score=2, problem_type='Wind Slab', probability=0.37),
            ],
            region_status='ready',
        )

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertEqual(bulletin['confidence_state'], 'reduced')
        self.assertEqual(
            bulletin['confidence_reasons'],
            ['high_uncertainty_share', 'low_sar_coverage_share'],
        )
        self.assertEqual(
            bulletin['uncertainty_summary'],
            {
                'eligible_cell_count': 4,
                'high_uncertainty_cell_count': 1,
                'high_uncertainty_share': 0.25,
                'low_sar_coverage_cell_count': 1,
                'low_sar_coverage_share': 0.25,
            },
        )

    def test_primary_problem_tie_break_is_deterministic(self) -> None:
        bulletin = build_forecast_bulletin(
            rows=[
                _cell(probability_risk_score=4, problem_type='Persistent Slab', probability=0.72),
                _cell(probability_risk_score=4, problem_type='Persistent Slab', probability=0.70),
                _cell(probability_risk_score=4, problem_type='Wind Slab', probability=0.72),
                _cell(probability_risk_score=4, problem_type='Wind Slab', probability=0.70),
            ],
            region_status='ready',
        )

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertEqual(
            bulletin['problems'],
            ['persistent_weak_layers', 'wind_slab'],
        )
        self.assertEqual(bulletin['primary_problem'], 'persistent_weak_layers')

    def test_orders_aspects_across_north_wrap_and_rounds_elevation_outward(self) -> None:
        bulletin = build_forecast_bulletin(
            rows=[
                _cell(probability_risk_score=4, problem_type='Wind Slab', aspect_deg=270.0, elevation_m=2410.0),
                _cell(probability_risk_score=4, problem_type='Wind Slab', aspect_deg=315.0, elevation_m=2575.0),
                _cell(probability_risk_score=4, problem_type='Wind Slab', aspect_deg=350.0, elevation_m=3380.0),
                _cell(probability_risk_score=4, problem_type='Wind Slab', aspect_deg=25.0, elevation_m=3310.0),
            ],
            region_status='ready',
        )

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertEqual(bulletin['critical_aspects'], ['W', 'NW', 'N', 'NE'])
        self.assertEqual(
            bulletin['critical_elevations'],
            {'min_m': 2400, 'max_m': 3400, 'band_step_m': 200},
        )

    def test_returns_none_when_no_apt_eligible_ready_cells_exist(self) -> None:
        bulletin = build_forecast_bulletin(
            rows=[
                _cell(probability_risk_score=4, risk_score=0, problem_type='Wind Slab', apt_eligible=False, slope_angle_deg=22.0),
                _cell(probability_risk_score=5, risk_score=0, problem_type='Wet Loose', apt_eligible=False, slope_angle_deg=54.0),
            ],
            region_status='ready',
        )

        self.assertIsNone(bulletin)

    def test_sparse_level_five_rolls_down_to_level_four_with_cumulative_frequency(self) -> None:
        rows = [
            _cell(probability_risk_score=1, problem_type='Wet Loose', probability=0.05)
            for _ in range(357)
        ]
        rows.extend(
            _cell(probability_risk_score=4, problem_type='Wet Loose', probability=0.55)
            for _ in range(41)
        )
        rows.extend(
            _cell(probability_risk_score=5, problem_type='Wet Loose', probability=0.67)
            for _ in range(2)
        )

        bulletin = build_forecast_bulletin(rows=rows, region_status='ready')

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertEqual(bulletin['danger_level'], 4)
        self.assertEqual(bulletin['danger_label'], 'High')
        self.assertEqual(bulletin['derived_from']['frequency_basis'], 'cumulative_ge_threshold')
        self.assertEqual(bulletin['derived_from']['frequency_class'], 'some')
        self.assertEqual(bulletin['derived_from']['eligible_cell_count'], 400)
        self.assertEqual(bulletin['derived_from']['selected_level_cell_count'], 43)
        self.assertAlmostEqual(bulletin['derived_from']['selected_level_cell_share'], 0.1075)

    def test_daypart_builder_uses_public_eligible_cells_for_denominator_and_elevation_floor(self) -> None:
        bulletin = build_daypart_forecast_bulletin(
            hourly_grids=[[
                _cell(
                    probability_risk_score=5,
                    risk_score=0,
                    problem_type='Wet Snow',
                    problem_slug='wet_snow',
                    elevation_m=420.0,
                    apt_eligible=True,
                    public_eligible=False,
                ),
                _cell(
                    probability_risk_score=4,
                    risk_score=4,
                    problem_type='Wind Slab',
                    problem_slug='wind_slab',
                    elevation_m=2810.0,
                    aspect_deg=315.0,
                    apt_eligible=True,
                    public_eligible=True,
                ),
            ]],
            region_status='ready',
            forecast_date='2026-04-25T06:00:00+00:00',
            timezone_name='UTC',
            horizon_hours=1,
        )

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertEqual(bulletin['primary_window'], 'day_1_morning')
        self.assertEqual(bulletin['danger_level'], 4)
        self.assertEqual(bulletin['critical_elevations'], {'min_m': 2800, 'max_m': 3000, 'band_step_m': 200})
        self.assertEqual(bulletin['derived_from']['eligible_cell_count'], 1)
        self.assertEqual(bulletin['frequency_threshold_profile'], 'local_grid_share_heuristic_v2')
        self.assertEqual(bulletin['primary_window_policy'], 'first_available_current_or_future_daypart_v1')
        self.assertEqual(bulletin['dayparts'][0]['daypart_aggregation_mode'], 'peak_hour_within_daypart_v1')
        self.assertEqual(bulletin['dayparts'][0]['window_frequency_basis'], 'hourly_peak_cumulative_frequency_over_public_eligible_cells')
        self.assertEqual(bulletin['dayparts'][0]['selected_forecast_hour'], 0)

    def test_daypart_builder_uses_rolling_live_primary_window_and_wet_snow_double_map(self) -> None:
        night_cells = [_cell(probability_risk_score=4, risk_score=4, problem_type='Wind Slab', problem_slug='wind_slab', aspect_deg=315.0)]
        morning_cells = [_cell(probability_risk_score=3, risk_score=3, problem_type='Wind Slab', problem_slug='wind_slab', aspect_deg=315.0)]
        afternoon_cells = [_cell(probability_risk_score=4, risk_score=4, problem_type='Wet Snow', problem_slug='wet_snow', aspect_deg=180.0)]

        bulletin = build_daypart_forecast_bulletin(
            hourly_grids=[night_cells] * 6 + [morning_cells] * 6 + [afternoon_cells],
            region_status='ready',
            forecast_date='2026-04-25T00:00:00+00:00',
            timezone_name='UTC',
            horizon_hours=13,
        )

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertEqual(bulletin['primary_window'], 'day_1_night')
        self.assertEqual(bulletin['primary_window_policy'], 'first_available_current_or_future_daypart_v1')
        self.assertTrue(bulletin['double_map'])
        self.assertEqual(bulletin['peak_window']['window'], 'day_1_night')
        self.assertNotIn('night_high_danger_override_applied', bulletin['aggregation_notes'])

    def test_daypart_builder_suppresses_problems_for_level_one_bulletins(self) -> None:
        bulletin = build_daypart_forecast_bulletin(
            hourly_grids=[[
                _cell(
                    probability_risk_score=1,
                    risk_score=1,
                    problem_type='Wet Snow',
                    problem_slug='wet_snow',
                    public_eligible=True,
                ),
            ]],
            region_status='ready',
            forecast_date='2026-04-25T06:00:00+00:00',
            timezone_name='UTC',
            horizon_hours=1,
        )

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertEqual(bulletin['danger_level'], 1)
        self.assertEqual(bulletin['primary_problem'], 'no_distinct_avalanche_problem')
        self.assertEqual(bulletin['problems'], [])

    def test_daypart_builder_keeps_peak_hour_level_five_inside_morning_window(self) -> None:
        def cells(risk_score: int, count: int = 24) -> list[dict[str, object]]:
            return [
                _cell(
                    probability_risk_score=risk_score,
                    risk_score=risk_score,
                    problem_type='Wind Slab',
                    problem_slug='wind_slab',
                    aspect_deg=315.0,
                    elevation_m=2810.0,
                    public_eligible=True,
                )
                for _ in range(count)
            ]

        hourly_grids = [
            cells(1),
            cells(1),
            cells(5),
            cells(1),
            cells(1),
            cells(1),
        ]

        bulletin = build_daypart_forecast_bulletin(
            hourly_grids=hourly_grids,
            region_status='ready',
            forecast_date='2026-04-25T06:00:00+00:00',
            timezone_name='UTC',
            horizon_hours=len(hourly_grids),
        )

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertEqual(bulletin['primary_window'], 'day_1_morning')
        self.assertEqual(bulletin['danger_level'], 5)
        self.assertEqual(bulletin['dayparts'][0]['danger_level'], 5)
        self.assertEqual(bulletin['dayparts'][0]['selected_forecast_hour'], 2)
        self.assertEqual(bulletin['dayparts'][0]['window_diagnostics']['danger_level'], 4)
        self.assertAlmostEqual(bulletin['dayparts'][0]['window_diagnostics']['selected_level_cell_share'], 0.1667)

    def test_daypart_builder_uses_day_1_evening_for_rolling_live_local_evening_start(self) -> None:
        bulletin = build_daypart_forecast_bulletin(
            hourly_grids=[[
                _cell(
                    probability_risk_score=4,
                    risk_score=4,
                    problem_type='Wind Slab',
                    problem_slug='wind_slab',
                    aspect_deg=315.0,
                    elevation_m=2810.0,
                    public_eligible=True,
                ),
            ]],
            region_status='ready',
            forecast_date='2026-05-02T00:00:00+00:00',
            timezone_name='America/Denver',
            horizon_hours=1,
        )

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertEqual(bulletin['primary_window'], 'day_1_evening')
        self.assertEqual(bulletin['primary_window_policy'], 'first_available_current_or_future_daypart_v1')
        self.assertIn('day_1_morning_missing_fell_back_to_first_available_window', bulletin['aggregation_notes'])

    def test_daypart_builder_falls_back_to_utc_for_invalid_timezone(self) -> None:
        bulletin = build_daypart_forecast_bulletin(
            hourly_grids=[[
                _cell(
                    probability_risk_score=3,
                    risk_score=3,
                    problem_type='Wind Slab',
                    problem_slug='wind_slab',
                    public_eligible=True,
                ),
            ]],
            region_status='ready',
            forecast_date='2026-04-25T06:00:00+00:00',
            timezone_name='Invalid/Timezone',
            horizon_hours=1,
        )

        self.assertIsNotNone(bulletin)
        assert bulletin is not None
        self.assertIn('timezone_fallback_to_utc', bulletin['aggregation_notes'])


if __name__ == '__main__':
    unittest.main()
