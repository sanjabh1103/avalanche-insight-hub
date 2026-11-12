/**
 * Audience-specific section generators for the knowledge graph explainer.
 *
 * Each generator produces an ExplanationSection tailored to a specific
 * audience (novice / ml_expert / technical_customer) and depth
 * (briefing / working / deep). Content is deterministic, source-backed,
 * and uses structured claims with evidence references.
 *
 * Generators are pure functions with no network/model/UI dependencies.
 */

import type { GraphNode } from './graphData';
import {
  getChildren,
  getCallers,
  getCallees,
  getImporters,
  getTesters,
  getLayerForNode,
} from './graphData';
import {
  createStructuredClaim,
  renderStructuredClaim,
  type AudienceId,
  type ClaimCategory,
  type DepthId,
  type GraphFreshness,
} from './audienceModel';
import type { ExplanationSection } from './explainer';

export interface SectionGeneratorContext {
  audience: AudienceId;
  depth: DepthId;
  evidenceRefs: readonly string[];
  snapshotId?: string | null;
  graphHash?: string | null;
  graphFreshness?: GraphFreshness;
  proofLevel: 'snapshot-linked' | 'unverified';
}

type SectionGenerator = (node: GraphNode, ctx: SectionGeneratorContext) => ExplanationSection | null;

// ============================================================================
// Depth adaptation helpers
// ============================================================================

function depthPrefix(depth: DepthId): string {
  switch (depth) {
    case 'briefing':
      return '';  // no prefix — keep it concise
    case 'working':
      return '';
    case 'deep':
      return '';
  }
}

function depthSuffix(depth: DepthId, nodeName: string): string {
  switch (depth) {
    case 'briefing':
      return '';
    case 'working':
      return `\n\n_Next check: verify ${nodeName} against the current graph snapshot before acting on this._`;
    case 'deep':
      return `\n\n_Audit note: provenance, boundaries, and unresolved evidence must be preserved for ${nodeName}. Do not collapse caveats._`;
  }
}

function depthTruncate(text: string, depth: DepthId): string {
  const limits: Record<DepthId, number> = { briefing: 300, working: 600, deep: 1200 };
  const limit = limits[depth];
  if (text.length <= limit) return text;
  return text.substring(0, limit) + '…';
}

// ============================================================================
// Claim category helper
// ============================================================================

function resolveClaimCategory(
  preferred: ClaimCategory,
  ctx: SectionGeneratorContext,
): ClaimCategory {
  if (preferred === 'plan') return preferred;
  if (ctx.proofLevel === 'snapshot-linked' && ctx.graphFreshness === 'current') {
    return preferred;
  }
  return ctx.graphFreshness === 'stale' ? 'stale' : 'blocked';
}

function makeSection(
  heading: string,
  body: string,
  preferredCategory: ClaimCategory,
  ctx: SectionGeneratorContext,
  nodeName: string,
): ExplanationSection {
  const category = resolveClaimCategory(preferredCategory, ctx);
  const fullBody = depthTruncate(body + depthSuffix(ctx.depth, nodeName), ctx.depth);
  const claim = createStructuredClaim(
    fullBody,
    category,
    ctx.evidenceRefs,
    { snapshotId: ctx.snapshotId, graphHash: ctx.graphHash },
  );
  return {
    heading: `${depthPrefix(ctx.depth)}${heading}`,
    body: renderStructuredClaim(claim),
    sourceRefs: [...ctx.evidenceRefs],
    claimCategory: claim.category,
    claim,
    claims: [claim],
  };
}

// ============================================================================
// Novice section generators
// ============================================================================

const generatePurpose: SectionGenerator = (node, ctx) => {
  const summary = node.summary || `This ${node.type} is part of the Avalanche Insight Hub codebase.`;
  const body = `**${node.name}** exists to: ${summary} It contributes to the overall avalanche risk intelligence platform by providing ${node.type === 'file' ? 'code structure' : 'a specific function or class'} that supports the system's goals.`;
  return makeSection('Purpose', body, 'fact', ctx, node.name);
};

