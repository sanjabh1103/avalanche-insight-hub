import { supabase } from '@/integrations/supabase/client';
import type { GridCell } from '@/lib/gridUtils';

export type ScientistValidationCaseType =
  | 'weak_layer'
  | 'runout'
  | 'false_positive'
  | 'false_negative'
  | 'masked_terrain'
  | 'sar_candidate'
  | 'model_gate';

export type ScientistValidationStatus =
  | 'pending'
  | 'in_review'
  | 'reviewed'
  | 'blocked'
  | 'accepted_limitation';

export type ScientistValidationVerdict =
  | 'accepted'
  | 'rejected'
  | 'needs_info'
  | 'accepted_limitation'
  | 'blocked';

export type OfficialAvalancheProblem =
  | 'new_snow'
  | 'wind_slab'
  | 'persistent_weak_layers'
  | 'wet_snow'
  | 'gliding_snow'
  | 'cornices'
  | 'no_distinct_problem'
  | 'not_assessed';

export type LabelQualityVerdict =
  | 'label_reliable'
  | 'label_underreported'
  | 'label_overreported'
  | 'location_or_time_uncertain'
  | 'source_conflict'
  | 'not_assessed';

export type ModelErrorVerdict =
  | 'model_plausible'
  | 'model_false_positive'
  | 'model_false_negative'
  | 'model_miscalibrated'
  | 'insufficient_evidence'
  | 'not_assessed';

export type TerrainSarAmbiguity =
  | 'none'
  | 'terrain_context_required'
  | 'sar_layover_or_shadow'
  | 'registration_or_projection_issue'
  | 'runout_path_uncertain'
  | 'not_assessed';

export type EvidenceNeededNext =
  | 'none'
  | 'field_observation'
  | 'snowpit_or_weak_layer_profile'
  | 'sar_or_optical_review'
  | 'historical_event_lookup'
  | 'benchmark_slice'
  | 'partner_data_request'
  | 'not_assessed';

export type ClaimImpact = 'no_change' | 'downgrade' | 'block' | 'promote_candidate';

export type DailyVerificationDangerLevel = '1' | '2' | '3' | '4' | '5' | 'not_assessed';

export interface PublicationReference {
  id: string;
  title: string;
  year: number;
  topic: string;
  local_path: string;
  evidence_note: string;
}

export const PUBLICATION_REFERENCES: PublicationReference[] = [
  {
    id: 'iacmag-2008',
    title: '12th IACMAG avalanche and mountain risk paper',
    year: 2008,
    topic: 'Early geotechnical and mountain-risk lineage',
    local_path: 'docs/publications/2008 _ 12th IACMAG__F08.pdf',
    evidence_note: 'Use only as background lineage unless a specific claim is traced to the paper.',
  },
  {
    id: 'geospatial-world-2011',
    title: 'GeoSpatial World Forum avalanche paper',
    year: 2011,
    topic: 'Geospatial decision-support context',
    local_path: 'docs/publications/2011 _ GeoSpatial World Forum.pdf',
    evidence_note: 'Useful for GIS workflow continuity, not direct model validation.',
  },
  {
    id: 'elsevier-2015',
    title: '2015 cold-regions / terrain modelling publication',
    year: 2015,
    topic: 'Terrain and environmental modelling',
    local_path: 'docs/publications/2015 _ 1-s2.0-S0165232X14001694-main.pdf',
    evidence_note: 'Attach when terrain or environmental-model assumptions need source lineage.',
  },
  {
    id: 'elsevier-2017',
    title: '2017 high-performance / geospatial avalanche publication',
    year: 2017,
    topic: 'Computation and geospatial modelling',
    local_path: 'docs/publications/2017 _ 1-s2.0-S0743731517300096-main.pdf',
    evidence_note: 'Attach for platform lineage, not for completed Himalayan validation.',
  },
  {
    id: 'him-strat-2020',
    title: 'HIM-STRAT Himalayan snowpack stability publication',
    year: 2020,
    topic: 'HIM-STRAT and Himalayan snowpack memory',
    local_path: 'docs/publications/2020 _ 10.1007_s11069-020-04032-6 _ HIM-STRAT.pdf',
    evidence_note: 'Most relevant source for Himalayan snowpack-proxy and weak-layer validation discussion.',
  },
  {
    id: 'environmental-model-2025',
    title: '2025 environmental modelling publication',
    year: 2025,
    topic: 'Recent model and environmental evidence',
    local_path: 'docs/publications/2025 _ 10.1007_s10666-025-10061-x.pdf',
    evidence_note: 'Attach only where the reviewed claim maps directly to the publication.',
  },
  {
    id: 'crst-2025',
    title: '2025 Manish Kala CRST publication',
    year: 2025,
    topic: 'Recent Himalayan / climate-risk context',
    local_path: 'docs/publications/2025 _ manish kala _ crst.pdf',
    evidence_note: 'Use as supporting context until a direct validation linkage is recorded.',
  },
];

export const OFFICIAL_AVALANCHE_PROBLEM_OPTIONS: Array<{ value: OfficialAvalancheProblem; label: string }> = [
  { value: 'new_snow', label: 'EAWS new snow' },
  { value: 'wind_slab', label: 'EAWS wind slab' },
  { value: 'persistent_weak_layers', label: 'EAWS persistent weak layers' },
  { value: 'wet_snow', label: 'EAWS wet snow' },
  { value: 'gliding_snow', label: 'EAWS gliding snow' },
  { value: 'cornices', label: 'EAWS optional cornices' },
  { value: 'no_distinct_problem', label: 'EAWS optional no distinct problem' },
  { value: 'not_assessed', label: 'Not assessed' },
];

