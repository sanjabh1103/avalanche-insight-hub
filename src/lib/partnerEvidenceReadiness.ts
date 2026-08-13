export const PARTNER_INTAKE_CLAIM_LOCKS = {
  production_scoring_allowed: false,
  himalayan_accuracy_claim_allowed: false,
  sar_shadow_only: true,
} as const;

export const PARTNER_SOURCE_MANIFEST_FILENAME = 'partner_source_manifest.json';

export type PartnerEvidenceKey =
  | 'station_metadata'
  | 'weather_station_observations'
  | 'snowpack_profile_features'
  | 'danger_labels_and_bulletins'
  | 'warning_region_polygons'
  | 'historical_avalanche_events'
  | 'remote_sensing_validation_scenes'
  | 'terrain_ates_runout_validation'
  | 'scientist_reviews'
  | 'independent_himalayan_holdout';

export interface PartnerEvidenceRequirement {
  key: PartnerEvidenceKey;
  filename: string;
  label: string;
  owner: string;
  week: string;
  uiToday: 'no' | 'partial';
  requiredColumns: string[];
  nextAction: string;
  claimBoundary: string;
}

export interface PartnerEvidenceFileInput {
  name: string;
  text: string;
  sizeBytes?: number;
  lastModified?: number;
}

export interface PartnerEvidenceFileReport {
  filename: string;
  label: string;
  key: PartnerEvidenceKey | 'source_manifest';
  status: 'missing' | 'header_mismatch' | 'empty' | 'pending_review' | 'reviewed' | 'synthetic_marker' | 'valid_manifest' | 'invalid_manifest';
  present: boolean;
  sha256: string | null;
  sizeBytes: number;
  rowCount: number;
  reviewedRowCount: number;
  missingColumns: string[];
  unexpectedColumns: string[];
  blockers: string[];
  warnings: string[];
}

export interface PartnerEvidenceReadinessSummary {
  schema_version: 'partner-evidence-browser-preflight/v1';
  generated_at: string;
  usage_boundary: 'research_validation_only';
  production_scoring_allowed: false;
  himalayan_accuracy_claim_allowed: false;
  required_file_count: number;
  present_file_count: number;
  missing_file_count: number;
  header_pass_count: number;
  reviewed_row_count: number;
  total_row_count: number;
  synthetic_marker_detected: boolean;
  decision:
    | 'blocked_synthetic_package_detected'
    | 'blocked_required_partner_files_missing'
    | 'blocked_source_manifest_invalid'
    | 'blocked_partner_schema_mismatch'
    | 'blocked_no_reviewed_partner_rows'
    | 'partner_intake_preflight_ready_for_cli_triage';
  blockers: string[];
  warnings: string[];
  files: PartnerEvidenceFileReport[];
  claim_boundary: {
    production_scoring_allowed: false;
    himalayan_accuracy_claim_allowed: false;
    reason: string;
  };
}

