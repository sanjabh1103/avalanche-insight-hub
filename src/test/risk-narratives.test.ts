import { describe, expect, it } from 'vitest';
import { buildRiskExplanation, selectRiskDrivers } from '@/lib/riskNarratives';
import type { GridCell } from '@/lib/gridUtils';

function buildCell(overrides: Partial<GridCell> = {}): GridCell {
  return {
    row: 1,
    col: 1,
    lat: 0,
    lng: 0,
    latEnd: 0,
    lngEnd: 0,
    riskScore: 4,
    hazard: 0.72,
    exposure: 0.44,
    vulnerability: 0.33,
    problemType: 'Persistent Slab',
    shapValues: {
      snowfall_24h: 0.18,
      wind_loading: 0.11,
      terrain_roughness: -0.06,
    },
    probability: 0.66,
    ...overrides,
  };
}

describe('risk narratives', () => {
  it('prefers authoritative shap_context rows from the batch artifact', () => {
    const cell = buildCell({
      shapContext: {
        topFeatures: [
          { feature: 'shear_strength', shap_value: 0.42, feature_value: 0.18, rank: 1 },
          { feature: 'wind_loading', shap_value: 0.14, feature_value: 0.62, rank: 2 },
        ],
      },
    });

    const { shapSource, drivers } = selectRiskDrivers(cell);

    expect(shapSource).toBe('artifact');
    expect(drivers[0].feature).toBe('shear_strength');
    expect(drivers[0].label).toBe('shear strength');
  });

  it('falls back to artifact shap_values when shap_context is missing', () => {
    const { shapSource, drivers } = selectRiskDrivers(buildCell());

    expect(shapSource).toBe('artifact');
    expect(drivers[0].feature).toBe('snowfall_24h');
  });

  it('builds a deterministic explanation from the selected SHAP source', () => {
    const explanation = buildRiskExplanation(buildCell({
      shapContext: {
        topFeatures: [
          { feature: 'wind_loading', shap_value: 0.31, feature_value: 0.71, rank: 1 },
          { feature: 'terrain_roughness', shap_value: -0.12, feature_value: 0.22, rank: 2 },
        ],
      },
    }));

    expect(explanation).toContain('Batch TreeSHAP indicates');
    expect(explanation).toContain('wind transport is building lee-side loading');
    expect(explanation).toContain('terrain roughness is diffusing some hazard');
  });

  it('renders an unavailable-terrain explanation without synthesizing drivers', () => {
    const explanation = buildRiskExplanation(buildCell({
      riskScore: 0,
      status: 'unavailable_terrain',
      stale: true,
      disabled: true,
      availabilityReason: 'unavailable_terrain',
      shapValues: {},
    }));

    expect(explanation).toContain('Terrain data is unavailable');
  });
});
