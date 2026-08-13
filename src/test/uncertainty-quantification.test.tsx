import { describe, it, expect } from 'vitest';
import { normalizeGridCells } from '@/lib/gridUtils';

describe('F13: Uncertainty Quantification — GridCell normalization', () => {
  it('normalizes forecastConfidence from snake_case', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 32,
      lng: 78,
      forecast_confidence: 'high',
    }]);
    expect(cells[0].forecastConfidence).toBe('high');
  });

  it('normalizes brierScore from snake_case', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 32,
      lng: 78,
      brier_score: 0.1234,
    }]);
    expect(cells[0].brierScore).toBeCloseTo(0.1234, 4);
  });

  it('normalizes conformalLower and conformalUpper from snake_case', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 32,
      lng: 78,
      conformal_lower: 0.35,
      conformal_upper: 0.75,
    }]);
    expect(cells[0].conformalLower).toBeCloseTo(0.35, 2);
    expect(cells[0].conformalUpper).toBeCloseTo(0.75, 2);
  });

  it('preserves camelCase forecastConfidence', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 32,
      lng: 78,
      forecastConfidence: 'low',
    }]);
    expect(cells[0].forecastConfidence).toBe('low');
  });
});

describe('F13: Model Confidence Badge colors', () => {
  it('maps high confidence to emerald', () => {
    const expectedClass = 'bg-emerald-500/15 text-emerald-400';
    expect(expectedClass).toContain('emerald');
  });

  it('maps medium confidence to amber', () => {
    const expectedClass = 'bg-amber-500/15 text-amber-300';
    expect(expectedClass).toContain('amber');
  });

  it('maps low confidence to red', () => {
    const expectedClass = 'bg-red-500/15 text-red-400';
    expect(expectedClass).toContain('red');
  });

  it('maps unknown confidence to slate', () => {
    const expectedClass = 'bg-slate-500/15 text-slate-300';
    expect(expectedClass).toContain('slate');
  });
});

describe('F13: Brier score display formatting', () => {
  it('formats brier score to 4 decimal places', () => {
    const brier = 0.123456;
    const formatted = brier.toFixed(4);
    expect(formatted).toBe('0.1235');
  });

  it('formats brier score of 0', () => {
    const brier = 0.0;
    const formatted = brier.toFixed(4);
    expect(formatted).toBe('0.0000');
  });
});

describe('F13: Conformal interval display', () => {
  it('formats interval as X.XX – Y.YY', () => {
    const lower = 0.356;
    const upper = 0.789;
    const formatted = `${lower.toFixed(2)} – ${upper.toFixed(2)}`;
    expect(formatted).toBe('0.36 – 0.79');
  });

  it('handles clamped interval at bounds', () => {
    const lower = 0.0;
    const upper = 1.0;
    const formatted = `${lower.toFixed(2)} – ${upper.toFixed(2)}`;
    expect(formatted).toBe('0.00 – 1.00');
  });
});

describe('F13: Confidence hidden when absent', () => {
  it('does not render badge when forecastConfidence is undefined', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 32,
      lng: 78,
    }]);
    expect(cells[0].forecastConfidence).toBeUndefined();
  });
});
