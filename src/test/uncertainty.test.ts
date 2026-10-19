import { describe, it, expect } from 'vitest';
import { isHighUncertaintyCell, HIGH_UNCERTAINTY_SPAN_THRESHOLD } from '@/lib/gridUtils';

// Story 16 regression: strict PRD rule — grey cells ONLY when the raw interval
// span exceeds 0.30, overriding any EAWS palette decision.

describe('isHighUncertaintyCell (Story 16 strict threshold)', () => {
  it('returns true when confidence interval span exceeds 0.30', () => {
    expect(isHighUncertaintyCell({ confidenceLower: 0.3, confidenceUpper: 0.62 })).toBe(true);
  });

  it('returns false when confidence interval span is 0.30 exactly (strict > rule)', () => {
    expect(isHighUncertaintyCell({ confidenceLower: 0.3, confidenceUpper: 0.6 })).toBe(false);
  });

  it('returns false when confidence interval span is 0.29', () => {
    expect(isHighUncertaintyCell({ confidenceLower: 0.3, confidenceUpper: 0.59 })).toBe(false);
  });

  it('falls back to uncertaintySpan when bounds missing', () => {
    expect(isHighUncertaintyCell({ uncertaintySpan: 0.31 })).toBe(true);
    expect(isHighUncertaintyCell({ uncertaintySpan: 0.25 })).toBe(false);
  });

  it('falls back to uncertaintyClass when numeric fields absent', () => {
    expect(isHighUncertaintyCell({ uncertaintyClass: 'high' })).toBe(true);
    expect(isHighUncertaintyCell({ uncertaintyClass: 'medium' })).toBe(false);
    expect(isHighUncertaintyCell({ uncertaintyClass: 'low' })).toBe(false);
  });

  it('returns false for null / undefined / empty cells', () => {
    expect(isHighUncertaintyCell(null)).toBe(false);
    expect(isHighUncertaintyCell(undefined)).toBe(false);
    expect(isHighUncertaintyCell({})).toBe(false);
  });

  it('exports the canonical threshold constant', () => {
    expect(HIGH_UNCERTAINTY_SPAN_THRESHOLD).toBe(0.3);
  });
});