export const REQUIRED_PARTNER_EVIDENCE_FILES: PartnerEvidenceRequirement[] = [
  {
    key: 'station_metadata',
    filename: 'station_metadata.csv',
    label: 'Station X/Y/Z metadata',
    owner: 'Partner + geospatial reviewer',
    week: 'W3',
    uiToday: 'no',
    requiredColumns: ['station_id', 'region_key', 'latitude', 'longitude', 'elevation_m', 'active_date_range', 'source_ref', 'license_scope', 'review_status', 'reviewer_id', 'reviewed_at', 'reviewer_notes'],
    nextAction: 'Provide reviewed station coordinates and elevation coverage before GPxyz can run.',
    claimBoundary: 'Spatial readiness input only; not a Himalayan accuracy result.',
  },
  {
    key: 'weather_station_observations',
    filename: 'weather_station_observations.csv',
    label: 'Weather station observations',
    owner: 'Partner',
    week: 'W3-W5',
    uiToday: 'no',
    requiredColumns: ['station_id', 'observed_at', 'air_temp_c', 'precipitation_mm', 'snowfall_cm', 'snow_depth_cm', 'wind_speed_ms', 'wind_dir_deg', 'source_ref', 'license_scope', 'review_status', 'reviewer_id', 'reviewed_at', 'reviewer_notes'],
    nextAction: 'Submit reviewed station weather rows for the pilot region and date windows.',
    claimBoundary: 'Feature evidence only; not production scoring authorization.',
  },
  {
    key: 'snowpack_profile_features',
    filename: 'snowpack_profile_features.csv',
    label: 'Snowpack and weak-layer evidence',
    owner: 'Partner + scientist',
    week: 'W4-W8',
    uiToday: 'no',
    requiredColumns: [
      'station_id',
      'observed_at',
      'layer_index',
      'layer_depth_cm',
      'grain_type',
      'hardness_index',
      'stability_index',
      'quality_flag',
      'profile_model',
      'snowpack_model_version',
      'profile_extracted_at_local_time',
      'stability_metric_name',
      'source_ref',
      'license_scope',
      'review_status',
      'reviewer_id',
      'reviewed_at',
      'reviewer_notes',
    ],
    nextAction: 'Fill layer and stability evidence with review notes and source refs.',
    claimBoundary: 'Weak-layer evidence remains research-only until validated locally.',
  },
  {
    key: 'danger_labels_and_bulletins',
    filename: 'danger_labels_and_bulletins.csv',
    label: 'D_tidy-grade danger labels',
    owner: 'Scientist + partner',
    week: 'W4',
    uiToday: 'no',
    requiredColumns: [
      'region_id',
      'valid_from',
      'valid_to',
      'danger_scale_standard',
      'danger_level_1_to_5',
      'danger_level_1_to_4',
      'label_source',
      'tidy_label_review_basis',
      'nowcast_evidence_ref',
      'observer_evidence_ref',
      'forecast_cycle',
      'forecast_issue_time',
      'valid_at',
      'window_center_local_time',
      'aggregation_window_hours',
      'avalanche_problem',
      'avalanche_regime',
      'elevation_band_policy',
      'critical_elevation_m',
      'aspect_policy',
      'forecaster_or_reviewer_id',
      'source_ref',
      'license_scope',
      'review_status',
      'reviewer_id',
      'reviewed_at',
      'reviewer_notes',
    ],
    nextAction: 'Provide reviewed labels with provenance; raw bulletins alone are not training truth.',
    claimBoundary: 'Label evidence must pass review before any local holdout claim.',
  },
  {
    key: 'warning_region_polygons',
    filename: 'warning_region_polygons.csv',
    label: 'Warning-region polygons',
    owner: 'Partner + geospatial reviewer',
    week: 'W7-W9',
    uiToday: 'no',
    requiredColumns: ['region_id', 'polygon_geometry', 'crs', 'elevation_policy', 'valid_date_range', 'source_ref', 'license_scope', 'review_status', 'reviewer_id', 'reviewed_at', 'reviewer_notes'],
    nextAction: 'Provide reviewed CRS, geometry, and elevation-policy rows for aggregation.',
    claimBoundary: 'Aggregation prerequisite only.',
  },
  {
    key: 'historical_avalanche_events',
    filename: 'historical_avalanche_events.csv',
    label: 'Historical avalanche events',
    owner: 'Scientist + partner',
    week: 'W5-W11',
    uiToday: 'no',
    requiredColumns: [
      'event_id',
      'observed_at',
      'latitude',
      'longitude',
      'elevation_m',
      'aspect',
      'avalanche_problem',
      'avalanche_regime',
      'observed_outcome',
      'confidence',
      'source',
      'field_report_ref',
      'avalanche_atlas_ref',
      'source_ref',
      'license_scope',
      'review_status',
      'reviewer_id',
      'reviewed_at',
      'reviewer_notes',
    ],
    nextAction: 'Provide event truth with confidence, source refs, and review status.',
    claimBoundary: 'Outcome evidence only; not a standalone accuracy result.',
  },
  {
    key: 'remote_sensing_validation_scenes',
    filename: 'remote_sensing_validation_scenes.csv',
    label: 'Remote-sensing validation scenes',
    owner: 'SAR/geospatial reviewer',
    week: 'W6-W11',
    uiToday: 'no',
    requiredColumns: ['scene_id', 'sensor', 'acquired_at', 'preprocessing_level', 'truth_mask_or_event_ref', 'holdout_split', 'license_scope', 'source_ref', 'review_status', 'reviewer_id', 'reviewed_at', 'reviewer_notes'],
    nextAction: 'Submit reviewed scene metadata only if available; keep SAR shadow-gated.',
    claimBoundary: 'SAR remains shadow-only and outside public scoring.',
  },
  {
    key: 'terrain_ates_runout_validation',
    filename: 'terrain_ates_runout_validation.csv',
    label: 'Terrain and runout validation',
    owner: 'Geospatial reviewer + scientist',
    week: 'W8-W11',
    uiToday: 'no',
    requiredColumns: ['region_id', 'dem_ref', 'slope', 'aspect', 'terrain_class', 'runout_validation_ref', 'quality_flag', 'source_ref', 'license_scope', 'review_status', 'reviewer_id', 'reviewed_at', 'reviewer_notes'],
    nextAction: 'Provide DEM/runout refs and terrain classes for scientist review.',
    claimBoundary: 'Terrain context evidence only.',
  },
  {
    key: 'scientist_reviews',
    filename: 'scientist_reviews.csv',
    label: 'Scientist adjudication ledger',
    owner: 'Scientist lead',
    week: 'W8-W12',
    uiToday: 'partial',
    requiredColumns: ['review_id', 'reviewer_id', 'reviewed_at', 'case_id', 'verdict', 'label_quality', 'model_error_type', 'confidence', 'source_ref', 'license_scope', 'review_status', 'reviewer_notes'],
    nextAction: 'Record verdicts, label quality, model error type, confidence, and notes.',
    claimBoundary: 'Human review evidence only; release gates still required.',
  },
  {
    key: 'independent_himalayan_holdout',
    filename: 'independent_himalayan_holdout.csv',
    label: 'Independent Himalayan holdout',
    owner: 'Holdout auditor + scientist',
    week: 'W9-W12',
    uiToday: 'no',
    requiredColumns: [
      'holdout_id',
      'source_refs',
      'region_ids',
      'date_range',
      'label_source',
      'tidy_label_review_basis',
      'nowcast_evidence_ref',
      'observer_evidence_ref',
      'forecast_cycle',
      'forecast_issue_time',
      'valid_at',
      'window_center_local_time',
      'aggregation_window_hours',
      'avalanche_regime',
      'critical_elevation_m',
      'aspect_policy',
      'field_report_ref',
      'avalanche_atlas_ref',
      'leakage_check',
      'acceptance_floors',
      'source_ref',
      'license_scope',
      'review_status',
      'reviewer_id',
      'reviewed_at',
      'reviewer_notes',
    ],
    nextAction: 'Define a leakage-checked fresh holdout before local accuracy claims.',
    claimBoundary: 'Required before release-gate claims.',
  },
];

