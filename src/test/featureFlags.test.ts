import { describe, expect, it } from 'vitest';
import { resolveFeatureFlags } from '@/lib/featureFlags';

describe('resolveFeatureFlags', () => {
  it('returns partnerIntake=true when VITE_FEATURE_PARTNER_INTAKE is "true"', () => {
    const flags = resolveFeatureFlags({ VITE_FEATURE_PARTNER_INTAKE: 'true' });
    expect(flags.partnerIntake).toBe(true);
  });

  it('returns partnerIntake=false when VITE_FEATURE_PARTNER_INTAKE is empty', () => {
    const flags = resolveFeatureFlags({ VITE_FEATURE_PARTNER_INTAKE: '' });
    expect(flags.partnerIntake).toBe(false);
  });

  it('returns partnerIntake=false when VITE_FEATURE_PARTNER_INTAKE is undefined', () => {
    const flags = resolveFeatureFlags({});
    expect(flags.partnerIntake).toBe(false);
  });

  it('returns partnerIntake=false when VITE_FEATURE_PARTNER_INTAKE is "false"', () => {
    const flags = resolveFeatureFlags({ VITE_FEATURE_PARTNER_INTAKE: 'false' });
    expect(flags.partnerIntake).toBe(false);
  });

  it('is a pure function — same input yields same output', () => {
    const env = { VITE_FEATURE_PARTNER_INTAKE: 'true' };
    expect(resolveFeatureFlags(env)).toEqual(resolveFeatureFlags(env));
  });
});