export const LABEL_QUALITY_OPTIONS: Array<{ value: LabelQualityVerdict; label: string }> = [
  { value: 'label_reliable', label: 'Label reliable' },
  { value: 'label_underreported', label: 'Label underreported' },
  { value: 'label_overreported', label: 'Label overreported' },
  { value: 'location_or_time_uncertain', label: 'Location or time uncertain' },
  { value: 'source_conflict', label: 'Source conflict' },
  { value: 'not_assessed', label: 'Not assessed' },
];

export const MODEL_ERROR_OPTIONS: Array<{ value: ModelErrorVerdict; label: string }> = [
  { value: 'model_plausible', label: 'Model plausible' },
  { value: 'model_false_positive', label: 'Model false positive' },
  { value: 'model_false_negative', label: 'Model false negative' },
  { value: 'model_miscalibrated', label: 'Model miscalibrated' },
  { value: 'insufficient_evidence', label: 'Insufficient evidence' },
  { value: 'not_assessed', label: 'Not assessed' },
];

export const TERRAIN_SAR_AMBIGUITY_OPTIONS: Array<{ value: TerrainSarAmbiguity; label: string }> = [
  { value: 'none', label: 'None' },
  { value: 'terrain_context_required', label: 'Terrain context required' },
  { value: 'sar_layover_or_shadow', label: 'SAR layover or shadow' },
  { value: 'registration_or_projection_issue', label: 'Registration or projection issue' },
  { value: 'runout_path_uncertain', label: 'Runout path uncertain' },
  { value: 'not_assessed', label: 'Not assessed' },
];

export const EVIDENCE_NEEDED_OPTIONS: Array<{ value: EvidenceNeededNext; label: string }> = [
  { value: 'none', label: 'No added evidence' },
  { value: 'field_observation', label: 'Field observation' },
  { value: 'snowpit_or_weak_layer_profile', label: 'Snowpit or weak-layer profile' },
  { value: 'sar_or_optical_review', label: 'SAR or optical review' },
  { value: 'historical_event_lookup', label: 'Historical event lookup' },
  { value: 'benchmark_slice', label: 'Benchmark slice' },
  { value: 'partner_data_request', label: 'Partner data request' },
  { value: 'not_assessed', label: 'Not assessed' },
];

export interface ScientistValidationCase {
  id: string;
  case_type: ScientistValidationCaseType;
  status: ScientistValidationStatus;
  priority: number;
  region_key: string | null;
  region_name: string | null;
  forecast_run_id: string | null;
  forecast_grid_id: string | null;
  forecast_hour: number | null;
  cell_row: number | null;
  cell_col: number | null;
  title: string;
  summary: string | null;
  evidence: Record<string, unknown>;
  cell_snapshot: Record<string, unknown>;
  model_metadata: Record<string, unknown>;
  gate_key: string | null;
  claim_boundary: string;
  requires_two_reviewers?: boolean;
  disagreement_count?: number;
  signoff_scope?: string;
  assigned_to: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  reviewed_at: string | null;
}

export interface ScientistValidationReview {
  id: string;
  case_id: string;
  reviewer_id: string | null;
  verdict: ScientistValidationVerdict;
  confidence: number;
  notes: string | null;
  failure_mode: string | null;
  weak_layer_class: string | null;
  runout_verdict: string | null;
  claim_impact: ClaimImpact;
  official_avalanche_problem: OfficialAvalancheProblem | null;
  label_quality_verdict: LabelQualityVerdict | null;
  model_error_verdict: ModelErrorVerdict | null;
  terrain_sar_ambiguity: TerrainSarAmbiguity | null;
  evidence_needed_next: EvidenceNeededNext | null;
  confidence_rationale: string | null;
  evidence_refs: Record<string, unknown>;
  created_at: string;
}

export interface ScientistValidationAction {
  id: string;
  case_id: string;
  review_id: string | null;
  action_type:
    | 'claim_downgrade'
    | 'claim_block'
    | 'data_remediation'
    | 'label_remediation'
    | 'benchmark_slice'
    | 'model_gap_candidate'
    | 'reviewer_disagreement'
    | 'evidence_request';
  status: 'open' | 'in_progress' | 'resolved' | 'rejected';
  priority: number;
  summary: string;
  owner_role: string;
  evidence_refs: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  resolved_at: string | null;
  resolution_notes?: string | null;
}

export interface CellEvidenceLinks {
  outcomes: Array<Record<string, unknown>>;
  field_reports: Array<Record<string, unknown>>;
}

export interface DailyVerificationInput {
  region_key?: string | null;
  region_name?: string | null;
  verification_date: string;
  forecast_run_id?: string | null;
  forecast_grid_id?: string | null;
  forecast_hour?: number | null;
  scientist_danger_level: DailyVerificationDangerLevel;
  model_danger_level: DailyVerificationDangerLevel;
  observed_outcome?: 'event_observed' | 'no_event_observed' | 'unknown';
  official_avalanche_problem?: OfficialAvalancheProblem | null;
  model_avalanche_problem?: OfficialAvalancheProblem | null;
  confidence?: number;
  notes?: string | null;
  evidence_refs?: Record<string, unknown>;
}

export interface DailyVerificationRecord extends DailyVerificationInput {
  id: string;
  reviewer_id: string | null;
  created_at: string;
}

