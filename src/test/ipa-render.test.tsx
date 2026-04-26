import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import RiskDashboard from '@/components/RiskDashboard';
import { forecastGridRowToCells, type ForecastGridRowRecord, type GridCell } from '@/lib/gridUtils';

function buildCell(overrides: Partial<GridCell> = {}): GridCell {
  return {
    row: 9,
    col: 12,
    lat: 0,
    lng: 0,
    latEnd: 0,
    lngEnd: 0,
    riskScore: 4,
    hazard: 0.72,
    exposure: 0.54,
    vulnerability: 0.33,
    problemType: 'Persistent Slab',
    shapValues: {
      snowfall_24h: 0.31,
      wind_speed: 0.14,
    },
    probability: 0.66,
    ...overrides,
  };
}

describe('IPA hydration and render contract', () => {
  it('hydrates IPA fields from forecast grid rows in both snake_case and camelCase forms', () => {
    const row: ForecastGridRowRecord = {
      id: 'grid-1',
      region_name: 'Colorado Rockies',
      forecast_date: '2026-04-23',
      horizon_hours: 24,
      bbox: [0, 0, 1, 1],
      grid_geojson: [
        {
          row: 9,
          col: 12,
          lat: 1,
          lng: 2,
          lat_end: 1.5,
          lng_end: 2.5,
          risk_score: 4,
          hazard: 0.72,
          exposure: 0.54,
          vulnerability: 0.33,
          problem_type: 'Persistent Slab',
          shap_values: { snowfall_24h: 0.31 },
          rf_probability: 0.71,
          fusion_method: 'chebyshev_ipa_v2',
          limiting_factor: 'snowpack_weakness',
          chebyshev_ipa_score: 0.8421,
          hazard_vector: {
            probability: 0.71,
            slope_deviation_from_38deg: 0.22,
            aspect_risk: 0.44,
            snowpack_weakness: 0.91,
            exposure: 0.54,
          },
        },
        {
          row: 10,
          col: 13,
          lat: 1,
          lng: 2,
          lat_end: 1.5,
          lng_end: 2.5,
          risk_score: 3,
          hazard: 0.61,
          exposure: 0.47,
          vulnerability: 0.29,
          problem_type: 'Storm Slab',
          shap_values: { wind_speed: 0.24 },
          rfProbability: 0.63,
          fusionMethod: 'chebyshev_ipa_v2',
          limitingFactor: 'probability',
          chebyshevIpaScore: 0.7812,
          hazardVector: {
            probability: 0.63,
            slope_deviation_from_38deg: 0.18,
            aspect_risk: 0.38,
            snowpack_weakness: 0.59,
            exposure: 0.47,
          },
        },
      ],
    };

    const cells = forecastGridRowToCells(row);

    expect(cells).toHaveLength(2);
    expect(cells[0].rfProbability).toBeCloseTo(0.71, 2);
    expect(cells[0].fusionMethod).toBe('chebyshev_ipa_v2');
    expect(cells[0].limitingFactor).toBe('snowpack_weakness');
    expect(cells[0].chebyshevIpaScore).toBeCloseTo(0.8421, 4);
    expect(cells[0].hazardVector).toEqual({
      probability: 0.71,
      slope_deviation_from_38deg: 0.22,
      aspect_risk: 0.44,
      snowpack_weakness: 0.91,
      exposure: 0.54,
    });

    expect(cells[1].rfProbability).toBeCloseTo(0.63, 2);
    expect(cells[1].fusionMethod).toBe('chebyshev_ipa_v2');
    expect(cells[1].limitingFactor).toBe('probability');
    expect(cells[1].chebyshevIpaScore).toBeCloseTo(0.7812, 4);
    expect(cells[1].hazardVector).toEqual({
      probability: 0.63,
      slope_deviation_from_38deg: 0.18,
      aspect_risk: 0.38,
      snowpack_weakness: 0.59,
      exposure: 0.47,
    });
  });

  it('renders the IPA block when the selected cell carries limiting-factor metadata', () => {
    render(
      <RiskDashboard
        cell={buildCell({
          fusionMethod: 'chebyshev_ipa_v2',
          limitingFactor: 'snowpack_weakness',
          chebyshevIpaScore: 0.8421,
          rfProbability: 0.71,
          hazardVector: {
            probability: 0.71,
            slope_deviation_from_38deg: 0.22,
            aspect_risk: 0.44,
            snowpack_weakness: 0.91,
            exposure: 0.54,
          },
        })}
        weatherSummary={null}
        shapResult={null}
      />,
    );

    expect(screen.getByText('Limiting factor')).toBeTruthy();
    expect(screen.getByText('snowpack weakness • IPA 0.84')).toBeTruthy();
    expect(screen.getByText('fusion: chebyshev_ipa_v2')).toBeTruthy();
  });
});
