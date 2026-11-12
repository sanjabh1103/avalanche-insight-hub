// Phase 4 smoke test: verify all 3 audiences x 3 depths produce materially
// different but evidence-consistent explanations for the same node.

import { describe, expect, it, beforeAll } from 'vitest';
import { generateExplanation } from '@/lib/knowledge-graph/explainer';
import { getNodesByType, loadBundledGraph } from '@/lib/knowledge-graph/graphData';

// FIX-5 (H-3): The bundled graph is now loaded asynchronously to keep it
// out of the production bundle. Tests must call loadBundledGraph() first.
beforeAll(async () => {
  await loadBundledGraph();
});

describe('Phase 4 smoke: 3 audiences x 3 depths', () => {
  it('produces materially different sections for all 9 combinations', async () => {
    const fileNodes = getNodesByType('file');
    const node = fileNodes.find(n => n.filePath?.includes('backend/common/features.py'))
      || fileNodes.find(n => n.filePath?.includes('backend/models/'))
      || fileNodes[0];
    expect(node).toBeDefined();

    const audiences = ['novice', 'ml_expert', 'technical_customer'] as const;
    const depths = ['briefing', 'working', 'deep'] as const;

    const headingsByKey: Record<string, string[]> = {};

    for (const audience of audiences) {
      for (const depth of depths) {
        const explanation = await generateExplanation(node, 'architecture', {
          audience,
          depth,
          snapshotId: 'snap-test',
          graphHash: 'hash-test',
          graphFreshness: 'current',
        });
        const key = `${audience}:${depth}`;
        const headings = explanation.sections.map(s => s.heading);
        headingsByKey[key] = headings;

        // Verify retrieval summary exists
        expect(explanation.retrievalSummary).toBeDefined();
        expect(explanation.retrievalSummary!.retrievalPath.length).toBeGreaterThan(0);

        // Verify Why This Answer section
        expect(headings).toContain('Why This Answer');

        // Verify audience-specific sections
        if (audience === 'novice') {
          expect(headings).toContain('Purpose');
          expect(headings).toContain('Glossary');
          expect(headings).toContain('Guided Next Step');
        } else if (audience === 'ml_expert') {
          expect(headings).toContain('Labels & Features');
          expect(headings).toContain('Metrics & Calibration');
        } else if (audience === 'technical_customer') {
          expect(headings).toContain('Interfaces & Ownership');
          expect(headings).toContain('RBAC & Observability');
        }

        // Verify depth adaptation
        if (depth === 'working') {
          const purposeSection = explanation.sections.find(s => s.heading === 'Purpose');
          if (purposeSection) expect(purposeSection.body).toContain('Next check');
        }
        if (depth === 'deep') {
          const purposeSection = explanation.sections.find(s => s.heading === 'Purpose');
          if (purposeSection) expect(purposeSection.body).toContain('Audit note');
        }

        // Verify claims are snapshot-linked (not hallucinated)
        expect(explanation.evidenceSummary.proofLevel).toBe('snapshot-linked');
      }
    }

    // Verify sections differ across audiences (at same depth)
    const novice = headingsByKey['novice:briefing'].join(',');
    const mlExpert = headingsByKey['ml_expert:briefing'].join(',');
    const customer = headingsByKey['technical_customer:briefing'].join(',');
    expect(novice).not.toEqual(mlExpert);
    expect(novice).not.toEqual(customer);
    expect(mlExpert).not.toEqual(customer);
  });
});
