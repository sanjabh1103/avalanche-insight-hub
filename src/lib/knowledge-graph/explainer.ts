/**
 * Dynamic explanation generator.
 *
 * Produces structured, perspective-aware explanations for any node
 * in the knowledge graph. Explanations are assembled from:
 *  - Node metadata (name, type, summary, tags, complexity)
 *  - Graph relationships (callers, callees, importers, children, testers)
 *  - Layer and tour membership
 *  - Live source code snippets (when available from the dev API)
 *
 * No LLM is used — all explanations are rule-based and source-backed.
 */

import type { GraphNode } from './graphData';
import {
  getChildren,
  getCallers,
  getCallees,
  getImporters,
  getTesters,
  getLayerForNode,
  getTourStepForNode,
} from './graphData';
import type { GraphFreshness } from './graphData';
import {
  buildAudienceLens,
  createStructuredClaim,
  getAudienceProfile,
  getDepthProfile,
  normalizeAudience,
  normalizeDepth,
  renderStructuredClaim,
  type AudienceId,
  type AudienceLens,
  type ClaimCategory,
  type DepthId,
  type StructuredClaim,
} from './audienceModel';
import type { PerspectiveId } from './perspectives';
import { fetchCodeSnippet, type CodeSnippet } from './safeCodeApi';
import {
  generateAudienceSections,
  buildRetrievalSummary,
  renderRetrievalSummary,
  type SectionGeneratorContext,
} from './sectionGenerators';

export interface ExplanationOptions {
  audience?: AudienceId;
  depth?: DepthId;
  snapshotId?: string | null;
  graphHash?: string | null;
  graphFreshness?: GraphFreshness;
}

export interface ExplanationSection {
  heading: string;
  body: string;
  sourceRefs: string[];
  claimCategory: ClaimCategory;
  claim: StructuredClaim;
  claims: StructuredClaim[];
}

export interface NodeExplanation {
  nodeId: string;
  nodeName: string;
  nodeType: string;
  perspective: PerspectiveId;
  audience: AudienceId;
  depth: DepthId;
  audienceLens: AudienceLens;
  evidenceSummary: {
    proofLevel: AudienceLens['proofLevel'];
    snapshotId: string | null;
    graphHash: string | null;
    evidenceRefs: string[];
  };
  sections: ExplanationSection[];
  sourceSnippet?: CodeSnippet;
  retrievalSummary?: {
    evidenceRefs: string[];
    proofLevel: 'snapshot-linked' | 'unverified';
    graphFreshness: GraphFreshness;
    retrievalPath: string[];
    caveats: string[];
  };
  generatedAt: string;
}

function formatNodeList(nodes: GraphNode[], max = 10): string {
  if (nodes.length === 0) return 'None found.';
  const shown = nodes.slice(0, max);
  const lines = shown.map((n) => `- \`${n.name}\` (${n.type}${n.filePath ? `, ${n.filePath}` : ''})`);
  if (nodes.length > max) {
    lines.push(`- ... and ${nodes.length - max} more`);
  }
  return lines.join('\n');
}

function typeLabel(type: string): string {
  const labels: Record<string, string> = {
    file: 'File',
    function: 'Function',
    class: 'Class',
    pipeline: 'Pipeline',
    config: 'Configuration',
    document: 'Document',
  };
  return labels[type] || type;
}