export interface DailyVerificationAnalytics {
  record_count: number;
  assessable_danger_pair_count: number;
  exact_danger_matches: number;
  exact_danger_match_rate: number | null;
  danger_level_confusion_matrix: Record<string, Record<string, number>>;
  avalanche_problem_confusion_matrix: Record<string, Record<string, number>>;
  observed_outcome_distribution: Record<string, number>;
  unknown_outcome_count: number;
  claim_boundary: string;
}

export interface ScientistValidationCaseInput {
  case_type: ScientistValidationCaseType;
  priority: number;
  region_key?: string | null;
  region_name?: string | null;
  forecast_run_id?: string | null;
  forecast_grid_id?: string | null;
  forecast_hour?: number | null;
  cell_row?: number | null;
  cell_col?: number | null;
  title: string;
  summary?: string | null;
  evidence?: Record<string, unknown>;
  cell_snapshot?: Record<string, unknown>;
  model_metadata?: Record<string, unknown>;
  gate_key?: string | null;
  claim_boundary?: string;
  requires_two_reviewers?: boolean;
  signoff_scope?: string;
}

export interface ScientistValidationReviewInput {
  verdict: ScientistValidationVerdict;
  confidence: number;
  notes?: string | null;
  failure_mode?: string | null;
  weak_layer_class?: string | null;
  runout_verdict?: string | null;
  claim_impact?: ClaimImpact;
  official_avalanche_problem?: OfficialAvalancheProblem | null;
  label_quality_verdict?: LabelQualityVerdict | null;
  model_error_verdict?: ModelErrorVerdict | null;
  terrain_sar_ambiguity?: TerrainSarAmbiguity | null;
  evidence_needed_next?: EvidenceNeededNext | null;
  confidence_rationale?: string | null;
  evidence_refs?: Record<string, unknown>;
}

export function isSyntheticDemoCase(caseRow: ScientistValidationCase): boolean {
  const evidence = normalizeRecord(caseRow.evidence);
  const cellSnapshot = normalizeRecord(caseRow.cell_snapshot);
  const modelMetadata = normalizeRecord(caseRow.model_metadata);
  return (
    caseRow.region_key === 'demo_himalayas_synthetic'
    || caseRow.claim_boundary === 'synthetic_demo_not_scientific_evidence'
    || evidence.synthetic_demo === true
    || cellSnapshot.synthetic_demo === true
    || modelMetadata.synthetic_demo === true
  );
}

type SupabaseQueryResult = {
  data: unknown;
  error: {
    message?: string;
    code?: string;
    status?: number;
  } | null;
};

type SupabaseQuery = PromiseLike<SupabaseQueryResult> & {
  select: (columns?: string) => SupabaseQuery;
  order: (column: string, options?: Record<string, unknown>) => SupabaseQuery;
  limit: (count: number) => SupabaseQuery;
  in: (column: string, values: unknown[]) => SupabaseQuery;
  eq: (column: string, value: unknown) => SupabaseQuery;
  update: (payload: Record<string, unknown>) => SupabaseQuery;
  insert: (payload: unknown) => SupabaseQuery;
  single: () => Promise<SupabaseQueryResult>;
};

const db = supabase as unknown as {
  from: (table: string) => SupabaseQuery;
  auth: typeof supabase.auth;
};

function normalizeRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

export function validationStatusLabel(status: ScientistValidationStatus): string {
  return status.replace(/_/g, ' ');
}

export function validationCaseTypeLabel(type: ScientistValidationCaseType): string {
  return type.replace(/_/g, ' ');
}

export function optionLabel<T extends string>(options: Array<{ value: T; label: string }>, value: T | null | undefined): string {
  return options.find((option) => option.value === value)?.label ?? 'n/a';
}

export async function getAuthenticatedUserId(): Promise<string> {
  const { data, error } = await supabase.auth.getUser();
  if (error) throw error;
  if (!data.user?.id) {
    throw new Error('Sign in as a scientist or admin reviewer before using scientist validation tools.');
  }
  return data.user.id;
}

export async function fetchScientistValidationCases(limit = 30): Promise<ScientistValidationCase[]> {
  const { data, error } = await db
    .from('scientist_validation_cases')
    .select('*')
    .order('priority', { ascending: false })
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) throw error;
  return (data ?? []) as ScientistValidationCase[];
}

export async function fetchScientistValidationReviews(caseIds: string[]): Promise<ScientistValidationReview[]> {
  if (caseIds.length === 0) return [];
  const { data, error } = await db
    .from('scientist_validation_reviews')
    .select('*')
    .in('case_id', caseIds)
    .order('created_at', { ascending: false });
  if (error) throw error;
  return (data ?? []) as ScientistValidationReview[];
}

export async function fetchScientistValidationActions(caseIds: string[]): Promise<ScientistValidationAction[]> {
  if (caseIds.length === 0) return [];
  const { data, error } = await db
    .from('scientist_validation_actions')
    .select('*')
    .in('case_id', caseIds)
    .order('created_at', { ascending: false });
  if (error) {
    const message = String(error.message ?? '').toLowerCase();
    if (error.code === '42P01' || error.status === 404 || message.includes('scientist_validation_actions')) {
      return [];
    }
    throw error;
  }
  return (data ?? []) as ScientistValidationAction[];
}

export async function updateScientistValidationAction(
  actionId: string,
  input: { status: ScientistValidationAction['status']; resolution_notes?: string | null },
): Promise<ScientistValidationAction> {
  const payload = {
    status: input.status,
    resolution_notes: input.resolution_notes ?? null,
    resolved_at: input.status === 'resolved' || input.status === 'rejected' ? new Date().toISOString() : null,
  };
  const { data, error } = await db
    .from('scientist_validation_actions')
    .update(payload)
    .eq('id', actionId)
    .select('*')
    .single();
  if (error) throw error;
  return data as ScientistValidationAction;
}