function basename(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() ?? path;
}

function parseCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = '';
  let inQuotes = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === '"' && inQuotes && next === '"') {
      current += '"';
      index += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      values.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  values.push(current.trim());
  return values.map((value) => value.replace(/^\uFEFF/, ''));
}

export function parseCsvHeader(text: string): string[] {
  const firstLine = text.split(/\r?\n/).find((line) => line.trim().length > 0) ?? '';
  return parseCsvLine(firstLine);
}

function parseCsvRows(text: string, headers: string[]): Array<Record<string, string>> {
  return text
    .split(/\r?\n/)
    .slice(1)
    .filter((line) => line.trim().length > 0)
    .map((line) => {
      const values = parseCsvLine(line);
      return headers.reduce<Record<string, string>>((record, header, index) => {
        record[header] = values[index] ?? '';
        return record;
      }, {});
    });
}

function detectSyntheticMarker(name: string, text: string): boolean {
  const marker = `${name}\n${text}`.toLowerCase();
  return (
    marker.includes('synthetic_do_not_submit')
    || marker.includes('synthetic demo')
    || marker.includes('synthetic_demo')
    || marker.includes('not_partner_evidence')
  );
}

export async function sha256Text(text: string): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error('Web Crypto SHA-256 is unavailable in this runtime.');
  }
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