export async function generateExplanation(
  node: GraphNode,
  perspective: PerspectiveId,
  options: ExplanationOptions = {},
): Promise<NodeExplanation> {
  const sections: ExplanationSection[] = [];
  const audience = normalizeAudience(options.audience);
  const depth = normalizeDepth(options.depth);
  const evidenceRefs = node.filePath ? [node.filePath] : [`graph:${node.id}`];
  const audienceLens = buildAudienceLens({
    audience,
    depth,
    perspective,
    nodeName: node.name,
    evidenceRefs,
    snapshotId: options.snapshotId,
    graphHash: options.graphHash,
    graphFreshness: options.graphFreshness,
  });

  const claimCategory = (preferred: ClaimCategory): ClaimCategory => {
    if (preferred === 'plan') return preferred;
    if (audienceLens.proofLevel === 'snapshot-linked' && options.graphFreshness === 'current') {
      return preferred;
    }
    return options.graphFreshness === 'stale' ? 'stale' : 'blocked';
  };

  const makeSection = (
    heading: string,
    body: string,
    preferredCategory: ClaimCategory,
  ): ExplanationSection => {
    const claim = createStructuredClaim(
      body,
      claimCategory(preferredCategory),
      evidenceRefs,
      audienceLens,
    );
    return {
      heading,
      body: renderStructuredClaim(claim),
      sourceRefs: [...evidenceRefs],
      claimCategory: claim.category,
      claim,
      claims: [claim],
    };
  };

  const makeAudienceSection = (): ExplanationSection => {
    const claims = audienceLens.claims;
    const firstClaim = claims[0];
    return {
      heading: `${getAudienceProfile(audience).label} / ${getDepthProfile(depth).label} Lens`,
      body: claims.map(renderStructuredClaim).join('\n\n'),
      sourceRefs: [...new Set(claims.flatMap((claim) => claim.evidenceRefs))],
      claimCategory: firstClaim.category,
      claim: firstClaim,
      claims,
    };
  };

  // Section 1: Overview
  sections.push(makeSection('Overview', [
      `**${node.name}** is a ${typeLabel(node.type).toLowerCase()} in the Avalanche Insight Hub codebase.`,
      node.summary ? `\n\n${node.summary}` : '',
      node.complexity ? `\n\n**Complexity:** ${node.complexity}` : '',
      node.tags?.length ? `\n\n**Tags:** ${node.tags.join(', ')}` : '',
    ].join(''), 'fact'));

  // Audience/depth shaping is additive; keep Overview first for existing consumers.
  sections.push(makeAudienceSection());

  // Section 2: Location and layer
  const layer = getLayerForNode(node.id);
  const tourStep = getTourStepForNode(node.id);
  if (layer || tourStep) {
    const parts: string[] = [];
    if (layer) {
      parts.push(`This node belongs to the **${layer.name}** layer.`);
      parts.push(`\n\n${layer.description}`);
    }
    if (tourStep) {
      parts.push(`\n\n**Tour step ${tourStep.order}: ${tourStep.title}**`);
      parts.push(`\n\n${tourStep.description}`);
      if (tourStep.languageLesson) {
        parts.push(`\n\n*Lesson:* ${tourStep.languageLesson}`);
      }
    }
    sections.push(makeSection('Context', parts.join(''), 'fact'));
  }

  // Section 3: Relationships (perspective-aware)
  const children = getChildren(node.id);
  const callers = getCallers(node.id);
  const callees = getCallees(node.id);
  const importers = getImporters(node.id);
  const testers = getTesters(node.id);

  const relParts: string[] = [];
  if (children.length > 0) {
    relParts.push(`**Contains (${children.length}):**\n${formatNodeList(children)}`);
  }
  if (callers.length > 0) {
    relParts.push(`**Called by (${callers.length}):**\n${formatNodeList(callers)}`);
  }
  if (callees.length > 0) {
    relParts.push(`**Calls (${callees.length}):**\n${formatNodeList(callees)}`);
  }
  if (importers.length > 0) {
    relParts.push(`**Imported by (${importers.length}):**\n${formatNodeList(importers)}`);
  }
  if (testers.length > 0) {
    relParts.push(`**Tested by (${testers.length}):**\n${formatNodeList(testers)}`);
  }

  if (relParts.length > 0) {
    let heading = 'Relationships';
    switch (perspective) {
      case 'ml-pipeline':
        heading = 'ML Pipeline Relationships';
        break;
      case 'data-flow':
        heading = 'Data Flow Relationships';
        break;
      case 'security-gates':
        heading = 'Security & Gate Relationships';
        break;
      case 'tests':
        heading = 'Test Coverage';
        break;
      case 'release-evidence':
        heading = 'Release Evidence Chain';
        break;
    }
    sections.push(makeSection(heading, relParts.join('\n\n'), 'fact'));
  }

  // Section 4: Perspective-specific interpretation
  const interpretation = getPerspectiveInterpretation(node, perspective);
  if (interpretation) {
    sections.push(makeSection(`${getPerspectiveLabel(perspective)} View`, interpretation, 'inference'));
  }

  // Section 5: Live source (if available)
  let sourceSnippet: CodeSnippet | undefined;
  if (node.filePath) {
    const response = await fetchCodeSnippet(node.filePath, 1, 50);
    if (response.available && response.snippet) {
      sourceSnippet = response.snippet;
      sections.push(makeSection(
        'Source Code (first 50 lines)',
        `Live source from \`${node.filePath}\`:\n\n\`\`\`${getLanguageFromPath(node.filePath)}\n${sourceSnippet.content}\n\`\`\`${sourceSnippet.truncated ? '\n\n*File continues beyond this snippet.*' : ''}`,
        'fact',
      ));
    } else if (response.error) {
      sections.push(makeSection(
        'Source Code',
        `Live source is not available${response.error === 'Live code API is not available in this build' ? ' in this build' : ''}. File path: \`${node.filePath}\``,
        'blocked',
      ));
    }
  }

  // Section 6: Audience-specific sections (Phase 4)
  const sectionCtx: SectionGeneratorContext = {
    audience,
    depth,
    evidenceRefs,
    snapshotId: options.snapshotId,
    graphHash: options.graphHash,
    graphFreshness: options.graphFreshness,
    proofLevel: audienceLens.proofLevel,
  };
  const audienceSections = generateAudienceSections(node, audienceLens.requiredSections, sectionCtx);
  sections.push(...audienceSections);

  // Section 7: "Why this answer" retrieval summary (Phase 4)
  const retrievalSummary = buildRetrievalSummary(node, sectionCtx);
  sections.push(makeSection(
    'Why This Answer',
    renderRetrievalSummary(retrievalSummary),
    'fact',
  ));

  return {
    nodeId: node.id,
    nodeName: node.name,
    nodeType: node.type,
    perspective,
    audience,
    depth,
    audienceLens,
    evidenceSummary: {
      proofLevel: audienceLens.proofLevel,
      snapshotId: audienceLens.snapshotId,
      graphHash: audienceLens.graphHash,
      evidenceRefs: [...evidenceRefs],
    },
    sections,
    sourceSnippet,
    retrievalSummary,
    generatedAt: new Date().toISOString(),
  };
}

