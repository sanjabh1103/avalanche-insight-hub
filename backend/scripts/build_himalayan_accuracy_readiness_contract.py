from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from backend.reproduction.himalayan_accuracy_contract import (
    STATUS_AVAILABLE,
    STATUS_NOT_APPLICABLE,
    build_himalayan_local_holdout_leakage_audit,
    build_himalayan_local_holdout_metric_report,
    build_himalayan_local_holdout_prediction_template,
    build_himalayan_local_holdout_protocol,
    build_himalayan_top10_feature_gap_matrix,
    build_partner_evidence_intake_checklist,
    build_partner_field_dictionary,
    build_partner_handoff_readme,
    build_partner_incoming_triage_runbook,
    build_partner_intake_dry_run_runbook,
    build_partner_package_index,
    build_partner_sample_row_pack,
    build_partner_source_package_checksum_guide,
    build_partner_source_manifest_starter,
    build_partner_submission_manifest_diff,
    build_partner_submission_review_ledger,
    build_partner_submission_status_dashboard,
    build_partner_submission_acceptance_checklist,
    build_partner_submission_quality_score,
    build_partner_submission_status_summary,
    build_release_gate_attestation_template_pack,
    markdown_partner_synthetic_validation_package,
    load_not_applicable_waivers,
    load_partner_source_manifest,
    load_release_gate_attestations,
    load_status_overrides,
    markdown_himalayan_top10_feature_gap_matrix,
    markdown_himalayan_local_holdout_leakage_audit,
    markdown_himalayan_local_holdout_metric_report,
    markdown_himalayan_local_holdout_prediction_template,
    markdown_himalayan_local_holdout_protocol,
    markdown_contract,
    markdown_partner_evidence_intake_checklist,
    markdown_partner_evidence_validation,
    markdown_partner_field_dictionary,
    markdown_partner_handoff_readme,
    markdown_partner_incoming_triage_runbook,
    markdown_partner_intake_dry_run_runbook,
    markdown_partner_intake_package_preflight,
    markdown_partner_package_index,
    markdown_partner_sample_row_pack,
    markdown_partner_source_package_checksum_guide,
    markdown_partner_submission_manifest_diff,
    markdown_partner_submission_review_ledger,
    markdown_partner_submission_status_dashboard,
    markdown_partner_source_manifest_starter,
    markdown_partner_submission_acceptance_checklist,
    markdown_partner_submission_quality_score,
    markdown_partner_submission_status_summary,
    markdown_partner_source_manifest_validation,
    markdown_release_gate_attestation_template_pack,
    validate_partner_intake_package_preflight,
    validate_partner_evidence_root,
    validate_partner_source_manifest,
    write_partner_synthetic_validation_package,
    write_partner_evidence_templates,
    write_himalayan_local_holdout_prediction_template_csv,
    write_contract,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Build a research-only Himalayan avalanche accuracy readiness contract.'
    )
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--output-markdown', type=Path)
    parser.add_argument(
        '--status-overrides',
        type=Path,
        help='Optional JSON object mapping requirement key to available, partner_required, or not_applicable.',
    )
    parser.add_argument(
        '--not-applicable-waivers',
        type=Path,
        help='Optional JSON object with approved_by, reason, evidence_ref, and reviewed_at for each not_applicable override.',
    )
    parser.add_argument(
        '--release-gate-attestations',
        type=Path,
        help='Optional JSON object with approved_by, summary, evidence_ref, and reviewed_at for each completed release gate.',
    )
    parser.add_argument(
        '--release-gate-attestation-template-pack-output',
        type=Path,
        help='Optional JSON output path for fillable release-gate attestation templates.',
    )
    parser.add_argument(
        '--release-gate-attestation-template-pack-markdown',
        type=Path,
        help='Optional Markdown output path for fillable release-gate attestation templates.',
    )
    parser.add_argument(
        '--templates-output-root',
        type=Path,
        help='Optional directory for partner evidence CSV templates and template manifest.',
    )
    parser.add_argument(
        '--top10-feature-gap-matrix-output',
        type=Path,
        help='Optional JSON output path for the Himalayan top-10 feature gap matrix.',
    )
    parser.add_argument(
        '--top10-feature-gap-matrix-markdown',
        type=Path,
        help='Optional Markdown output path for the Himalayan top-10 feature gap matrix.',
    )
    parser.add_argument(
        '--local-holdout-protocol-output',
        type=Path,
        help='Optional JSON output path for the pre-registered Himalayan local holdout protocol.',
    )
    parser.add_argument(
        '--local-holdout-protocol-markdown',
        type=Path,
        help='Optional Markdown output path for the pre-registered Himalayan local holdout protocol.',
    )
    parser.add_argument(
        '--local-holdout-leakage-audit-output',
        type=Path,
        help='Optional JSON output path for the Himalayan local holdout leakage audit.',
    )
    parser.add_argument(
        '--local-holdout-leakage-audit-markdown',
        type=Path,
        help='Optional Markdown output path for the Himalayan local holdout leakage audit.',
    )
    parser.add_argument(
        '--local-holdout-metric-report-output',
        type=Path,
        help='Optional JSON output path for the Himalayan local holdout metric report.',
    )
    parser.add_argument(
        '--local-holdout-metric-report-markdown',
        type=Path,
        help='Optional Markdown output path for the Himalayan local holdout metric report.',
    )
    parser.add_argument(
        '--local-holdout-prediction-template-output',
        type=Path,
        help='Optional JSON output path for the Himalayan local holdout prediction template.',
    )
    parser.add_argument(
        '--local-holdout-prediction-template-markdown',
        type=Path,
        help='Optional Markdown output path for the Himalayan local holdout prediction template.',
    )
    parser.add_argument(
        '--local-holdout-prediction-template-csv',
        type=Path,
        help='Optional CSV output path for the header-only Himalayan local holdout prediction template.',
    )
    parser.add_argument(
        '--local-holdout-predictions',
        type=Path,
        help='Optional CSV containing independent holdout predictions and class probabilities.',
    )
    parser.add_argument(
        '--partner-evidence-root',
        type=Path,
        help='Optional directory containing filled partner evidence CSVs to validate and derive readiness statuses.',
    )
    parser.add_argument(
        '--partner-intake-root',
        type=Path,
        help='Optional directory containing a partner intake package to preflight before deeper CSV validation.',
    )
    parser.add_argument(
        '--partner-source-manifest',
        type=Path,
        help='Optional JSON source manifest mapping source_ref SHA-256 values to owner/license/review metadata.',
    )
    parser.add_argument(
        '--partner-evidence-validation-output',
        type=Path,
        help='Optional JSON output path for partner evidence validation details.',
    )
    parser.add_argument(
        '--partner-evidence-validation-markdown',
        type=Path,
        help='Optional Markdown output path for partner evidence validation details.',
    )
    parser.add_argument(
        '--partner-source-manifest-validation-output',
        type=Path,
        help='Optional JSON output path for standalone partner source manifest validation details.',
    )
    parser.add_argument(
        '--partner-source-manifest-validation-markdown',
        type=Path,
        help='Optional Markdown output path for standalone partner source manifest validation details.',
    )
    parser.add_argument(
        '--partner-source-manifest-starter-output',
        type=Path,
        help='Optional JSON output path for a fillable source manifest starter generated from evidence CSV source_ref values.',
    )
    parser.add_argument(
        '--partner-source-manifest-starter-markdown',
        type=Path,
        help='Optional Markdown output path for the source manifest starter generated from evidence CSV source_ref values.',
    )
    parser.add_argument(
        '--partner-intake-checklist-output',
        type=Path,
        help='Optional JSON output path for the partner evidence package intake checklist.',
    )
    parser.add_argument(
        '--partner-intake-checklist-markdown',
        type=Path,
        help='Optional Markdown output path for the partner evidence package intake checklist.',
    )
    parser.add_argument(
        '--partner-intake-preflight-output',
        type=Path,
        help='Optional JSON output path for required partner intake package file preflight.',
    )
    parser.add_argument(
        '--partner-intake-preflight-markdown',
        type=Path,
        help='Optional Markdown output path for required partner intake package file preflight.',
    )
    parser.add_argument(
        '--partner-intake-dry-run-runbook-output',
        type=Path,
        help='Optional JSON output path for the partner intake dry-run runbook.',
    )
    parser.add_argument(
        '--partner-intake-dry-run-runbook-markdown',
        type=Path,
        help='Optional Markdown output path for the partner intake dry-run runbook.',
    )
    parser.add_argument(
        '--partner-incoming-triage-runbook-output',
        type=Path,
        help='Optional JSON output path for the incoming partner package triage runbook.',
    )
    parser.add_argument(
        '--partner-incoming-triage-runbook-markdown',
        type=Path,
        help='Optional Markdown output path for the incoming partner package triage runbook.',
    )
    parser.add_argument(
        '--partner-submission-summary-output',
        type=Path,
        help='Optional JSON output path for combined partner submission status.',
    )
    parser.add_argument(
        '--partner-submission-summary-markdown',
        type=Path,
        help='Optional Markdown output path for combined partner submission status.',
    )
    parser.add_argument(
        '--partner-submission-quality-score-output',
        type=Path,
        help='Optional JSON output path for partner submission quality scoring.',
    )
    parser.add_argument(
        '--partner-submission-quality-score-markdown',
        type=Path,
        help='Optional Markdown output path for partner submission quality scoring.',
    )
    parser.add_argument(
        '--partner-submission-acceptance-checklist-output',
        type=Path,
        help='Optional JSON output path for partner submission acceptance checklist.',
    )
    parser.add_argument(
        '--partner-submission-acceptance-checklist-markdown',
        type=Path,
        help='Optional Markdown output path for partner submission acceptance checklist.',
    )
    parser.add_argument(
        '--partner-submission-manifest-diff-output',
        type=Path,
        help='Optional JSON output path for partner submission manifest diff.',
    )
    parser.add_argument(
        '--partner-submission-manifest-diff-markdown',
        type=Path,
        help='Optional Markdown output path for partner submission manifest diff.',
    )
    parser.add_argument(
        '--partner-submission-manifest-diff-previous',
        type=Path,
        help='Optional previous manifest diff or snapshot JSON to compare against.',
    )
    parser.add_argument(
        '--partner-submission-review-ledger-output',
        type=Path,
        help='Optional JSON output path for partner submission/resubmission review ledger.',
    )
    parser.add_argument(
        '--partner-submission-review-ledger-markdown',
        type=Path,
        help='Optional Markdown output path for partner submission/resubmission review ledger.',
    )
    parser.add_argument(
        '--partner-submission-review-ledger-previous',
        type=Path,
        help='Optional previous review ledger JSON to append to.',
    )
    parser.add_argument(
        '--partner-submission-status-dashboard-output',
        type=Path,
        help='Optional JSON output path for one-page partner submission status dashboard.',
    )
    parser.add_argument(
        '--partner-submission-status-dashboard-markdown',
        type=Path,
        help='Optional Markdown output path for one-page partner submission status dashboard.',
    )
    parser.add_argument(
        '--partner-package-index-output',
        type=Path,
        help='Optional JSON output path for the partner evidence package handoff index.',
    )
    parser.add_argument(
        '--partner-package-index-markdown',
        type=Path,
        help='Optional Markdown output path for the partner evidence package handoff index.',
    )
    parser.add_argument(
        '--partner-source-package-checksum-guide-output',
        type=Path,
        help='Optional JSON output path for the partner source package checksum guide.',
    )
    parser.add_argument(
        '--partner-source-package-checksum-guide-markdown',
        type=Path,
        help='Optional Markdown output path for the partner source package checksum guide.',
    )
    parser.add_argument(
        '--partner-field-dictionary-output',
        type=Path,
        help='Optional JSON output path for the partner evidence field dictionary.',
    )
    parser.add_argument(
        '--partner-field-dictionary-markdown',
        type=Path,
        help='Optional Markdown output path for the partner evidence field dictionary.',
    )
    parser.add_argument(
        '--partner-sample-row-pack-output',
        type=Path,
        help='Optional JSON output path for non-submit-ready partner evidence sample rows.',
    )
    parser.add_argument(
        '--partner-sample-row-pack-markdown',
        type=Path,
        help='Optional Markdown output path for non-submit-ready partner evidence sample rows.',
    )
    parser.add_argument(
        '--partner-synthetic-validation-package-root',
        type=Path,
        help='Optional output directory for a synthetic-only partner validation package smoke fixture.',
    )
    parser.add_argument(
        '--partner-synthetic-validation-report-output',
        type=Path,
        help='Optional JSON output path for the synthetic partner validation package report.',
    )
    parser.add_argument(
        '--partner-synthetic-validation-report-markdown',
        type=Path,
        help='Optional Markdown output path for the synthetic partner validation package report.',
    )
    parser.add_argument(
        '--partner-handoff-readme-output',
        type=Path,
        help='Optional JSON output path for compact partner evidence handoff README.',
    )
    parser.add_argument(
        '--partner-handoff-readme-markdown',
        type=Path,
        help='Optional Markdown output path for compact partner evidence handoff README.',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    generated_at = datetime.now(timezone.utc)
    status_overrides = load_status_overrides(args.status_overrides)
    not_applicable_waivers = load_not_applicable_waivers(args.not_applicable_waivers)
    release_gate_attestations = load_release_gate_attestations(args.release_gate_attestations)
    partner_source_manifest = load_partner_source_manifest(args.partner_source_manifest)
    partner_intake_checklist = None
    if args.partner_intake_checklist_output or args.partner_intake_checklist_markdown:
        partner_intake_checklist = build_partner_evidence_intake_checklist(generated_at=generated_at)
    partner_intake_dry_run_runbook = None
    if args.partner_intake_dry_run_runbook_output or args.partner_intake_dry_run_runbook_markdown:
        partner_intake_dry_run_runbook = build_partner_intake_dry_run_runbook(
            generated_at=generated_at,
        )
    partner_incoming_triage_runbook = None
    if args.partner_incoming_triage_runbook_output or args.partner_incoming_triage_runbook_markdown:
        partner_incoming_triage_runbook = build_partner_incoming_triage_runbook(
            generated_at=generated_at,
        )
    release_gate_attestation_template_pack = None
    if (
        args.release_gate_attestation_template_pack_output
        or args.release_gate_attestation_template_pack_markdown
    ):
        release_gate_attestation_template_pack = build_release_gate_attestation_template_pack(
            generated_at=generated_at,
        )
    partner_package_index = None
    if args.partner_package_index_output or args.partner_package_index_markdown:
        partner_package_index = build_partner_package_index(generated_at=generated_at)
    partner_field_dictionary = None
    if args.partner_field_dictionary_output or args.partner_field_dictionary_markdown:
        partner_field_dictionary = build_partner_field_dictionary(generated_at=generated_at)
    partner_sample_row_pack = None
    if args.partner_sample_row_pack_output or args.partner_sample_row_pack_markdown:
        partner_sample_row_pack = build_partner_sample_row_pack(generated_at=generated_at)
    partner_source_package_checksum_guide = None
    if (
        args.partner_source_package_checksum_guide_output
        or args.partner_source_package_checksum_guide_markdown
    ):
        partner_source_package_checksum_guide = build_partner_source_package_checksum_guide(
            generated_at=generated_at,
        )
    partner_handoff_readme_requested = bool(
        args.partner_handoff_readme_output or args.partner_handoff_readme_markdown
    )
    partner_submission_review_ledger_requested = bool(
        args.partner_submission_review_ledger_output
        or args.partner_submission_review_ledger_markdown
    )
    partner_submission_status_dashboard_requested = bool(
        args.partner_submission_status_dashboard_output
        or args.partner_submission_status_dashboard_markdown
    )
    previous_submission_review_ledger = None
    if args.partner_submission_review_ledger_previous:
        previous_submission_review_ledger = json.loads(
            args.partner_submission_review_ledger_previous.read_text(encoding='utf-8')
        )
    partner_submission_manifest_diff = None
    if (
        args.partner_submission_manifest_diff_output
        or args.partner_submission_manifest_diff_markdown
        or partner_submission_review_ledger_requested
        or partner_submission_status_dashboard_requested
    ):
        diff_root = args.partner_intake_root or args.partner_evidence_root
        if diff_root is None and (
            args.partner_submission_manifest_diff_output
            or args.partner_submission_manifest_diff_markdown
        ):
            raise ValueError(
                'partner submission manifest diff requires --partner-intake-root or --partner-evidence-root'
            )
        previous_snapshot = None
        if args.partner_submission_manifest_diff_previous:
            previous_snapshot = json.loads(
                args.partner_submission_manifest_diff_previous.read_text(encoding='utf-8')
            )
        if diff_root is not None:
            partner_submission_manifest_diff = build_partner_submission_manifest_diff(
                diff_root,
                previous_snapshot=previous_snapshot,
                generated_at=generated_at,
            )
    partner_intake_preflight = None
    if (
        args.partner_intake_root
        or args.partner_intake_preflight_output
        or args.partner_intake_preflight_markdown
        or args.partner_submission_summary_output
        or args.partner_submission_summary_markdown
        or args.partner_submission_quality_score_output
        or args.partner_submission_quality_score_markdown
        or args.partner_submission_acceptance_checklist_output
        or args.partner_submission_acceptance_checklist_markdown
        or partner_handoff_readme_requested
        or partner_submission_review_ledger_requested
        or partner_submission_status_dashboard_requested
    ):
        preflight_root = args.partner_intake_root or args.partner_evidence_root
        if preflight_root is None:
            raise ValueError(
                'partner intake preflight requires --partner-intake-root or --partner-evidence-root'
            )
        partner_intake_preflight = validate_partner_intake_package_preflight(
            preflight_root,
            generated_at=generated_at,
        )
    partner_source_manifest_validation = None
    if (
        args.partner_source_manifest
        or args.partner_source_manifest_validation_output
        or args.partner_source_manifest_validation_markdown
        or args.partner_submission_summary_output
        or args.partner_submission_summary_markdown
        or args.partner_submission_quality_score_output
        or args.partner_submission_quality_score_markdown
        or args.partner_submission_acceptance_checklist_output
        or args.partner_submission_acceptance_checklist_markdown
        or partner_handoff_readme_requested
        or partner_submission_review_ledger_requested
        or partner_submission_status_dashboard_requested
    ):
        partner_source_manifest_validation = validate_partner_source_manifest(
            partner_source_manifest,
            generated_at=generated_at,
        )
    partner_source_manifest_starter = None
    if args.partner_source_manifest_starter_output or args.partner_source_manifest_starter_markdown:
        starter_root = args.partner_evidence_root or args.partner_intake_root
        if starter_root is None:
            raise ValueError(
                'partner source manifest starter requires --partner-evidence-root or --partner-intake-root'
            )
        partner_source_manifest_starter = build_partner_source_manifest_starter(
            starter_root,
            generated_at=generated_at,
        )
    partner_evidence_validation = None
    if args.partner_evidence_root:
        partner_evidence_validation = validate_partner_evidence_root(
            args.partner_evidence_root,
            generated_at=generated_at,
            partner_source_manifest=partner_source_manifest,
        )
        evidence_statuses = dict(partner_evidence_validation['status_overrides'])
        invalid_available_overrides = [
            key
            for key, value in status_overrides.items()
            if value == STATUS_AVAILABLE and evidence_statuses.get(key) != STATUS_AVAILABLE
        ]
        if invalid_available_overrides:
            raise ValueError(
                'cannot mark Himalayan evidence available without reviewed partner evidence files: '
                f'{invalid_available_overrides}'
            )
        not_applicable_overrides = {
            key: value for key, value in status_overrides.items() if value == STATUS_NOT_APPLICABLE
        }
        status_overrides = {**evidence_statuses, **not_applicable_overrides}

    payload = write_contract(
        output_path=args.output,
        status_overrides=status_overrides,
        partner_evidence_validation=partner_evidence_validation,
        not_applicable_waivers=not_applicable_waivers,
        release_gate_attestations=release_gate_attestations,
    )
    partner_submission_summary = None
    if (
        args.partner_submission_summary_output
        or args.partner_submission_summary_markdown
        or partner_submission_review_ledger_requested
        or partner_submission_status_dashboard_requested
    ):
        partner_submission_summary = build_partner_submission_status_summary(
            generated_at=generated_at,
            intake_preflight=partner_intake_preflight,
            source_manifest_validation=partner_source_manifest_validation,
            evidence_validation=partner_evidence_validation,
            readiness_contract=payload,
        )
    partner_submission_quality_score = None
    if (
        args.partner_submission_quality_score_output
        or args.partner_submission_quality_score_markdown
        or partner_submission_review_ledger_requested
        or partner_submission_status_dashboard_requested
    ):
        partner_submission_quality_score = build_partner_submission_quality_score(
            generated_at=generated_at,
            intake_preflight=partner_intake_preflight,
            source_manifest_validation=partner_source_manifest_validation,
            evidence_validation=partner_evidence_validation,
            readiness_contract=payload,
        )
    partner_submission_acceptance_checklist = None
    if (
        args.partner_submission_acceptance_checklist_output
        or args.partner_submission_acceptance_checklist_markdown
        or partner_handoff_readme_requested
        or partner_submission_review_ledger_requested
        or partner_submission_status_dashboard_requested
    ):
        if partner_submission_quality_score is None:
            partner_submission_quality_score = build_partner_submission_quality_score(
                generated_at=generated_at,
                intake_preflight=partner_intake_preflight,
                source_manifest_validation=partner_source_manifest_validation,
                evidence_validation=partner_evidence_validation,
                readiness_contract=payload,
            )
        partner_submission_acceptance_checklist = build_partner_submission_acceptance_checklist(
            generated_at=generated_at,
            quality_score=partner_submission_quality_score,
        )
    partner_handoff_readme = None
    if partner_handoff_readme_requested:
        if partner_package_index is None:
            partner_package_index = build_partner_package_index(generated_at=generated_at)
        if partner_submission_quality_score is None:
            partner_submission_quality_score = build_partner_submission_quality_score(
                generated_at=generated_at,
                intake_preflight=partner_intake_preflight,
                source_manifest_validation=partner_source_manifest_validation,
                evidence_validation=partner_evidence_validation,
                readiness_contract=payload,
            )
        if partner_submission_acceptance_checklist is None:
            partner_submission_acceptance_checklist = build_partner_submission_acceptance_checklist(
                generated_at=generated_at,
                quality_score=partner_submission_quality_score,
            )
        if partner_submission_summary is None:
            partner_submission_summary = build_partner_submission_status_summary(
                generated_at=generated_at,
                intake_preflight=partner_intake_preflight,
                source_manifest_validation=partner_source_manifest_validation,
                evidence_validation=partner_evidence_validation,
                readiness_contract=payload,
            )
        partner_handoff_readme = build_partner_handoff_readme(
            generated_at=generated_at,
            package_index=partner_package_index,
            quality_score=partner_submission_quality_score,
            acceptance_checklist=partner_submission_acceptance_checklist,
            submission_summary=partner_submission_summary,
        )
    partner_submission_review_ledger = None
    if partner_submission_review_ledger_requested:
        ledger_root = args.partner_intake_root or args.partner_evidence_root
        partner_submission_review_ledger = build_partner_submission_review_ledger(
            generated_at=generated_at,
            package_root=ledger_root,
            previous_ledger=previous_submission_review_ledger,
            manifest_diff=partner_submission_manifest_diff,
            intake_preflight=partner_intake_preflight,
            source_manifest_validation=partner_source_manifest_validation,
            evidence_validation=partner_evidence_validation,
            readiness_contract=payload,
            quality_score=partner_submission_quality_score,
            acceptance_checklist=partner_submission_acceptance_checklist,
            submission_summary=partner_submission_summary,
        )
    partner_submission_status_dashboard = None
    if partner_submission_status_dashboard_requested:
        if partner_package_index is None:
            partner_package_index = build_partner_package_index(generated_at=generated_at)
        if partner_submission_review_ledger is None:
            ledger_root = args.partner_intake_root or args.partner_evidence_root
            partner_submission_review_ledger = build_partner_submission_review_ledger(
                generated_at=generated_at,
                package_root=ledger_root,
                previous_ledger=previous_submission_review_ledger,
                manifest_diff=partner_submission_manifest_diff,
                intake_preflight=partner_intake_preflight,
                source_manifest_validation=partner_source_manifest_validation,
                evidence_validation=partner_evidence_validation,
                readiness_contract=payload,
                quality_score=partner_submission_quality_score,
                acceptance_checklist=partner_submission_acceptance_checklist,
                submission_summary=partner_submission_summary,
            )
        top10_feature_gap_matrix_for_dashboard = build_himalayan_top10_feature_gap_matrix(
            generated_at=generated_at,
            readiness_contract=payload,
            evidence_validation=partner_evidence_validation,
        )
        partner_submission_status_dashboard = build_partner_submission_status_dashboard(
            generated_at=generated_at,
            package_index=partner_package_index,
            review_ledger=partner_submission_review_ledger,
            submission_summary=partner_submission_summary,
            quality_score=partner_submission_quality_score,
            acceptance_checklist=partner_submission_acceptance_checklist,
            top10_feature_gap_matrix=top10_feature_gap_matrix_for_dashboard,
            readiness_contract=payload,
        )
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown_contract(payload), encoding='utf-8')
    if args.templates_output_root:
        write_partner_evidence_templates(args.templates_output_root)
    partner_synthetic_validation_report = None
    if (
        args.partner_synthetic_validation_package_root
        or args.partner_synthetic_validation_report_output
        or args.partner_synthetic_validation_report_markdown
    ):
        if args.partner_synthetic_validation_package_root is None:
            raise ValueError(
                'partner synthetic validation report requires --partner-synthetic-validation-package-root'
            )
        partner_synthetic_validation_report = write_partner_synthetic_validation_package(
            args.partner_synthetic_validation_package_root,
            generated_at=generated_at,
        )
    if partner_evidence_validation is not None and args.partner_evidence_validation_output:
        args.partner_evidence_validation_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_evidence_validation_output.write_text(
            json.dumps(partner_evidence_validation, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_evidence_validation is not None and args.partner_evidence_validation_markdown:
        args.partner_evidence_validation_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_evidence_validation_markdown.write_text(
            markdown_partner_evidence_validation(partner_evidence_validation),
            encoding='utf-8',
        )
    if partner_source_manifest_validation is not None and args.partner_source_manifest_validation_output:
        args.partner_source_manifest_validation_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_source_manifest_validation_output.write_text(
            json.dumps(partner_source_manifest_validation, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_source_manifest_validation is not None and args.partner_source_manifest_validation_markdown:
        args.partner_source_manifest_validation_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_source_manifest_validation_markdown.write_text(
            markdown_partner_source_manifest_validation(partner_source_manifest_validation),
            encoding='utf-8',
        )
    if partner_source_manifest_starter is not None and args.partner_source_manifest_starter_output:
        args.partner_source_manifest_starter_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_source_manifest_starter_output.write_text(
            json.dumps(partner_source_manifest_starter, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_source_manifest_starter is not None and args.partner_source_manifest_starter_markdown:
        args.partner_source_manifest_starter_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_source_manifest_starter_markdown.write_text(
            markdown_partner_source_manifest_starter(partner_source_manifest_starter),
            encoding='utf-8',
        )
    if partner_intake_checklist is not None and args.partner_intake_checklist_output:
        args.partner_intake_checklist_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_intake_checklist_output.write_text(
            json.dumps(partner_intake_checklist, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_intake_checklist is not None and args.partner_intake_checklist_markdown:
        args.partner_intake_checklist_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_intake_checklist_markdown.write_text(
            markdown_partner_evidence_intake_checklist(partner_intake_checklist),
            encoding='utf-8',
        )
    if partner_intake_preflight is not None and args.partner_intake_preflight_output:
        args.partner_intake_preflight_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_intake_preflight_output.write_text(
            json.dumps(partner_intake_preflight, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_intake_preflight is not None and args.partner_intake_preflight_markdown:
        args.partner_intake_preflight_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_intake_preflight_markdown.write_text(
            markdown_partner_intake_package_preflight(partner_intake_preflight),
            encoding='utf-8',
        )
    if partner_intake_dry_run_runbook is not None and args.partner_intake_dry_run_runbook_output:
        args.partner_intake_dry_run_runbook_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_intake_dry_run_runbook_output.write_text(
            json.dumps(partner_intake_dry_run_runbook, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_intake_dry_run_runbook is not None and args.partner_intake_dry_run_runbook_markdown:
        args.partner_intake_dry_run_runbook_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_intake_dry_run_runbook_markdown.write_text(
            markdown_partner_intake_dry_run_runbook(partner_intake_dry_run_runbook),
            encoding='utf-8',
        )
    if partner_incoming_triage_runbook is not None and args.partner_incoming_triage_runbook_output:
        args.partner_incoming_triage_runbook_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_incoming_triage_runbook_output.write_text(
            json.dumps(partner_incoming_triage_runbook, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_incoming_triage_runbook is not None and args.partner_incoming_triage_runbook_markdown:
        args.partner_incoming_triage_runbook_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_incoming_triage_runbook_markdown.write_text(
            markdown_partner_incoming_triage_runbook(partner_incoming_triage_runbook),
            encoding='utf-8',
        )
    if (
        release_gate_attestation_template_pack is not None
        and args.release_gate_attestation_template_pack_output
    ):
        args.release_gate_attestation_template_pack_output.parent.mkdir(parents=True, exist_ok=True)
        args.release_gate_attestation_template_pack_output.write_text(
            json.dumps(release_gate_attestation_template_pack, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if (
        release_gate_attestation_template_pack is not None
        and args.release_gate_attestation_template_pack_markdown
    ):
        args.release_gate_attestation_template_pack_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.release_gate_attestation_template_pack_markdown.write_text(
            markdown_release_gate_attestation_template_pack(release_gate_attestation_template_pack),
            encoding='utf-8',
        )
    if partner_submission_summary is not None and args.partner_submission_summary_output:
        args.partner_submission_summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_summary_output.write_text(
            json.dumps(partner_submission_summary, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_submission_summary is not None and args.partner_submission_summary_markdown:
        args.partner_submission_summary_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_summary_markdown.write_text(
            markdown_partner_submission_status_summary(partner_submission_summary),
            encoding='utf-8',
        )
    if partner_submission_quality_score is not None and args.partner_submission_quality_score_output:
        args.partner_submission_quality_score_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_quality_score_output.write_text(
            json.dumps(partner_submission_quality_score, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_submission_quality_score is not None and args.partner_submission_quality_score_markdown:
        args.partner_submission_quality_score_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_quality_score_markdown.write_text(
            markdown_partner_submission_quality_score(partner_submission_quality_score),
            encoding='utf-8',
        )
    if (
        partner_submission_acceptance_checklist is not None
        and args.partner_submission_acceptance_checklist_output
    ):
        args.partner_submission_acceptance_checklist_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_acceptance_checklist_output.write_text(
            json.dumps(partner_submission_acceptance_checklist, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if (
        partner_submission_acceptance_checklist is not None
        and args.partner_submission_acceptance_checklist_markdown
    ):
        args.partner_submission_acceptance_checklist_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_acceptance_checklist_markdown.write_text(
            markdown_partner_submission_acceptance_checklist(partner_submission_acceptance_checklist),
            encoding='utf-8',
        )
    if partner_handoff_readme is not None and args.partner_handoff_readme_output:
        args.partner_handoff_readme_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_handoff_readme_output.write_text(
            json.dumps(partner_handoff_readme, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_handoff_readme is not None and args.partner_handoff_readme_markdown:
        args.partner_handoff_readme_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_handoff_readme_markdown.write_text(
            markdown_partner_handoff_readme(partner_handoff_readme),
            encoding='utf-8',
        )
    if partner_submission_manifest_diff is not None and args.partner_submission_manifest_diff_output:
        args.partner_submission_manifest_diff_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_manifest_diff_output.write_text(
            json.dumps(partner_submission_manifest_diff, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_submission_manifest_diff is not None and args.partner_submission_manifest_diff_markdown:
        args.partner_submission_manifest_diff_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_manifest_diff_markdown.write_text(
            markdown_partner_submission_manifest_diff(partner_submission_manifest_diff),
            encoding='utf-8',
        )
    if (
        partner_submission_review_ledger is not None
        and args.partner_submission_review_ledger_output
    ):
        args.partner_submission_review_ledger_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_review_ledger_output.write_text(
            json.dumps(partner_submission_review_ledger, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if (
        partner_submission_review_ledger is not None
        and args.partner_submission_review_ledger_markdown
    ):
        args.partner_submission_review_ledger_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_review_ledger_markdown.write_text(
            markdown_partner_submission_review_ledger(partner_submission_review_ledger),
            encoding='utf-8',
        )
    if (
        partner_submission_status_dashboard is not None
        and args.partner_submission_status_dashboard_output
    ):
        args.partner_submission_status_dashboard_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_status_dashboard_output.write_text(
            json.dumps(partner_submission_status_dashboard, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if (
        partner_submission_status_dashboard is not None
        and args.partner_submission_status_dashboard_markdown
    ):
        args.partner_submission_status_dashboard_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_submission_status_dashboard_markdown.write_text(
            markdown_partner_submission_status_dashboard(partner_submission_status_dashboard),
            encoding='utf-8',
        )
    if partner_package_index is not None and args.partner_package_index_output:
        args.partner_package_index_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_package_index_output.write_text(
            json.dumps(partner_package_index, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_package_index is not None and args.partner_package_index_markdown:
        args.partner_package_index_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_package_index_markdown.write_text(
            markdown_partner_package_index(partner_package_index),
            encoding='utf-8',
        )
    if (
        partner_source_package_checksum_guide is not None
        and args.partner_source_package_checksum_guide_output
    ):
        args.partner_source_package_checksum_guide_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_source_package_checksum_guide_output.write_text(
            json.dumps(partner_source_package_checksum_guide, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if (
        partner_source_package_checksum_guide is not None
        and args.partner_source_package_checksum_guide_markdown
    ):
        args.partner_source_package_checksum_guide_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_source_package_checksum_guide_markdown.write_text(
            markdown_partner_source_package_checksum_guide(partner_source_package_checksum_guide),
            encoding='utf-8',
        )
    if args.top10_feature_gap_matrix_output or args.top10_feature_gap_matrix_markdown:
        top10_feature_gap_matrix = build_himalayan_top10_feature_gap_matrix(
            generated_at=generated_at,
            readiness_contract=payload,
            evidence_validation=partner_evidence_validation,
        )
        if args.top10_feature_gap_matrix_output:
            args.top10_feature_gap_matrix_output.parent.mkdir(parents=True, exist_ok=True)
            args.top10_feature_gap_matrix_output.write_text(
                json.dumps(top10_feature_gap_matrix, indent=2, sort_keys=True),
                encoding='utf-8',
            )
        if args.top10_feature_gap_matrix_markdown:
            args.top10_feature_gap_matrix_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.top10_feature_gap_matrix_markdown.write_text(
                markdown_himalayan_top10_feature_gap_matrix(top10_feature_gap_matrix),
                encoding='utf-8',
            )
    if args.local_holdout_protocol_output or args.local_holdout_protocol_markdown:
        local_holdout_protocol = build_himalayan_local_holdout_protocol(
            generated_at=generated_at,
        )
        if args.local_holdout_protocol_output:
            args.local_holdout_protocol_output.parent.mkdir(parents=True, exist_ok=True)
            args.local_holdout_protocol_output.write_text(
                json.dumps(local_holdout_protocol, indent=2, sort_keys=True),
                encoding='utf-8',
            )
        if args.local_holdout_protocol_markdown:
            args.local_holdout_protocol_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.local_holdout_protocol_markdown.write_text(
                markdown_himalayan_local_holdout_protocol(local_holdout_protocol),
                encoding='utf-8',
            )
    if (
        args.local_holdout_prediction_template_output
        or args.local_holdout_prediction_template_markdown
        or args.local_holdout_prediction_template_csv
    ):
        local_holdout_prediction_template = build_himalayan_local_holdout_prediction_template(
            generated_at=generated_at,
        )
        if args.local_holdout_prediction_template_output:
            args.local_holdout_prediction_template_output.parent.mkdir(parents=True, exist_ok=True)
            args.local_holdout_prediction_template_output.write_text(
                json.dumps(local_holdout_prediction_template, indent=2, sort_keys=True),
                encoding='utf-8',
            )
        if args.local_holdout_prediction_template_markdown:
            args.local_holdout_prediction_template_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.local_holdout_prediction_template_markdown.write_text(
                markdown_himalayan_local_holdout_prediction_template(
                    local_holdout_prediction_template
                ),
                encoding='utf-8',
            )
        if args.local_holdout_prediction_template_csv:
            write_himalayan_local_holdout_prediction_template_csv(
                args.local_holdout_prediction_template_csv
            )
    local_holdout_leakage_audit = None
    if args.local_holdout_leakage_audit_output or args.local_holdout_leakage_audit_markdown:
        holdout_audit_root = args.partner_evidence_root or args.partner_intake_root
        if holdout_audit_root is None:
            raise ValueError(
                'local holdout leakage audit requires --partner-evidence-root or --partner-intake-root'
            )
        local_holdout_leakage_audit = build_himalayan_local_holdout_leakage_audit(
            holdout_audit_root,
            generated_at=generated_at,
            partner_source_manifest=partner_source_manifest,
        )
        if args.local_holdout_leakage_audit_output:
            args.local_holdout_leakage_audit_output.parent.mkdir(parents=True, exist_ok=True)
            args.local_holdout_leakage_audit_output.write_text(
                json.dumps(local_holdout_leakage_audit, indent=2, sort_keys=True),
                encoding='utf-8',
            )
        if args.local_holdout_leakage_audit_markdown:
            args.local_holdout_leakage_audit_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.local_holdout_leakage_audit_markdown.write_text(
                markdown_himalayan_local_holdout_leakage_audit(local_holdout_leakage_audit),
                encoding='utf-8',
            )
    if args.local_holdout_metric_report_output or args.local_holdout_metric_report_markdown:
        holdout_metric_root = args.partner_evidence_root or args.partner_intake_root
        if holdout_metric_root is None:
            raise ValueError(
                'local holdout metric report requires --partner-evidence-root or --partner-intake-root'
            )
        if local_holdout_leakage_audit is None:
            local_holdout_leakage_audit = build_himalayan_local_holdout_leakage_audit(
                holdout_metric_root,
                generated_at=generated_at,
                partner_source_manifest=partner_source_manifest,
            )
        local_holdout_metric_report = build_himalayan_local_holdout_metric_report(
            holdout_metric_root,
            generated_at=generated_at,
            leakage_audit=local_holdout_leakage_audit,
            partner_source_manifest=partner_source_manifest,
            predictions_path=args.local_holdout_predictions,
        )
        if args.local_holdout_metric_report_output:
            args.local_holdout_metric_report_output.parent.mkdir(parents=True, exist_ok=True)
            args.local_holdout_metric_report_output.write_text(
                json.dumps(local_holdout_metric_report, indent=2, sort_keys=True),
                encoding='utf-8',
            )
        if args.local_holdout_metric_report_markdown:
            args.local_holdout_metric_report_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.local_holdout_metric_report_markdown.write_text(
                markdown_himalayan_local_holdout_metric_report(local_holdout_metric_report),
                encoding='utf-8',
            )
    if partner_field_dictionary is not None and args.partner_field_dictionary_output:
        args.partner_field_dictionary_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_field_dictionary_output.write_text(
            json.dumps(partner_field_dictionary, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_field_dictionary is not None and args.partner_field_dictionary_markdown:
        args.partner_field_dictionary_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_field_dictionary_markdown.write_text(
            markdown_partner_field_dictionary(partner_field_dictionary),
            encoding='utf-8',
        )
    if partner_sample_row_pack is not None and args.partner_sample_row_pack_output:
        args.partner_sample_row_pack_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_sample_row_pack_output.write_text(
            json.dumps(partner_sample_row_pack, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if partner_sample_row_pack is not None and args.partner_sample_row_pack_markdown:
        args.partner_sample_row_pack_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_sample_row_pack_markdown.write_text(
            markdown_partner_sample_row_pack(partner_sample_row_pack),
            encoding='utf-8',
        )
    if (
        partner_synthetic_validation_report is not None
        and args.partner_synthetic_validation_report_output
    ):
        args.partner_synthetic_validation_report_output.parent.mkdir(parents=True, exist_ok=True)
        args.partner_synthetic_validation_report_output.write_text(
            json.dumps(partner_synthetic_validation_report, indent=2, sort_keys=True),
            encoding='utf-8',
        )
    if (
        partner_synthetic_validation_report is not None
        and args.partner_synthetic_validation_report_markdown
    ):
        args.partner_synthetic_validation_report_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.partner_synthetic_validation_report_markdown.write_text(
            markdown_partner_synthetic_validation_package(partner_synthetic_validation_report),
            encoding='utf-8',
        )
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
