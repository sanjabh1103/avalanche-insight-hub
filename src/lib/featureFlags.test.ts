import { describe, it, expect } from 'vitest';
import { resolveFeatureFlags } from '@/lib/featureFlags';

describe('resolveFeatureFlags', () => {
  it('enables technicalArtifact when VITE_FEATURE_TECHNICAL_ARTIFACT is "true"', () => {
    const flags = resolveFeatureFlags({ VITE_FEATURE_TECHNICAL_ARTIFACT: 'true' });
    expect(flags.technicalArtifact).toBe(true);
  });

  it('disables technicalArtifact when VITE_FEATURE_TECHNICAL_ARTIFACT is not set', () => {
    const flags = resolveFeatureFlags({});
    expect(flags.technicalArtifact).toBe(false);
  });

  it('disables technicalArtifact when VITE_FEATURE_TECHNICAL_ARTIFACT is "false"', () => {
    const flags = resolveFeatureFlags({ VITE_FEATURE_TECHNICAL_ARTIFACT: 'false' });
    expect(flags.technicalArtifact).toBe(false);
  });

  it('enables partnerIntake when VITE_FEATURE_PARTNER_INTAKE is "true"', () => {
    const flags = resolveFeatureFlags({ VITE_FEATURE_PARTNER_INTAKE: 'true' });
    expect(flags.partnerIntake).toBe(true);
  });

  it('disables partnerIntake when VITE_FEATURE_PARTNER_INTAKE is not set', () => {
    const flags = resolveFeatureFlags({});
    expect(flags.partnerIntake).toBe(false);
  });
});
