import { describe, expect, it } from 'vitest';
import { buildRiskExplanation, selectRiskDrivers } from '@/lib/riskNarratives';
import type { GridCell } from '@/lib/gridUtils';
import type { ShapResult } from '@/lib/shapLoader';

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
  it('prefers real TreeSHAP rows over inline heuristic values', () => {
    const cell = buildCell();
    const shapResult: ShapResult = {
      origin: 'forecast_shap_cache',
      topFeatures: [
        { feature: 'shear_strength', shap_value: 0.42, feature_value: 0.18, rank: 1 },
        { feature: 'wind_loading', shap_value: 0.14, feature_value: 0.62, rank: 2 },
      ],
      modelVersion: 'model-1',
      dominantDriver: 'shear_strength',
      baseValue: 0.41,
    };

    const { shapSource, drivers } = selectRiskDrivers(cell, shapResult);

    expect(shapSource).toBe('treeshap');
    expect(drivers[0].feature).toBe('shear_strength');
    expect(drivers[0].label).toBe('shear strength');
  });

  it('falls back to heuristic SHAP values when cached TreeSHAP is missing', () => {
    const { shapSource, drivers } = selectRiskDrivers(buildCell(), null);

    expect(shapSource).toBe('heuristic');
    expect(drivers[0].feature).toBe('snowfall_24h');
  });

  it('builds a deterministic explanation from the selected SHAP source', () => {
    const explanation = buildRiskExplanation(buildCell(), {
      origin: 'forecast_shap_cache',
      topFeatures: [
        { feature: 'wind_loading', shap_value: 0.31, feature_value: 0.71, rank: 1 },
        { feature: 'terrain_roughness', shap_value: -0.12, feature_value: 0.22, rank: 2 },
      ],
      modelVersion: 'model-1',
      dominantDriver: 'wind_loading',
      baseValue: 0.41,
    });

    expect(explanation).toContain('TreeSHAP indicates');
    expect(explanation).toContain('wind transport is building lee-side loading');
    expect(explanation).toContain('terrain roughness is diffusing some hazard');
  });
});
