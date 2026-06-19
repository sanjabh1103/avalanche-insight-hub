import {
  PARTNER_INTAKE_CLAIM_LOCKS,
  REQUIRED_PARTNER_EVIDENCE_FILES,
} from '@/lib/partnerEvidenceReadiness';
import {
  buildDailyVerificationAnalytics,
  type DailyVerificationRecord,
} from '@/lib/scientistValidation';

export function buildScientistWeeklyReadinessReport(
  dailyVerificationRecords: DailyVerificationRecord[],
  generatedAt = new Date(),
) {
  const analytics = buildDailyVerificationAnalytics(dailyVerificationRecords);
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
): string {
  return JSON.stringify(buildScientistWeeklyReadinessReport(dailyVerificationRecords, generatedAt), null, 2);
}