const generateInputsOutputs: SectionGenerator = (node, ctx) => {
  const callers = getCallers(node.id);
  const callees = getCallees(node.id);
  const importers = getImporters(node.id);
  const children = getChildren(node.id);

  const inputs: string[] = [];
  const outputs: string[] = [];

  if (importers.length > 0) inputs.push(`Imported by ${importers.length} module(s)`);
  if (callers.length > 0) inputs.push(`Called by ${callers.length} function(s)`);
  if (children.length > 0) outputs.push(`Contains ${children.length} child element(s)`);
  if (callees.length > 0) outputs.push(`Calls ${callees.length} function(s)`);

  const inputText = inputs.length > 0 ? inputs.join(', ') : 'No explicit inputs found in the graph';
  const outputText = outputs.length > 0 ? outputs.join(', ') : 'No explicit outputs found in the graph';

  const body = `**Inputs:** ${inputText}.\n\n**Outputs:** ${outputText}.\n\nThis node receives data or control from its inputs and produces results or side effects through its outputs.`;
  return makeSection('Inputs & Outputs', body, 'fact', ctx, node.name);
};

const generateTrustLimits: SectionGenerator = (node, ctx) => {
  const testers = getTesters(node.id);
  const hasTests = testers.length > 0;
  const layer = getLayerForNode(node.id);

  const parts: string[] = [
    `This explanation is based on the structural knowledge graph, not a semantic analysis.`,
  ];
  if (!hasTests) {
    parts.push(`This node has no direct test coverage in the graph — its behavior may not be verified.`);
  } else {
    parts.push(`This node has ${testers.length} test file(s) covering it.`);
  }
  if (layer) {
    parts.push(`It belongs to the ${layer.name} layer, which provides ${layer.description.toLowerCase()}`);
  }
  parts.push(`Do not use this explanation as a safety recommendation. Avalanche safety decisions require professional forecast judgment.`);

  return makeSection('Trust Limits', parts.join(' '), 'inference', ctx, node.name);
};

const generateGlossary: SectionGenerator = (node, ctx) => {
  const terms: Record<string, string> = {
    file: 'A source code file containing implementation logic.',
    function: 'A callable unit of code that performs a specific task.',
    class: 'A blueprint for objects that encapsulates data and behavior.',
    pipeline: 'A sequence of processing stages that transform inputs to outputs.',
    config: 'A configuration file that controls system behavior.',
    document: 'A documentation file providing context or instructions.',
  };
  const termDef = terms[node.type] || `A ${node.type} in the codebase.`;
  const body = `**${node.type.charAt(0).toUpperCase() + node.type.slice(1)}:** ${termDef}\n\n**Node:** A single entity in the knowledge graph representing a code element.\n\n**Edge:** A relationship between two nodes (e.g., calls, imports, contains).\n\n**Perspective:** A filtered view of the graph that highlights specific concerns (e.g., ML pipeline, security gates).`;
  return makeSection('Glossary', body, 'fact', ctx, node.name);
};

const generateGuidedNextStep: SectionGenerator = (node, ctx) => {
  const callers = getCallers(node.id);
  const callees = getCallees(node.id);
  const testers = getTesters(node.id);

  const steps: string[] = [];
  if (node.filePath) {
    steps.push(`1. Read the source code at \`${node.filePath}\` to understand the implementation.`);
  }
  if (callers.length > 0) {
    steps.push(`2. Explore what calls this node — start with \`${callers[0].name}\`.`);
  }
  if (callees.length > 0) {
    steps.push(`3. Follow what this node calls — start with \`${callees[0].name}\`.`);
  }
  if (testers.length > 0) {
    steps.push(`4. Review the test coverage in \`${testers[0].name}\`.`);
  } else {
    steps.push(`4. Note: no direct tests found — consider whether this node needs test coverage.`);
  }
  steps.push(`5. Switch to a different perspective (e.g., ML Pipeline or Security Gates) to see this node from another angle.`);

  return makeSection('Guided Next Step', steps.join('\n'), 'plan', ctx, node.name);
};

// ============================================================================
// ML Expert section generators
// ============================================================================