export async function fetchCellEvidenceLinks(params: {
  regionKey?: string | null;
  forecastRunId?: string | null;
  forecastGridId?: string | null;
  cellRow?: number | null;
  cellCol?: number | null;
}): Promise<CellEvidenceLinks> {
  const { forecastRunId, forecastGridId, cellRow, cellCol } = params;
  if (cellRow == null || cellCol == null) {
    return { outcomes: [], field_reports: [] };
  }
  let outcomesQuery = db
    .from('forecast_outcomes')
    .select('*')
    .eq('cell_row', cellRow)
    .eq('cell_col', cellCol)
    .limit(5);
  if (forecastRunId) {
    outcomesQuery = outcomesQuery.eq('forecast_id', forecastRunId);
  } else if (forecastGridId) {
    outcomesQuery = outcomesQuery.eq('forecast_grid_id', forecastGridId);
  }
  const fieldReportsQuery = db
    .from('field_reports')
    .select('*')
    .limit(5);
  const [{ data: outcomes, error: outcomesError }, { data: fieldReports, error: fieldReportsError }] = await Promise.all([
    outcomesQuery,
    fieldReportsQuery,
  ]);
  if (outcomesError) throw outcomesError;
  if (fieldReportsError) throw fieldReportsError;
  return {
    outcomes: (outcomes ?? []) as Array<Record<string, unknown>>,
    field_reports: (fieldReports ?? []) as Array<Record<string, unknown>>,
  };
}

export async function createScientistValidationCase(
  input: ScientistValidationCaseInput,
): Promise<ScientistValidationCase> {
  const userId = await getAuthenticatedUserId();
  const payload = {
    ...input,
    status: 'pending',
    created_by: userId,
    evidence: normalizeRecord(input.evidence),
    cell_snapshot: normalizeRecord(input.cell_snapshot),
    model_metadata: normalizeRecord(input.model_metadata),
    claim_boundary: input.claim_boundary ?? 'decision_support_validation',
    requires_two_reviewers: input.requires_two_reviewers ?? input.priority >= 5,
    signoff_scope: input.signoff_scope ?? 'single_case_review',
  };
  const { data, error } = await db
    .from('scientist_validation_cases')
    .insert(payload)
    .select('*')
    .single();
  if (error) throw error;
  return data as ScientistValidationCase;
}

export async function createScientistValidationReview(
  caseId: string,
  input: ScientistValidationReviewInput,
): Promise<ScientistValidationReview> {
  const userId = await getAuthenticatedUserId();
  const { data: caseRow, error: caseError } = await db
    .from('scientist_validation_cases')
    .select('*')
    .eq('id', caseId)
    .single();
  if (caseError) throw caseError;
  const validationCase = caseRow as ScientistValidationCase;
  const existingReviews = await fetchScientistValidationReviews([caseId]);
  const payload = {
    case_id: caseId,
    reviewer_id: userId,
    verdict: input.verdict,
    confidence: input.confidence,
    notes: input.notes ?? null,
    failure_mode: input.failure_mode ?? null,
    weak_layer_class: input.weak_layer_class ?? null,
    runout_verdict: input.runout_verdict ?? null,
    claim_impact: input.claim_impact ?? 'no_change',
    official_avalanche_problem: input.official_avalanche_problem ?? null,
    label_quality_verdict: input.label_quality_verdict ?? null,
    model_error_verdict: input.model_error_verdict ?? null,
    terrain_sar_ambiguity: input.terrain_sar_ambiguity ?? null,
    evidence_needed_next: input.evidence_needed_next ?? null,
    confidence_rationale: input.confidence_rationale ?? null,
    evidence_refs: normalizeRecord(input.evidence_refs),
  };
  const { data, error } = await db
    .from('scientist_validation_reviews')
    .insert(payload)
    .select('*')
    .single();
  if (error) throw error;

  const createdReview = data as ScientistValidationReview;
  const allReviews = [...existingReviews, createdReview];
  const uniqueReviewerCount = new Set(allReviews.map((review) => review.reviewer_id).filter(Boolean)).size;
  const requiresTwoReviewers = validationCase.requires_two_reviewers ?? validationCase.priority >= 5;
  const verdicts = new Set(allReviews.map((review) => review.verdict));
  const impacts = new Set(allReviews.map((review) => review.claim_impact));
  const hasDisagreement = allReviews.length >= 2 && (verdicts.size > 1 || impacts.size > 1);
  const nextStatus: ScientistValidationStatus = input.claim_impact === 'block'
    ? 'blocked'
    : requiresTwoReviewers && uniqueReviewerCount < 2
      ? 'in_review'
      : hasDisagreement
        ? 'in_review'
        : input.verdict === 'accepted_limitation'
          ? 'accepted_limitation'
          : 'reviewed';
  const actionPayloads = buildActionPayloads(validationCase, createdReview, userId, hasDisagreement);

  await db
    .from('scientist_validation_cases')
    .update({
      status: nextStatus,
      reviewed_at: nextStatus === 'reviewed' || nextStatus === 'blocked' || nextStatus === 'accepted_limitation'
        ? new Date().toISOString()
        : null,
      requires_two_reviewers: requiresTwoReviewers,
      disagreement_count: hasDisagreement ? 1 : 0,
    })
    .eq('id', caseId);
  if (actionPayloads.length > 0) {
    const { error: actionError } = await db.from('scientist_validation_actions').insert(actionPayloads);
    if (actionError) throw actionError;
  }

  return createdReview;
}

