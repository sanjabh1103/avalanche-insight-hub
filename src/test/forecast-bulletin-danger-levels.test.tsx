import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import ForecastBulletinBadge from '@/components/ForecastBulletinBadge';
import { normalizeForecastBulletin } from '@/lib/forecastBulletins';

function buildBulletin(dangerLevel: number, dangerLabel: string, overrides: Record<string, unknown> = {}) {
  return normalizeForecastBulletin({
    schema_version: 'forecast-bulletin/v1',
    standard: 'EAWS-style experimental',
    danger_level: dangerLevel,
    danger_label: dangerLabel,
    primary_problem: 'wind_slab',
    problems: ['wind_slab'],
    critical_elevations: { min_m: 2400, max_m: 3400, band_step_m: 200 },
    critical_aspects: ['W', 'NW', 'N', 'NE'],
    coverage: 'ready',
    confidence_state: 'normal',
    confidence_reasons: [],
    uncertainty_summary: {
      eligible_cell_count: 92,
      high_uncertainty_cell_count: 10,
      high_uncertainty_share: 0.11,
      low_sar_coverage_cell_count: 5,
      low_sar_coverage_share: 0.05,
    },
    source_health: {
      summary_version: 'source_health_v1',
      support_status: 'full',
      overall_completeness: 0.95,
      weather_freshness_hours: 3,
      sar_coverage_mode: 'good',
      snowpack_proxy_available: true,
    },
    decision_provenance: {
      summary_version: 'decision_provenance_v1',
      threshold_profile: 'heuristic-risk-bands-v1',
      threshold_profile_origin: 'heuristic_seeded',
      dominant_mapping: 'heuristic_thresholds_and_frequency',
      calibration_method: 'isotonic_v1',
      selected_feature_count: 12,
    },
    issue_window_policy: 'daypart_v1',
    primary_window: 'day_1_morning',
    primary_window_policy: 'first_available_current_or_future_daypart_v1',
    peak_window: {
      window: 'day_1_afternoon',
      danger_level: dangerLevel,
      danger_label: dangerLabel,
      primary_problem: 'wind_slab',
      forecast_hours: [12, 13, 14],
      local_start: '2026-04-29T12:00:00-06:00',
      local_end: '2026-04-29T15:00:00-06:00',
      selected_forecast_hour: 12,
      selected_hour_local_start: '2026-04-29T12:00:00-06:00',
      selected_hour_local_end: '2026-04-29T13:00:00-06:00',
    },
    dayparts: [
      { window: 'day_1_night', day_index: 1, daypart: 'night', danger_level: dangerLevel, danger_label: dangerLabel, primary_problem: 'wind_slab', selected_forecast_hour: 0 },
      { window: 'day_1_morning', day_index: 1, daypart: 'morning', danger_level: dangerLevel, danger_label: dangerLabel, primary_problem: 'wind_slab', selected_forecast_hour: 6 },
      { window: 'day_1_afternoon', day_index: 1, daypart: 'afternoon', danger_level: dangerLevel, danger_label: dangerLabel, primary_problem: 'wind_slab', selected_forecast_hour: 12 },
      { window: 'day_1_evening', day_index: 1, daypart: 'evening', danger_level: dangerLevel, danger_label: dangerLabel, primary_problem: 'wind_slab', selected_forecast_hour: 18 },
    ],
    double_map: true,
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
    ...overrides,
  });
}

describe('ForecastBulletinBadge danger levels 1-4', () => {
  it('renders Low for danger level 1', () => {
    const bulletin = buildBulletin(1, 'Low');
    render(<ForecastBulletinBadge bulletin={bulletin} timeOffset={6} />);
    expect(screen.getByText('Danger Level 1: Low')).toBeTruthy();
  });

  it('renders Moderate for danger level 2', () => {
    const bulletin = buildBulletin(2, 'Moderate');
    render(<ForecastBulletinBadge bulletin={bulletin} timeOffset={6} />);
    expect(screen.getByText('Danger Level 2: Moderate')).toBeTruthy();
  });

  it('renders Considerable for danger level 3', () => {
    const bulletin = buildBulletin(3, 'Considerable');
    render(<ForecastBulletinBadge bulletin={bulletin} timeOffset={6} />);
    expect(screen.getByText('Danger Level 3: Considerable')).toBeTruthy();
  });

  it('renders High for danger level 4', () => {
    const bulletin = buildBulletin(4, 'High');
    render(<ForecastBulletinBadge bulletin={bulletin} timeOffset={6} />);
    expect(screen.getByText('Danger Level 4: High')).toBeTruthy();
  });
});

describe('ForecastBulletinBadge stale state', () => {
  it('renders stale indicator when stale prop is true', () => {
    const bulletin = buildBulletin(3, 'Considerable', { coverage: 'partial' });
    render(<ForecastBulletinBadge bulletin={bulletin} stale={true} timeOffset={6} />);
    expect(screen.getByText('Stale')).toBeTruthy();
  });

  it('renders reduced confidence badge when confidence_state is reduced', () => {
    const bulletin = buildBulletin(2, 'Moderate', {
      coverage: 'partial',
      confidence_state: 'reduced',
      confidence_reasons: ['partial_coverage'],
    });
    render(<ForecastBulletinBadge bulletin={bulletin} timeOffset={6} />);
    expect(screen.getByTestId('confidence-badge').textContent).toContain('Reduced Confidence');
  });

  it('does not show reduced confidence badge when confidence_state is normal', () => {
    const bulletin = buildBulletin(1, 'Low');
    render(<ForecastBulletinBadge bulletin={bulletin} timeOffset={6} />);
    expect(screen.queryByTestId('confidence-badge')).toBeNull();
  });
});