const generateLabelsFeatures: SectionGenerator = (node, ctx) => {
  const name = node.name.toLowerCase();
  const path = (node.filePath || '').toLowerCase();
  const parts: string[] = [];

  if (name.includes('feature') || path.includes('feature')) {
    parts.push('This module handles feature engineering — converting raw weather, terrain, and snowpack signals into model-ready features.');
    parts.push('Features are physical proxies unless backed by local measured evidence.');
  } else if (name.includes('label') || path.includes('label')) {
    parts.push('This module manages labels — the ground-truth avalanche outcomes used for training and evaluation.');
    parts.push('Labels are sourced from independent observation datasets and are gated by provenance checks.');
  } else {
    parts.push('This node is part of the ML pipeline but is not directly a feature or label module.');
    parts.push('To inspect features, look for modules with "feature" in their name or path.');
    parts.push('To inspect labels, look for modules with "label" in their name or path.');
  }

  return makeSection('Labels & Features', parts.join(' '), 'inference', ctx, node.name);
};

const generateSplitsLeakage: SectionGenerator = (node, ctx) => {
  const path = (node.filePath || '').toLowerCase();
  const parts: string[] = [];

  if (path.includes('split') || path.includes('dataset')) {
    parts.push('This module is involved in dataset splitting. The system uses temporal splits to prevent leakage between training and evaluation.');
    parts.push('Source independence is enforced: training and evaluation data must come from distinct sources or time periods.');
  } else if (path.includes('leakage') || path.includes('verify')) {
    parts.push('This module checks for data leakage. Leakage detection ensures that training data does not contain information that would not be available at prediction time.');
  } else {
    parts.push('This node is not directly a split or leakage module.');
    parts.push('The system enforces temporal splits and source independence to prevent leakage.');
    parts.push('Leakage checks are gated by preflight verification before training and release.');
  }

  return makeSection('Splits & Leakage', parts.join(' '), 'inference', ctx, node.name);
};

const generateMetricsCalibration: SectionGenerator = (node, ctx) => {
  const name = node.name.toLowerCase();
  const path = (node.filePath || '').toLowerCase();
  const parts: string[] = [];

  if (name.includes('pss') || path.includes('pss') || name.includes('brier') || path.includes('brier')) {
    parts.push('This module is part of the verification and evaluation chain.');
    parts.push('PSS (Peirce Skill Score) and Brier Score are the primary quality metrics.');
    parts.push('The model must exceed PSS 0.45 floor and Brier 0.15 ceiling before promotion.');
  } else if (name.includes('metric') || path.includes('metric') || name.includes('eval')) {
    parts.push('This module computes or validates ML metrics.');
    parts.push('Key metrics: PSS (discrimination), Brier Score (calibration), and per-region accuracy.');
  } else {
    parts.push('This node is not directly a metrics module.');
    parts.push('The system uses PSS (Peirce Skill Score) as the primary discrimination metric with a floor of 0.45.');
    parts.push('Brier Score is used for calibration assessment with a ceiling of 0.15.');
  }

  return makeSection('Metrics & Calibration', parts.join(' '), 'inference', ctx, node.name);
};

const generateShapArtifactProvenance: SectionGenerator = (node, ctx) => {
  const name = node.name.toLowerCase();
  const path = (node.filePath || '').toLowerCase();
  const parts: string[] = [];

  if (name.includes('shap') || path.includes('shap')) {
    parts.push('This module handles SHAP (SHapley Additive exPlanations) values for model interpretability.');
    parts.push('SHAP values show which features contribute most to individual predictions.');
    parts.push('The SHAP explainer uses Gemini for natural language summaries with a deterministic fallback.');
  } else if (name.includes('artifact') || path.includes('artifact')) {
    parts.push('This module manages artifacts — timestamped, hash-addressed evidence bundles.');
    parts.push('Artifacts must include row snapshots, split boundaries, code SHA, and environment manifests for exact replay.');
  } else if (name.includes('manifest') || path.includes('manifest') || name.includes('provenance')) {
    parts.push('This module manages provenance — the audit trail for every evidence claim.');
    parts.push('Manifests record hashes, eligibility flags, and source lineage.');
  } else {
    parts.push('This node is not directly a SHAP, artifact, or provenance module.');
    parts.push('SHAP explanations are generated via the shap-explainer edge function.');
    parts.push('Artifacts are hash-addressed bundles with row snapshots and environment manifests.');
  }

  return makeSection('SHAP & Artifact Provenance', parts.join(' '), 'inference', ctx, node.name);
};