export async function createDailyVerification(input: DailyVerificationInput): Promise<DailyVerificationRecord> {
  const userId = await getAuthenticatedUserId();
  const { data, error } = await db
    .from('scientist_daily_verifications')
    .insert({
      ...input,
      reviewer_id: userId,
      observed_outcome: input.observed_outcome ?? 'unknown',
      confidence: input.confidence ?? 0.75,
      official_avalanche_problem: input.official_avalanche_problem ?? null,
      model_avalanche_problem: input.model_avalanche_problem ?? null,
      notes: input.notes ?? null,
      evidence_refs: normalizeRecord(input.evidence_refs),
    })
    .select('*')
    .single();
  if (error) throw error;
  return data as DailyVerificationRecord;
}

export async function fetchDailyVerifications(limit = 30): Promise<DailyVerificationRecord[]> {
  const { data, error } = await db
    .from('scientist_daily_verifications')
    .select('*')
    .order('verification_date', { ascending: false })
    .order('created_at', { ascending: false })
    .limit(limit);
  if (error) {
    const message = String(error.message ?? '').toLowerCase();
    if (error.code === '42P01' || error.status === 404 || message.includes('scientist_daily_verifications')) {
      return [];
    }
    throw error;
  }
  return (data ?? []) as DailyVerificationRecord[];
}

function incrementMatrix(matrix: Record<string, Record<string, number>>, rowKey: string, colKey: string) {
  matrix[rowKey] = matrix[rowKey] ?? {};
  matrix[rowKey][colKey] = (matrix[rowKey][colKey] ?? 0) + 1;
}

export function buildDailyVerificationAnalytics(records: DailyVerificationRecord[]): DailyVerificationAnalytics {
  const dangerMatrix: Record<string, Record<string, number>> = {};
  const problemMatrix: Record<string, Record<string, number>> = {};
  const observedOutcomeDistribution: Record<string, number> = {};
  let assessableDangerPairCount = 0;
  let exactDangerMatches = 0;

  records.forEach((record) => {
    const scientistDanger = record.scientist_danger_level ?? 'not_assessed';
    const modelDanger = record.model_danger_level ?? 'not_assessed';
    const scientistProblem = record.official_avalanche_problem ?? 'not_assessed';
    const modelProblem = record.model_avalanche_problem ?? 'not_assessed';
    const observedOutcome = record.observed_outcome ?? 'unknown';

    incrementMatrix(dangerMatrix, scientistDanger, modelDanger);
    incrementMatrix(problemMatrix, scientistProblem, modelProblem);
    observedOutcomeDistribution[observedOutcome] = (observedOutcomeDistribution[observedOutcome] ?? 0) + 1;

    if (scientistDanger !== 'not_assessed' && modelDanger !== 'not_assessed') {
      assessableDangerPairCount += 1;
      if (scientistDanger === modelDanger) {
        exactDangerMatches += 1;
      }
    }
  });

  return {
    record_count: records.length,
    assessable_danger_pair_count: assessableDangerPairCount,
    exact_danger_matches: exactDangerMatches,
    exact_danger_match_rate: assessableDangerPairCount ? exactDangerMatches / assessableDangerPairCount : null,
    danger_level_confusion_matrix: dangerMatrix,
    avalanche_problem_confusion_matrix: problemMatrix,
    observed_outcome_distribution: observedOutcomeDistribution,
    unknown_outcome_count: observedOutcomeDistribution.unknown ?? 0,
    claim_boundary: 'Paired verification is comparison evidence only. It does not promote public scoring or replace official scientist sign-off.',
  };
}

export function buildDailyVerificationExport(records: DailyVerificationRecord[]): string {
  const analytics = buildDailyVerificationAnalytics(records);
  return JSON.stringify({
    schema_version: 'scientist-daily-verification/v1',
    exported_at: new Date().toISOString(),
    summary: analytics,
    analytics,
    records,
  }, null, 2);
}

function buildActionPayloads(
  validationCase: ScientistValidationCase,
  review: ScientistValidationReview,
  userId: string,
  hasDisagreement: boolean,
): Array<Record<string, unknown>> {
  const base = {
    case_id: validationCase.id,
    review_id: review.id,
    priority: Math.max(3, validationCase.priority),
    created_by: userId,
    evidence_refs: {
      gate_key: validationCase.gate_key,
      forecast_run_id: validationCase.forecast_run_id,
      forecast_hour: validationCase.forecast_hour,
      cell_row: validationCase.cell_row,
      cell_col: validationCase.cell_col,
      claim_boundary: validationCase.claim_boundary,
    },
  };
  const actions: Array<Record<string, unknown>> = [];
  if (review.claim_impact === 'downgrade') {
    actions.push({
      ...base,
      action_type: 'claim_downgrade',
      owner_role: 'operator',
      summary: `Downgrade claim boundary for ${validationCase.title}`,
    });
  }
  if (review.claim_impact === 'block') {
    actions.push({
      ...base,
      action_type: 'claim_block',
      owner_role: 'operator',
      summary: `Block claim or promotion path for ${validationCase.title}`,
    });
  }
  if (review.label_quality_verdict && review.label_quality_verdict !== 'label_reliable' && review.label_quality_verdict !== 'not_assessed') {
    actions.push({
      ...base,
      action_type: 'label_remediation',
      owner_role: 'data',
      summary: `Review label quality issue ${review.label_quality_verdict} for ${validationCase.title}`,
    });
  }
  if (review.model_error_verdict === 'model_false_positive' || review.model_error_verdict === 'model_false_negative' || review.model_error_verdict === 'model_miscalibrated') {
    actions.push({
      ...base,
      action_type: 'model_gap_candidate',
      owner_role: 'ml',
      summary: `Add model-gap candidate from ${review.model_error_verdict} on ${validationCase.title}`,
    });
  }
  if (review.evidence_needed_next && review.evidence_needed_next !== 'none' && review.evidence_needed_next !== 'not_assessed') {
    actions.push({
      ...base,
      action_type: review.evidence_needed_next === 'benchmark_slice' ? 'benchmark_slice' : 'evidence_request',
      owner_role: review.evidence_needed_next === 'benchmark_slice' ? 'ml' : 'scientist',
      summary: `Collect next evidence ${review.evidence_needed_next} for ${validationCase.title}`,
    });
  }
  if (hasDisagreement) {
    actions.push({
      ...base,
      action_type: 'reviewer_disagreement',
      owner_role: 'operator',
      summary: `Resolve reviewer disagreement for ${validationCase.title}`,
    });
  }
  return actions;
}

