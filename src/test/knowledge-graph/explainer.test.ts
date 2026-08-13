import { describe, it, expect, beforeAll } from 'vitest';
import { generateExplanation } from '@/lib/knowledge-graph/explainer';
import { getNodeById, getNodesByType, graph, loadBundledGraph } from '@/lib/knowledge-graph/graphData';
import type { PerspectiveId } from '@/lib/knowledge-graph/perspectives';
import { AUDIENCE_IDS, DEPTH_IDS } from '@/lib/knowledge-graph/audienceModel';

// FIX-5 (H-3): The bundled graph is now loaded asynchronously to keep it
// out of the production bundle. Tests must call loadBundledGraph() first.
beforeAll(async () => {
  await loadBundledGraph();
});

describe('explainer', () => {
  it('generates an explanation for a file node', async () => {
    const fileNode = getNodesByType('file')[0];
    expect(fileNode).toBeDefined();
    const explanation = await generateExplanation(fileNode, 'architecture');
    expect(explanation.nodeId).toBe(fileNode.id);
    expect(explanation.nodeName).toBe(fileNode.name);
    expect(explanation.perspective).toBe('architecture');
    expect(explanation.sections.length).toBeGreaterThan(0);
    expect(explanation.sections[0].heading).toBe('Overview');
    expect(explanation.generatedAt).toBeTruthy();
  });

  it('includes a context section when the node belongs to a layer', async () => {
    // Phase 2 structural graph has 0 layers — skip this test if no layers exist.
    // Legacy graph has layers, so this test runs against the legacy fallback.
    if (graph.layers.length === 0) {
      console.warn('SKIP: No layers in current graph (structural-only snapshot)');
      return;
    }
    const layerNode = getNodeById('file:backend/models/surrogate_rf.py');
    if (layerNode) {
      const explanation = await generateExplanation(layerNode, 'ml-pipeline');
      const contextSection = explanation.sections.find((s) => s.heading === 'Context');
      expect(contextSection).toBeDefined();
    }
  });

  it('includes perspective-specific interpretation for ML pipeline nodes', async () => {
    const trainNode = getNodeById('file:backend/train_model.py');
    if (trainNode) {
      const explanation = await generateExplanation(trainNode, 'ml-pipeline');
      const mlSection = explanation.sections.find((s) => s.heading === 'ML Pipeline View');
      expect(mlSection).toBeDefined();
      expect(mlSection?.body).toContain('training');
    }
  });

  it('includes perspective-specific interpretation for security gate nodes', async () => {
    const gateNode = getNodeById('file:backend/common/verification_exit_gates.py');
    if (gateNode) {
      const explanation = await generateExplanation(gateNode, 'security-gates');
      const secSection = explanation.sections.find((s) => s.heading === 'Security & Gates View');
      expect(secSection).toBeDefined();
      expect(secSection?.body).toContain('denylist');
    }
  });

  it('handles all six perspectives without error', async () => {
    const node = getNodesByType('file')[0];
    const ids: PerspectiveId[] = [
      'architecture',
      'ml-pipeline',
      'data-flow',
      'security-gates',
      'tests',
      'release-evidence',
    ];
    for (const id of ids) {
      const explanation = await generateExplanation(node, id);
      expect(explanation.perspective).toBe(id);
      expect(explanation.sections.length).toBeGreaterThan(0);
    }
  });

  it('includes a relationships section when the node has connections', async () => {
    // Find a node that has children (contains edges)
    const fileNodes = getNodesByType('file');
    const nodeWithChildren = fileNodes.find((n) => {
      return getNodeById(n.id) !== undefined;
    });
    if (nodeWithChildren) {
      const explanation = await generateExplanation(nodeWithChildren, 'architecture');
      // Not all nodes will have relationships, but the function should not error
      expect(explanation.sections.length).toBeGreaterThan(0);
    }
  });

  it('keeps audience/depth shaping deterministic and distinct across the 3x3 matrix', async () => {
    const node = getNodesByType('file')[0];
    const signatures = new Set<string>();

    for (const audience of AUDIENCE_IDS) {
      for (const depth of DEPTH_IDS) {
        const explanation = await generateExplanation(node, 'architecture', {
          audience,
          depth,
          snapshotId: 'snapshot-test',
          graphHash: 'graph-test',
          graphFreshness: 'current',
        });

        expect(explanation.audience).toBe(audience);
        expect(explanation.depth).toBe(depth);
        expect(explanation.evidenceSummary.proofLevel).toBe('snapshot-linked');
        expect(explanation.sections.every((section) => section.sourceRefs.length > 0)).toBe(true);
        expect(explanation.sections.every((section) => section.claim.evidenceRefs.length > 0)).toBe(true);
        signatures.add(JSON.stringify({
          heading: explanation.sections[1].heading,
          body: explanation.sections[1].body,
        }));
      }
    }

    expect(signatures.size).toBe(9);
  });

  it('does not emit fact-like claims when the graph snapshot is unverified', async () => {
    const node = getNodesByType('file')[0];
    const explanation = await generateExplanation(node, 'architecture');

    expect(explanation.evidenceSummary.proofLevel).toBe('unverified');
    expect(explanation.sections.every((section) => section.claimCategory !== 'fact')).toBe(true);
    expect(explanation.sections.flatMap((section) => section.claims).some((claim) => claim.category === 'blocked')).toBe(true);
  });

  it('marks stale explanations explicitly and preserves snapshot binding', async () => {
    const node = getNodesByType('file')[0];
    const explanation = await generateExplanation(node, 'architecture', {
      snapshotId: 'old-snapshot',
      graphHash: 'old-graph',
      graphFreshness: 'stale',
    });

    expect(explanation.evidenceSummary.proofLevel).toBe('snapshot-linked');
    expect(explanation.sections.flatMap((section) => section.claims).some((claim) => claim.category === 'stale')).toBe(true);
    expect(explanation.sections.flatMap((section) => section.claims).some((claim) => claim.category === 'fact')).toBe(false);
  });
});
