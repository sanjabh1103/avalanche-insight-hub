import { describe, expect, it } from 'vitest';

import {
  AUDIENCE_IDS,
  CLAIM_CATEGORIES,
  DEPTH_IDS,
  buildAudienceLens,
  createStructuredClaim,
  getAudienceProfile,
  getDepthProfile,
  normalizeAudience,
  normalizeDepth,
  renderStructuredClaim,
  type AudienceId,
  type DepthId,
} from '@/lib/knowledge-graph/audienceModel';

const evidenceRefs = ['file:src/lib/knowledge-graph/explainer.ts'];

describe('audience model contract', () => {
  it('defines the approved 3x3 audience and depth matrix', () => {
    expect(AUDIENCE_IDS).toEqual(['novice', 'ml_expert', 'technical_customer']);
    expect(DEPTH_IDS).toEqual(['briefing', 'working', 'deep']);
    expect(CLAIM_CATEGORIES).toEqual([
      'fact',
      'inference',
      'plan',
      'unsupported',
      'stale',
      'blocked',
    ]);
  });

  it('produces materially distinct, evidence-bound lenses for every matrix cell', () => {
    const signatures = new Set<string>();

    for (const audience of AUDIENCE_IDS) {
      for (const depth of DEPTH_IDS) {
        const lens = buildAudienceLens({
          audience,
          depth,
          perspective: 'architecture',
          nodeName: 'KnowledgeGraphPage',
          evidenceRefs,
          snapshotId: 'snapshot-20260802',
          graphHash: 'graph-sha256',
          graphFreshness: 'current',
        });

        expect(lens.audience).toBe(audience);
        expect(lens.depth).toBe(depth);
        expect(lens.proofLevel).toBe('snapshot-linked');
        expect(lens.requiredSections.length).toBeGreaterThan(0);
        expect(lens.claims.length).toBeGreaterThan(0);
        for (const claim of lens.claims) {
          expect(CLAIM_CATEGORIES).toContain(claim.category);
          expect(claim.evidenceRefs.length).toBeGreaterThan(0);
          expect(claim.snapshotId).toBe('snapshot-20260802');
          expect(claim.graphHash).toBe('graph-sha256');
        }
        signatures.add(JSON.stringify(lens));
      }
    }

    expect(signatures.size).toBe(9);
  });

  it('marks missing provenance as unverified rather than silently current', () => {
    const lens = buildAudienceLens({
      audience: 'ml_expert',
      depth: 'deep',
      perspective: 'ml-pipeline',
      nodeName: 'train_model.py',
      evidenceRefs,
    });

    expect(lens.proofLevel).toBe('unverified');
    expect(lens.claims.every((claim) => claim.proofLevel === 'unverified')).toBe(true);
    expect(lens.claims.some((claim) => claim.category === 'blocked')).toBe(true);
  });

  it('marks stale graph context explicitly and never renders it as a fact', () => {
    const lens = buildAudienceLens({
      audience: 'novice',
      depth: 'briefing',
      perspective: 'architecture',
      nodeName: 'KnowledgeGraphPage',
      evidenceRefs,
      graphFreshness: 'stale',
    });

    const staleClaims = lens.claims.filter((claim) => claim.category === 'stale');
    expect(staleClaims.length).toBeGreaterThan(0);
    expect(staleClaims.every((claim) => renderStructuredClaim(claim).includes('Stale'))).toBe(true);
  });

  it('requires non-empty claim text and evidence references', () => {
    expect(() => createStructuredClaim('', 'fact', evidenceRefs)).toThrow(/claim text/i);
    expect(() => createStructuredClaim('A claim', 'fact', [])).toThrow(/evidence reference/i);
  });

  it('renders category and evidence so unsupported claims cannot look factual', () => {
    const claim = createStructuredClaim(
      'This statement is not established by the selected snapshot.',
      'unsupported',
      evidenceRefs,
    );

    const rendered = renderStructuredClaim(claim);
    expect(rendered).toContain('Unsupported');
    expect(rendered).toContain(evidenceRefs[0]);
    expect(rendered).not.toMatch(/^This statement/);
  });

  it('normalizes invalid selection values to safe defaults', () => {
    expect(normalizeAudience('ml_expert')).toBe<AudienceId>('ml_expert');
    expect(normalizeAudience('unknown')).toBe<AudienceId>('novice');
    expect(normalizeDepth('deep')).toBe<DepthId>('deep');
    expect(normalizeDepth('unknown')).toBe<DepthId>('briefing');
    expect(getAudienceProfile('technical_customer').label).toBe('Technical customer');
    expect(getDepthProfile('working').label).toBe('Working');
  });
});