export function buildCellValidationCaseInput(params: {
  selectedCell: GridCell;
  regionKey?: string | null;
  regionName?: string | null;
  forecastRunId?: string | null;
  forecastGridId?: string | null;
  forecastHour?: number | null;
  modelMetadata?: Record<string, unknown> | null;
}): ScientistValidationCaseInput {
  const { selectedCell, regionKey, regionName, forecastRunId, forecastGridId, forecastHour, modelMetadata } = params;
  const publicEligible = selectedCell.publicEligible;
  const caseType: ScientistValidationCaseType = publicEligible === false || selectedCell.disabled
    ? 'masked_terrain'
    : selectedCell.runoutSeed || selectedCell.riskScore >= 4
      ? 'runout'
      : 'weak_layer';
  const priority = selectedCell.riskScore >= 4 || selectedCell.uncertaintyClass === 'high' ? 5 : 4;
  const title = `${validationCaseTypeLabel(caseType)} review: r${selectedCell.row} c${selectedCell.col}`;
  const evidence = {
    risk_score: selectedCell.riskScore,
    probability: selectedCell.probability ?? null,
    uncertainty_class: selectedCell.uncertaintyClass ?? null,
    uncertainty_span: selectedCell.uncertaintySpan ?? null,
    problem_slug: selectedCell.problemSlug ?? null,
    problem_type: selectedCell.problemType ?? null,
    runout_seed: selectedCell.runoutSeed ?? false,
    explainability_mode: selectedCell.explainabilityMode ?? null,
    explainability_reason: selectedCell.explainabilityReason ?? null,
    dominant_driver_feature: selectedCell.dominantDriverFeature ?? null,
    public_mask_reasons: selectedCell.publicMaskReasons ?? [],
    snowpack_proxy: selectedCell.snowpackProxy ?? null,
  };
  return {
    case_type: caseType,
    priority,
    region_key: regionKey ?? null,
    region_name: regionName ?? null,
    forecast_run_id: forecastRunId ?? null,
    forecast_grid_id: forecastGridId ?? null,
    forecast_hour: forecastHour ?? null,
    cell_row: selectedCell.row,
    cell_col: selectedCell.col,
    title,
    summary: 'Scientist review case created from the selected forecast cell. Review should determine whether the displayed evidence supports the current claim boundary.',
    evidence,
    cell_snapshot: selectedCell as unknown as Record<string, unknown>,
    model_metadata: modelMetadata ?? {},
    gate_key: caseType === 'runout' ? 'runout_validation' : caseType === 'weak_layer' ? 'weak_layer_validation' : 'public_mask_validation',
    claim_boundary: 'decision_support_validation',
    requires_two_reviewers: priority >= 5,
  };
}

export function buildValidationPacket(caseRow: ScientistValidationCase, reviews: ScientistValidationReview[] = []): string {
  return JSON.stringify({
    schema_version: 'scientist-validation-packet/v1',
    exported_at: new Date().toISOString(),
    case: caseRow,
    reviews,
    claim_boundary: 'This packet is review evidence only. It does not promote SAR, MTS-LSTM, TreeSHAP, or Whitebox claims without separate release artifacts.',
  }, null, 2);
}

export function calculateReviewAgreement(reviews: ScientistValidationReview[]): {
  paired_case_count: number;
  exact_verdict_agreement_count: number;
  exact_verdict_agreement_rate: number | null;
  cohen_kappa: number | null;
  cohen_kappa_reason: string | null;
} {
  const reviewsByCase = new Map<string, ScientistValidationReview[]>();
  reviews.forEach((review) => {
    const existing = reviewsByCase.get(review.case_id) ?? [];
    existing.push(review);
    reviewsByCase.set(review.case_id, existing);
  });
  const pairedCases = [...reviewsByCase.values()]
    .map((caseReviews) => {
      const firstByReviewer = new Map<string, ScientistValidationReview>();
      [...caseReviews]
        .filter((review) => Boolean(review.reviewer_id))
        .sort((a, b) => a.created_at.localeCompare(b.created_at))
        .forEach((review) => {
          if (review.reviewer_id && !firstByReviewer.has(review.reviewer_id)) {
            firstByReviewer.set(review.reviewer_id, review);
          }
        });
      return [...firstByReviewer.values()].slice(0, 2);
    })
    .filter((caseReviews) => caseReviews.length >= 2);
  const agreementCount = pairedCases.filter((caseReviews) => caseReviews[0].verdict === caseReviews[1].verdict).length;
  const kappa = calculateCohenKappa(pairedCases.map((caseReviews) => [caseReviews[0].verdict, caseReviews[1].verdict]));
  return {
    paired_case_count: pairedCases.length,
    exact_verdict_agreement_count: agreementCount,
    exact_verdict_agreement_rate: pairedCases.length ? agreementCount / pairedCases.length : null,
    cohen_kappa: kappa.value,
    cohen_kappa_reason: kappa.reason,
  };
}

