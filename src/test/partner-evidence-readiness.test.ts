import { describe, expect, it } from 'vitest';

import {
  PARTNER_SOURCE_MANIFEST_FILENAME,
  REQUIRED_PARTNER_EVIDENCE_FILES,
  buildPartnerEvidenceReadinessSummary,
  markdownPartnerEvidenceReadinessSummary,
  type PartnerEvidenceFileInput,
  type PartnerEvidenceRequirement,
} from '@/lib/partnerEvidenceReadiness';

function manifest(text = '{"sources": []}'): PartnerEvidenceFileInput {
  return {
    name: PARTNER_SOURCE_MANIFEST_FILENAME,
    text,
    sizeBytes: text.length,
  };
}

function csv(requirement: PartnerEvidenceRequirement, options: { reviewed?: boolean; headerDrop?: string; marker?: string; empty?: boolean } = {}): PartnerEvidenceFileInput {
  const headers = requirement.requiredColumns.filter((column) => column !== options.headerDrop);
  const row = headers.map((column) => {
    if (column === 'review_status') return options.reviewed ? 'reviewed' : 'pending';
    if (column === 'reviewer_notes') return options.marker ?? 'reviewed by test';
    if (column === 'license_scope') return 'research_validation_only';
    if (column === 'source_ref') return 'a'.repeat(64);
    return `${column}_value`;
  });
  const text = options.empty ? `${headers.join(',')}\n` : `${headers.join(',')}\n${row.join(',')}\n`;
  return {
    name: requirement.filename,
    text,
    sizeBytes: text.length,
  };
}

function packageFiles(options: { reviewed?: boolean; headerMismatchKey?: string; syntheticKey?: string; empty?: boolean } = {}): PartnerEvidenceFileInput[] {
  return [
    manifest(),
    ...REQUIRED_PARTNER_EVIDENCE_FILES.map((requirement) => csv(requirement, {
      reviewed: options.reviewed,
      empty: options.empty,
      headerDrop: options.headerMismatchKey === requirement.key ? requirement.requiredColumns[0] : undefined,
      marker: options.syntheticKey === requirement.key ? 'SYNTHETIC_DO_NOT_SUBMIT' : undefined,
    })),
  ];
}

describe('partner evidence browser preflight', () => {
  it('keeps frontend template columns aligned with backend v3 critical provenance fields', () => {
    const byKey = new Map(REQUIRED_PARTNER_EVIDENCE_FILES.map((requirement) => [requirement.key, requirement.requiredColumns]));

    expect(byKey.get('danger_labels_and_bulletins')).toEqual(expect.arrayContaining([
      'label_source',
      'tidy_label_review_basis',
      'nowcast_evidence_ref',
      'observer_evidence_ref',
      'forecast_cycle',
      'forecast_issue_time',
      'window_center_local_time',
      'aggregation_window_hours',
      'avalanche_regime',
      'critical_elevation_m',
      'aspect_policy',
    ]));
    expect(byKey.get('snowpack_profile_features')).toEqual(expect.arrayContaining([
      'profile_model',
      'snowpack_model_version',
      'profile_extracted_at_local_time',
      'stability_metric_name',
    ]));
    expect(byKey.get('historical_avalanche_events')).toEqual(expect.arrayContaining([
      'avalanche_regime',
      'field_report_ref',
      'avalanche_atlas_ref',
    ]));
    expect(byKey.get('independent_himalayan_holdout')).toEqual(expect.arrayContaining([
      'label_source',
      'tidy_label_review_basis',
      'field_report_ref',
      'avalanche_atlas_ref',
      'leakage_check',
      'acceptance_floors',
    ]));
  });

  it('fails closed when the source manifest is missing', async () => {
    const summary = await buildPartnerEvidenceReadinessSummary(packageFiles({ reviewed: true }).slice(1));

    expect(summary.decision).toBe('blocked_required_partner_files_missing');
    expect(summary.production_scoring_allowed).toBe(false);
    expect(summary.himalayan_accuracy_claim_allowed).toBe(false);
    expect(summary.blockers.some((blocker) => blocker.includes(PARTNER_SOURCE_MANIFEST_FILENAME))).toBe(true);
  });

  it('rejects exact-header mismatches', async () => {
    const summary = await buildPartnerEvidenceReadinessSummary(packageFiles({
      reviewed: true,
      headerMismatchKey: 'station_metadata',
    }));

    expect(summary.decision).toBe('blocked_partner_schema_mismatch');
    expect(summary.files.find((file) => file.filename === 'station_metadata.csv')?.status).toBe('header_mismatch');
  });

  it('blocks synthetic package markers', async () => {
    const summary = await buildPartnerEvidenceReadinessSummary(packageFiles({
      reviewed: true,
      syntheticKey: 'danger_labels_and_bulletins',
    }));

    expect(summary.decision).toBe('blocked_synthetic_package_detected');
    expect(summary.synthetic_marker_detected).toBe(true);
  });

  it('keeps blank templates blocked from accuracy claims', async () => {
    const summary = await buildPartnerEvidenceReadinessSummary(packageFiles({ empty: true }));

    expect(summary.decision).toBe('blocked_no_reviewed_partner_rows');
    expect(summary.total_row_count).toBe(0);
    expect(summary.reviewed_row_count).toBe(0);
  });

  it('marks reviewed package files ready for later CLI triage while preserving claim locks', async () => {
    const summary = await buildPartnerEvidenceReadinessSummary(packageFiles({ reviewed: true }));
    const markdown = markdownPartnerEvidenceReadinessSummary(summary);

    expect(summary.decision).toBe('partner_intake_preflight_ready_for_cli_triage');
    expect(summary.reviewed_row_count).toBe(REQUIRED_PARTNER_EVIDENCE_FILES.length);
    expect(summary.files.every((file) => file.sha256 == null || /^[a-f0-9]{64}$/.test(file.sha256))).toBe(true);
    expect(markdown).toContain('production_scoring_allowed=false');
    expect(markdown).toContain('himalayan_accuracy_claim_allowed=false');
  });
});