// ============================================================================
// Technical customer section generators
// ============================================================================

const generateInterfacesOwnership: SectionGenerator = (node, ctx) => {
  const path = (node.filePath || '').toLowerCase();
  const parts: string[] = [];

  if (path.includes('supabase/functions/')) {
    parts.push('This is a Supabase Edge Function — a serverless API endpoint deployed on the Supabase platform.');
    parts.push('It is invoked via HTTP POST and requires JWT authentication (verify_jwt = true).');
  } else if (path.includes('src/pages/') || path.includes('src/components/')) {
    parts.push('This is a frontend component — part of the React/TypeScript user interface.');
    parts.push('It is rendered in the browser and communicates with backend APIs via Supabase client.');
  } else if (path.includes('backend/')) {
    parts.push('This is a backend Python module — part of the ML training and evaluation pipeline.');
    parts.push('It runs on the server and is invoked by scheduled jobs or edge functions.');
  } else {
    parts.push('This node is part of the application codebase.');
    parts.push('Interfaces: check for API endpoints (Supabase Edge Functions), UI components (React), or Python modules (backend).');
  }

  return makeSection('Interfaces & Ownership', parts.join(' '), 'fact', ctx, node.name);
};

const generateSloReliability: SectionGenerator = (node, ctx) => {
  const path = (node.filePath || '').toLowerCase();
  const parts: string[] = [];

  if (path.includes('supabase/functions/')) {
    parts.push('Edge functions have cold-start latency of 1-3 seconds and a 512MB memory limit (2GB max).');
    parts.push('Reliability depends on Supabase platform SLA. No custom SLO is defined for individual functions.');
  } else if (path.includes('test')) {
    parts.push('This is a test file — it contributes to reliability by verifying code correctness.');
    parts.push('Test coverage is tracked via tested_by edges in the knowledge graph.');
  } else {
    parts.push('The system does not define explicit SLOs for individual code modules.');
    parts.push('Reliability is enforced through: preflight gates, test coverage, verification exit gates, and artifact provenance.');
    parts.push('Failure recovery: the system is designed to fail-closed — blocked operations are safer than silent failures.');
  }

  return makeSection('SLO & Reliability', parts.join(' '), 'inference', ctx, node.name);
};

const generateRbacObservability: SectionGenerator = (node, ctx) => {
  const path = (node.filePath || '').toLowerCase();
  const name = node.name.toLowerCase();
  const parts: string[] = [];

  if (name.includes('auth') || path.includes('auth') || path.includes('rls') || path.includes('rbac')) {
    parts.push('This module handles authentication or authorization.');
    parts.push('The system uses Supabase Auth with JWT verification, role-based access control via app_metadata.roles, and RLS policies.');
    parts.push('Roles: admin, scientist. Admin access is granted via app_metadata.roles, ADMIN_USER_IDS, or ADMIN_USER_EMAILS.');
  } else if (name.includes('audit') || path.includes('audit') || path.includes('log')) {
    parts.push('This module handles audit logging or observability.');
    parts.push('The system logs to Supabase tables with RLS policies for audit trail integrity.');
  } else {
    parts.push('This node is not directly an RBAC or observability module.');
    parts.push('RBAC: Supabase Auth + JWT + app_metadata.roles + RLS policies.');
    parts.push('Observability: audit logs in Postgres tables, console logging in edge functions.');
  }

  return makeSection('RBAC & Observability', parts.join(' '), 'inference', ctx, node.name);
};

const generateLicensingIntegration: SectionGenerator = (node, ctx) => {
  const path = (node.filePath || '').toLowerCase();
  const parts: string[] = [];

  if (path.includes('package.json') || path.includes('requirements') || path.includes('pyproject')) {
    parts.push('This file defines dependencies. Check for license compatibility before integration.');
    parts.push('The project uses MIT-licensed dependencies by default. Review each dependency license before commercial use.');
  } else if (path.includes('vite.config') || path.includes('tsconfig')) {
    parts.push('This is a build configuration file. It controls how the frontend is compiled and bundled.');
    parts.push('Integration: ensure your build environment matches the Node.js and Vite versions specified.');
  } else {
    parts.push('This node is not directly a licensing or integration module.');
    parts.push('Licensing: the project uses open-source dependencies. Review package.json and requirements files for license details.');
    parts.push('Integration: the frontend is a Vite/React app; the backend uses Supabase Edge Functions (Deno) and Python modules.');
  }

  return makeSection('Licensing & Integration', parts.join(' '), 'inference', ctx, node.name);
};

