import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ForecastBulletinBadge from '@/components/ForecastBulletinBadge';
import { normalizeForecastBulletin } from '@/lib/forecastBulletins';

describe('ForecastBulletinBadge', () => {
  it('renders Very High for danger level 5 and shows prone locations', () => {
    const bulletin = normalizeForecastBulletin({
      schema_version: 'forecast-bulletin/v1',
      standard: 'EAWS-style experimental',
      danger_level: 5,
      danger_label: 'Very High',
      primary_problem: 'wind_slab',
      problems: ['wind_slab'],
      critical_elevations: { min_m: 2400, max_m: 3400, band_step_m: 200 },
      critical_aspects: ['W', 'NW', 'N', 'NE'],
      coverage: 'ready',
      issue_window_policy: 'daypart_v1',
      primary_window: 'day_1_morning',
      primary_window_policy: 'first_available_current_or_future_daypart_v1',
      peak_window: {
        window: 'day_1_afternoon',
        danger_level: 5,
        danger_label: 'Very High',
        primary_problem: 'wet_snow',
        forecast_hours: [12, 13, 14],
        local_start: '2026-04-29T12:00:00-06:00',
        local_end: '2026-04-29T15:00:00-06:00',
        selected_forecast_hour: 12,
        selected_hour_local_start: '2026-04-29T12:00:00-06:00',
        selected_hour_local_end: '2026-04-29T13:00:00-06:00',
      },
      dayparts: [
        { window: 'day_1_night', day_index: 1, daypart: 'night', danger_level: 3, danger_label: 'Considerable', primary_problem: 'wind_slab', selected_forecast_hour: 0 },
        { window: 'day_1_morning', day_index: 1, daypart: 'morning', danger_level: 4, danger_label: 'High', primary_problem: 'wind_slab', selected_forecast_hour: 6 },
        { window: 'day_1_afternoon', day_index: 1, daypart: 'afternoon', danger_level: 5, danger_label: 'Very High', primary_problem: 'wet_snow', selected_forecast_hour: 12 },
        { window: 'day_1_evening', day_index: 1, daypart: 'evening', danger_level: 4, danger_label: 'High', primary_problem: 'wind_slab', selected_forecast_hour: 18 },
      ],
      double_map: true,
      aggregation_notes: ['night_high_danger_override_applied'],
      public_mask_profile: {
        profile: 'apt_then_snow_elevation_public_eligible_v1',
        stage_a: 'apt_30_50_v1',
        stage_b: 'snow_elevation_proxy_v1',
      },
      frequency_threshold_profile: 'local_grid_share_heuristic_v2',
      derived_from: {
        aggregation: 'highest_regional_level_by_cumulative_frequency',
        source_field: 'risk_score',
        base_metric: 'probability_risk_score',
        terrain_filter_profile: 'apt_30_50_v1',
        frequency_basis: 'cumulative_ge_threshold',
        frequency_class: 'some',
        ready_cell_count: 381,
        eligible_cell_count: 92,
        selected_level_cell_count: 47,
        selected_level_cell_share: 0.1234,
        max_danger_cell_count: 47,
        problem_counts: { wind_slab: 47 },
      },
    });

    const onSelectForecastHour = vi.fn();
    render(<ForecastBulletinBadge bulletin={bulletin} timeOffset={12} onSelectForecastHour={onSelectForecastHour} />);

    expect(screen.getByText('Danger Level 5: Very High')).toBeTruthy();
    expect(screen.getByText('Wind Slab')).toBeTruthy();
    expect(screen.getByText(/W, NW, N, NE • 2400–3400 m • EAWS-style experimental/i)).toBeTruthy();
    expect(screen.getByTestId('daypart-strip')).toBeTruthy();
    expect(screen.getByTestId('daypart-chip-night').textContent).toContain('Night');
    expect(screen.getByTestId('daypart-chip-morning').textContent).toContain('Morning');
    expect(screen.getByTestId('daypart-chip-afternoon').textContent).toContain('Afternoon');
    expect(screen.getByTestId('daypart-chip-evening').textContent).toContain('Evening');
    expect(screen.getByTestId('daypart-chip-morning').getAttribute('data-primary-window')).toBe('true');
    expect(screen.getByTestId('daypart-chip-afternoon').getAttribute('data-active-daypart')).toBe('true');
    expect(screen.getByTestId('peak-window-caption').textContent).toContain('Peak: Day 1 Afternoon • Level 5');

    fireEvent.click(screen.getByTestId('daypart-chip-morning'));
    expect(onSelectForecastHour).toHaveBeenCalledWith(6);
  }, 15_000);

  it('does not render for a null bulletin', () => {
    const { container } = render(<ForecastBulletinBadge bulletin={null} />);
    expect(container.firstChild).toBeNull();
  });
});
