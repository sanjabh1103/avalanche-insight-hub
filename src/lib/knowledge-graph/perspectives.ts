/**
 * Perspective definitions for the knowledge graph.
 *
 * Each perspective filters and highlights a subset of the graph
 * relevant to a specific way of understanding the codebase.
 */

import type { GraphNode, GraphEdge } from './graphData';
import { graph, graphIndex } from './graphData';

export type PerspectiveId =
  | 'architecture'
  | 'ml-pipeline'
  | 'data-flow'
  | 'security-gates'
  | 'tests'
  | 'release-evidence';

export interface Perspective {
  id: PerspectiveId;
  label: string;
  description: string;
  icon: string;
  filter: (node: GraphNode) => boolean;
  edgeFilter: (edge: GraphEdge) => boolean;
  highlightIds?: Set<string>;
}

const ML_KEYWORDS = [
  'model', 'train', 'forecast', 'feature', 'inference', 'surrogate',
  'rf', 'random_forest', 'lstm', 'neural', 'sklearn', 'torch',
  'pytorch', 'scoring', 'prediction', 'dataset', 'snowpack',
  'terrain', 'risk_math', 'abc_optimizer', 'pss', 'brier',
  'shap', 'explainability', 'verification', 'evaluation',
];

const SECURITY_KEYWORDS = [
  'gate', 'verify', 'verification', 'audit', 'denylist', 'auth',
  'token', 'secret', 'credential', 'license', 'provenance',
  'preflight', 'conformance', 'compliance', 'governance',
  'label_governance', 'sar_acceptance', 'risk_math',
  'verification_exit_gates', 'security', 'access',
];

const RELEASE_KEYWORDS = [
  'artifact', 'manifest', 'release', 'evidence', 'snapshot',
  'mvp4', 'mvp3', 'progress', 'governance', 'approval',
  'preflight', 'audit', 'reproduction', 'benchmark',
  'release_manifest', 'source_overlap', 'reviewed',
];

const TEST_KEYWORDS = ['test', 'mock', 'fixture', 'spec', 'verify'];

function matchesKeywords(node: GraphNode, keywords: string[]): boolean {
  const haystack = [
    node.name,
    node.filePath || '',
    node.summary || '',
    ...(node.tags || []),
  ].join(' ').toLowerCase();
  return keywords.some((kw) => haystack.includes(kw));
}

function isFileNode(node: GraphNode): boolean {
  return node.type === 'file' || node.type === 'pipeline' || node.type === 'config';
}

export const perspectives: Perspective[] = [
  {
    id: 'architecture',
    label: 'Architecture',
    description: 'Full codebase structure: files, modules, imports, and containment hierarchy.',
    icon: 'Network',
    filter: (node) => node.type === 'file' || node.type === 'pipeline' || node.type === 'config',
    edgeFilter: (edge) => edge.type === 'imports' || edge.type === 'contains',
  },
  {
    id: 'ml-pipeline',
    label: 'ML Pipeline',
    description: 'The active forecast path: RF surrogate, feature engineering, training, inference, and verification.',
    icon: 'Brain',
    filter: (node) => {
      if (node.type === 'file' || node.type === 'function' || node.type === 'class') {
        return matchesKeywords(node, ML_KEYWORDS);
      }
      return false;
    },
    edgeFilter: (edge) => edge.type === 'calls' || edge.type === 'imports' || edge.type === 'contains',
  },
  {
    id: 'data-flow',
    label: 'Data Flow',
    description: 'How data moves through the system: source ingestion → feature engineering → model → output.',
    icon: 'GitBranch',
    filter: (node) => {
      if (matchesKeywords(node, ['source', 'ingest', 'snapshot', 'dataset', 'feature', 'training', 'data'])) {
        return true;
      }
      return isFileNode(node) && matchesKeywords(node, ['source', 'ingest', 'snapshot', 'dataset', 'feature', 'training', 'data']);
    },
    edgeFilter: (edge) => edge.type === 'calls' || edge.type === 'imports',
  },
  {
    id: 'security-gates',
    label: 'Security & Gates',
    description: 'Verification gates, denylist zones, auth, provenance, and safety thresholds.',
    icon: 'ShieldCheck',
    filter: (node) => matchesKeywords(node, SECURITY_KEYWORDS),
    edgeFilter: (edge) => edge.type === 'calls' || edge.type === 'imports' || edge.type === 'tested_by',
  },
  {
    id: 'tests',
    label: 'Tests',
    description: 'Test coverage: which source files have tests and which test files cover what.',
    icon: 'FlaskConical',
    filter: (node) => {
      if (node.type === 'file') {
        return matchesKeywords(node, TEST_KEYWORDS) || (node.filePath || '').includes('test');
      }
      return false;
    },
    edgeFilter: (edge) => edge.type === 'tested_by' || edge.type === 'contains',
  },
  {
    id: 'release-evidence',
    label: 'Release & Evidence',
    description: 'Artifacts, manifests, governance, approval gates, and release evidence chain.',
    icon: 'FileCheck',
    filter: (node) => matchesKeywords(node, RELEASE_KEYWORDS),
    edgeFilter: (edge) => edge.type === 'imports' || edge.type === 'contains',
  },
];

export function getPerspective(id: PerspectiveId): Perspective {
  return perspectives.find((p) => p.id === id) || perspectives[0];
}

// Map of perspective ID to the edge types it includes — enables O(relevant) instead of O(all) edge scan
const PERSPECTIVE_EDGE_TYPES: Record<string, string[]> = {
  'architecture': ['imports', 'contains'],
  'ml-pipeline': ['calls', 'imports', 'contains'],
  'data-flow': ['calls', 'imports'],
  'security-gates': ['calls', 'imports', 'tested_by'],
  'tests': ['tested_by', 'contains'],
  'release-evidence': ['imports', 'contains'],
};

export function filterGraph(
  perspective: Perspective,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  // Filter nodes using the perspective filter (still O(N) due to keyword matching)
  const filteredNodes = graph.nodes.filter(perspective.filter);
  const nodeIds = new Set(filteredNodes.map((n) => n.id));

  // Filter edges — use indexed edgesByType to only scan relevant edge types
  // instead of all edges. Falls back to full scan if perspective is unknown.
  const relevantEdgeTypes = PERSPECTIVE_EDGE_TYPES[perspective.id];
  const filteredEdges: GraphEdge[] = [];
  if (relevantEdgeTypes) {
    for (const edgeType of relevantEdgeTypes) {
      const edgesOfType = graphIndex.getEdgesByType(edgeType);
      for (const edge of edgesOfType) {
        if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
          filteredEdges.push(edge);
        }
      }
    }
  } else {
    // Fallback: full scan with edgeFilter
    for (const edge of graph.edges) {
      if (perspective.edgeFilter(edge) && nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
        filteredEdges.push(edge);
      }
    }
  }
  return { nodes: filteredNodes, edges: filteredEdges };
}
