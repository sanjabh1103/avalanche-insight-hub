import { describe, expect, it, vi } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({
  supabase: { from: vi.fn() },
}));

import { buildScientistReviewOperationsAnalytics } from '@/lib/scientistReadinessReport';
import type { ScientistValidationCase, ScientistValidationReview } from '@/lib/scientistValidation';

function makeCase(overrides: Partial<ScientistValidationCase> = {}): ScientistValidationCase {
  return {
    id: 'case-1',
    case_type: 'verification_discrepancy',
    status: 'pending',
    priority: 3,
    region_key: 'himalaya-west',
    forecast_run_id: null,
    cell_row: 1,
    cell_col: 1,
    title: 'Test case',
    case_origin: 'forecast_publication',
    requires_two_reviewers: false,
    reviewed_at: null,
    created_at: '2026-07-10T00:00:00Z',
    ...overrides,
  } as ScientistValidationCase;
}

function makeReview(overrides: Partial<ScientistValidationReview> = {}): ScientistValidationReview {
  return {
    id: 'review-1',
    case_id: 'case-1',
    reviewer_id: 'reviewer-a',
    verdict: 'accepted',
    confidence: 0.8,
    notes: null,
    evidence_needed_next: 'none',
    created_at: '2026-07-11T00:00:00Z',
    ...overrides,
  } as ScientistValidationReview;
}

describe('buildScientistReviewOperationsAnalytics', () => {
  it('counts priority-5 cases and two-reviewer sign-off', () => {
    const cases = [
      makeCase({ id: 'c1', priority: 5, created_at: '2026-07-10T00:00:00Z' }),
      makeCase({ id: 'c2', priority: 5, created_at: '2026-07-10T00:00:00Z' }),
      makeCase({ id: 'c3', priority: 3, created_at: '2026-07-10T00:00:00Z' }),
    ];
    const reviews = [
      makeReview({ case_id: 'c1', reviewer_id: 'a', created_at: '2026-07-11T00:00:00Z' }),
      makeReview({ case_id: 'c1', reviewer_id: 'b', created_at: '2026-07-12T00:00:00Z' }),
      makeReview({ case_id: 'c2', reviewer_id: 'a', created_at: '2026-07-11T00:00:00Z' }),
    ];
    const result = buildScientistReviewOperationsAnalytics(cases, reviews, new Date('2026-07-16T00:00:00Z'));
    expect(result.priority_5_cases).toBe(2);
    expect(result.priority_5_two_reviewer_signoff).toBe(1);
  });

  it('computes priority-5 first-response and decision age averages', () => {
    const cases = [
      makeCase({ id: 'c1', priority: 5, created_at: '2026-07-10T00:00:00Z', reviewed_at: '2026-07-14T00:00:00Z' }),
    ];
    const reviews = [
      makeReview({ case_id: 'c1', reviewer_id: 'a', created_at: '2026-07-11T00:00:00Z' }),
    ];
    const result = buildScientistReviewOperationsAnalytics(cases, reviews, new Date('2026-07-16T00:00:00Z'));
    expect(result.priority_5_first_response_hours_avg).toBe(24);
    expect(result.priority_5_decision_hours_avg).toBe(96);
  });

  it('counts disagreements from diverging verdicts', () => {
    const cases = [
      makeCase({ id: 'c1', priority: 3 }),
      makeCase({ id: 'c2', priority: 3, disagreement_count: 1 } as ScientistValidationCase),
    ];
    const reviews = [
      makeReview({ case_id: 'c1', verdict: 'accepted', reviewer_id: 'a' }),
      makeReview({ case_id: 'c1', verdict: 'rejected', reviewer_id: 'b' }),
      makeReview({ case_id: 'c2', verdict: 'accepted', reviewer_id: 'a' }),
    ];
    const result = buildScientistReviewOperationsAnalytics(cases, reviews, new Date('2026-07-16T00:00:00Z'));
    expect(result.disagreement_count).toBe(2);
  });

  it('counts evidence-needed reviews', () => {
    const cases = [makeCase({ id: 'c1', priority: 3 })];
    const reviews = [
      makeReview({ case_id: 'c1', evidence_needed_next: 'field_observation' }),
      makeReview({ case_id: 'c1', evidence_needed_next: 'none' }),
      makeReview({ case_id: 'c1', evidence_needed_next: 'not_assessed' }),
    ];
    const result = buildScientistReviewOperationsAnalytics(cases, reviews, new Date('2026-07-16T00:00:00Z'));
    expect(result.evidence_needed_count).toBe(1);
  });

  it('counts grounded Himalayan cases', () => {
    const cases = [
      makeCase({ id: 'c1', region_key: 'himalaya-west' }),
      makeCase({ id: 'c2', region_key: 'colorado-rockies' }),
      makeCase({ id: 'c3', region_key: 'HIMALAYA-east' }),
    ];
    const result = buildScientistReviewOperationsAnalytics(cases, [], new Date('2026-07-16T00:00:00Z'));
    expect(result.grounded_himalayan_cases).toBe(2);
  });

  it('sets claim boundary to non-promotion', () => {
    const result = buildScientistReviewOperationsAnalytics([], [], new Date('2026-07-16T00:00:00Z'));
    expect(result.claim_boundary).toContain('never auto-promote');
  });
});
