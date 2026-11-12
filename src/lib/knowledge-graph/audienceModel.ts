/**
 * Deterministic audience/depth/claim contract for the local knowledge workspace.
 *
 * This module deliberately has no network, model, filesystem, or UI dependency.
 * It shapes explanations and records whether their evidence is linked to a
 * known graph snapshot. It is not a forecast or a safety recommendation.
 */

export const AUDIENCE_IDS = ['novice', 'ml_expert', 'technical_customer'] as const;
export const DEPTH_IDS = ['briefing', 'working', 'deep'] as const;
export const CLAIM_CATEGORIES = [
  'fact',
  'inference',
  'plan',
  'unsupported',
  'stale',
  'blocked',
] as const;

export type AudienceId = (typeof AUDIENCE_IDS)[number];
export type DepthId = (typeof DEPTH_IDS)[number];
export type ClaimCategory = (typeof CLAIM_CATEGORIES)[number];
export type ProofLevel = 'snapshot-linked' | 'unverified';
export type GraphFreshness = 'current' | 'stale' | 'unknown';

export interface AudienceProfile {
  id: AudienceId;
  label: string;
  description: string;
  requiredSections: readonly string[];
}

export interface DepthProfile {
  id: DepthId;
  label: string;
  description: string;
}

export interface EvidenceBinding {
  snapshotId: string | null;
  graphHash: string | null;
  proofLevel: ProofLevel;
}

export interface StructuredClaim extends EvidenceBinding {
  text: string;
  category: ClaimCategory;
  evidenceRefs: string[];
}

export interface AudienceLensInput {
  audience: AudienceId;
  depth: DepthId;
  perspective: string;
  nodeName: string;
  evidenceRefs: readonly string[];
  snapshotId?: string | null;
  graphHash?: string | null;
  graphFreshness?: GraphFreshness;
}

export interface AudienceLens extends EvidenceBinding {
  audience: AudienceId;
  depth: DepthId;
  perspective: string;
  requiredSections: string[];
  claims: StructuredClaim[];
}

const audienceProfiles: Record<AudienceId, AudienceProfile> = {
  novice: {
    id: 'novice',
    label: 'Novice',
    description: 'Builds a correct mental model of purpose, inputs, outputs, and trust limits.',
    requiredSections: ['purpose', 'inputs_outputs', 'trust_limits', 'glossary', 'guided_next_step'],
  },
  ml_expert: {
    id: 'ml_expert',
    label: 'ML expert',
    description: 'Inspects labels, features, splits, leakage controls, metrics, calibration, and artifacts.',
    requiredSections: ['labels_features', 'splits_leakage', 'metrics_calibration', 'shap_artifact_provenance'],
  },
  technical_customer: {
    id: 'technical_customer',
    label: 'Technical customer',
    description: 'Evaluates interfaces, ownership, reliability, access, licensing, and integration obligations.',
    requiredSections: ['interfaces_ownership', 'slo_reliability', 'rbac_observability', 'licensing_integration'],
  },
};

const depthProfiles: Record<DepthId, DepthProfile> = {
  briefing: {
    id: 'briefing',
    label: 'Briefing',
    description: 'A concise orientation with the minimum evidence and the most important caveat.',
  },
  working: {
    id: 'working',
    label: 'Working',
    description: 'An actionable explanation with relationships, assumptions, and next checks.',
  },
  deep: {
    id: 'deep',
    label: 'Deep',
    description: 'An audit-oriented explanation with boundaries, provenance, and unresolved evidence.',
  },
};

function isAudienceId(value: unknown): value is AudienceId {
  return typeof value === 'string' && (AUDIENCE_IDS as readonly string[]).includes(value);
}

function isDepthId(value: unknown): value is DepthId {
  return typeof value === 'string' && (DEPTH_IDS as readonly string[]).includes(value);
}

export function normalizeAudience(value: unknown): AudienceId {
  return isAudienceId(value) ? value : 'novice';
}

export function normalizeDepth(value: unknown): DepthId {
  return isDepthId(value) ? value : 'briefing';
}

export function getAudienceProfile(id: AudienceId): AudienceProfile {
  return audienceProfiles[id];
}

export function getDepthProfile(id: DepthId): DepthProfile {
  return depthProfiles[id];
}

function cleanOptional(value: string | null | undefined): string | null {
  const cleaned = value?.trim();
  return cleaned ? cleaned : null;
}

function proofLevelFor(snapshotId: string | null, graphHash: string | null): ProofLevel {
  return snapshotId && graphHash ? 'snapshot-linked' : 'unverified';
}

