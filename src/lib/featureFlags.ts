/**
 * Pure feature-flag resolver.
 *
 * Centralizes all feature flag reads into a single injectable function.
 * No module-scoped state — the resolver is called at render time with
 * the environment object, making it fully testable without module resets.
 */

export interface FeatureFlags {
  partnerIntake: boolean;
  technicalArtifact: boolean;
}

export interface FeatureFlagEnv {
  VITE_FEATURE_PARTNER_INTAKE?: string;
  VITE_FEATURE_TECHNICAL_ARTIFACT?: string;
}

/**
 * Resolve feature flags from a given environment object.
 * Pure function — no side effects, no module-scoped state.
 */
export function resolveFeatureFlags(env: FeatureFlagEnv): FeatureFlags {
  return {
    partnerIntake: env.VITE_FEATURE_PARTNER_INTAKE === 'true',
    technicalArtifact: env.VITE_FEATURE_TECHNICAL_ARTIFACT === 'true',
  };
}

/**
 * Default resolver using import.meta.env.
 * Call this at render time, not at module scope.
 */
export function getDefaultFeatureFlags(): FeatureFlags {
  return resolveFeatureFlags(import.meta.env as unknown as FeatureFlagEnv);
}
