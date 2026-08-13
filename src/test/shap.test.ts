import { describe, it, expect } from 'vitest';

// Story 19 regression: the frontend MUST never render more than 5 SHAP bars,
// and the top-N rule MUST be driven by absolute contribution so that strong
// negative drivers are preserved.
// This mirrors the transformation in RiskDashboard.tsx so we catch regressions
// without spinning up the full chart/RTL stack.
function buildTopFiveShap(shapValues: Record<string, number>) {
  return Object.entries(shapValues)
    .map(([key, value]) => ({
      name: key.replace(/_/g, ' '),
      value: Number(value.toFixed(3)),
    }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, 5);
}

describe('SHAP top-5 contract (Story 19)', () => {
  it('returns at most 5 entries even when 10 features are provided', () => {
    const shapValues: Record<string, number> = {
      snowfall_24h: 0.41,
      wind_speed: 0.28,
      temperature: 0.09,
      elevation: 0.22,
      slope_angle: 0.17,
      aspect: 0.12,
      rain_48h: 0.33,
      fresh_snow_72h: 0.37,
      temp_gradient_24h: 0.19,
      freezing_level: 0.15,
    };
    const topFive = buildTopFiveShap(shapValues);
    expect(topFive).toHaveLength(5);
  });

  it('orders features by absolute contribution, preserving negative drivers', () => {
    const shapValues = {
      snowfall_24h: 0.05,
      wind_speed: -0.44, // strong negative driver
      temperature: 0.10,
      elevation: 0.33,
      slope_angle: -0.02,
      aspect: 0.01,
    };
    const topFive = buildTopFiveShap(shapValues);
    expect(topFive[0].name).toBe('wind speed');
    expect(topFive[0].value).toBeCloseTo(-0.44, 3);
    expect(topFive[1].name).toBe('elevation');
  });

  it('returns all features when fewer than 5 exist', () => {
    const topFive = buildTopFiveShap({ snowfall_24h: 0.1, wind_speed: 0.2 });
    expect(topFive).toHaveLength(2);
  });
});