export function createStructuredClaim(
  text: string,
  category: ClaimCategory,
  evidenceRefs: readonly string[],
  binding: Partial<Pick<EvidenceBinding, 'snapshotId' | 'graphHash'>> = {},
): StructuredClaim {
  const cleanText = text.trim();
  if (!cleanText) {
    throw new Error('Structured claim text is required.');
  }

  const cleanRefs = [...new Set(evidenceRefs.map((ref) => ref.trim()).filter(Boolean))];
  if (cleanRefs.length === 0) {
    throw new Error('At least one evidence reference is required for a structured claim.');
  }

  const snapshotId = cleanOptional(binding.snapshotId);
  const graphHash = cleanOptional(binding.graphHash);

  return {
    text: cleanText,
    category,
    evidenceRefs: cleanRefs,
    snapshotId,
    graphHash,
    proofLevel: proofLevelFor(snapshotId, graphHash),
  };
}

const categoryLabels: Record<ClaimCategory, string> = {
  fact: 'Fact',
  inference: 'Inference',
  plan: 'Plan',
  unsupported: 'Unsupported',
  stale: 'Stale',
  blocked: 'Blocked',
};

export function renderStructuredClaim(claim: StructuredClaim): string {
  const evidence = claim.evidenceRefs.join(', ');
  const snapshot = claim.snapshotId ? `; snapshot=${claim.snapshotId}` : '';
  const graph = claim.graphHash ? `; graph=${claim.graphHash}` : '';
  return `**${categoryLabels[claim.category]}:** ${claim.text}\n\n_Evidence (${claim.proofLevel}${snapshot}${graph}): ${evidence}_`;
}

function bindingFor(input: AudienceLensInput): EvidenceBinding {
  const snapshotId = cleanOptional(input.snapshotId);
  const graphHash = cleanOptional(input.graphHash);
  return {
    snapshotId,
    graphHash,
    proofLevel: proofLevelFor(snapshotId, graphHash),
  };
}

function claimCategoryForEvidence(
  freshness: GraphFreshness | undefined,
  proofLevel: ProofLevel,
): ClaimCategory {
  return proofLevel === 'snapshot-linked' && freshness === 'current' ? 'fact' : 'blocked';
}

export function buildAudienceLens(input: AudienceLensInput): AudienceLens {
  const audience = normalizeAudience(input.audience);
  const depth = normalizeDepth(input.depth);
  const perspective = input.perspective.trim() || 'architecture';
  const nodeName = input.nodeName.trim() || 'selected node';
  const evidenceRefs = input.evidenceRefs;
  const binding = bindingFor(input);
  const audienceProfile = getAudienceProfile(audience);
  const depthProfile = getDepthProfile(depth);
  const freshness = input.graphFreshness ?? 'unknown';
  const claims: StructuredClaim[] = [];

  claims.push(createStructuredClaim(
    `${nodeName} is being explained through the ${perspective} perspective for a ${audienceProfile.label.toLowerCase()} reader at ${depthProfile.label.toLowerCase()} depth.`,
    claimCategoryForEvidence(freshness, binding.proofLevel),
    evidenceRefs,
    binding,
  ));

  claims.push(createStructuredClaim(
    `${audienceProfile.label} mode prioritizes ${audienceProfile.description.toLowerCase()}`,
    binding.proofLevel === 'snapshot-linked' && freshness === 'current' ? 'inference' : 'plan',
    evidenceRefs,
    binding,
  ));

  claims.push(createStructuredClaim(
    `${depthProfile.label} depth should expose: ${audienceProfile.requiredSections.join(', ')}.`,
    'plan',
    evidenceRefs,
    binding,
  ));

  if (depth === 'deep') {
    claims.push(createStructuredClaim(
      `Deep review must preserve provenance, caveats, and unresolved evidence for ${nodeName}.`,
      binding.proofLevel === 'snapshot-linked' && freshness === 'current' ? 'inference' : 'blocked',
      evidenceRefs,
      binding,
    ));
  }

  if (freshness === 'stale') {
    claims.push(createStructuredClaim(
      `The graph evidence for ${nodeName} is stale and must not be presented as current implementation behavior.`,
      'stale',
      evidenceRefs,
      binding,
    ));
  } else if (freshness !== 'current' || binding.proofLevel !== 'snapshot-linked') {
    claims.push(createStructuredClaim(
      `Currentness is not established for ${nodeName}; customer-facing or operational conclusions remain blocked.`,
      'blocked',
      evidenceRefs,
      binding,
    ));
  }

  return {
    audience,
    depth,
    perspective,
    requiredSections: [...audienceProfile.requiredSections],
    claims,
    ...binding,
  };
}