function calculateCohenKappa(pairs: Array<[ScientistValidationVerdict, ScientistValidationVerdict]>): { value: number | null; reason: string | null } {
  if (pairs.length < 2) {
    return { value: null, reason: 'insufficient_pairs' };
  }
  const labels = [...new Set(pairs.flat())];
  if (labels.length < 2) {
    return { value: null, reason: 'degenerate_labels' };
  }
  const observedAgreement = pairs.filter(([left, right]) => left === right).length / pairs.length;
  const leftCounts = new Map<ScientistValidationVerdict, number>();
  const rightCounts = new Map<ScientistValidationVerdict, number>();
  pairs.forEach(([left, right]) => {
    leftCounts.set(left, (leftCounts.get(left) ?? 0) + 1);
    rightCounts.set(right, (rightCounts.get(right) ?? 0) + 1);
  });
  const expectedAgreement = labels.reduce((sum, label) => {
    return sum + ((leftCounts.get(label) ?? 0) / pairs.length) * ((rightCounts.get(label) ?? 0) / pairs.length);
  }, 0);
  if (expectedAgreement >= 1) {
    return { value: null, reason: 'degenerate_expected_agreement' };
  }
  return {
    value: (observedAgreement - expectedAgreement) / (1 - expectedAgreement),
    reason: null,
  };
}

export function buildValidationSummaryPacket(
  cases: ScientistValidationCase[],
  reviews: ScientistValidationReview[],
  gateStatuses: Array<{ key: string; label: string; status: string; detail: string }> = [],
  actions: ScientistValidationAction[] = [],
): string {
  const reviewsByCase = new Map<string, ScientistValidationReview[]>();
  reviews.forEach((review) => {
    const existing = reviewsByCase.get(review.case_id) ?? [];
    existing.push(review);
    reviewsByCase.set(review.case_id, existing);
  });
  const actionsByCase = new Map<string, ScientistValidationAction[]>();
  actions.forEach((action) => {
    const existing = actionsByCase.get(action.case_id) ?? [];
    existing.push(action);
    actionsByCase.set(action.case_id, existing);
  });
  const statusCounts = cases.reduce<Record<string, number>>((acc, caseRow) => {
    acc[caseRow.status] = (acc[caseRow.status] ?? 0) + 1;
    return acc;
  }, {});
  const claimImpactCounts = reviews.reduce<Record<string, number>>((acc, review) => {
    acc[review.claim_impact] = (acc[review.claim_impact] ?? 0) + 1;
    return acc;
  }, {});
  const actionCounts = actions.reduce<Record<string, number>>((acc, action) => {
    acc[action.action_type] = (acc[action.action_type] ?? 0) + 1;
    return acc;
  }, {});
  const agreement = calculateReviewAgreement(reviews);
  return JSON.stringify({
    schema_version: 'scientist-validation-signoff-summary/v1',
    exported_at: new Date().toISOString(),
    summary: {
      case_count: cases.length,
      review_count: reviews.length,
      action_count: actions.length,
      synthetic_demo_case_count: cases.filter(isSyntheticDemoCase).length,
      status_counts: statusCounts,
      claim_impact_counts: claimImpactCounts,
      action_counts: actionCounts,
      reviewer_agreement: agreement,
      synthetic_demo_boundary: 'Synthetic demo rows are smoke-test fixtures only. They are excluded from training, public promotion, and grounded Himalayan evidence counts.',
      open_actions: actions
        .filter((action) => action.status === 'open' || action.status === 'in_progress')
        .map((action) => ({
          id: action.id,
          case_id: action.case_id,
          action_type: action.action_type,
          priority: action.priority,
          owner_role: action.owner_role,
          summary: action.summary,
        })),
      blocked_claims: cases
        .filter((caseRow) => caseRow.status === 'blocked')
        .map((caseRow) => ({ id: caseRow.id, title: caseRow.title, gate_key: caseRow.gate_key })),
      accepted_limitations: cases
        .filter((caseRow) => caseRow.status === 'accepted_limitation')
        .map((caseRow) => ({ id: caseRow.id, title: caseRow.title, gate_key: caseRow.gate_key })),
    },
    gates: gateStatuses,
    cases: cases.map((caseRow) => ({
      ...caseRow,
      reviews: reviewsByCase.get(caseRow.id) ?? [],
      actions: actionsByCase.get(caseRow.id) ?? [],
    })),
    claim_boundary: 'This summary is scientist-review evidence. Validation is complete only when the review protocol and sign-off scope are explicitly accepted by the scientist team.',
  }, null, 2);
}