function manifestReport(file: PartnerEvidenceFileInput | undefined, generatedAt: Date): Promise<PartnerEvidenceFileReport> {
  if (!file) {
    return Promise.resolve({
      filename: PARTNER_SOURCE_MANIFEST_FILENAME,
      label: 'Partner source manifest',
      key: 'source_manifest',
      status: 'missing',
      present: false,
      sha256: null,
      sizeBytes: 0,
      rowCount: 0,
      reviewedRowCount: 0,
      missingColumns: [],
      unexpectedColumns: [],
      blockers: [`Missing required ${PARTNER_SOURCE_MANIFEST_FILENAME}.`],
      warnings: [],
    });
  }
  return sha256Text(file.text).then((sha256) => {
    const blockers: string[] = [];
    const warnings: string[] = [];
    let status: PartnerEvidenceFileReport['status'] = 'valid_manifest';
    if (detectSyntheticMarker(file.name, file.text)) {
      status = 'synthetic_marker';
      blockers.push('Synthetic package marker detected in source manifest.');
    } else {
      try {
        const payload = JSON.parse(file.text) as Record<string, unknown>;
        if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
          blockers.push('Source manifest JSON must be an object.');
        }
        if (!('sources' in payload)) {
          warnings.push('Source manifest has no sources field yet; partner data can still be preflighted but source governance is incomplete.');
        }
      } catch {
        status = 'invalid_manifest';
        blockers.push('Source manifest is not valid JSON.');
      }
    }
    if (blockers.length > 0 && status === 'valid_manifest') {
      status = 'invalid_manifest';
    }
    return {
      filename: PARTNER_SOURCE_MANIFEST_FILENAME,
      label: 'Partner source manifest',
      key: 'source_manifest',
      status,
      present: true,
      sha256,
      sizeBytes: file.sizeBytes ?? new Blob([file.text]).size,
      rowCount: 0,
      reviewedRowCount: 0,
      missingColumns: [],
      unexpectedColumns: [],
      blockers,
      warnings: [
        ...warnings,
        `Browser preflight generated ${generatedAt.toISOString()}; run CLI triage before treating this as package evidence.`,
      ],
    };
  });
}

async function evidenceReport(
  requirement: PartnerEvidenceRequirement,
  file: PartnerEvidenceFileInput | undefined,
): Promise<PartnerEvidenceFileReport> {
  if (!file) {
    return {
      filename: requirement.filename,
      label: requirement.label,
      key: requirement.key,
      status: 'missing',
      present: false,
      sha256: null,
      sizeBytes: 0,
      rowCount: 0,
      reviewedRowCount: 0,
      missingColumns: requirement.requiredColumns,
      unexpectedColumns: [],
      blockers: [`Missing required ${requirement.filename}.`],
      warnings: [],
    };
  }
  const sha256 = await sha256Text(file.text);
  const headers = parseCsvHeader(file.text);
  const missingColumns = requirement.requiredColumns.filter((column) => !headers.includes(column));
  const unexpectedColumns = headers.filter((column) => !requirement.requiredColumns.includes(column));
  const rows = parseCsvRows(file.text, headers);
  const reviewedRowCount = rows.filter((row) => row.review_status?.trim().toLowerCase() === 'reviewed').length;
  const blockers: string[] = [];
  const warnings: string[] = [];
  let status: PartnerEvidenceFileReport['status'];

  if (detectSyntheticMarker(file.name, file.text)) {
    status = 'synthetic_marker';
    blockers.push(`Synthetic marker detected in ${requirement.filename}.`);
  } else if (missingColumns.length > 0 || unexpectedColumns.length > 0) {
    status = 'header_mismatch';
    if (missingColumns.length > 0) {
      blockers.push(`Missing required columns: ${missingColumns.join(', ')}.`);
    }
    if (unexpectedColumns.length > 0) {
      blockers.push(`Unexpected columns require schema review: ${unexpectedColumns.join(', ')}.`);
    }
  } else if (rows.length === 0) {
    status = 'empty';
    warnings.push('CSV has the correct header but no evidence rows yet.');
  } else if (reviewedRowCount === 0) {
    status = 'pending_review';
    blockers.push('Rows exist but none have review_status=reviewed.');
  } else {
    status = 'reviewed';
  }

  return {
    filename: requirement.filename,
    label: requirement.label,
    key: requirement.key,
    status,
    present: true,
    sha256,
    sizeBytes: file.sizeBytes ?? new Blob([file.text]).size,
    rowCount: rows.length,
    reviewedRowCount,
    missingColumns,
    unexpectedColumns,
    blockers,
    warnings,
  };
}

