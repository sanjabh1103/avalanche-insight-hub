import { describe, expect, it } from 'vitest';

import {
  forecastGridRowToCells,
  forecastGridRowToHourlyGrids,
  forecastGridRowUsesLegacyStaticPlayback,
  hasRenderableCellGeometry,
  isCellMasked,
  isCellUnavailable,
  type ForecastGridRowRecord,
} from '@/lib/gridUtils';

describe('forecastGridRowToHourlyGrids', () => {
  it('prefers persisted hourly grids over cloned legacy playback', () => {
    const row: ForecastGridRowRecord = {
      id: 'forecast-1',
      region_name: 'Colorado Rockies',
      forecast_date: '2026-04-29',
      horizon_hours: 2,
      bbox: [38.5, -107.5, 40.5, -105.5],
      grid_geojson: [{ row: 0, col: 0, lat: 39, lng: -106, lat_end: 39.1, lng_end: -105.9, risk_score: 2, hazard: 0.2, exposure: 0.2, vulnerability: 0.2, problem_type: 'Storm Slab', shap_values: {} }],
      hourly_grids: [
        [{ row: 0, col: 0, lat: 39, lng: -106, lat_end: 39.1, lng_end: -105.9, risk_score: 2, hazard: 0.2, exposure: 0.2, vulnerability: 0.2, problem_type: 'Storm Slab', shap_values: {} }],
        [{ row: 0, col: 0, lat: 39, lng: -106, lat_end: 39.1, lng_end: -105.9, risk_score: 5, hazard: 0.9, exposure: 0.2, vulnerability: 0.2, problem_type: 'Storm Slab', shap_values: {} }],
      ],
    };

    const grids = forecastGridRowToHourlyGrids(row);

    expect(grids).toHaveLength(2);
    expect(grids[0][0].riskScore).toBe(2);
    expect(grids[1][0].riskScore).toBe(5);
    expect(forecastGridRowUsesLegacyStaticPlayback(row)).toBe(false);
  });

  it('falls back to a single static legacy hour when hourly_grids are missing', () => {
    const row: ForecastGridRowRecord = {
      id: 'forecast-legacy',
      region_name: 'Colorado Rockies',
      forecast_date: '2026-04-29',
      horizon_hours: 72,
      bbox: [38.5, -107.5, 40.5, -105.5],
      grid_geojson: [{ row: 0, col: 0, lat: 39, lng: -106, lat_end: 39.1, lng_end: -105.9, risk_score: 3, hazard: 0.4, exposure: 0.2, vulnerability: 0.2, problem_type: 'Wind Slab', shap_values: {} }],
    };

    const grids = forecastGridRowToHourlyGrids(row);

    expect(grids).toHaveLength(1);
    expect(grids[0][0].riskScore).toBe(3);
    expect(forecastGridRowUsesLegacyStaticPlayback(row)).toBe(true);
  });

  it('hydrates APT masking fields without collapsing masked terrain into unavailable state', () => {
    const row: ForecastGridRowRecord = {
      id: 'forecast-apt',
      region_name: 'Himalayas',
      forecast_date: '2026-05-01',
      horizon_hours: 72,
      bbox: [27.5, 86.0, 28.5, 87.0],
      grid_geojson: [{
        row: 0,
        col: 0,
        lat: 27.5,
        lng: 86.0,
        lat_end: 27.55,
        lng_end: 86.05,
        risk_score: 0,
        terrain_fused_risk_score: 5,
        probability_risk_score: 4,
        apt_eligible: false,
        apt_profile: 'apt_30_50_v1',
        apt_mask_reason: 'slope_outside_30_to_50_deg',
        hazard: 0.7,
        exposure: 0.2,
        vulnerability: 0.2,
        problem_type: 'Wet Loose',
        shap_values: {},
      }],
    };

    const [cell] = forecastGridRowToCells(row);

    expect(cell.riskScore).toBe(0);
    expect(cell.terrainFusedRiskScore).toBe(5);
    expect(cell.aptEligible).toBe(false);
    expect(cell.aptProfile).toBe('apt_30_50_v1');
    expect(cell.disabled).toBe(false);
  });

  it('hydrates snow/elevation public masking fields without collapsing masked terrain into unavailable state', () => {
    const row: ForecastGridRowRecord = {
      id: 'forecast-public-mask',
      region_name: 'Himalayas',
      forecast_date: '2026-05-01',
      horizon_hours: 72,
      bbox: [27.5, 86.0, 28.5, 87.0],
      grid_geojson: [{
        row: 0,
        col: 1,
        lat: 27.5,
        lng: 86.1,
        lat_end: 27.55,
        lng_end: 86.15,
        risk_score: 0,
        terrain_fused_risk_score: 4,
        probability_risk_score: 4,
        apt_eligible: true,
        public_eligible: false,
        public_mask_reasons: ['warm_low_elevation_no_snow_support'],
        snow_elevation_eligible: false,
        snow_elevation_mask_reason: 'warm_low_elevation_no_snow_support',
        snow_elevation_profile: 'snow_elevation_proxy_v1',
        snow_relevance_basis: ['hard_negative_warm_low_elevation_no_snow_support'],
        hazard: 0.6,
        exposure: 0.2,
        vulnerability: 0.2,
        problem_type: 'Wet Snow',
        problem_slug: 'wet_snow',
        shap_values: {},
      }],
    };

    const [cell] = forecastGridRowToCells(row);

    expect(cell.publicEligible).toBe(false);
    expect(cell.snowElevationEligible).toBe(false);
    expect(cell.publicMaskReasons).toEqual(['warm_low_elevation_no_snow_support']);
    expect(cell.disabled).toBe(false);
    expect(isCellMasked(cell)).toBe(true);
    expect(isCellUnavailable(cell)).toBe(false);
  });

  it('hydrates published-artifact snake_case bounds when camelCase bounds are null', () => {
    const row: ForecastGridRowRecord = {
      id: 'forecast-artifact-hour-0',
      region_name: 'Himalayas (Nepal)',
      forecast_date: '2026-05-02',
      horizon_hours: 72,
      bbox: [27.0, 85.0, 29.0, 87.0],
      grid_size: 20,
      grid_geojson: [{
        row: 0,
        col: 0,
        lat: 27.05,
        lng: 85.0625,
        latEnd: null,
        lngEnd: null,
        lat_end: 27.1,
        lng_end: 85.125,
        risk_score: 4,
        hazard: 0.8,
        exposure: 0.2,
        vulnerability: 0.2,
        problem_type: 'Wind Slab',
        shap_values: {},
      }],
      hourly_grids: [[{
        row: 0,
        col: 0,
        lat: 27.05,
        lng: 85.0625,
        latEnd: null,
        lngEnd: null,
        lat_end: 27.1,
        lng_end: 85.125,
        risk_score: 4,
        hazard: 0.8,
        exposure: 0.2,
        vulnerability: 0.2,
        problem_type: 'Wind Slab',
        shap_values: {},
      }]],
    };

    const [cell] = forecastGridRowToCells(row);
    const [hourCell] = forecastGridRowToHourlyGrids(row)[0];

    expect(cell.latEnd).toBeCloseTo(27.1, 6);
    expect(cell.lngEnd).toBeCloseTo(85.125, 6);
    expect(hourCell.latEnd).toBeCloseTo(27.1, 6);
    expect(hourCell.lngEnd).toBeCloseTo(85.125, 6);
    expect(hasRenderableCellGeometry(cell)).toBe(true);
  });

  it('falls back to bbox plus grid size when end bounds are absent', () => {
    const row: ForecastGridRowRecord = {
      id: 'forecast-bbox-fallback',
      region_name: 'Colorado Rockies',
      forecast_date: '2026-05-02',
      horizon_hours: 24,
      bbox: [39.0, -106.0, 40.0, -105.0],
      grid_size: 20,
      grid_geojson: [{
        row: 0,
        col: 0,
        lat: 39.0,
        lng: -106.0,
        risk_score: 2,
        hazard: 0.3,
        exposure: 0.2,
        vulnerability: 0.2,
        problem_type: 'Storm Slab',
        shap_values: {},
      }],
    };

    const [cell] = forecastGridRowToCells(row);

    expect(cell.latEnd).toBeCloseTo(39.05, 6);
    expect(cell.lngEnd).toBeCloseTo(-105.95, 6);
    expect(hasRenderableCellGeometry(cell)).toBe(true);
  });

  it('does not coerce impossible geometry to zero or treat it as renderable', () => {
    const row: ForecastGridRowRecord = {
      id: 'forecast-invalid-geometry',
      region_name: 'Colorado Rockies',
      forecast_date: '2026-05-02',
      horizon_hours: 24,
      bbox: [39.0, -106.0, 39.0, -106.0],
      grid_geojson: [{
        row: 0,
        col: 0,
        lat: 39.0,
        lng: -106.0,
        risk_score: 2,
        hazard: 0.3,
        exposure: 0.2,
        vulnerability: 0.2,
        problem_type: 'Storm Slab',
        shap_values: {},
      }],
    };

    const [cell] = forecastGridRowToCells(row);

    expect(Number.isNaN(cell.latEnd)).toBe(true);
    expect(Number.isNaN(cell.lngEnd)).toBe(true);
    expect(hasRenderableCellGeometry(cell)).toBe(false);
  });
});
