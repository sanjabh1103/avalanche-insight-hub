import { describe, expect, it } from 'vitest';

import { availableAvalancheLocales, resolveAvalancheCopy } from '@/lib/avalancheCopyI18n';

describe('avalancheCopyI18n', () => {
  it('provides Hindi and Nepali scaffold labels with English fallback', () => {
    expect(availableAvalancheLocales()).toEqual(['en', 'hi', 'ne']);
    expect(resolveAvalancheCopy('danger.high', 'hi')).toBeTruthy();
    expect(resolveAvalancheCopy('danger.high', 'ne')).toBeTruthy();
    expect(resolveAvalancheCopy('validation.synthetic_demo_boundary', 'en')).toContain('Synthetic demo');
  });
});
