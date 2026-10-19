import {
  PARTNER_INTAKE_CLAIM_LOCKS,
  REQUIRED_PARTNER_EVIDENCE_FILES,
} from '@/lib/partnerEvidenceReadiness';
import {
  buildDailyVerificationAnalytics,
  calculateReviewAgreement,
  type DailyVerificationRecord,
  type ScientistValidationCase,
  type ScientistValidationReview,
} from '@/lib/scientistValidation';

function hoursBetween(start: string | null | undefined, end: string | null | undefined): number | null {
  if (!start || !end) return null;
  const startMs = Date.parse(start);
  const endMs = Date.parse(end);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return null;
  return Math.max(0, (endMs - startMs) / 3_600_000);
}

export function buildScientistReviewOperationsAnalytics(
  cases: ScientistValidationCase[],
  reviews: ScientistValidationReview[],
  generatedAt = new Date(),
) {
  const weekStart = generatedAt.getTime() - 7 * 24 * 3_600_000;
  const reviewsByCase = new Map<string, ScientistValidationReview[]>();
  reviews.forEach((review) => {
    const existing = reviewsByCase.get(review.case_id) ?? [];
    existing.push(review);
    reviewsByCase.set(review.case_id, existing);
  });
  const priorityFive = cases.filter((caseRow) => caseRow.priority >= 5);
  const pending = cases.filter((caseRow) => caseRow.status === 'pending' || caseRow.status === 'in_review');
  const responseAges = priorityFive
    .map((caseRow) => {
      const firstReview = [...(reviewsByCase.get(caseRow.id) ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
      return hoursBetween(caseRow.created_at, firstReview?.created_at);
    })
    .filter((value): value is number => value != null);
  const decisionAges = priorityFive
    .map((caseRow) => hoursBetween(caseRow.created_at, caseRow.reviewed_at))
    .filter((value): value is number => value != null);
  const reviewerSignoffCount = priorityFive.filter((caseRow) => (
    new Set((reviewsByCase.get(caseRow.id) ?? []).map((review) => review.reviewer_id).filter(Boolean)).size >= 2
  )).length;
  const groundedHimalayanCases = cases.filter((caseRow) => String(caseRow.region_key ?? '').toLowerCase().includes('himalaya')).length;
  const evidenceNeededCount = reviews.filter((review) => (
    review.evidence_needed_next != null
      && review.evidence_needed_next !== 'none'
      && review.evidence_needed_next !== 'not_assessed'
  )).length;
  const disagreements = cases.filter((caseRow) => (
    (caseRow.disagreement_count ?? 0) > 0
      || new Set((reviewsByCase.get(caseRow.id) ?? []).map((review) => review.verdict)).size > 1
  )).length;
  const reviewedThisWeek = cases.filter((caseRow) => {
    const timestamp = Date.parse(caseRow.reviewed_at ?? '');
    return Number.isFinite(timestamp) && timestamp >= weekStart;
  }).length;
  const agreement = calculateReviewAgreement(reviews);

  return {
    total_cases: cases.length,
    reviewed_this_week: reviewedThisWeek,
    pending_or_in_review: pending.length,
    priority_5_cases: priorityFive.length,
    priority_5_two_reviewer_signoff: reviewerSignoffCount,
    priority_5_first_response_hours_avg: responseAges.length
      ? responseAges.reduce((sum, value) => sum + value, 0) / responseAges.length
      : null,
    priority_5_decision_hours_avg: decisionAges.length
      ? decisionAges.reduce((sum, value) => sum + value, 0) / decisionAges.length
      : null,
    disagreement_count: disagreements,
    evidence_needed_count: evidenceNeededCount,
    grounded_himalayan_cases: groundedHimalayanCases,
    reviewer_agreement: agreement,
    claim_boundary: 'Operational review analytics support scientist workload and label-quality inspection only; they never auto-promote training or public scoring.',
  };
}

export function buildScientistWeeklyReadinessReport(
  dailyVerificationRecords: DailyVerificationRecord[],
  generatedAt = new Date(),
  validationCases: ScientistValidationCase[] = [],
  validationReviews: ScientistValidationReview[] = [],
) {
  const analytics = buildDailyVerificationAnalytics(dailyVerificationRecords);
  const reviewOperations = buildScientistReviewOperationsAnalytics(validationCases, validationReviews, generatedAt);
  const evidenceGroups = REQUIRED_PARTNER_EVIDENCE_FILES.map((requirement) => ({
    key: requirement.key,
    filename: requirement.filename,
    label: requirement.label,
    owner: requirement.owner,
    week: requirement.week,
    ui_today: requirement.uiToday,
    status: requirement.uiToday === 'partial' ? 'ui_partial_partner_pending' : 'template_ready_partner_pending',
    required_columns: requirement.requiredColumns,
    next_action: requirement.nextAction,
    claim_boundary: requirement.claimBoundary,
  }));

  return {
    schema_version: 'scientist-weekly-readiness-report/v1',
    generated_at: generatedAt.toISOString(),
    usage_boundary: 'research_validation_only',
    ...PARTNER_INTAKE_CLAIM_LOCKS,
    current_scope: {
      colorado_rockies: 'live_technical_proof_surface',
      himalayas: 'partner_evidence_intake_and_scientist_review_pending',
      sar: 'shadow_only',
    },
    partner_intake: {
      status: 'browser_preflight_available_not_persistent',
      required_file_count: REQUIRED_PARTNER_EVIDENCE_FILES.length + 1,
      authoritative_next_step: 'Run backend CLI triage after real partner files arrive.',
    },
    readiness_blockers: [
      'No real reviewed Himalayan D_tidy-grade evidence rows are present in this browser report.',
      'Station latitude/longitude/elevation coverage must pass before GPxyz or uncertainty maps can be claimed.',
      'Independent Himalayan holdout metrics and named release attestation are still required before accuracy claims.',
      'Browser preflight exports are not a substitute for CLI triage, scientist adjudication, or release-gate evidence.',
    ],
    evidence_groups: evidenceGroups,
    daily_verification: analytics,
    review_operations: reviewOperations,
    next_actions: [
      'Send partner package templates and field dictionary before the client call.',
      'Use the partner-intake route for filename/header/hash preflight during the call.',
      'Export daily verification analytics for scientist review, not as local holdout proof.',
      'After real partner data arrives, run CLI triage and attach the authoritative quality score.',
    ],
    claim_boundary: {
      production_scoring_allowed: false,
      himalayan_accuracy_claim_allowed: false,
      reason: 'This weekly report aggregates UI readiness and paired-review analytics only; it does not validate Himalayan accuracy or authorize production scoring.',
    },
  };
}

export function buildScientistWeeklyReadinessReportJson(
  dailyVerificationRecords: DailyVerificationRecord[],
  generatedAt = new Date(),
  validationCases: ScientistValidationCase[] = [],
  validationReviews: ScientistValidationReview[] = [],
): string {
  return JSON.stringify(buildScientistWeeklyReadinessReport(
    dailyVerificationRecords,
    generatedAt,
    validationCases,
    validationReviews,
  ), null, 2);
}