// ============================================================================
// Section generator registry
// ============================================================================

export const SECTION_GENERATORS: Record<string, SectionGenerator> = {
  // Novice
  purpose: generatePurpose,
  inputs_outputs: generateInputsOutputs,
  trust_limits: generateTrustLimits,
  glossary: generateGlossary,
  guided_next_step: generateGuidedNextStep,
  // ML expert
  labels_features: generateLabelsFeatures,
  splits_leakage: generateSplitsLeakage,
  metrics_calibration: generateMetricsCalibration,
  shap_artifact_provenance: generateShapArtifactProvenance,
  // Technical customer
  interfaces_ownership: generateInterfacesOwnership,
  slo_reliability: generateSloReliability,
  rbac_observability: generateRbacObservability,
  licensing_integration: generateLicensingIntegration,
};

export function generateAudienceSections(
  node: GraphNode,
  sectionIds: string[],
  ctx: SectionGeneratorContext,
): ExplanationSection[] {
  const sections: ExplanationSection[] = [];
  for (const id of sectionIds) {
    const generator = SECTION_GENERATORS[id];
    if (!generator) continue;
    const section = generator(node, ctx);
    if (section) sections.push(section);
  }
  return sections;
}

// ============================================================================
// "Why this answer" retrieval summary
// ============================================================================

export interface RetrievalSummary {
  evidenceRefs: string[];
  proofLevel: 'snapshot-linked' | 'unverified';
  graphFreshness: GraphFreshness;
  retrievalPath: string[];
  caveats: string[];
}

export function buildRetrievalSummary(
  node: GraphNode,
  ctx: SectionGeneratorContext,
): RetrievalSummary {
  const evidenceRefs = [...ctx.evidenceRefs];
  const retrievalPath: string[] = [];
  const caveats: string[] = [];

  // Build retrieval path description
  retrievalPath.push(`Selected node: ${node.name} (${node.id})`);
  if (node.filePath) {
    retrievalPath.push(`Source file: ${node.filePath}`);
  }
  const layer = getLayerForNode(node.id);
  if (layer) {
    retrievalPath.push(`Layer: ${layer.name}`);
  }
  retrievalPath.push(`Audience: ${ctx.audience}`);
  retrievalPath.push(`Depth: ${ctx.depth}`);

  // Add caveats based on evidence quality
  if (ctx.proofLevel === 'unverified') {
    caveats.push('Evidence is not linked to a verified graph snapshot.');
  }
  if (ctx.graphFreshness === 'stale') {
    caveats.push('Graph evidence is stale — do not treat as current implementation behavior.');
  }
  if (ctx.graphFreshness === 'unknown') {
    caveats.push('Graph freshness could not be determined.');
  }
  const testers = getTesters(node.id);
  if (testers.length === 0) {
    caveats.push('No direct test coverage found for this node.');
  }

  return {
    evidenceRefs,
    proofLevel: ctx.proofLevel,
    graphFreshness: ctx.graphFreshness || 'unknown',
    retrievalPath,
    caveats,
  };
}

export function renderRetrievalSummary(summary: RetrievalSummary): string {
  const lines: string[] = [
    '**Why this answer:**',
    '',
    `*Retrieval path:*`,
    ...summary.retrievalPath.map((p) => `  - ${p}`),
    '',
    `*Evidence:* ${summary.evidenceRefs.join(', ')}`,
    `*Proof level:* ${summary.proofLevel}`,
    `*Graph freshness:* ${summary.graphFreshness}`,
  ];
  if (summary.caveats.length > 0) {
    lines.push('', '*Caveats:*');
    lines.push(...summary.caveats.map((c) => `  - ${c}`));
  }
  return lines.join('\n');
}