function getPerspectiveLabel(id: PerspectiveId): string {
  const labels: Record<PerspectiveId, string> = {
    'architecture': 'Architecture',
    'ml-pipeline': 'ML Pipeline',
    'data-flow': 'Data Flow',
    'security-gates': 'Security & Gates',
    'tests': 'Tests',
    'release-evidence': 'Release & Evidence',
  };
  return labels[id] || id;
}

function getPerspectiveInterpretation(node: GraphNode, perspective: PerspectiveId): string | null {
  const name = node.name.toLowerCase();
  const path = (node.filePath || '').toLowerCase();

  switch (perspective) {
    case 'ml-pipeline':
      if (name.includes('train') || path.includes('train')) {
        return 'This is a training entry point. It orchestrates dataset loading, feature engineering, model fitting, and artifact generation. The training path is gated by preflight, source independence, and terrain-loss checks.';
      }
      if (name.includes('feature') || path.includes('feature')) {
        return 'This module handles feature engineering — converting raw weather, terrain, and snowpack signals into model-ready features. Features are physical proxies unless backed by local measured evidence.';
      }
      if (name.includes('surrogate') || name.includes('rf') || name.includes('model')) {
        return 'This is part of the active Random Forest surrogate model path. The RF model is the current public scorer; deep-learning candidates remain shadow-only until their quality gates pass.';
      }
      if (name.includes('verify') || name.includes('evaluation') || name.includes('pss') || name.includes('brier')) {
        return 'This module is part of the verification and evaluation chain. PSS (Peirce Skill Score) and Brier Score are the primary quality metrics. The model must exceed PSS 0.45 floor and Brier 0.15 ceiling before promotion.';
      }
      return null;

    case 'security-gates':
      if (path.includes('verification_exit_gates') || path.includes('label_governance') || path.includes('sar_acceptance')) {
        return 'This is a denylist zone — a safety-critical gate that must not be weakened. Any change requires explicit planner approval and must preserve or strengthen the threshold.';
      }
      if (name.includes('auth') || name.includes('token') || path.includes('auth')) {
        return 'This module handles authentication or authorization. It checks JWT tokens, role metadata, and access controls before allowing privileged operations.';
      }
      if (name.includes('preflight') || name.includes('gate') || name.includes('provenance')) {
        return 'This is a preflight or provenance gate. It blocks training or release when evidence is insufficient. The gate is fail-closed: exit code 2 means "blocked pending evidence", not a crash.';
      }
      return null;

    case 'data-flow':
      if (name.includes('ingest') || path.includes('ingest')) {
        return 'This is a data ingestion point. Raw events from external sources (BIPAD, GEE, HiAVAL, Everest Sentinel-1) enter the system here. Each source has its own adapter that normalizes, hashes, and stamps provenance.';
      }
      if (name.includes('snapshot') || path.includes('snapshot')) {
        return 'This builds a deterministic, hash-pinned snapshot. Snapshots are the reproducible evidence units — their SHA-256 hashes are checked at every stage from training to release.';
      }
      if (name.includes('dataset') || path.includes('dataset') || path.includes('training_dataset')) {
        return 'This is the training dataset assembly module. It combines label events, features, terrain, and snowpack proxies into a model-ready frame. The frame is gated by source independence, season coverage, and terrain-loss checks.';
      }
      return null;

    case 'tests':
      if (path.includes('test')) {
        const testers = getTesters(node.id);
        if (testers.length === 0 && node.type === 'file') {
          return 'This file does not have a direct tested_by edge in the graph. It may still be exercised indirectly through integration tests.';
        }
        return `This test file covers ${testers.length} source ${testers.length === 1 ? 'file' : 'files'}. Test coverage is tracked via the tested_by edge type.`;
      }
      return null;

    case 'release-evidence':
      if (name.includes('artifact') || path.includes('artifact')) {
        return 'This module manages artifacts — the timestamped, hash-addressed evidence bundles produced by training and inference runs. Artifacts must include row snapshots, split boundaries, code SHA, and environment manifests for exact replay.';
      }
      if (name.includes('manifest') || path.includes('manifest')) {
        return 'This is a manifest — a JSON document that records the provenance, hashes, and eligibility flags of a snapshot or artifact. Manifests are the audit trail for every evidence claim.';
      }
      if (name.includes('preflight') || name.includes('approval') || name.includes('governance')) {
        return 'This is part of the release governance chain. The release remains NO-GO until the exact-time independent-label gate, environment gate, and clean-candidate gate all pass.';
      }
      return null;

    case 'architecture':
      if (node.type === 'file') {
        const childCount = getChildren(node.id).length;
        if (childCount > 5) {
          return `This file contains ${childCount} functions or classes, making it a significant module in the codebase structure.`;
        }
      }
      return null;

    default:
      return null;
  }
}

function getLanguageFromPath(filePath: string): string {
  if (filePath.endsWith('.py')) return 'python';
  if (filePath.endsWith('.ts') || filePath.endsWith('.tsx')) return 'typescript';
  if (filePath.endsWith('.js') || filePath.endsWith('.jsx')) return 'javascript';
  if (filePath.endsWith('.json')) return 'json';
  if (filePath.endsWith('.md')) return 'markdown';
  return 'text';
}