export function buildValidationSummaryMarkdown(
  cases: ScientistValidationCase[],
  reviews: ScientistValidationReview[],
  gateStatuses: Array<{ key: string; label: string; status: string; detail: string }> = [],
  actions: ScientistValidationAction[] = [],
): string {
  const statusCounts = cases.reduce<Record<string, number>>((acc, caseRow) => {
    acc[caseRow.status] = (acc[caseRow.status] ?? 0) + 1;
    return acc;
  }, {});
  const claimImpactCounts = reviews.reduce<Record<string, number>>((acc, review) => {
    acc[review.claim_impact] = (acc[review.claim_impact] ?? 0) + 1;
    return acc;
  }, {});
  const actionCounts = actions.reduce<Record<string, number>>((acc, action) => {
    acc[action.action_type] = (acc[action.action_type] ?? 0) + 1;
    return acc;
  }, {});
  const agreement = calculateReviewAgreement(reviews);
  const actionsByCase = new Map<string, ScientistValidationAction[]>();
  actions.forEach((action) => {
    const existing = actionsByCase.get(action.case_id) ?? [];
    existing.push(action);
    actionsByCase.set(action.case_id, existing);
  });
  const lines = [
    '# Scientist Validation Sign-Off Packet',
    '',
    `Exported: ${new Date().toISOString()}`,
    '',
    '## Claim Boundary',
    '',
    'This packet is scientist-review evidence. It does not complete scientific validation or promote SAR, MTS-LSTM, TreeSHAP, or Whitebox claims without separate release artifacts and accepted sign-off scope.',
    '',
    '## Queue Summary',
    '',
    `- Cases: ${cases.length}`,
    `- Reviews: ${reviews.length}`,
    `- Governed actions: ${actions.length}`,
    `- Synthetic demo cases: ${cases.filter(isSyntheticDemoCase).length}`,
    `- Status counts: ${JSON.stringify(statusCounts)}`,
    `- Claim impact counts: ${JSON.stringify(claimImpactCounts)}`,
    `- Action counts: ${JSON.stringify(actionCounts)}`,
    `- Reviewer agreement: ${JSON.stringify(agreement)}`,
    '',
    '## Promotion Gates',
    '',
    ...gateStatuses.map((gate) => `- ${gate.label}: ${gate.status} - ${gate.detail}`),
    '',
    '## Cases',
    '',
    ...cases.map((caseRow) => [
      `### ${caseRow.title}`,
      '',
      `- Type: ${validationCaseTypeLabel(caseRow.case_type)}`,
      `- Status: ${validationStatusLabel(caseRow.status)}`,
      `- Priority: ${caseRow.priority}`,
      `- Region: ${caseRow.region_name ?? caseRow.region_key ?? 'n/a'}`,
      `- Run ID: ${caseRow.forecast_run_id ?? 'n/a'}`,
      `- Hour/cell: h${caseRow.forecast_hour ?? 'n/a'} r${caseRow.cell_row ?? 'n/a'} c${caseRow.cell_col ?? 'n/a'}`,
      `- Gate: ${caseRow.gate_key ?? 'n/a'}`,
      `- Claim boundary: ${caseRow.claim_boundary}`,
      `- Synthetic demo: ${isSyntheticDemoCase(caseRow) ? 'yes - excluded from training/public promotion' : 'no'}`,
      `- Two-reviewer required: ${caseRow.requires_two_reviewers ? 'yes' : 'no'}`,
      `- Disagreements: ${caseRow.disagreement_count ?? 0}`,
      `- Open actions: ${(actionsByCase.get(caseRow.id) ?? []).filter((action) => action.status === 'open' || action.status === 'in_progress').length}`,
      `- Summary: ${caseRow.summary ?? 'n/a'}`,
      '',
      '#### Reviews',
      '',
      ...((reviews.filter((review) => review.case_id === caseRow.id).length > 0)
        ? reviews
          .filter((review) => review.case_id === caseRow.id)
          .map((review) => [
            `- Review ${review.id}`,
            `  - Reviewer: ${review.reviewer_id ?? 'n/a'}`,
            `  - Verdict: ${review.verdict}`,
            `  - Claim impact: ${review.claim_impact}`,
            `  - Avalanche problem: ${review.official_avalanche_problem ?? 'n/a'}`,
            `  - Label quality: ${review.label_quality_verdict ?? 'n/a'}`,
            `  - Model error: ${review.model_error_verdict ?? 'n/a'}`,
            `  - Terrain/SAR ambiguity: ${review.terrain_sar_ambiguity ?? 'n/a'}`,
            `  - Evidence needed next: ${review.evidence_needed_next ?? 'n/a'}`,
            `  - Confidence rationale: ${review.confidence_rationale ?? 'n/a'}`,
            `  - Attached references: ${formatAttachedReferences(review.evidence_refs)}`,
            `  - Notes: ${review.notes ?? 'n/a'}`,
          ].join('\n'))
        : ['- No reviews recorded in this export.']),
      '',
      '#### Governed Actions',
      '',
      ...(((actionsByCase.get(caseRow.id) ?? []).length > 0)
        ? (actionsByCase.get(caseRow.id) ?? []).map((action) => [
          `- Action ${action.id}`,
          `  - Type: ${action.action_type}`,
          `  - Status: ${action.status}`,
          `  - Priority: ${action.priority}`,
          `  - Owner role: ${action.owner_role}`,
          `  - Summary: ${action.summary}`,
          `  - Resolution notes: ${action.resolution_notes ?? 'n/a'}`,
        ].join('\n'))
        : ['- No governed actions recorded in this export.']),
      '',
    ].join('\n')),
  ];
  return lines.join('\n');
}

function formatAttachedReferences(evidenceRefs: Record<string, unknown>): string {
  const attached = evidenceRefs.attached_publications;
  if (!Array.isArray(attached) || attached.length === 0) {
    return 'none';
  }
  return attached
    .map((reference) => {
      if (!reference || typeof reference !== 'object' || Array.isArray(reference)) {
        return null;
      }
      const record = reference as Record<string, unknown>;
      const id = typeof record.id === 'string' ? record.id : null;
      const title = typeof record.title === 'string' ? record.title : null;
      return [id, title].filter(Boolean).join(' - ') || null;
    })
    .filter((value): value is string => Boolean(value))
    .join('; ') || 'none';
}
