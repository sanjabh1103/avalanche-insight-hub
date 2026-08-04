import type { GraphNode, GraphEdge } from './graphLoader';

export type PerspectiveId =
  | 'all'
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
  filter: (node: GraphNode) => boolean;
  edgeFilter: (edge: GraphEdge) => boolean;
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

const DATA_FLOW_KEYWORDS = [
  'data', 'load', 'fetch', 'parse', 'ingest', 'export',
  'pipeline', 'stream', 'batch', 'archive', 'snapshot',
  'sar', 'sentinel', 'era5', 'dem', 'geojson',
];

function matchesKeywords(node: GraphNode, keywords: string[]): boolean {
  const haystack = [
    node.name,
    node.relativePath || '',
    node.summary || '',
    ...(node.tags || []),
  ].join(' ').toLowerCase();
  return keywords.some((kw) => haystack.includes(kw));
}

export const perspectives: Perspective[] = [
  {
    id: 'all',
    label: 'All',
    description: 'Show all nodes in the graph',
    filter: () => true,
    edgeFilter: () => true,
  },
  {
    id: 'architecture',
    label: 'Architecture',
    description: 'File structure and component organization',
    filter: (node) => node.type === 'file' || node.type === 'class',
    edgeFilter: (edge) => edge.type === 'contains',
  },
  {
    id: 'ml-pipeline',
    label: 'ML Pipeline',
    description: 'Machine learning, training, and forecasting components',
    filter: (node) => matchesKeywords(node, ML_KEYWORDS),
    edgeFilter: () => true,
  },
  {
    id: 'data-flow',
    label: 'Data Flow',
    description: 'Data loading, processing, and pipeline components',
    filter: (node) => matchesKeywords(node, DATA_FLOW_KEYWORDS),
    edgeFilter: () => true,
  },
  {
    id: 'security-gates',
    label: 'Security Gates',
    description: 'Verification, audit, and security components',
    filter: (node) => matchesKeywords(node, SECURITY_KEYWORDS),
    edgeFilter: () => true,
  },
  {
    id: 'tests',
    label: 'Tests',
    description: 'Test files and test utilities',
    filter: (node) => matchesKeywords(node, TEST_KEYWORDS),
    edgeFilter: () => true,
  },
  {
    id: 'release-evidence',
    label: 'Release Evidence',
    description: 'Release management and evidence collection',
    filter: (node) => matchesKeywords(node, RELEASE_KEYWORDS),
    edgeFilter: () => true,
  },
];

export function getPerspective(id: PerspectiveId): Perspective {
  return perspectives.find((p) => p.id === id) ?? perspectives[0];
}

export function filterGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  perspective: Perspective,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const filteredNodes = nodes.filter(perspective.filter);
  const nodeIds = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = edges.filter(
    (e) => perspective.edgeFilter(e) && nodeIds.has(e.source) && nodeIds.has(e.target),
  );
  return { nodes: filteredNodes, edges: filteredEdges };
}
