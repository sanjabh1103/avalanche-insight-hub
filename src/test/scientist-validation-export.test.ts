import { describe, expect, it, vi } from 'vitest';

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getUser: vi.fn(),
    },
    from: vi.fn(() => {
      throw new Error('Supabase table access is not expected in export-only tests.');
    }),
  },
}));

import {
  buildDailyVerificationExport,
  buildValidationSummaryMarkdown,
  buildValidationSummaryPacket,
  calculateReviewAgreement,
  type ScientistValidationAction,
  type ScientistValidationCase,
  type ScientistValidationReview,
} from '@/lib/scientistValidation';
import { buildScientistWeeklyReadinessReport } from '@/lib/scientistReadinessReport';

describe('scientist validation export', () => {
  it('includes synthetic demo boundary, reviewer counts, actions, references, and claim boundary', () => {
    const caseRow: ScientistValidationCase = {
      id: 'case-1',
      case_type: 'weak_layer',
      status: 'in_review',
      priority: 5,
      region_key: 'demo_himalayas_synthetic',
      region_name: 'Synthetic Himalayan Demo',
      forecast_run_id: null,
      forecast_grid_id: null,
      forecast_hour: 12,
      cell_row: 8,
      cell_col: 9,
      title: 'Synthetic demo weak-layer review',
      summary: 'Synthetic demo only',
      evidence: { synthetic_demo: true, training_eligible: false, production_eligible: false },
      cell_snapshot: {},
      model_metadata: {},
      gate_key: 'synthetic_demo_flow_validation',
      claim_boundary: 'synthetic_demo_not_scientific_evidence',
      requires_two_reviewers: true,
      disagreement_count: 0,
      signoff_scope: 'synthetic_demo_flow_only',
      assigned_to: null,
      created_by: 'scientist-user',
      created_at: '2026-05-21T00:00:00Z',
      updated_at: '2026-05-21T00:00:00Z',
      reviewed_at: null,
    };
    const review: ScientistValidationReview = {
      id: 'review-1',
      case_id: 'case-1',
      reviewer_id: 'scientist-user',
      verdict: 'needs_info',
      confidence: 0.75,
      notes: 'Needs field confirmation',
      failure_mode: null,
      weak_layer_class: null,
      runout_verdict: null,
      claim_impact: 'downgrade',
      official_avalanche_problem: 'persistent_weak_layers',
      label_quality_verdict: 'location_or_time_uncertain',
      model_error_verdict: 'model_miscalibrated',
      terrain_sar_ambiguity: 'terrain_context_required',
      evidence_needed_next: 'field_observation',
      confidence_rationale: 'Synthetic demo rationale',
      evidence_refs: {
        attached_publications: [{ id: 'him-strat-2020', title: 'HIM-STRAT' }],
      },
      created_at: '2026-05-21T00:05:00Z',
    };
    const action: ScientistValidationAction = {
      id: 'action-1',
      case_id: 'case-1',
      review_id: 'review-1',
      action_type: 'evidence_request',
      status: 'open',
      priority: 5,
      summary: 'Collect field observation',
      owner_role: 'scientist',
      evidence_refs: { claim_boundary: 'synthetic_demo_not_scientific_evidence' },
      created_by: 'scientist-user',
      created_at: '2026-05-21T00:06:00Z',
      resolved_at: null,
      resolution_notes: null,
    };

    const packet = JSON.parse(buildValidationSummaryPacket([caseRow], [review], [], [action]));

    expect(packet.summary.synthetic_demo_case_count).toBe(1);
    expect(packet.summary.action_count).toBe(1);
    expect(packet.summary.reviewer_agreement.paired_case_count).toBe(0);
    expect(packet.summary.reviewer_agreement.cohen_kappa).toBeNull();
    expect(packet.summary.reviewer_agreement.cohen_kappa_reason).toBe('insufficient_pairs');
    expect(packet.summary.synthetic_demo_boundary).toContain('excluded from training');
    expect(packet.cases[0].claim_boundary).toBe('synthetic_demo_not_scientific_evidence');
    expect(packet.cases[0].requires_two_reviewers).toBe(true);
    expect(packet.cases[0].reviews[0].evidence_refs.attached_publications[0].id).toBe('him-strat-2020');
    expect(packet.cases[0].actions[0].action_type).toBe('evidence_request');

    const markdown = buildValidationSummaryMarkdown([caseRow], [review], [], [action]);
    expect(markdown).toContain('#### Reviews');
    expect(markdown).toContain('Review review-1');
    expect(markdown).toContain('Attached references: him-strat-2020 - HIM-STRAT');
    expect(markdown).toContain('#### Governed Actions');
    expect(markdown).toContain('Action action-1');
    expect(markdown).toContain('Collect field observation');
  });

  it('computes Cohen kappa for paired distinct reviewers', () => {
    const reviews = [
      makeReview('case-1', 'reviewer-a', 'accepted'),
      makeReview('case-1', 'reviewer-b', 'accepted'),
      makeReview('case-2', 'reviewer-a', 'rejected'),
      makeReview('case-2', 'reviewer-b', 'accepted'),
      makeReview('case-3', 'reviewer-a', 'rejected'),
      makeReview('case-3', 'reviewer-b', 'rejected'),
      makeReview('case-4', 'reviewer-a', 'accepted'),
      makeReview('case-4', 'reviewer-b', 'rejected'),
    ];

    const agreement = calculateReviewAgreement(reviews);

    expect(agreement.paired_case_count).toBe(4);
    expect(agreement.exact_verdict_agreement_count).toBe(2);
    expect(agreement.exact_verdict_agreement_rate).toBe(0.5);
    expect(agreement.cohen_kappa).toBe(0);
    expect(agreement.cohen_kappa_reason).toBeNull();
  });

  it('returns explicit kappa reasons for insufficient and degenerate reviewer pairs', () => {
    expect(calculateReviewAgreement([makeReview('case-1', 'reviewer-a', 'accepted')]).cohen_kappa_reason).toBe('insufficient_pairs');

    const degenerate = calculateReviewAgreement([
      makeReview('case-1', 'reviewer-a', 'accepted'),
      makeReview('case-1', 'reviewer-b', 'accepted'),
      makeReview('case-2', 'reviewer-a', 'accepted'),
      makeReview('case-2', 'reviewer-b', 'accepted'),
    ]);

    expect(degenerate.cohen_kappa).toBeNull();
    expect(degenerate.cohen_kappa_reason).toBe('degenerate_labels');
  });

  it('includes daily analytics in paired verification export', () => {
    const packet = JSON.parse(buildDailyVerificationExport([
      {
        id: 'daily-1',
        reviewer_id: 'reviewer-a',
        region_key: 'himalayas_nepal',
        region_name: 'Himalayas Nepal',
        verification_date: '2026-05-21',
        forecast_run_id: null,
        forecast_grid_id: null,
        forecast_hour: 12,
        scientist_danger_level: '3',
        model_danger_level: '3',
        official_avalanche_problem: 'wind_slab',
        model_avalanche_problem: 'wind_slab',
        observed_outcome: 'event_observed',
        notes: null,
        evidence_refs: {},
        created_at: '2026-05-21T00:00:00Z',
      },
      {
        id: 'daily-2',
        reviewer_id: 'reviewer-a',
        region_key: 'himalayas_nepal',
        region_name: 'Himalayas Nepal',
        verification_date: '2026-05-20',
        forecast_run_id: null,
        forecast_grid_id: null,
        forecast_hour: 12,
        scientist_danger_level: '4',
        model_danger_level: '2',
        official_avalanche_problem: 'wet_snow',
        model_avalanche_problem: 'wind_slab',
        observed_outcome: 'unknown',
        notes: null,
        evidence_refs: {},
        created_at: '2026-05-20T00:00:00Z',
      },
    ]));

    expect(packet.summary.record_count).toBe(2);
    expect(packet.summary.exact_danger_match_rate).toBe(0.5);
    expect(packet.analytics.danger_level_confusion_matrix['3']['3']).toBe(1);
    expect(packet.analytics.avalanche_problem_confusion_matrix.wet_snow.wind_slab).toBe(1);
    expect(packet.analytics.unknown_outcome_count).toBe(1);
    expect(packet.summary.claim_boundary).toContain('does not promote public scoring');
  });

  it('builds a weekly readiness report with evidence groups, daily analytics, and claim locks', () => {
    const report = buildScientistWeeklyReadinessReport([
      {
        id: 'daily-1',
        reviewer_id: 'reviewer-a',
        region_key: 'himalayas_nepal',
        region_name: 'Himalayas Nepal',
        verification_date: '2026-05-21',
        forecast_run_id: null,
        forecast_grid_id: null,
        forecast_hour: 12,
        scientist_danger_level: '3',
        model_danger_level: '2',
        official_avalanche_problem: 'wind_slab',
        model_avalanche_problem: 'persistent_weak_layers',
        observed_outcome: 'event_observed',
        notes: null,
        evidence_refs: {},
        created_at: '2026-05-21T00:00:00Z',
      },
    ], new Date('2026-05-29T00:00:00Z'));

    expect(report.schema_version).toBe('scientist-weekly-readiness-report/v1');
    expect(report.production_scoring_allowed).toBe(false);
    expect(report.himalayan_accuracy_claim_allowed).toBe(false);
    expect(report.current_scope.colorado_rockies).toBe('live_technical_proof_surface');
    expect(report.partner_intake.status).toBe('browser_preflight_available_not_persistent');
    expect(report.evidence_groups.some((group) => group.key === 'danger_labels_and_bulletins')).toBe(true);
    expect(report.evidence_groups.find((group) => group.key === 'danger_labels_and_bulletins')?.required_columns).toEqual(expect.arrayContaining([
      'label_source',
      'tidy_label_review_basis',
      'avalanche_regime',
    ]));
    expect(report.daily_verification.danger_disagreement_count).toBe(1);
    expect(report.claim_boundary.reason).toContain('does not validate Himalayan accuracy');
  });
});

function makeReview(caseId: string, reviewerId: string, verdict: ScientistValidationReview['verdict']): ScientistValidationReview {
  return {
    id: `${caseId}-${reviewerId}`,
    case_id: caseId,
    reviewer_id: reviewerId,
    verdict,
    confidence: 0.75,
    notes: null,
    failure_mode: null,
    weak_layer_class: null,
    runout_verdict: null,
    claim_impact: 'no_change',
    official_avalanche_problem: 'not_assessed',
    label_quality_verdict: 'not_assessed',
    model_error_verdict: 'not_assessed',
    terrain_sar_ambiguity: 'not_assessed',
    evidence_needed_next: 'not_assessed',
    confidence_rationale: null,
    evidence_refs: {},
    created_at: '2026-05-21T00:00:00Z',
  };
}