export async function buildPartnerEvidenceReadinessSummary(
  files: PartnerEvidenceFileInput[],
  generatedAt = new Date(),
): Promise<PartnerEvidenceReadinessSummary> {
  const byName = new Map(files.map((file) => [basename(file.name), file]));
  const manifest = await manifestReport(byName.get(PARTNER_SOURCE_MANIFEST_FILENAME), generatedAt);
  const reports = await Promise.all(
    REQUIRED_PARTNER_EVIDENCE_FILES.map((requirement) => evidenceReport(requirement, byName.get(requirement.filename))),
  );
  const allReports = [manifest, ...reports];
  const blockers = allReports.flatMap((report) => report.blockers.map((blocker) => `${report.filename}: ${blocker}`));
  const warnings = allReports.flatMap((report) => report.warnings.map((warning) => `${report.filename}: ${warning}`));
  const syntheticMarkerDetected = allReports.some((report) => report.status === 'synthetic_marker');
  const missingFileCount = allReports.filter((report) => !report.present).length;
  const headerMismatchCount = reports.filter((report) => report.status === 'header_mismatch').length;
  const manifestInvalid = manifest.status === 'invalid_manifest';
  const reviewedRowCount = reports.reduce((sum, report) => sum + report.reviewedRowCount, 0);
  const totalRowCount = reports.reduce((sum, report) => sum + report.rowCount, 0);

  let decision: PartnerEvidenceReadinessSummary['decision'];
  if (syntheticMarkerDetected) {
    decision = 'blocked_synthetic_package_detected';
  } else if (missingFileCount > 0) {
    decision = 'blocked_required_partner_files_missing';
  } else if (manifestInvalid) {
    decision = 'blocked_source_manifest_invalid';
  } else if (headerMismatchCount > 0) {
    decision = 'blocked_partner_schema_mismatch';
  } else if (reviewedRowCount === 0) {
    decision = 'blocked_no_reviewed_partner_rows';
  } else {
    decision = 'partner_intake_preflight_ready_for_cli_triage';
  }

  return {
    schema_version: 'partner-evidence-browser-preflight/v1',
    generated_at: generatedAt.toISOString(),
    usage_boundary: 'research_validation_only',
    production_scoring_allowed: false,
    himalayan_accuracy_claim_allowed: false,
    required_file_count: allReports.length,
    present_file_count: allReports.filter((report) => report.present).length,
    missing_file_count: missingFileCount,
    header_pass_count: reports.filter((report) => report.present && report.missingColumns.length === 0 && report.unexpectedColumns.length === 0).length,
    reviewed_row_count: reviewedRowCount,
    total_row_count: totalRowCount,
    synthetic_marker_detected: syntheticMarkerDetected,
    decision,
    blockers,
    warnings,
    files: allReports,
    claim_boundary: {
      production_scoring_allowed: false,
      himalayan_accuracy_claim_allowed: false,
      reason: 'Browser preflight checks filenames, headers, hashes, and reviewed-row status only. It does not validate model accuracy, run CLI triage, promote SAR, or authorize production scoring.',
    },
  };
}

export function markdownPartnerEvidenceReadinessSummary(summary: PartnerEvidenceReadinessSummary): string {
  const lines = [
    '# Himalayan Partner Intake Browser Preflight',
    '',
    `Generated: ${summary.generated_at}`,
    '',
    '## Claim Boundary',
    '',
    '- `production_scoring_allowed=false`',
    '- `himalayan_accuracy_claim_allowed=false`',
    '- SAR remains shadow-only.',
    '- Browser preflight is not CLI triage, local holdout validation, or release-gate attestation.',
    '',
    '## Summary',
    '',
    `- Decision: ${summary.decision}`,
    `- Present files: ${summary.present_file_count} / ${summary.required_file_count}`,
    `- Header-pass evidence CSVs: ${summary.header_pass_count} / ${REQUIRED_PARTNER_EVIDENCE_FILES.length}`,
    `- Evidence rows: ${summary.total_row_count}`,
    `- Reviewed evidence rows: ${summary.reviewed_row_count}`,
    `- Synthetic marker detected: ${summary.synthetic_marker_detected ? 'yes' : 'no'}`,
    '',
    '## Blockers',
    '',
    ...(summary.blockers.length ? summary.blockers.map((blocker) => `- ${blocker}`) : ['- None from browser preflight; run CLI triage before any scientific review.']),
    '',
    '## Files',
    '',
    '| File | Status | Rows | Reviewed rows | SHA-256 |',
    '|---|---|---:|---:|---|',
    ...summary.files.map((file) => `| ${file.filename} | ${file.status} | ${file.rowCount} | ${file.reviewedRowCount} | ${file.sha256 ?? 'n/a'} |`),
    '',
  ];
  return lines.join('\n');
}
