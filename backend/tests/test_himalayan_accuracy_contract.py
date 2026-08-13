from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.scripts.build_himalayan_accuracy_readiness_contract import main as build_himalayan_contract_main
from backend.scripts.run_himalayan_partner_package_triage import main as run_himalayan_triage_main
from backend.reproduction.himalayan_accuracy_contract import (
    DEPRECATED_SCHEMA_VERSIONS,
    HIMALAYAN_LOCAL_HOLDOUT_PROTOCOL_SCHEMA_VERSION,
    HIMALAYAN_LOCAL_HOLDOUT_ACCEPTANCE_FLOORS,
    HIMALAYAN_LOCAL_HOLDOUT_LEAKAGE_AUDIT_SCHEMA_VERSION,
    HIMALAYAN_LOCAL_HOLDOUT_METRIC_REPORT_SCHEMA_VERSION,
    HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_TEMPLATE_SCHEMA_VERSION,
    HIMALAYAN_BOUNDARY_READINESS_REPORT_SCHEMA_VERSION,
    HIMALAYAN_TOP10_FEATURE_GAP_MATRIX_SCHEMA_VERSION,
    PARTNER_INTAKE_CHECKLIST_SCHEMA_VERSION,
    PARTNER_INTAKE_PREFLIGHT_SCHEMA_VERSION,
    PARTNER_FIELD_DICTIONARY_SCHEMA_VERSION,
    PARTNER_HANDOFF_README_SCHEMA_VERSION,
    PARTNER_INCOMING_TRIAGE_RUNBOOK_SCHEMA_VERSION,
    PARTNER_PACKAGE_INDEX_SCHEMA_VERSION,
    PARTNER_INTAKE_DRY_RUN_RUNBOOK_SCHEMA_VERSION,
    PARTNER_SAMPLE_ROW_PACK_SCHEMA_VERSION,
    PARTNER_SOURCE_PACKAGE_CHECKSUM_GUIDE_SCHEMA_VERSION,
    PARTNER_SUBMISSION_ACCEPTANCE_CHECKLIST_SCHEMA_VERSION,
    PARTNER_SUBMISSION_MANIFEST_DIFF_SCHEMA_VERSION,
    PARTNER_SUBMISSION_REVIEW_LEDGER_SCHEMA_VERSION,
    PARTNER_SUBMISSION_STATUS_DASHBOARD_SCHEMA_VERSION,
    PARTNER_SUBMISSION_QUALITY_SCORE_SCHEMA_VERSION,
    PARTNER_SUBMISSION_STATUS_SCHEMA_VERSION,
    PARTNER_SYNTHETIC_VALIDATION_PACKAGE_SCHEMA_VERSION,
    PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION,
    PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION,
    PARTNER_TEMPLATE_SCHEMA_VERSION,
    REQUIRED_RELEASE_GATES,
    RELEASE_GATE_ATTESTATION_TEMPLATE_PACK_SCHEMA_VERSION,
    REQUIREMENTS,
    SCHEMA_VERSION,
    STATUS_AVAILABLE,
    STATUS_NOT_APPLICABLE,
    VALIDATION_POLICY_VERSION,
    build_himalayan_local_holdout_leakage_audit,
    build_himalayan_local_holdout_metric_report,
    build_himalayan_local_holdout_prediction_template,
    build_himalayan_local_holdout_protocol,
    build_himalayan_boundary_readiness_report,
    build_himalayan_top10_feature_gap_matrix,
    build_partner_evidence_intake_checklist,
    build_partner_evidence_template_manifest,
    build_partner_field_dictionary,
    build_partner_handoff_readme,
    build_partner_incoming_triage_runbook,
    build_partner_intake_dry_run_runbook,
    build_partner_package_index,
    build_partner_sample_row_pack,
    build_partner_source_package_checksum_guide,
    build_partner_source_manifest_starter,
    build_partner_submission_acceptance_checklist,
    build_partner_submission_manifest_diff,
    build_partner_submission_review_ledger,
    build_partner_submission_status_dashboard,
    build_partner_submission_quality_score,
    build_partner_submission_status_summary,
    build_partner_source_manifest_template,
    build_release_gate_attestation_template_pack,
    build_contract,
    load_not_applicable_waivers,
    load_partner_source_manifest,
    load_release_gate_attestations,
    load_status_overrides,
    markdown_himalayan_local_holdout_leakage_audit,
    markdown_himalayan_local_holdout_metric_report,
    markdown_himalayan_local_holdout_prediction_template,
    markdown_himalayan_local_holdout_protocol,
    markdown_himalayan_boundary_readiness_report,
    markdown_himalayan_top10_feature_gap_matrix,
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
    markdown_partner_source_manifest_starter,
    markdown_partner_submission_acceptance_checklist,
    markdown_partner_submission_manifest_diff,
    markdown_partner_submission_review_ledger,
    markdown_partner_submission_status_dashboard,
    markdown_partner_submission_quality_score,
    markdown_partner_submission_status_summary,
    markdown_partner_synthetic_validation_package,
    markdown_partner_source_manifest_validation,
    markdown_partner_source_manifest_template,
    markdown_release_gate_attestation_template_pack,
    partner_template_columns,
    validate_partner_evidence_root,
    validate_partner_intake_package_preflight,
    validate_partner_source_manifest,
    write_partner_synthetic_validation_package,
    write_partner_evidence_templates,
    write_himalayan_local_holdout_prediction_template_csv,
    write_contract,
    compute_event_ratio_bins,
    event_ratio_to_dict,
    markdown_event_ratio_report,
)


class HimalayanAccuracyContractTests(unittest.TestCase):
    def _acceptance_floors_for_gate(self, gate: str) -> dict[str, object]:
        floors: dict[str, dict[str, object]] = {
            'local_himalayan_holdout_passed': {
                'macro_f1_min': 0.70,
                'high_danger_recall_min': 0.80,
                'brier_score_max': 0.18,
                'ece_max': 0.08,
                'mean_day_accuracy_min': 0.75,
                'region_accuracy_min': 0.70,
                'leakage_check_required': True,
                'independent_holdout_required': True,
            },
            'scientist_review_complete': {
                'reviewed_case_count_min': 20,
                'reviewer_count_min': 1,
                'adjudication_completion_rate_min': 0.95,
                'unresolved_critical_issue_max': 0,
            },
            'license_clearance_complete': {
                'source_license_review_coverage_min': 1.0,
                'blocked_license_scope_count_max': 0,
                'unsupported_license_scope_count_max': 0,
            },
            'production_promotion_approved': {
                'rollback_plan_required': True,
                'monitoring_required': True,
                'human_override_required': True,
                'production_scoring_approval_required': True,
            },
        }
        return floors[gate]

    def _measured_results_for_gate(self, gate: str) -> dict[str, object]:
        floors = self._acceptance_floors_for_gate(gate)
        results: dict[str, dict[str, object]] = {
            'local_himalayan_holdout_passed': {
                **floors,
                'macro_f1_min': 0.74,
                'high_danger_recall_min': 0.84,
                'brier_score_max': 0.15,
                'ece_max': 0.05,
                'mean_day_accuracy_min': 0.79,
                'region_accuracy_min': 0.73,
            },
            'scientist_review_complete': {
                **floors,
                'reviewed_case_count_min': 24,
                'reviewer_count_min': 2,
                'adjudication_completion_rate_min': 1.0,
            },
            'license_clearance_complete': {
                **floors,
                'source_license_review_coverage_min': 1.0,
            },
            'production_promotion_approved': dict(floors),
        }
        return results[gate]

    def _release_gate_attestations(self) -> dict[str, dict[str, object]]:
        return {
            gate: {
                'approved_by': 'Dr. Release Reviewer',
                'summary': f'{gate} evidence was reviewed and accepted for claim-review gating.',
                'evidence_ref': 'sha256:' + 'a' * 64,
                'reviewed_at': '2026-05-20T12:00:00+00:00',
                'evidence_schema_version': PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION,
                'validation_policy_version': VALIDATION_POLICY_VERSION,
                'acceptance_floors_ref': 'sha256:' + 'd' * 64,
                'acceptance_floors': self._acceptance_floors_for_gate(gate),
                'measured_results': self._measured_results_for_gate(gate),
            }
            for gate in REQUIRED_RELEASE_GATES
        }

    def _partner_source_manifest(
        self,
        digests: set[str] | list[str] | tuple[str, ...] | None = None,
        *,
        reviewed_at: str = '2026-01-20T12:00:00+00:00',
        license_scope: str = 'internal_research_validation',
        review_status: str = 'reviewed',
    ) -> dict[str, object]:
        if digests is None:
            digests = {f'{idx:064x}' for idx in range(1, 40)}
        return {
            'schema_version': PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION,
            'validation_policy_version': VALIDATION_POLICY_VERSION,
            'sources': [
                {
                    'source_id': f'himalayan_source_{idx}',
                    'sha256': digest,
                    'source_owner': 'Himalayan Partner Review Team',
                    'dataset_name': f'Reviewed Himalayan source package {idx}',
                    'license_scope': license_scope,
                    'date_range': '2026-01-01/2026-02-20',
                    'review_status': review_status,
                    'reviewer_id': 'Dr. Source Reviewer',
                    'reviewed_at': reviewed_at,
                    'evidence_package_ref': 'sha256:' + 'e' * 64,
                }
                for idx, digest in enumerate(sorted(set(digests)), start=1)
            ],
        }

    def _valid_value_for_column(self, column: str, row_index: int = 0) -> str:
        day = (row_index % 20) + 1
        values = {
            'latitude': f'{31.25 + (row_index * 0.01):.4f}',
            'longitude': f'{78.12 + (row_index * 0.01):.4f}',
            'elevation_m': str(3200 + (row_index * 100)),
            'danger_level_1_to_4': str((row_index % 4) + 1),
            'confidence': '0.82',
            'stability_index': '0.64',
            'slope': str(25 + (row_index * 5)),
            'aspect': str((row_index * 30) % 360),
            'holdout_split': 'independent_holdout',
            'observed_at': f'2026-01-{day:02d}T06:00:00+00:00',
            'valid_from': f'2026-01-{day:02d}T00:00:00+00:00',
            'valid_to': f'2026-02-{day:02d}T00:00:00+00:00',
            'forecast_issue_time': f'2026-01-{day:02d}T05:30:00+00:00',
            'valid_at': f'2026-01-{day:02d}T12:00:00+00:00',
            'acquired_at': f'2026-01-{day:02d}T10:00:00+00:00',
            'reviewed_at': f'2026-01-{day:02d}T12:00:00+00:00',
            'window_center_local_time': '12:00',
            'profile_extracted_at_local_time': '12:00',
            'aggregation_window_hours': '24',
            'review_status': 'reviewed',
            'license_scope': 'internal_research_validation',
            'danger_scale_standard': 'eaws_5_level',
            'danger_level_1_to_5': str((row_index % 5) + 1),
            'station_id': f'station_id_value_{row_index % 10}',
            'region_key': f'region_key_value_{row_index % 3}',
            'region_id': f'region_id_value_{row_index % 3}',
            'region_ids': 'region_id_value_0;region_id_value_1;region_id_value_2',
            'label_source': 'tidy_reanalysis',
            'tidy_label_review_basis': 'local_nowcast_and_observer_confirmed',
            'nowcast_evidence_ref': f'nowcast_evidence_ref_value_{row_index}',
            'observer_evidence_ref': f'observer_evidence_ref_value_{row_index}',
            'forecast_cycle': 'nowcast',
            'avalanche_regime': 'dry_snow',
            'avalanche_problem': 'wind_slab',
            'critical_elevation_m': str(2800 + row_index * 25),
            'aspect_policy': 'all',
            'observed_outcome': 'avalanche_observed',
            'preprocessing_level': 'reviewed_analysis_ready',
            'quality_flag': 'reviewed_valid',
            'profile_model': 'HIM_STRAT_REVIEWED',
            'snowpack_model_version': 'reviewed_v1',
            'stability_metric_name': 'stability_index',
            'terrain_class': 'challenging',
            'verdict': 'label_valid',
            'label_quality': 'valid',
            'model_error_type': 'not_applicable',
            'field_report_ref': f'field_report_ref_value_{row_index}',
            'avalanche_atlas_ref': f'avalanche_atlas_ref_value_{row_index}',
            'source_ref': 'sha256:' + f'{row_index + 1:064x}',
        }
        return values.get(column, f'{column}_value_{row_index}')

    def _write_complete_evidence_file(
        self,
        root: Path,
        requirement_index: int = 0,
        *,
        row_count: int = 1,
        diverse: bool = True,
    ) -> Path:
        requirement = REQUIREMENTS[requirement_index]
        path = root / f'{requirement.key}.csv'
        columns = partner_template_columns(requirement)
        rows = [
            ','.join(
                str(self._valid_value_for_column(column, row_index=_idx if diverse else 0))
                for column in columns
            )
            for _idx in range(row_count)
        ]
        path.write_text(
            ','.join(columns) + '\n' + '\n'.join(rows) + '\n',
            encoding='utf-8',
        )
        return path

    def _write_complete_synthetic_partner_package(self, root: Path) -> Path:
        write_partner_evidence_templates(root)
        for idx, requirement in enumerate(REQUIREMENTS):
            row_count = requirement.minimum_rows_for_availability
            if requirement.key == 'warning_region_polygons':
                row_count = 3
            self._write_complete_evidence_file(
                root,
                requirement_index=idx,
                row_count=row_count,
            )
        source_manifest_path = root / 'partner_source_manifest.json'
        source_manifest_path.write_text(
            json.dumps(self._partner_source_manifest(), indent=2, sort_keys=True),
            encoding='utf-8',
        )
        return source_manifest_path

    def _rewrite_column(self, path: Path, column: str, value: str) -> None:
        self._rewrite_column_values(path, column, lambda _idx: value)

    def _rewrite_column_values(self, path: Path, column: str, value_for_row: object) -> None:
        rows = path.read_text(encoding='utf-8').splitlines()
        header = rows[0]
        columns = header.split(',')
        column_idx = columns.index(column)
        rewritten = []
        for idx, row in enumerate(rows[1:]):
            values = row.split(',')
            values[column_idx] = str(value_for_row(idx))
            rewritten.append(','.join(values))
        path.write_text(header + '\n' + '\n'.join(rewritten) + '\n', encoding='utf-8')

    def test_default_contract_fails_closed_for_himalayan_accuracy_claims(self) -> None:
        payload = build_contract()

        self.assertEqual(payload['schema_version'], SCHEMA_VERSION)
        self.assertEqual(payload['validation_policy_version'], VALIDATION_POLICY_VERSION)
        self.assertIn('himalayan_accuracy_readiness_contract_v1', payload['deprecated_schema_versions'])
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['decision'], 'blocked_pending_himalayan_evidence')
        self.assertEqual(len(payload['requirements']), len(REQUIREMENTS))
        self.assertEqual(set(payload['missing_requirements']), {item.key for item in REQUIREMENTS})
        self.assertEqual(set(payload['blocked_release_gates']), set(REQUIRED_RELEASE_GATES))

    def test_top10_feature_gap_matrix_tracks_evidence_and_claim_boundary(self) -> None:
        payload = build_himalayan_top10_feature_gap_matrix(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_himalayan_top10_feature_gap_matrix(payload)

        self.assertEqual(payload['schema_version'], HIMALAYAN_TOP10_FEATURE_GAP_MATRIX_SCHEMA_VERSION)
        self.assertEqual(payload['validation_policy_version'], VALIDATION_POLICY_VERSION)
        self.assertEqual(payload['feature_count'], 10)
        self.assertEqual(payload['blocked_feature_count'], 10)
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['decision'], 'top10_feature_gap_matrix_written_pending_partner_evidence')
        self.assertTrue(
            all(item['readiness_status'] == 'blocked_partner_evidence_required' for item in payload['features'])
        )
        first_feature = payload['features'][0]
        self.assertEqual(first_feature['feature'], 'D_tidy-equivalent Himalayan label provenance')
        self.assertIn('danger_labels_and_bulletins', first_feature['blocked_evidence'])
        self.assertIn('scientist_reviews', first_feature['required_evidence'])
        self.assertIn('RAvaFcast v1.0.0', {item['name'] for item in payload['external_anchors']})
        self.assertIn('Himalayan Avalanche Prediction Top-10 Feature Gap Matrix', markdown)
        self.assertIn('Production scoring allowed | `false`', markdown)

    def test_local_holdout_protocol_locks_metrics_and_claim_boundary(self) -> None:
        payload = build_himalayan_local_holdout_protocol(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_himalayan_local_holdout_protocol(payload)

        self.assertEqual(payload['schema_version'], HIMALAYAN_LOCAL_HOLDOUT_PROTOCOL_SCHEMA_VERSION)
        self.assertEqual(payload['validation_policy_version'], VALIDATION_POLICY_VERSION)
        self.assertEqual(
            payload['decision'],
            'local_himalayan_holdout_protocol_written_pending_partner_evidence',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['protocol_is_evidence'])
        self.assertEqual(payload['acceptance_floors'], HIMALAYAN_LOCAL_HOLDOUT_ACCEPTANCE_FLOORS)
        self.assertTrue(payload['split_policy']['must_be_excluded_from_training'])
        self.assertTrue(payload['split_policy']['must_be_excluded_from_threshold_selection'])
        self.assertIn('independent_himalayan_holdout.csv', payload['required_partner_inputs'])
        self.assertIn('himalayan_local_holdout_leakage_audit.json', payload['required_report_outputs'])
        metrics = {metric for group in payload['metric_groups'] for metric in group['metrics']}
        self.assertIn('macro_f1', metrics)
        self.assertIn('expected_calibration_error', metrics)
        self.assertIn('Himalayan Local Holdout Evaluation Protocol', markdown)
        self.assertIn('Acceptance Floors', markdown)

    def test_local_holdout_leakage_audit_blocks_blank_and_passes_synthetic_package(self) -> None:
        generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            blank_payload = build_himalayan_local_holdout_leakage_audit(
                root,
                generated_at=generated_at,
            )
            blank_markdown = markdown_himalayan_local_holdout_leakage_audit(blank_payload)

        self.assertEqual(
            blank_payload['schema_version'],
            HIMALAYAN_LOCAL_HOLDOUT_LEAKAGE_AUDIT_SCHEMA_VERSION,
        )
        self.assertEqual(blank_payload['decision'], 'blocked_local_holdout_leakage_audit_no_holdout_rows')
        self.assertFalse(blank_payload['production_scoring_allowed'])
        self.assertFalse(blank_payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(blank_payload['audit_is_prediction_evidence'])
        self.assertIn('Himalayan Local Holdout Leakage Audit', blank_markdown)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_synthetic_validation_package(root, generated_at=generated_at)
            source_manifest = json.loads(
                (root / 'partner_source_manifest.json').read_text(encoding='utf-8')
            )
            passed_payload = build_himalayan_local_holdout_leakage_audit(
                root,
                generated_at=generated_at,
                partner_source_manifest=source_manifest,
            )

        self.assertEqual(
            passed_payload['decision'],
            'local_holdout_leakage_audit_passed_release_gate_attestation_required',
        )
        self.assertGreater(passed_payload['holdout_row_count'], 0)
        self.assertEqual(passed_payload['source_ref_overlap_count'], 0)
        self.assertEqual(passed_payload['missing_manifest_hash_count'], 0)
        self.assertEqual(passed_payload['row_issue_count'], 0)

    def test_local_holdout_metric_report_blocks_until_leakage_and_predictions_pass(self) -> None:
        generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            blocked_payload = build_himalayan_local_holdout_metric_report(
                root,
                generated_at=generated_at,
            )
            blocked_markdown = markdown_himalayan_local_holdout_metric_report(blocked_payload)

        self.assertEqual(
            blocked_payload['schema_version'],
            HIMALAYAN_LOCAL_HOLDOUT_METRIC_REPORT_SCHEMA_VERSION,
        )
        self.assertEqual(
            blocked_payload['decision'],
            'blocked_local_holdout_metric_report_leakage_audit_not_passed',
        )
        self.assertFalse(blocked_payload['production_scoring_allowed'])
        self.assertFalse(blocked_payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(blocked_payload['metric_report_is_prediction_evidence'])
        self.assertIn('Himalayan Local Holdout Metric Report', blocked_markdown)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_synthetic_validation_package(root, generated_at=generated_at)
            source_manifest = json.loads(
                (root / 'partner_source_manifest.json').read_text(encoding='utf-8')
            )
            leakage_audit = build_himalayan_local_holdout_leakage_audit(
                root,
                generated_at=generated_at,
                partner_source_manifest=source_manifest,
            )
            missing_predictions = build_himalayan_local_holdout_metric_report(
                root,
                generated_at=generated_at,
                leakage_audit=leakage_audit,
            )
            predictions_path = root / 'himalayan_local_holdout_predictions.csv'
            predictions_path.write_text(
                '\n'.join(
                    [
                        'holdout_id,valid_at,region_id,elevation_band,true_danger_level_1_to_4,predicted_danger_level_1_to_4,probability_level_1,probability_level_2,probability_level_3,probability_level_4',
                        'holdout_id_value_0,2026-05-20T00:00:00+00:00,region_id_value_0,all,3,3,0.01,0.01,0.97,0.01',
                    ]
                )
                + '\n',
                encoding='utf-8',
            )
            passed_payload = build_himalayan_local_holdout_metric_report(
                root,
                generated_at=generated_at,
                leakage_audit=leakage_audit,
                predictions_path=predictions_path,
            )

        self.assertEqual(
            missing_predictions['decision'],
            'blocked_local_holdout_metric_report_missing_predictions',
        )
        self.assertEqual(
            passed_payload['decision'],
            'local_holdout_metrics_passed_release_gate_attestation_required',
        )
        self.assertTrue(passed_payload['metric_report_is_prediction_evidence'])
        self.assertEqual(passed_payload['prediction_row_count'], 1)
        self.assertEqual(passed_payload['metrics']['macro_f1'], 1.0)
        self.assertEqual(passed_payload['metrics']['high_danger_recall'], 1.0)
        self.assertTrue(all(item['passed'] for item in passed_payload['floor_results']))

    def test_local_holdout_prediction_template_writes_header_only_csv(self) -> None:
        generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / 'himalayan_local_holdout_predictions.csv'
            payload = build_himalayan_local_holdout_prediction_template(
                generated_at=generated_at,
            )
            markdown = markdown_himalayan_local_holdout_prediction_template(payload)
            write_himalayan_local_holdout_prediction_template_csv(csv_path)
            csv_text = csv_path.read_text(encoding='utf-8')

        self.assertEqual(
            payload['schema_version'],
            HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_TEMPLATE_SCHEMA_VERSION,
        )
        self.assertEqual(
            payload['decision'],
            'local_holdout_prediction_template_written_pending_model_outputs',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['template_is_prediction_evidence'])
        self.assertIn('probability_level_4', payload['required_columns'])
        self.assertIn('Himalayan Local Holdout Prediction Template', markdown)
        self.assertIn('holdout_id,valid_at,region_id,elevation_band', csv_text)
        self.assertEqual(len(csv_text.strip().splitlines()), 1)

    def test_all_available_still_requires_release_gates(self) -> None:
        overrides = {item.key: STATUS_AVAILABLE for item in REQUIREMENTS}

        payload = build_contract(status_overrides=overrides)

        self.assertEqual(payload['missing_requirements'], [])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(set(payload['blocked_release_gates']), set(REQUIRED_RELEASE_GATES))

    def test_all_available_and_all_release_gates_allows_review_not_production_scoring(self) -> None:
        overrides = {item.key: STATUS_AVAILABLE for item in REQUIREMENTS}
        release_gates = {gate: True for gate in REQUIRED_RELEASE_GATES}

        with self.assertRaisesRegex(ValueError, 'true release gate requires attestation'):
            build_contract(status_overrides=overrides, release_gates=release_gates)
        payload = build_contract(
            status_overrides=overrides,
            release_gates=release_gates,
            release_gate_attestations=self._release_gate_attestations(),
        )

        self.assertTrue(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertEqual(payload['decision'], 'ready_for_himalayan_accuracy_claim_review')
        self.assertEqual(set(payload['release_gate_attestations']), set(REQUIRED_RELEASE_GATES))
        self.assertEqual(
            payload['release_gate_attestations']['local_himalayan_holdout_passed']['evidence_schema_version'],
            PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION,
        )
        self.assertIn(
            'acceptance_floors_ref',
            payload['release_gate_attestations']['local_himalayan_holdout_passed'],
        )
        self.assertEqual(
            payload['release_gate_attestations']['local_himalayan_holdout_passed']['acceptance_floors']['macro_f1_min'],
            0.70,
        )
        self.assertTrue(
            payload['release_gate_attestations']['local_himalayan_holdout_passed']['acceptance_floors'][
                'leakage_check_required'
            ],
        )
        self.assertEqual(
            payload['release_gate_attestations']['local_himalayan_holdout_passed']['measured_results']['macro_f1_min'],
            0.74,
        )

    def test_release_gate_attestations_can_drive_release_gate_status(self) -> None:
        overrides = {item.key: STATUS_AVAILABLE for item in REQUIREMENTS}

        payload = build_contract(
            status_overrides=overrides,
            release_gate_attestations=self._release_gate_attestations(),
        )

        self.assertTrue(all(payload['release_gates'].values()))
        self.assertTrue(payload['himalayan_accuracy_claim_allowed'])

    def test_release_gate_attestation_validation_fails_closed(self) -> None:
        overrides = {item.key: STATUS_AVAILABLE for item in REQUIREMENTS}
        release_gates = {gate: True for gate in REQUIRED_RELEASE_GATES}

        with self.assertRaisesRegex(ValueError, 'unknown release gate'):
            build_contract(
                status_overrides=overrides,
                release_gate_attestations={'unknown_gate': self._release_gate_attestations()[REQUIRED_RELEASE_GATES[0]]},
            )
        bad_attestations = self._release_gate_attestations()
        bad_attestations[REQUIRED_RELEASE_GATES[0]] = {
            'approved_by': 'Dr. Release Reviewer',
            'summary': 'too short',
            'evidence_ref': 'sha256:' + 'b' * 64,
            'reviewed_at': '2026-01-20T12:00:00+00:00',
            'evidence_schema_version': PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION,
            'validation_policy_version': VALIDATION_POLICY_VERSION,
            'acceptance_floors_ref': 'floors',
            'acceptance_floors': self._acceptance_floors_for_gate(REQUIRED_RELEASE_GATES[0]),
            'measured_results': self._measured_results_for_gate(REQUIRED_RELEASE_GATES[0]),
        }
        with self.assertRaisesRegex(ValueError, 'invalid release gate attestation'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=bad_attestations,
            )

    def test_release_gate_attestation_requires_current_validation_artifact_and_floors(self) -> None:
        overrides = {item.key: STATUS_AVAILABLE for item in REQUIREMENTS}
        release_gates = {gate: True for gate in REQUIRED_RELEASE_GATES}
        gate = REQUIRED_RELEASE_GATES[0]

        missing_floor = self._release_gate_attestations()
        del missing_floor[gate]['acceptance_floors_ref']
        with self.assertRaisesRegex(ValueError, 'missing required attestation field'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=missing_floor,
            )

        stale_schema = self._release_gate_attestations()
        stale_schema[gate]['evidence_schema_version'] = 'himalayan_accuracy_partner_evidence_validation_v1'
        with self.assertRaisesRegex(ValueError, 'evidence_schema_version must match'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=stale_schema,
            )

        stale_policy = self._release_gate_attestations()
        stale_policy[gate]['validation_policy_version'] = 'old_policy'
        with self.assertRaisesRegex(ValueError, 'validation_policy_version must match'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=stale_policy,
            )

        unverified_ref = self._release_gate_attestations()
        unverified_ref[gate]['evidence_ref'] = 'review-note-without-digest'
        with self.assertRaisesRegex(ValueError, 'evidence_ref must include'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=unverified_ref,
            )

        unverified_floors_ref = self._release_gate_attestations()
        unverified_floors_ref[gate]['acceptance_floors_ref'] = 'floors-without-digest'
        with self.assertRaisesRegex(ValueError, 'acceptance_floors_ref must include'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=unverified_floors_ref,
            )

        stale_review = self._release_gate_attestations()
        with self.assertRaisesRegex(ValueError, 'reviewed_at is stale'):
            build_contract(
                status_overrides=overrides,
                generated_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
                release_gates=release_gates,
                release_gate_attestations=stale_review,
            )

        future_review = self._release_gate_attestations()
        with self.assertRaisesRegex(ValueError, 'reviewed_at is in the future'):
            build_contract(
                status_overrides=overrides,
                generated_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
                release_gates=release_gates,
                release_gate_attestations=future_review,
            )

    def test_release_gate_attestation_requires_structured_acceptance_floors(self) -> None:
        overrides = {item.key: STATUS_AVAILABLE for item in REQUIREMENTS}
        release_gates = {gate: True for gate in REQUIRED_RELEASE_GATES}
        gate = 'local_himalayan_holdout_passed'

        missing_structured_floors = self._release_gate_attestations()
        del missing_structured_floors[gate]['acceptance_floors']
        with self.assertRaisesRegex(ValueError, 'missing required attestation field'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=missing_structured_floors,
            )

        incomplete_floors = self._release_gate_attestations()
        del incomplete_floors[gate]['acceptance_floors']['macro_f1_min']
        with self.assertRaisesRegex(ValueError, 'missing acceptance_floors field'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=incomplete_floors,
            )

        invalid_metric_range = self._release_gate_attestations()
        invalid_metric_range[gate]['acceptance_floors']['ece_max'] = 1.5
        with self.assertRaisesRegex(ValueError, 'ece_max must be numeric'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=invalid_metric_range,
            )

        missing_leakage_check = self._release_gate_attestations()
        missing_leakage_check[gate]['acceptance_floors']['leakage_check_required'] = False
        with self.assertRaisesRegex(ValueError, 'leakage_check_required must be true'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=missing_leakage_check,
            )

    def test_release_gate_attestation_requires_measured_results_to_meet_floors(self) -> None:
        overrides = {item.key: STATUS_AVAILABLE for item in REQUIREMENTS}
        release_gates = {gate: True for gate in REQUIRED_RELEASE_GATES}
        gate = 'local_himalayan_holdout_passed'

        missing_results = self._release_gate_attestations()
        del missing_results[gate]['measured_results']
        with self.assertRaisesRegex(ValueError, 'missing required attestation field'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=missing_results,
            )

        incomplete_results = self._release_gate_attestations()
        del incomplete_results[gate]['measured_results']['high_danger_recall_min']
        with self.assertRaisesRegex(ValueError, 'missing measured_results field'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=incomplete_results,
            )

        low_macro_f1 = self._release_gate_attestations()
        low_macro_f1[gate]['measured_results']['macro_f1_min'] = 0.69
        with self.assertRaisesRegex(ValueError, 'macro_f1_min measured result must be >= acceptance floor'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=low_macro_f1,
            )

        high_brier = self._release_gate_attestations()
        high_brier[gate]['measured_results']['brier_score_max'] = 0.20
        with self.assertRaisesRegex(ValueError, 'brier_score_max measured result must be <= acceptance floor'):
            build_contract(
                status_overrides=overrides,
                release_gates=release_gates,
                release_gate_attestations=high_brier,
            )

    def test_unknown_or_invalid_override_fails_clearly(self) -> None:
        with self.assertRaisesRegex(ValueError, 'unknown Himalayan accuracy requirement'):
            build_contract(status_overrides={'unknown_key': STATUS_AVAILABLE})
        with self.assertRaisesRegex(ValueError, 'invalid Himalayan accuracy status'):
            build_contract(status_overrides={REQUIREMENTS[0].key: 'done'})

    def test_not_applicable_override_requires_governed_waiver(self) -> None:
        key = REQUIREMENTS[0].key

        with self.assertRaisesRegex(ValueError, 'not_applicable override requires waiver'):
            build_contract(status_overrides={key: STATUS_NOT_APPLICABLE})
        with self.assertRaisesRegex(ValueError, 'evidence_ref must include'):
            build_contract(
                status_overrides={key: STATUS_NOT_APPLICABLE},
                not_applicable_waivers={
                    key: {
                        'approved_by': 'Dr. Reviewer',
                        'reason': 'Station metadata is not applicable for this synthetic validation-only fixture.',
                        'evidence_ref': 'review-note-1',
                        'reviewed_at': '2026-01-20T12:00:00+00:00',
                    }
                },
            )
        with self.assertRaisesRegex(ValueError, 'reviewed_at is stale'):
            build_contract(
                generated_at=datetime(2027, 2, 1, tzinfo=timezone.utc),
                status_overrides={key: STATUS_NOT_APPLICABLE},
                not_applicable_waivers={
                    key: {
                        'approved_by': 'Dr. Reviewer',
                        'reason': 'Station metadata is not applicable for this synthetic validation-only fixture.',
                        'evidence_ref': 'sha256:' + 'c' * 64,
                        'reviewed_at': '2026-01-20T12:00:00+00:00',
                    }
                },
            )
        with self.assertRaisesRegex(ValueError, 'reviewed_at is in the future'):
            build_contract(
                generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                status_overrides={key: STATUS_NOT_APPLICABLE},
                not_applicable_waivers={
                    key: {
                        'approved_by': 'Dr. Reviewer',
                        'reason': 'Station metadata is not applicable for this synthetic validation-only fixture.',
                        'evidence_ref': 'sha256:' + 'c' * 64,
                        'reviewed_at': '2026-01-20T12:00:00+00:00',
                    }
                },
            )
        with self.assertRaisesRegex(ValueError, 'invalid not_applicable waiver'):
            build_contract(
                status_overrides={key: STATUS_NOT_APPLICABLE},
                not_applicable_waivers={
                    key: {
                        'approved_by': 'Dr. Reviewer',
                        'reason': 'too short',
                        'evidence_ref': 'sha256:' + 'c' * 64,
                        'reviewed_at': '2026-01-20T12:00:00+00:00',
                    }
                },
            )
        payload = build_contract(
            status_overrides={key: STATUS_NOT_APPLICABLE},
            not_applicable_waivers={
                key: {
                    'approved_by': 'Dr. Reviewer',
                    'reason': 'Station metadata is not applicable for this synthetic validation-only fixture.',
                    'evidence_ref': 'sha256:' + 'c' * 64,
                    'reviewed_at': '2026-01-20T12:00:00+00:00',
                }
            },
        )

        self.assertEqual(payload['requirements'][0]['current_status'], STATUS_NOT_APPLICABLE)
        self.assertEqual(payload['not_applicable_waivers'][key]['approved_by'], 'Dr. Reviewer')
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])

    def test_contract_writer_and_markdown_are_research_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'contract.json'
            payload = write_contract(output_path=output)
            markdown = markdown_contract(payload)
            loaded = json.loads(output.read_text(encoding='utf-8'))

        self.assertEqual(loaded['usage_boundary'], 'research_validation_only')
        self.assertIn('Himalayan accuracy claim allowed', markdown)
        self.assertIn('station_metadata', markdown)

    def test_status_override_loader_requires_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            good = root / 'good.json'
            good.write_text(json.dumps({REQUIREMENTS[0].key: STATUS_AVAILABLE}), encoding='utf-8')
            bad = root / 'bad.json'
            bad.write_text(json.dumps([REQUIREMENTS[0].key]), encoding='utf-8')

            self.assertEqual(load_status_overrides(good), {REQUIREMENTS[0].key: STATUS_AVAILABLE})
            with self.assertRaisesRegex(ValueError, 'must be a JSON object'):
                load_status_overrides(bad)

    def test_not_applicable_waiver_loader_requires_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            good = root / 'waivers.json'
            good.write_text(
                json.dumps(
                    {
                        REQUIREMENTS[0].key: {
                            'approved_by': 'Dr. Reviewer',
                            'reason': 'Station metadata is not applicable for this synthetic validation-only fixture.',
                            'evidence_ref': 'sha256:' + 'c' * 64,
                            'reviewed_at': '2026-01-20T12:00:00+00:00',
                        }
                    }
                ),
                encoding='utf-8',
            )
            bad = root / 'bad.json'
            bad.write_text(json.dumps([REQUIREMENTS[0].key]), encoding='utf-8')

            self.assertIn(REQUIREMENTS[0].key, load_not_applicable_waivers(good))
            with self.assertRaisesRegex(ValueError, 'waivers must be a JSON object'):
                load_not_applicable_waivers(bad)

    def test_release_gate_attestation_loader_requires_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            good = root / 'release_gates.json'
            good.write_text(json.dumps(self._release_gate_attestations()), encoding='utf-8')
            bad = root / 'bad.json'
            bad.write_text(json.dumps(REQUIRED_RELEASE_GATES), encoding='utf-8')

            self.assertEqual(set(load_release_gate_attestations(good)), set(REQUIRED_RELEASE_GATES))
            with self.assertRaisesRegex(ValueError, 'attestations must be a JSON object'):
                load_release_gate_attestations(bad)

    def test_partner_source_manifest_loader_and_validator_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            good = root / 'source_manifest.json'
            good.write_text(json.dumps(self._partner_source_manifest({'1' * 64})), encoding='utf-8')
            bad = root / 'bad.json'
            bad.write_text(json.dumps(['not', 'object']), encoding='utf-8')

            loaded = load_partner_source_manifest(good)
            payload = validate_partner_source_manifest(
                loaded,
                generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            )
            missing_payload = validate_partner_source_manifest(
                None,
                generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            )

            self.assertEqual(payload['schema_version'], PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION)
            self.assertEqual(payload['decision'], 'partner_source_manifest_available')
            self.assertEqual(payload['valid_source_hashes'], ['1' * 64])
            self.assertEqual(missing_payload['decision'], 'partner_source_manifest_not_supplied')
            with self.assertRaisesRegex(ValueError, 'source manifest must be a JSON object'):
                load_partner_source_manifest(bad)

    def test_partner_source_manifest_rejects_stale_unlicensed_unreviewed_or_duplicate_sources(self) -> None:
        stale = self._partner_source_manifest({'1' * 64}, reviewed_at='2025-01-01T00:00:00+00:00')
        stale_payload = validate_partner_source_manifest(
            stale,
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        unlicensed = self._partner_source_manifest({'2' * 64}, license_scope='pending_license_review')
        unlicensed_payload = validate_partner_source_manifest(
            unlicensed,
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        unreviewed = self._partner_source_manifest({'3' * 64}, review_status='pending')
        unreviewed_payload = validate_partner_source_manifest(
            unreviewed,
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        duplicate = self._partner_source_manifest({'4' * 64})
        duplicate['sources'].append(dict(duplicate['sources'][0]))
        duplicate_payload = validate_partner_source_manifest(
            duplicate,
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )

        self.assertEqual(stale_payload['decision'], 'blocked_invalid_partner_source_manifest')
        self.assertIn('stale', stale_payload['invalid_source_examples'][0]['error'])
        self.assertEqual(unlicensed_payload['decision'], 'blocked_invalid_partner_source_manifest')
        self.assertIn('license_scope', unlicensed_payload['invalid_source_examples'][0]['error'])
        self.assertEqual(unreviewed_payload['decision'], 'blocked_invalid_partner_source_manifest')
        self.assertIn('review_status', unreviewed_payload['invalid_source_examples'][0]['error'])
        self.assertEqual(duplicate_payload['decision'], 'blocked_invalid_partner_source_manifest')
        self.assertEqual(duplicate_payload['duplicate_source_hashes'], ['4' * 64])

    def test_partner_source_manifest_template_documents_required_provider_fields(self) -> None:
        payload = build_partner_source_manifest_template(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_partner_source_manifest_template(payload)

        self.assertEqual(payload['schema_version'], PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(payload['validation_policy_version'], VALIDATION_POLICY_VERSION)
        self.assertEqual(payload['decision'], 'source_manifest_template_written_pending_partner_sources')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['max_review_age_days'], 365.0)
        self.assertIn('sha256', payload['required_source_fields'])
        self.assertIn('source_owner', payload['required_source_fields'])
        self.assertIn('evidence_package_ref', payload['required_source_fields'])
        self.assertEqual(payload['sources'], [])
        self.assertIn('partner_source_package_001', payload['example_source']['source_id'])
        self.assertIn('internal_research_validation', payload['allowed_license_scopes_for_research_validation'])
        self.assertIn('Every `source_ref`', markdown)
        self.assertIn('Maximum source-review age', markdown)

    def test_partner_source_manifest_validation_markdown_is_standalone_and_fail_closed(self) -> None:
        payload = validate_partner_source_manifest(
            None,
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_partner_source_manifest_validation(payload)

        self.assertEqual(payload['decision'], 'partner_source_manifest_not_supplied')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Himalayan Partner Source Manifest Validation', markdown)
        self.assertIn('partner_source_manifest_not_supplied', markdown)
        self.assertIn('Source count', markdown)
        self.assertIn('Invalid Source Examples', markdown)

    def test_partner_source_manifest_starter_extracts_source_refs_but_stays_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_requirement = REQUIREMENTS[0]
            self._write_complete_evidence_file(
                root,
                requirement_index=0,
                row_count=station_requirement.minimum_rows_for_availability,
            )
            payload = build_partner_source_manifest_starter(
                root,
                generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            )
            markdown = markdown_partner_source_manifest_starter(payload)
            validation = validate_partner_source_manifest(
                payload,
                generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            )

        self.assertEqual(payload['schema_version'], PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(payload['validation_policy_version'], VALIDATION_POLICY_VERSION)
        self.assertEqual(payload['decision'], 'source_manifest_starter_written_pending_source_review')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['source_ref_digest_count'], station_requirement.minimum_rows_for_availability)
        self.assertIn('weather_station_observations.csv', payload['scanned_files'])
        self.assertEqual(payload['missing_evidence_files'], [])
        self.assertEqual(payload['sources'][0]['review_status'], 'pending')
        self.assertEqual(payload['sources'][0]['license_scope'], 'pending_license_review')
        self.assertEqual(payload['sources'][0]['source_owner'], '')
        self.assertEqual(validation['decision'], 'blocked_invalid_partner_source_manifest')
        self.assertIn('missing required source field', validation['invalid_source_examples'][0]['error'])
        self.assertIn('Himalayan Partner Source Manifest Starter', markdown)
        self.assertIn('intentionally pending', markdown)

    def test_partner_intake_checklist_maps_package_files_and_claim_boundary(self) -> None:
        payload = build_partner_evidence_intake_checklist(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_partner_evidence_intake_checklist(payload)
        package_paths = {item['path'] for item in payload['required_package_files']}

        self.assertEqual(payload['schema_version'], PARTNER_INTAKE_CHECKLIST_SCHEMA_VERSION)
        self.assertEqual(payload['validation_policy_version'], VALIDATION_POLICY_VERSION)
        self.assertEqual(payload['decision'], 'partner_intake_checklist_written_pending_partner_submission')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('partner_source_manifest.json', package_paths)
        self.assertIn('station_metadata.csv', package_paths)
        self.assertIn('independent_himalayan_holdout.csv', package_paths)
        self.assertEqual(len(package_paths), len(REQUIREMENTS) + 1)
        self.assertTrue(payload['package_rules']['source_manifest_required'])
        self.assertIn('partner_evidence_validation.json', payload['validation_outputs'])
        self.assertIn('readiness_contract.json', payload['validation_outputs'])
        self.assertIn('Himalayan Partner Evidence Intake Checklist', markdown)
        self.assertIn('Production scoring allowed', markdown)

    def test_partner_field_dictionary_preserves_five_level_danger_semantics(self) -> None:
        payload = build_partner_field_dictionary(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_partner_field_dictionary(payload)
        fields = {item['column']: item for item in payload['field_definitions']}

        self.assertEqual(payload['schema_version'], PARTNER_FIELD_DICTIONARY_SCHEMA_VERSION)
        self.assertEqual(payload['validation_policy_version'], VALIDATION_POLICY_VERSION)
        self.assertEqual(payload['decision'], 'partner_field_dictionary_written_pending_partner_submission')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('danger_level_1_to_5', fields)
        self.assertIn('danger_level_1_to_4', fields)
        self.assertEqual(fields['danger_level_1_to_5']['expected_format'], 'integer from 1 to 5')
        self.assertIn('eaws_5_level', fields['danger_scale_standard']['controlled_values'])
        self.assertIn('EAWS avalanche danger scale', payload['standards_anchors'][0]['name'])
        self.assertIn('Himalayan Partner Evidence Field Dictionary', markdown)
        self.assertIn('danger_level_1_to_5', markdown)

    def test_partner_package_index_links_artifacts_and_claim_boundary(self) -> None:
        payload = build_partner_package_index(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_partner_package_index(payload)

        self.assertEqual(payload['schema_version'], PARTNER_PACKAGE_INDEX_SCHEMA_VERSION)
        self.assertEqual(payload['validation_policy_version'], VALIDATION_POLICY_VERSION)
        self.assertEqual(payload['decision'], 'partner_package_index_written_pending_partner_submission')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        artifacts = {item['artifact'] for item in payload['artifact_sequence']}
        self.assertIn('partner_field_dictionary.md', artifacts)
        self.assertIn('partner_sample_row_pack.md', artifacts)
        self.assertIn('partner_source_package_checksum_guide.md', artifacts)
        self.assertIn('partner_synthetic_validation_report.md', artifacts)
        self.assertIn('partner_intake_dry_run_runbook.md', artifacts)
        self.assertIn('partner_incoming_triage_runbook.md', artifacts)
        self.assertIn('release_gate_attestation_template_pack.md', artifacts)
        self.assertIn('partner_submission_review_ledger.md', artifacts)
        self.assertIn('partner_submission_status_dashboard.md', artifacts)
        self.assertIn('himalayan_local_holdout_leakage_audit.md', artifacts)
        self.assertIn('himalayan_local_holdout_prediction_template.md', artifacts)
        self.assertIn('himalayan_local_holdout_metric_report.md', artifacts)
        self.assertIn('partner_intake_checklist.md', artifacts)
        self.assertIn('partner_submission_summary.md', artifacts)
        self.assertIn('readiness_contract.md', artifacts)
        required_files = {item['path'] for item in payload['required_partner_files']}
        self.assertIn('partner_source_manifest.json', required_files)
        self.assertIn('station_metadata.csv', required_files)
        self.assertIn('independent_himalayan_holdout.csv', required_files)
        self.assertIn('Himalayan Partner Evidence Package Index', markdown)
        self.assertIn('Artifact Sequence', markdown)
        self.assertIn('production scoring', markdown.lower())

    def test_partner_submission_review_ledger_records_submission_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
            manifest_diff = build_partner_submission_manifest_diff(
                root,
                generated_at=generated_at,
            )
            intake_preflight = validate_partner_intake_package_preflight(
                root,
                generated_at=generated_at,
            )
            evidence_validation = validate_partner_evidence_root(
                root,
                generated_at=generated_at,
            )
            readiness_contract = build_contract(generated_at=generated_at)
            payload = build_partner_submission_review_ledger(
                generated_at=generated_at,
                package_root=root,
                manifest_diff=manifest_diff,
                intake_preflight=intake_preflight,
                evidence_validation=evidence_validation,
                readiness_contract=readiness_contract,
            )
            appended = build_partner_submission_review_ledger(
                generated_at=generated_at,
                package_root=root,
                previous_ledger=payload,
                manifest_diff=manifest_diff,
                intake_preflight=intake_preflight,
                evidence_validation=evidence_validation,
                readiness_contract=readiness_contract,
            )
            markdown = markdown_partner_submission_review_ledger(payload)

        self.assertEqual(payload['schema_version'], PARTNER_SUBMISSION_REVIEW_LEDGER_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_submission_review_ledger_updated_blocked')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['ledger_is_prediction_evidence'])
        self.assertEqual(payload['submission_count'], 1)
        self.assertEqual(appended['submission_count'], 2)
        self.assertEqual(payload['entries'][0]['package_root'], str(root))
        self.assertEqual(payload['entries'][0]['package_fingerprint'], manifest_diff['current_package_fingerprint'])
        self.assertEqual(payload['entries'][0]['first_blocker'], 'intake_preflight')
        self.assertIn('Himalayan Partner Submission Review Ledger', markdown)
        self.assertIn('governance trace', markdown)

    def test_partner_submission_status_dashboard_summarizes_current_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
            manifest_diff = build_partner_submission_manifest_diff(
                root,
                generated_at=generated_at,
            )
            intake_preflight = validate_partner_intake_package_preflight(
                root,
                generated_at=generated_at,
            )
            evidence_validation = validate_partner_evidence_root(
                root,
                generated_at=generated_at,
            )
            readiness_contract = build_contract(generated_at=generated_at)
            quality_score = build_partner_submission_quality_score(
                generated_at=generated_at,
                intake_preflight=intake_preflight,
                evidence_validation=evidence_validation,
                readiness_contract=readiness_contract,
            )
            acceptance_checklist = build_partner_submission_acceptance_checklist(
                generated_at=generated_at,
                quality_score=quality_score,
            )
            summary = build_partner_submission_status_summary(
                generated_at=generated_at,
                intake_preflight=intake_preflight,
                evidence_validation=evidence_validation,
                readiness_contract=readiness_contract,
            )
            ledger = build_partner_submission_review_ledger(
                generated_at=generated_at,
                package_root=root,
                manifest_diff=manifest_diff,
                intake_preflight=intake_preflight,
                evidence_validation=evidence_validation,
                readiness_contract=readiness_contract,
                quality_score=quality_score,
                acceptance_checklist=acceptance_checklist,
                submission_summary=summary,
            )
            top10_matrix = build_himalayan_top10_feature_gap_matrix(
                generated_at=generated_at,
                readiness_contract=readiness_contract,
                evidence_validation=evidence_validation,
            )
            payload = build_partner_submission_status_dashboard(
                generated_at=generated_at,
                review_ledger=ledger,
                submission_summary=summary,
                quality_score=quality_score,
                acceptance_checklist=acceptance_checklist,
                top10_feature_gap_matrix=top10_matrix,
                readiness_contract=readiness_contract,
            )
            markdown = markdown_partner_submission_status_dashboard(payload)

        self.assertEqual(
            payload['schema_version'],
            PARTNER_SUBMISSION_STATUS_DASHBOARD_SCHEMA_VERSION,
        )
        self.assertEqual(
            payload['decision'],
            'partner_submission_status_dashboard_blocked_partner_action_required',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['dashboard_is_prediction_evidence'])
        self.assertEqual(payload['current_status']['latest_first_blocker'], 'intake_preflight')
        self.assertEqual(payload['current_status']['top10_blocked_feature_count'], 10)
        self.assertIn('partner_submission_review_ledger.json', {item['artifact'] for item in payload['source_artifacts']})
        self.assertIn('local_himalayan_holdout_passed', payload['release_gate_status'])
        self.assertIn('Himalayan Partner Submission Status Dashboard', markdown)
        self.assertIn('Latest blocker', markdown)

    def test_partner_source_package_checksum_guide_explains_sha256_and_claim_boundary(self) -> None:
        payload = build_partner_source_package_checksum_guide(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_partner_source_package_checksum_guide(payload)

        self.assertEqual(
            payload['schema_version'],
            PARTNER_SOURCE_PACKAGE_CHECKSUM_GUIDE_SCHEMA_VERSION,
        )
        self.assertEqual(
            payload['decision'],
            'partner_source_package_checksum_guide_written_pending_partner_sources',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('sha256', payload['required_source_manifest_fields'])
        self.assertIn('evidence_package_ref', payload['required_source_manifest_fields'])
        supported_formats = {item['format'] for item in payload['supported_reference_formats']}
        self.assertIn('sha256:<64-hex-sha256-of-source-package>', supported_formats)
        self.assertIn(
            'file:raw_sources/<source-file>#sha256=<64-hex-sha256-of-source-package>',
            supported_formats,
        )
        commands = '\n'.join(item['command'] for item in payload['checksum_commands'])
        self.assertIn('shasum -a 256', commands)
        self.assertIn('sha256sum', commands)
        self.assertIn('hashlib.sha256', commands)
        self.assertIn('Himalayan Partner Source Package Checksum Guide', markdown)
        self.assertIn('source_ref', markdown)
        self.assertIn('partner_source_manifest.json', markdown)

    def test_partner_intake_dry_run_runbook_lists_commands_and_expected_decisions(self) -> None:
        payload = build_partner_intake_dry_run_runbook(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_partner_intake_dry_run_runbook(payload)

        self.assertEqual(payload['schema_version'], PARTNER_INTAKE_DRY_RUN_RUNBOOK_SCHEMA_VERSION)
        self.assertEqual(
            payload['decision'],
            'partner_intake_dry_run_runbook_written_pending_partner_package',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('partner_source_manifest.json', payload['required_partner_files'])
        self.assertEqual(len(payload['dry_run_steps']), 5)
        step_names = {item['name'] for item in payload['dry_run_steps']}
        self.assertIn('Confirm package files', step_names)
        self.assertIn('Validate source manifest', step_names)
        self.assertIn('Validate evidence rows', step_names)
        self.assertIn('Capture manifest diff', step_names)
        commands = '\n'.join(item['command'] for item in payload['dry_run_steps'])
        self.assertIn('--partner-intake-root <partner-package-root>', commands)
        self.assertIn('--partner-source-manifest <partner-package-root>/partner_source_manifest.json', commands)
        self.assertEqual(
            payload['expected_current_template_status']['decision'],
            'blocked_missing_partner_intake_files',
        )
        self.assertIn('Himalayan Partner Intake Dry-Run Runbook', markdown)
        self.assertIn('Stop if blocked', markdown)

    def test_partner_incoming_triage_runbook_orders_first_response(self) -> None:
        payload = build_partner_incoming_triage_runbook(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_partner_incoming_triage_runbook(payload)

        self.assertEqual(payload['schema_version'], PARTNER_INCOMING_TRIAGE_RUNBOOK_SCHEMA_VERSION)
        self.assertEqual(
            payload['decision'],
            'partner_incoming_triage_runbook_written_pending_partner_package',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['runbook_is_prediction_evidence'])
        self.assertEqual(len(payload['triage_sequence']), 8)
        commands = '\n'.join(item['command'] for item in payload['triage_sequence'])
        self.assertIn('--partner-intake-root <partner-package-root>', commands)
        self.assertIn('--local-holdout-leakage-audit-output', commands)
        self.assertIn('--local-holdout-predictions <partner-package-root>/himalayan_local_holdout_predictions.csv', commands)
        routes = {item['route'] for item in payload['routing_decisions']}
        self.assertIn('return_to_partner_for_resubmission', routes)
        self.assertIn('request_frozen_candidate_predictions_using_template', routes)
        self.assertIn('Himalayan Incoming Partner Package Triage Runbook', markdown)
        self.assertIn('Stop Conditions', markdown)

    def test_release_gate_attestation_template_pack_matches_contract_requirements(self) -> None:
        payload = build_release_gate_attestation_template_pack(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_release_gate_attestation_template_pack(payload)

        self.assertEqual(
            payload['schema_version'],
            RELEASE_GATE_ATTESTATION_TEMPLATE_PACK_SCHEMA_VERSION,
        )
        self.assertEqual(
            payload['decision'],
            'release_gate_attestation_template_pack_written_pending_validated_evidence',
        )
        self.assertFalse(payload['template_is_evidence'])
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['release_gate_order'], list(REQUIRED_RELEASE_GATES))
        templates = {item['gate']: item for item in payload['templates']}
        self.assertEqual(set(templates), set(REQUIRED_RELEASE_GATES))
        holdout = templates['local_himalayan_holdout_passed']
        self.assertIn('acceptance_floors', holdout['required_fields'])
        self.assertIn('measured_results', holdout['required_fields'])
        self.assertIn('macro_f1_min', holdout['acceptance_floor_requirements']['ratio_fields'])
        self.assertEqual(
            holdout['template']['evidence_schema_version'],
            PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION,
        )
        self.assertEqual(holdout['template']['validation_policy_version'], VALIDATION_POLICY_VERSION)
        self.assertIn('NIST AI Risk Management Framework', {item['name'] for item in payload['standards_anchors']})
        self.assertIn('Himalayan Release-Gate Attestation Template Pack', markdown)

    def test_partner_synthetic_validation_package_smoke_tests_without_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / 'synthetic_package'
            payload = write_partner_synthetic_validation_package(
                root,
                generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            )
            markdown = markdown_partner_synthetic_validation_package(payload)
            source_manifest = json.loads(
                (root / 'partner_source_manifest.json').read_text(encoding='utf-8')
            )

        self.assertEqual(
            payload['schema_version'],
            PARTNER_SYNTHETIC_VALIDATION_PACKAGE_SCHEMA_VERSION,
        )
        self.assertEqual(
            payload['decision'],
            'synthetic_partner_validation_package_structurally_passed_claims_blocked',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['synthetic_data_policy']['is_real_himalayan_evidence'])
        self.assertFalse(payload['synthetic_data_policy']['may_be_submitted_as_partner_evidence'])
        self.assertEqual(payload['validation_decisions']['intake_preflight'], 'partner_intake_package_files_present')
        self.assertEqual(
            payload['validation_decisions']['source_manifest_validation'],
            'partner_source_manifest_available',
        )
        self.assertEqual(
            payload['validation_decisions']['evidence_validation'],
            'all_partner_evidence_available',
        )
        self.assertEqual(payload['validation_counts']['available_requirements'], len(REQUIREMENTS))
        self.assertEqual(payload['validation_counts']['blocked_requirements'], 0)
        self.assertEqual(payload['validation_counts']['missing_requirements'], 0)
        self.assertEqual(payload['validation_counts']['blocked_release_gates'], len(REQUIRED_RELEASE_GATES))
        self.assertEqual(len(source_manifest['sources']), len(REQUIREMENTS))
        self.assertTrue(all(item['source_ref'].startswith('file:raw_sources/') for item in payload['evidence_files']))
        self.assertIn('Synthetic Himalayan Partner Validation Package', markdown)
        self.assertIn('not a basis for a Himalayan accuracy', markdown)

    def test_partner_sample_row_pack_is_example_only_and_not_evidence(self) -> None:
        payload = build_partner_sample_row_pack(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_partner_sample_row_pack(payload)
        examples_by_key = {item['requirement_key']: item for item in payload['examples']}
        danger_example = examples_by_key['danger_labels_and_bulletins']['example_row']

        self.assertEqual(payload['schema_version'], PARTNER_SAMPLE_ROW_PACK_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_sample_row_pack_written_example_only')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['sample_rows_are_evidence'])
        self.assertFalse(payload['sample_row_policy']['write_csv_files'])
        self.assertEqual(payload['examples_count'], len(REQUIREMENTS))
        self.assertIn('<64-hex-sha256-from-partner-source-manifest>', danger_example['source_ref'])
        self.assertEqual(danger_example['danger_level_1_to_5'], '4')
        self.assertEqual(danger_example['review_status'], 'EXAMPLE_ONLY_REPLACE_WITH_REVIEWED')
        self.assertTrue(all(item['sample_only'] for item in payload['examples']))
        self.assertIn('Himalayan Partner Evidence Sample Row Pack', markdown)
        self.assertIn('Sample rows are evidence | `false`', markdown)

    def test_partner_intake_package_preflight_reports_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            (root / 'danger_labels_and_bulletins.csv').unlink()
            payload = validate_partner_intake_package_preflight(
                root,
                generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            )
            markdown = markdown_partner_intake_package_preflight(payload)

        self.assertEqual(payload['schema_version'], PARTNER_INTAKE_PREFLIGHT_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'blocked_missing_partner_intake_files')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['required_file_count'], len(REQUIREMENTS) + 1)
        self.assertIn('partner_source_manifest.json', payload['missing_files'])
        self.assertIn('danger_labels_and_bulletins.csv', payload['missing_files'])
        self.assertEqual(payload['missing_file_count'], 2)
        self.assertIn('Himalayan Partner Intake Package Preflight', markdown)
        self.assertIn('danger_labels_and_bulletins.csv', markdown)

    def test_partner_submission_status_summary_combines_validation_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_manifest_path = self._write_complete_synthetic_partner_package(root)
            generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
            intake_preflight = validate_partner_intake_package_preflight(root, generated_at=generated_at)
            source_validation = validate_partner_source_manifest(
                load_partner_source_manifest(source_manifest_path),
                generated_at=generated_at,
            )
            evidence_validation = validate_partner_evidence_root(
                root,
                generated_at=generated_at,
                partner_source_manifest=load_partner_source_manifest(source_manifest_path),
            )
            contract = build_contract(
                status_overrides=evidence_validation['status_overrides'],
                generated_at=generated_at,
                partner_evidence_validation=evidence_validation,
            )
            payload = build_partner_submission_status_summary(
                generated_at=generated_at,
                intake_preflight=intake_preflight,
                source_manifest_validation=source_validation,
                evidence_validation=evidence_validation,
                readiness_contract=contract,
            )
            markdown = markdown_partner_submission_status_summary(payload)

        self.assertEqual(payload['schema_version'], PARTNER_SUBMISSION_STATUS_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_submission_evidence_available_release_gates_pending')
        self.assertEqual(payload['first_blocker'], 'readiness_contract')
        self.assertEqual(payload['checks_passed_count'], 3)
        self.assertEqual(payload['checks_failed_count'], 1)
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Release-gated readiness contract', markdown)
        self.assertIn('release-gate attestations', markdown)

    def test_partner_submission_quality_score_grades_blank_template_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
            intake_preflight = validate_partner_intake_package_preflight(root, generated_at=generated_at)
            source_validation = validate_partner_source_manifest(None, generated_at=generated_at)
            evidence_validation = validate_partner_evidence_root(root, generated_at=generated_at)
            contract = build_contract(
                status_overrides=evidence_validation['status_overrides'],
                generated_at=generated_at,
                partner_evidence_validation=evidence_validation,
            )
            payload = build_partner_submission_quality_score(
                generated_at=generated_at,
                intake_preflight=intake_preflight,
                source_manifest_validation=source_validation,
                evidence_validation=evidence_validation,
                readiness_contract=contract,
            )
            markdown = markdown_partner_submission_quality_score(payload)

        self.assertEqual(payload['schema_version'], PARTNER_SUBMISSION_QUALITY_SCORE_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'blocked_low_partner_submission_quality')
        self.assertEqual(payload['readiness_band'], 'low_quality_or_missing')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertLess(payload['score'], 25.0)
        self.assertIn('package_file_completeness', {item['key'] for item in payload['dimensions']})
        self.assertIn('source_governance', payload['failed_dimensions'])
        self.assertIn('evidence_row_sufficiency', payload['failed_dimensions'])
        self.assertTrue(payload['quality_policy']['score_is_not_accuracy'])
        self.assertIn('Himalayan Partner Submission Quality Score', markdown)

    def test_partner_submission_quality_score_marks_evidence_ready_release_gates_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_manifest_path = self._write_complete_synthetic_partner_package(root)
            generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
            intake_preflight = validate_partner_intake_package_preflight(root, generated_at=generated_at)
            source_manifest = load_partner_source_manifest(source_manifest_path)
            source_validation = validate_partner_source_manifest(
                source_manifest,
                generated_at=generated_at,
            )
            evidence_validation = validate_partner_evidence_root(
                root,
                generated_at=generated_at,
                partner_source_manifest=source_manifest,
            )
            contract = build_contract(
                status_overrides=evidence_validation['status_overrides'],
                generated_at=generated_at,
                partner_evidence_validation=evidence_validation,
            )
            payload = build_partner_submission_quality_score(
                generated_at=generated_at,
                intake_preflight=intake_preflight,
                source_manifest_validation=source_validation,
                evidence_validation=evidence_validation,
                readiness_contract=contract,
            )

        self.assertEqual(payload['decision'], 'partner_submission_quality_evidence_ready_release_gates_pending')
        self.assertEqual(payload['readiness_band'], 'evidence_ready_release_gates_pending')
        self.assertEqual(payload['score'], 90.0)
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['failed_dimensions'], ['release_gate_readiness'])

    def test_partner_submission_acceptance_checklist_maps_quality_failures_to_fixes(self) -> None:
        quality_score = build_partner_submission_quality_score(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        payload = build_partner_submission_acceptance_checklist(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            quality_score=quality_score,
        )
        markdown = markdown_partner_submission_acceptance_checklist(payload)

        self.assertEqual(
            payload['schema_version'],
            PARTNER_SUBMISSION_ACCEPTANCE_CHECKLIST_SCHEMA_VERSION,
        )
        self.assertEqual(payload['decision'], 'blocked_acceptance_checklist_partner_fixes_required')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['scientist_review_ready'])
        self.assertFalse(payload['claim_review_ready'])
        self.assertIn('source_governance', payload['blocking_items'])
        self.assertIn('source_governance', payload['scientist_review_blockers'])
        self.assertIn('Himalayan Partner Submission Acceptance Checklist', markdown)
        self.assertIn('partner-side fixes', markdown)

    def test_partner_submission_acceptance_checklist_allows_scientist_review_when_evidence_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_manifest_path = self._write_complete_synthetic_partner_package(root)
            generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
            intake_preflight = validate_partner_intake_package_preflight(root, generated_at=generated_at)
            source_manifest = load_partner_source_manifest(source_manifest_path)
            source_validation = validate_partner_source_manifest(
                source_manifest,
                generated_at=generated_at,
            )
            evidence_validation = validate_partner_evidence_root(
                root,
                generated_at=generated_at,
                partner_source_manifest=source_manifest,
            )
            contract = build_contract(
                status_overrides=evidence_validation['status_overrides'],
                generated_at=generated_at,
                partner_evidence_validation=evidence_validation,
            )
            quality_score = build_partner_submission_quality_score(
                generated_at=generated_at,
                intake_preflight=intake_preflight,
                source_manifest_validation=source_validation,
                evidence_validation=evidence_validation,
                readiness_contract=contract,
            )
            payload = build_partner_submission_acceptance_checklist(
                generated_at=generated_at,
                quality_score=quality_score,
            )

        self.assertEqual(
            payload['decision'],
            'partner_submission_acceptance_scientist_review_ready_release_gates_pending',
        )
        self.assertTrue(payload['scientist_review_ready'])
        self.assertFalse(payload['claim_review_ready'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['scientist_review_blockers'], [])
        self.assertEqual(payload['blocking_items'], ['release_gate_readiness'])

    def test_boundary_readiness_report_defaults_to_methodology_only(self) -> None:
        payload = build_himalayan_boundary_readiness_report(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_himalayan_boundary_readiness_report(payload)

        self.assertEqual(
            payload['schema_version'],
            HIMALAYAN_BOUNDARY_READINESS_REPORT_SCHEMA_VERSION,
        )
        self.assertEqual(payload['decision'], 'boundary_readiness_blocked_methodology_evidence_only')
        self.assertEqual(payload['claim_state'], 'methodology_evidence_only')
        self.assertEqual(payload['production_state'], 'production_blocked')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('public_himalayan_route_switch', payload['explicitly_deferred_items'])
        self.assertIn('d_tidy_label_gate', payload['score4_plus_decisions_implemented'])
        self.assertTrue(payload['quality_summary']['score_is_not_accuracy'])
        self.assertIn('Himalayan Prediction Boundary Readiness Report', markdown)
        self.assertIn('D_tidy', markdown)

    def test_boundary_readiness_report_reaches_scientist_review_not_claim_review_from_evidence_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_synthetic_validation_package(
                root,
                generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            )
            source_manifest_path = root / 'partner_source_manifest.json'
            generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
            source_manifest = load_partner_source_manifest(source_manifest_path)
            intake_preflight = validate_partner_intake_package_preflight(root, generated_at=generated_at)
            source_validation = validate_partner_source_manifest(source_manifest, generated_at=generated_at)
            evidence_validation = validate_partner_evidence_root(
                root,
                generated_at=generated_at,
                partner_source_manifest=source_manifest,
            )
            readiness_contract = build_contract(
                status_overrides=evidence_validation['status_overrides'],
                generated_at=generated_at,
                partner_evidence_validation=evidence_validation,
            )
            leakage_audit = build_himalayan_local_holdout_leakage_audit(
                root,
                generated_at=generated_at,
                partner_source_manifest=source_manifest,
            )
            metric_report = build_himalayan_local_holdout_metric_report(
                root,
                generated_at=generated_at,
                leakage_audit=leakage_audit,
                partner_source_manifest=source_manifest,
            )
            quality_score = build_partner_submission_quality_score(
                generated_at=generated_at,
                intake_preflight=intake_preflight,
                source_manifest_validation=source_validation,
                evidence_validation=evidence_validation,
                readiness_contract=readiness_contract,
            )
            acceptance_checklist = build_partner_submission_acceptance_checklist(
                generated_at=generated_at,
                quality_score=quality_score,
            )
            payload = build_himalayan_boundary_readiness_report(
                generated_at=generated_at,
                intake_preflight=intake_preflight,
                source_manifest_validation=source_validation,
                evidence_validation=evidence_validation,
                readiness_contract=readiness_contract,
                leakage_audit=leakage_audit,
                metric_report=metric_report,
                quality_score=quality_score,
                acceptance_checklist=acceptance_checklist,
            )

        self.assertEqual(
            payload['decision'],
            'boundary_readiness_scientist_review_ready_release_gates_pending',
        )
        self.assertEqual(payload['claim_state'], 'scientist_review_ready')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['quality_summary']['score'], 90.0)
        gates = {item['key']: item for item in payload['gates']}
        self.assertEqual(gates['d_tidy_label_provenance']['status'], 'passed')
        self.assertEqual(gates['station_gpxyz_readiness']['status'], 'passed')
        self.assertEqual(gates['holdout_leakage_audit']['status'], 'passed')
        self.assertEqual(gates['holdout_metrics_uncertainty']['status'], 'blocked')
        self.assertEqual(gates['release_gate_attestations']['status'], 'blocked')
        self.assertEqual(
            payload['uncertainty_boundary']['calibration_status'],
            'blocked_until_local_holdout_metrics_pass',
        )
        self.assertEqual(
            payload['uncertainty_boundary']['gpxyz_uncertainty_status'],
            'station_xyz_ready_for_gpxyz_design',
        )

    def test_boundary_readiness_report_requires_d_tidy_label_corroborration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_manifest_path = self._write_complete_synthetic_partner_package(root)
            labels_path = root / 'danger_labels_and_bulletins.csv'
            self._rewrite_column(labels_path, 'label_source', 'official_forecast')
            self._rewrite_column(labels_path, 'nowcast_evidence_ref', '')
            source_manifest = load_partner_source_manifest(source_manifest_path)
            generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
            evidence_validation = validate_partner_evidence_root(
                root,
                generated_at=generated_at,
                partner_source_manifest=source_manifest,
            )
            payload = build_himalayan_boundary_readiness_report(
                generated_at=generated_at,
                evidence_validation=evidence_validation,
                readiness_contract=build_contract(
                    status_overrides=evidence_validation['status_overrides'],
                    generated_at=generated_at,
                    partner_evidence_validation=evidence_validation,
                ),
            )

        label_report = next(
            report for report in evidence_validation['reports']
            if report['requirement_key'] == 'danger_labels_and_bulletins'
        )
        gates = {item['key']: item for item in payload['gates']}
        self.assertEqual(label_report['label_provenance_gate']['status'], 'blocked')
        self.assertGreater(label_report['label_provenance_gate']['corroboration_issue_count'], 0)
        self.assertEqual(gates['d_tidy_label_provenance']['status'], 'blocked')
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Public bulletins are context only', label_report['label_provenance_gate']['claim_boundary'])

    def test_boundary_readiness_report_all_release_gates_route_to_claim_review_not_production(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_synthetic_validation_package(
                root,
                generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            )
            source_manifest_path = root / 'partner_source_manifest.json'
            generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
            source_manifest = load_partner_source_manifest(source_manifest_path)
            intake_preflight = validate_partner_intake_package_preflight(root, generated_at=generated_at)
            source_validation = validate_partner_source_manifest(source_manifest, generated_at=generated_at)
            evidence_validation = validate_partner_evidence_root(
                root,
                generated_at=generated_at,
                partner_source_manifest=source_manifest,
            )
            predictions_path = root / 'himalayan_local_holdout_predictions.csv'
            predictions_path.write_text(
                '\n'.join(
                    [
                        'holdout_id,valid_at,region_id,elevation_band,true_danger_level_1_to_4,predicted_danger_level_1_to_4,probability_level_1,probability_level_2,probability_level_3,probability_level_4',
                        'holdout_id_value_0,2026-05-20T00:00:00+00:00,region_id_value_0,all,3,3,0.01,0.01,0.97,0.01',
                    ]
                )
                + '\n',
                encoding='utf-8',
            )
            readiness_contract = build_contract(
                status_overrides=evidence_validation['status_overrides'],
                generated_at=generated_at,
                partner_evidence_validation=evidence_validation,
                release_gate_attestations=self._release_gate_attestations(),
            )
            leakage_audit = build_himalayan_local_holdout_leakage_audit(
                root,
                generated_at=generated_at,
                partner_source_manifest=source_manifest,
            )
            metric_report = build_himalayan_local_holdout_metric_report(
                root,
                generated_at=generated_at,
                leakage_audit=leakage_audit,
                partner_source_manifest=source_manifest,
                predictions_path=predictions_path,
            )
            quality_score = build_partner_submission_quality_score(
                generated_at=generated_at,
                intake_preflight=intake_preflight,
                source_manifest_validation=source_validation,
                evidence_validation=evidence_validation,
                readiness_contract=readiness_contract,
            )
            acceptance_checklist = build_partner_submission_acceptance_checklist(
                generated_at=generated_at,
                quality_score=quality_score,
            )
            payload = build_himalayan_boundary_readiness_report(
                generated_at=generated_at,
                intake_preflight=intake_preflight,
                source_manifest_validation=source_validation,
                evidence_validation=evidence_validation,
                readiness_contract=readiness_contract,
                leakage_audit=leakage_audit,
                metric_report=metric_report,
                quality_score=quality_score,
                acceptance_checklist=acceptance_checklist,
            )

        self.assertEqual(payload['decision'], 'boundary_readiness_claim_review_ready_production_blocked')
        self.assertEqual(payload['claim_state'], 'claim_review_ready')
        self.assertTrue(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertEqual(payload['production_state'], 'production_blocked')
        self.assertEqual(payload['blocking_gate_count'], 0)
        self.assertEqual(
            payload['uncertainty_boundary']['calibration_status'],
            'available_from_local_holdout_metric_report',
        )

    def test_partner_handoff_readme_points_to_core_artifacts_and_commands(self) -> None:
        payload = build_partner_handoff_readme(
            generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        )
        markdown = markdown_partner_handoff_readme(payload)

        self.assertEqual(payload['schema_version'], PARTNER_HANDOFF_README_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_handoff_readme_written_pending_partner_submission')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        open_first = {item['artifact'] for item in payload['open_first']}
        self.assertIn('partner_package_index.md', open_first)
        self.assertIn('partner_submission_acceptance_checklist.md', open_first)
        self.assertIn('partner_submission_quality_score.md', open_first)
        self.assertIn('partner_source_package_checksum_guide.md', open_first)
        self.assertIn('partner_synthetic_validation_report.md', open_first)
        self.assertIn('partner_intake_dry_run_runbook.md', open_first)
        self.assertIn('partner_incoming_triage_runbook.md', open_first)
        self.assertIn('release_gate_attestation_template_pack.md', open_first)
        self.assertIn('partner_submission_status_dashboard.md', open_first)
        self.assertIn('himalayan_local_holdout_leakage_audit.md', open_first)
        self.assertIn('himalayan_local_holdout_prediction_template.md', open_first)
        self.assertIn('himalayan_local_holdout_metric_report.md', open_first)
        self.assertIn('partner_sample_row_pack.md', open_first)
        self.assertFalse(payload['current_status']['scientist_review_ready'])
        self.assertFalse(payload['current_status']['claim_review_ready'])
        self.assertIn('<partner-package-root>', payload['resubmission_sequence'][1]['command'])
        self.assertIn('Do not claim Himalayan accuracy readiness', payload['do_not_claim'][0])
        self.assertIn('Himalayan Partner Evidence Handoff README', markdown)
        self.assertIn('Resubmission Sequence', markdown)

    def test_partner_submission_manifest_diff_reports_incomplete_template_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            payload = build_partner_submission_manifest_diff(
                root,
                generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            )
            markdown = markdown_partner_submission_manifest_diff(payload)

        self.assertEqual(payload['schema_version'], PARTNER_SUBMISSION_MANIFEST_DIFF_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'blocked_manifest_diff_current_package_incomplete')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['current_package_complete'])
        self.assertEqual(payload['current_snapshot']['present_file_count'], len(REQUIREMENTS))
        self.assertIn('partner_source_manifest.json', payload['current_snapshot']['missing_files'])
        self.assertEqual(payload['change_counts']['added'], 0)
        self.assertIn('Himalayan Partner Submission Manifest Diff', markdown)

    def test_partner_submission_manifest_diff_detects_changed_resubmission(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'synthetic_partner_package'
            self._write_complete_synthetic_partner_package(package_root)
            generated_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
            baseline = build_partner_submission_manifest_diff(
                package_root,
                generated_at=generated_at,
            )
            station_path = package_root / 'station_metadata.csv'
            station_path.write_text(
                station_path.read_text(encoding='utf-8')
                + 'station_id_value_extra,region_key_value_extra,31.9000,78.9000,4100,2026-01-01/2026-04-30,sha256:'
                + 'f' * 64
                + ',internal_research_validation,reviewed,Dr. Source Reviewer,2026-01-20T12:00:00+00:00,extra row\\n',
                encoding='utf-8',
            )
            payload = build_partner_submission_manifest_diff(
                package_root,
                previous_snapshot=baseline,
                generated_at=generated_at,
            )

        self.assertEqual(payload['decision'], 'partner_submission_manifest_diff_changed')
        self.assertTrue(payload['previous_snapshot_available'])
        self.assertTrue(payload['current_package_complete'])
        self.assertIn('station_metadata.csv', payload['changed_files'])
        self.assertIn('station_metadata.csv', {item['path'] for item in payload['row_count_changes']})
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])

    def test_readiness_cli_can_write_standalone_partner_source_manifest_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            source_validation_json = root / 'partner_source_manifest_validation.json'
            source_validation_md = root / 'partner_source_manifest_validation.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-source-manifest-validation-output',
                    str(source_validation_json),
                    '--partner-source-manifest-validation-markdown',
                    str(source_validation_md),
                ]
            )
            payload = json.loads(source_validation_json.read_text(encoding='utf-8'))
            source_validation_markdown = source_validation_md.read_text(encoding='utf-8')

            self.assertEqual(exit_code, 0)
            self.assertTrue(output.exists())
            self.assertEqual(payload['schema_version'], PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION)
            self.assertEqual(payload['validation_policy_version'], VALIDATION_POLICY_VERSION)
            self.assertEqual(payload['decision'], 'partner_source_manifest_not_supplied')
            self.assertFalse(payload['production_scoring_allowed'])
            self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
            self.assertIn('Himalayan Partner Source Manifest Validation', source_validation_markdown)

    def test_readiness_cli_can_write_partner_source_manifest_starter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'synthetic_partner_package'
            self._write_complete_synthetic_partner_package(package_root)
            output = root / 'readiness_contract.json'
            starter_json = root / 'partner_source_manifest_starter.json'
            starter_md = root / 'partner_source_manifest_starter.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-evidence-root',
                    str(package_root),
                    '--partner-source-manifest-starter-output',
                    str(starter_json),
                    '--partner-source-manifest-starter-markdown',
                    str(starter_md),
                ]
            )
            payload = json.loads(starter_json.read_text(encoding='utf-8'))
            starter_markdown = starter_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'source_manifest_starter_written_pending_source_review')
        self.assertEqual(payload['source_ref_digest_count'], 30)
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['sources'][0]['review_status'], 'pending')
        self.assertIn('Himalayan Partner Source Manifest Starter', starter_markdown)

    def test_readiness_cli_can_write_partner_intake_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            checklist_json = root / 'partner_intake_checklist.json'
            checklist_md = root / 'partner_intake_checklist.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-intake-checklist-output',
                    str(checklist_json),
                    '--partner-intake-checklist-markdown',
                    str(checklist_md),
                ]
            )
            payload = json.loads(checklist_json.read_text(encoding='utf-8'))
            checklist_markdown = checklist_md.read_text(encoding='utf-8')

            self.assertEqual(exit_code, 0)
            self.assertTrue(output.exists())
            self.assertEqual(payload['schema_version'], PARTNER_INTAKE_CHECKLIST_SCHEMA_VERSION)
            self.assertEqual(payload['decision'], 'partner_intake_checklist_written_pending_partner_submission')
            self.assertFalse(payload['production_scoring_allowed'])
            self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
            self.assertIn('partner_source_manifest.json', {item['path'] for item in payload['required_package_files']})
            self.assertIn('Himalayan Partner Evidence Intake Checklist', checklist_markdown)

    def test_readiness_cli_can_write_partner_intake_preflight_for_complete_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'synthetic_partner_package'
            self._write_complete_synthetic_partner_package(package_root)
            output = root / 'readiness_contract.json'
            preflight_json = root / 'partner_intake_preflight.json'
            preflight_md = root / 'partner_intake_preflight.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-intake-root',
                    str(package_root),
                    '--partner-intake-preflight-output',
                    str(preflight_json),
                    '--partner-intake-preflight-markdown',
                    str(preflight_md),
                ]
            )
            payload = json.loads(preflight_json.read_text(encoding='utf-8'))
            preflight_markdown = preflight_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_INTAKE_PREFLIGHT_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_intake_package_files_present')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['present_file_count'], len(REQUIREMENTS) + 1)
        self.assertEqual(payload['missing_files'], [])
        self.assertIn('Himalayan Partner Intake Package Preflight', preflight_markdown)

    def test_readiness_cli_can_write_partner_submission_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'synthetic_partner_package'
            source_manifest_path = self._write_complete_synthetic_partner_package(package_root)
            output = root / 'readiness_contract.json'
            summary_json = root / 'partner_submission_summary.json'
            summary_md = root / 'partner_submission_summary.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-intake-root',
                    str(package_root),
                    '--partner-evidence-root',
                    str(package_root),
                    '--partner-source-manifest',
                    str(source_manifest_path),
                    '--partner-submission-summary-output',
                    str(summary_json),
                    '--partner-submission-summary-markdown',
                    str(summary_md),
                ]
            )
            payload = json.loads(summary_json.read_text(encoding='utf-8'))
            summary_markdown = summary_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_SUBMISSION_STATUS_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_submission_evidence_available_release_gates_pending')
        self.assertEqual(payload['referenced_decisions']['intake_preflight'], 'partner_intake_package_files_present')
        self.assertEqual(
            payload['referenced_decisions']['source_manifest_validation'],
            'partner_source_manifest_available',
        )
        self.assertEqual(
            payload['referenced_decisions']['partner_evidence_validation'],
            'all_partner_evidence_available',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Himalayan Partner Submission Status Summary', summary_markdown)

    def test_readiness_cli_can_write_partner_submission_quality_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'synthetic_partner_package'
            source_manifest_path = self._write_complete_synthetic_partner_package(package_root)
            output = root / 'readiness_contract.json'
            score_json = root / 'partner_submission_quality_score.json'
            score_md = root / 'partner_submission_quality_score.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-intake-root',
                    str(package_root),
                    '--partner-evidence-root',
                    str(package_root),
                    '--partner-source-manifest',
                    str(source_manifest_path),
                    '--partner-submission-quality-score-output',
                    str(score_json),
                    '--partner-submission-quality-score-markdown',
                    str(score_md),
                ]
            )
            payload = json.loads(score_json.read_text(encoding='utf-8'))
            score_markdown = score_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_SUBMISSION_QUALITY_SCORE_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_submission_quality_evidence_ready_release_gates_pending')
        self.assertEqual(payload['score'], 90.0)
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Himalayan Partner Submission Quality Score', score_markdown)

    def test_readiness_cli_can_write_partner_submission_acceptance_checklist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'synthetic_partner_package'
            source_manifest_path = self._write_complete_synthetic_partner_package(package_root)
            output = root / 'readiness_contract.json'
            checklist_json = root / 'partner_submission_acceptance_checklist.json'
            checklist_md = root / 'partner_submission_acceptance_checklist.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-intake-root',
                    str(package_root),
                    '--partner-evidence-root',
                    str(package_root),
                    '--partner-source-manifest',
                    str(source_manifest_path),
                    '--partner-submission-acceptance-checklist-output',
                    str(checklist_json),
                    '--partner-submission-acceptance-checklist-markdown',
                    str(checklist_md),
                ]
            )
            payload = json.loads(checklist_json.read_text(encoding='utf-8'))
            checklist_markdown = checklist_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload['schema_version'],
            PARTNER_SUBMISSION_ACCEPTANCE_CHECKLIST_SCHEMA_VERSION,
        )
        self.assertEqual(
            payload['decision'],
            'partner_submission_acceptance_scientist_review_ready_release_gates_pending',
        )
        self.assertTrue(payload['scientist_review_ready'])
        self.assertFalse(payload['claim_review_ready'])
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Himalayan Partner Submission Acceptance Checklist', checklist_markdown)

    def test_readiness_cli_can_write_partner_handoff_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            readme_json = root / 'partner_handoff_readme.json'
            readme_md = root / 'partner_handoff_readme.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-intake-root',
                    str(root),
                    '--partner-evidence-root',
                    str(root),
                    '--partner-handoff-readme-output',
                    str(readme_json),
                    '--partner-handoff-readme-markdown',
                    str(readme_md),
                ]
            )
            payload = json.loads(readme_json.read_text(encoding='utf-8'))
            readme_markdown = readme_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_HANDOFF_README_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_handoff_readme_written_pending_partner_submission')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('partner_package_index.md', {item['artifact'] for item in payload['open_first']})
        self.assertIn('Himalayan Partner Evidence Handoff README', readme_markdown)

    def test_readiness_cli_can_write_partner_submission_manifest_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'synthetic_partner_package'
            self._write_complete_synthetic_partner_package(package_root)
            output = root / 'readiness_contract.json'
            diff_json = root / 'partner_submission_manifest_diff.json'
            diff_md = root / 'partner_submission_manifest_diff.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-intake-root',
                    str(package_root),
                    '--partner-submission-manifest-diff-output',
                    str(diff_json),
                    '--partner-submission-manifest-diff-markdown',
                    str(diff_md),
                ]
            )
            payload = json.loads(diff_json.read_text(encoding='utf-8'))
            diff_markdown = diff_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_SUBMISSION_MANIFEST_DIFF_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_submission_manifest_diff_baseline_written')
        self.assertTrue(payload['current_package_complete'])
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Himalayan Partner Submission Manifest Diff', diff_markdown)

    def test_readiness_cli_can_write_partner_package_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            index_json = root / 'partner_package_index.json'
            index_md = root / 'partner_package_index.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-package-index-output',
                    str(index_json),
                    '--partner-package-index-markdown',
                    str(index_md),
                ]
            )
            payload = json.loads(index_json.read_text(encoding='utf-8'))
            index_markdown = index_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_PACKAGE_INDEX_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_package_index_written_pending_partner_submission')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('partner_intake_checklist.md', {item['artifact'] for item in payload['artifact_sequence']})
        self.assertIn('partner_source_manifest.json', {item['path'] for item in payload['required_partner_files']})
        self.assertIn('Himalayan Partner Evidence Package Index', index_markdown)

    def test_readiness_cli_can_write_partner_submission_review_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'package'
            write_partner_evidence_templates(package_root)
            output = root / 'readiness_contract.json'
            ledger_json = root / 'partner_submission_review_ledger.json'
            ledger_md = root / 'partner_submission_review_ledger.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-intake-root',
                    str(package_root),
                    '--partner-submission-review-ledger-output',
                    str(ledger_json),
                    '--partner-submission-review-ledger-markdown',
                    str(ledger_md),
                ]
            )
            payload = json.loads(ledger_json.read_text(encoding='utf-8'))
            ledger_markdown = ledger_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_SUBMISSION_REVIEW_LEDGER_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_submission_review_ledger_updated_blocked')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(payload['submission_count'], 1)
        self.assertIn('Himalayan Partner Submission Review Ledger', ledger_markdown)

    def test_readiness_cli_can_write_partner_submission_status_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'package'
            write_partner_evidence_templates(package_root)
            output = root / 'readiness_contract.json'
            dashboard_json = root / 'partner_submission_status_dashboard.json'
            dashboard_md = root / 'partner_submission_status_dashboard.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-intake-root',
                    str(package_root),
                    '--partner-evidence-root',
                    str(package_root),
                    '--partner-submission-status-dashboard-output',
                    str(dashboard_json),
                    '--partner-submission-status-dashboard-markdown',
                    str(dashboard_md),
                ]
            )
            payload = json.loads(dashboard_json.read_text(encoding='utf-8'))
            dashboard_markdown = dashboard_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_SUBMISSION_STATUS_DASHBOARD_SCHEMA_VERSION)
        self.assertEqual(
            payload['decision'],
            'partner_submission_status_dashboard_blocked_partner_action_required',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('partner_submission_review_ledger.json', {item['artifact'] for item in payload['source_artifacts']})
        self.assertIn('Himalayan Partner Submission Status Dashboard', dashboard_markdown)

    def test_readiness_cli_can_write_local_holdout_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            protocol_json = root / 'himalayan_local_holdout_protocol.json'
            protocol_md = root / 'himalayan_local_holdout_protocol.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--local-holdout-protocol-output',
                    str(protocol_json),
                    '--local-holdout-protocol-markdown',
                    str(protocol_md),
                ]
            )
            payload = json.loads(protocol_json.read_text(encoding='utf-8'))
            protocol_markdown = protocol_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], HIMALAYAN_LOCAL_HOLDOUT_PROTOCOL_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'local_himalayan_holdout_protocol_written_pending_partner_evidence')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Himalayan Local Holdout Evaluation Protocol', protocol_markdown)

    def test_readiness_cli_can_write_local_holdout_leakage_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'package'
            write_partner_evidence_templates(package_root)
            output = root / 'readiness_contract.json'
            audit_json = root / 'himalayan_local_holdout_leakage_audit.json'
            audit_md = root / 'himalayan_local_holdout_leakage_audit.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-evidence-root',
                    str(package_root),
                    '--local-holdout-leakage-audit-output',
                    str(audit_json),
                    '--local-holdout-leakage-audit-markdown',
                    str(audit_md),
                ]
            )
            payload = json.loads(audit_json.read_text(encoding='utf-8'))
            audit_markdown = audit_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], HIMALAYAN_LOCAL_HOLDOUT_LEAKAGE_AUDIT_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'blocked_local_holdout_leakage_audit_no_holdout_rows')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Himalayan Local Holdout Leakage Audit', audit_markdown)

    def test_readiness_cli_can_write_local_holdout_metric_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'package'
            write_partner_evidence_templates(package_root)
            output = root / 'readiness_contract.json'
            report_json = root / 'himalayan_local_holdout_metric_report.json'
            report_md = root / 'himalayan_local_holdout_metric_report.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-evidence-root',
                    str(package_root),
                    '--local-holdout-metric-report-output',
                    str(report_json),
                    '--local-holdout-metric-report-markdown',
                    str(report_md),
                ]
            )
            payload = json.loads(report_json.read_text(encoding='utf-8'))
            report_markdown = report_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], HIMALAYAN_LOCAL_HOLDOUT_METRIC_REPORT_SCHEMA_VERSION)
        self.assertEqual(
            payload['decision'],
            'blocked_local_holdout_metric_report_leakage_audit_not_passed',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['metric_report_is_prediction_evidence'])
        self.assertIn('Himalayan Local Holdout Metric Report', report_markdown)

    def test_readiness_cli_can_write_local_holdout_prediction_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            template_json = root / 'himalayan_local_holdout_prediction_template.json'
            template_md = root / 'himalayan_local_holdout_prediction_template.md'
            template_csv = root / 'himalayan_local_holdout_predictions.csv'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--local-holdout-prediction-template-output',
                    str(template_json),
                    '--local-holdout-prediction-template-markdown',
                    str(template_md),
                    '--local-holdout-prediction-template-csv',
                    str(template_csv),
                ]
            )
            payload = json.loads(template_json.read_text(encoding='utf-8'))
            template_markdown = template_md.read_text(encoding='utf-8')
            template_csv_text = template_csv.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload['schema_version'],
            HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_TEMPLATE_SCHEMA_VERSION,
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['template_is_prediction_evidence'])
        self.assertIn('Himalayan Local Holdout Prediction Template', template_markdown)
        self.assertIn('predicted_danger_level_1_to_4', template_csv_text)

    def test_readiness_cli_can_write_partner_source_package_checksum_guide(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            guide_json = root / 'partner_source_package_checksum_guide.json'
            guide_md = root / 'partner_source_package_checksum_guide.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-source-package-checksum-guide-output',
                    str(guide_json),
                    '--partner-source-package-checksum-guide-markdown',
                    str(guide_md),
                ]
            )
            payload = json.loads(guide_json.read_text(encoding='utf-8'))
            guide_markdown = guide_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload['schema_version'],
            PARTNER_SOURCE_PACKAGE_CHECKSUM_GUIDE_SCHEMA_VERSION,
        )
        self.assertEqual(
            payload['decision'],
            'partner_source_package_checksum_guide_written_pending_partner_sources',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('hashlib.sha256', '\n'.join(item['command'] for item in payload['checksum_commands']))
        self.assertIn('Himalayan Partner Source Package Checksum Guide', guide_markdown)

    def test_readiness_cli_can_write_partner_intake_dry_run_runbook(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            runbook_json = root / 'partner_intake_dry_run_runbook.json'
            runbook_md = root / 'partner_intake_dry_run_runbook.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-intake-dry-run-runbook-output',
                    str(runbook_json),
                    '--partner-intake-dry-run-runbook-markdown',
                    str(runbook_md),
                ]
            )
            payload = json.loads(runbook_json.read_text(encoding='utf-8'))
            runbook_markdown = runbook_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_INTAKE_DRY_RUN_RUNBOOK_SCHEMA_VERSION)
        self.assertEqual(
            payload['decision'],
            'partner_intake_dry_run_runbook_written_pending_partner_package',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('partner_source_manifest.json', payload['required_partner_files'])
        self.assertIn('Himalayan Partner Intake Dry-Run Runbook', runbook_markdown)

    def test_readiness_cli_can_write_partner_incoming_triage_runbook(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            runbook_json = root / 'partner_incoming_triage_runbook.json'
            runbook_md = root / 'partner_incoming_triage_runbook.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-incoming-triage-runbook-output',
                    str(runbook_json),
                    '--partner-incoming-triage-runbook-markdown',
                    str(runbook_md),
                ]
            )
            payload = json.loads(runbook_json.read_text(encoding='utf-8'))
            runbook_markdown = runbook_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_INCOMING_TRIAGE_RUNBOOK_SCHEMA_VERSION)
        self.assertEqual(
            payload['decision'],
            'partner_incoming_triage_runbook_written_pending_partner_package',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Himalayan Incoming Partner Package Triage Runbook', runbook_markdown)

    def test_partner_package_triage_wrapper_writes_claim_blocked_status_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'partner_package'
            output_root = root / 'triage_output'
            write_partner_evidence_templates(package_root)

            exit_code = run_himalayan_triage_main(
                [
                    '--partner-package-root',
                    str(package_root),
                    '--output-root',
                    str(output_root),
                ]
            )
            summary = json.loads((output_root / 'triage_summary.json').read_text(encoding='utf-8'))
            dashboard = json.loads(
                (output_root / 'partner_submission_status_dashboard.json').read_text(encoding='utf-8')
            )
            evidence_validation = json.loads(
                (output_root / 'partner_evidence_validation.json').read_text(encoding='utf-8')
            )
            source_traceability = json.loads(
                (output_root / 'triage_source_traceability.json').read_text(encoding='utf-8')
            )
            boundary_report = json.loads(
                (output_root / 'himalayan_boundary_readiness_report.json').read_text(encoding='utf-8')
            )
            artifact_manifest = json.loads(
                (output_root / 'triage_artifact_manifest.json').read_text(encoding='utf-8')
            )
            summary_markdown = (output_root / 'triage_summary.md').read_text(encoding='utf-8')
            prediction_template_csv_exists = (output_root / 'himalayan_local_holdout_predictions.csv').exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary['schema_version'], 'himalayan_partner_package_triage_summary_v1')
        self.assertEqual(summary['decision'], 'triage_complete_partner_action_required')
        self.assertEqual(summary['referenced_decisions']['partner_evidence_validation'], 'blocked_pending_partner_evidence')
        self.assertFalse(summary['production_scoring_allowed'])
        self.assertFalse(summary['himalayan_accuracy_claim_allowed'])
        self.assertFalse(dashboard['production_scoring_allowed'])
        self.assertEqual(evidence_validation['schema_version'], PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION)
        self.assertEqual(source_traceability['decision'], 'blocked_source_traceability_source_manifest_unavailable')
        self.assertFalse(source_traceability['production_scoring_allowed'])
        self.assertEqual(
            boundary_report['schema_version'],
            HIMALAYAN_BOUNDARY_READINESS_REPORT_SCHEMA_VERSION,
        )
        self.assertEqual(boundary_report['claim_state'], 'methodology_evidence_only')
        self.assertFalse(boundary_report['production_scoring_allowed'])
        self.assertFalse(boundary_report['himalayan_accuracy_claim_allowed'])
        self.assertEqual(artifact_manifest['decision'], 'triage_artifact_manifest_complete')
        self.assertFalse(artifact_manifest['production_scoring_allowed'])
        self.assertTrue(
            any(
                item['filename'] == 'triage_summary.json' and item['sha256']
                for item in artifact_manifest['artifacts']
            )
        )
        self.assertTrue(
            any(
                item['filename'] == 'himalayan_boundary_readiness_report.json' and item['sha256']
                for item in artifact_manifest['artifacts']
            )
        )
        self.assertTrue(prediction_template_csv_exists)
        self.assertIn('Himalayan Partner Package Triage Summary', summary_markdown)

    def test_partner_package_triage_wrapper_verifies_synthetic_checksum_traceability_without_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'synthetic_package'
            output_root = root / 'triage_output'
            write_partner_synthetic_validation_package(
                package_root,
                generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
            )
            source_manifest = json.loads(
                (package_root / 'partner_source_manifest.json').read_text(encoding='utf-8')
            )

            exit_code = run_himalayan_triage_main(
                [
                    '--partner-package-root',
                    str(package_root),
                    '--output-root',
                    str(output_root),
                ]
            )
            summary = json.loads((output_root / 'triage_summary.json').read_text(encoding='utf-8'))
            traceability = json.loads(
                (output_root / 'triage_source_traceability.json').read_text(encoding='utf-8')
            )
            boundary_report = json.loads(
                (output_root / 'himalayan_boundary_readiness_report.json').read_text(encoding='utf-8')
            )
            artifact_manifest = json.loads(
                (output_root / 'triage_artifact_manifest.json').read_text(encoding='utf-8')
            )

        manifest_hashes = sorted(item['sha256'] for item in source_manifest['sources'])
        self.assertEqual(exit_code, 0)
        self.assertEqual(
            traceability['decision'],
            'source_traceability_passed_perfect_match_claims_blocked',
        )
        self.assertEqual(traceability['source_hashes']['declared_manifest_hashes'], manifest_hashes)
        self.assertEqual(traceability['source_hashes']['valid_manifest_hashes'], manifest_hashes)
        self.assertEqual(traceability['source_hashes']['evidence_source_ref_hashes'], manifest_hashes)
        self.assertEqual(traceability['source_hash_counts']['evidence_missing_from_manifest'], 0)
        self.assertTrue(traceability['synthetic_fixture_detected'])
        self.assertTrue(traceability['safety_locks_passed'])
        self.assertFalse(traceability['production_scoring_allowed'])
        self.assertFalse(traceability['himalayan_accuracy_claim_allowed'])
        self.assertFalse(summary['production_scoring_allowed'])
        self.assertFalse(summary['himalayan_accuracy_claim_allowed'])
        self.assertEqual(boundary_report['claim_state'], 'scientist_review_ready')
        self.assertEqual(boundary_report['referenced_decisions']['source_traceability'], traceability['decision'])
        self.assertFalse(boundary_report['production_scoring_allowed'])
        self.assertFalse(boundary_report['himalayan_accuracy_claim_allowed'])
        self.assertTrue(
            any(
                item['filename'] == 'triage_source_traceability.json' and item['sha256']
                for item in artifact_manifest['artifacts']
            )
        )

    def test_readiness_cli_can_write_release_gate_attestation_template_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            pack_json = root / 'release_gate_attestation_template_pack.json'
            pack_md = root / 'release_gate_attestation_template_pack.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--release-gate-attestation-template-pack-output',
                    str(pack_json),
                    '--release-gate-attestation-template-pack-markdown',
                    str(pack_md),
                ]
            )
            payload = json.loads(pack_json.read_text(encoding='utf-8'))
            pack_markdown = pack_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload['schema_version'],
            RELEASE_GATE_ATTESTATION_TEMPLATE_PACK_SCHEMA_VERSION,
        )
        self.assertEqual(payload['release_gate_count'], len(REQUIRED_RELEASE_GATES))
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Himalayan Release-Gate Attestation Template Pack', pack_markdown)

    def test_readiness_cli_can_write_top10_feature_gap_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            matrix_json = root / 'himalayan_top10_feature_gap_matrix.json'
            matrix_md = root / 'himalayan_top10_feature_gap_matrix.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--top10-feature-gap-matrix-output',
                    str(matrix_json),
                    '--top10-feature-gap-matrix-markdown',
                    str(matrix_md),
                ]
            )
            payload = json.loads(matrix_json.read_text(encoding='utf-8'))
            matrix_markdown = matrix_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], HIMALAYAN_TOP10_FEATURE_GAP_MATRIX_SCHEMA_VERSION)
        self.assertEqual(payload['feature_count'], 10)
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('Himalayan Avalanche Prediction Top-10 Feature Gap Matrix', matrix_markdown)

    def test_readiness_cli_can_write_partner_synthetic_validation_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            package_root = root / 'partner_synthetic_validation_package'
            report_json = root / 'partner_synthetic_validation_report.json'
            report_md = root / 'partner_synthetic_validation_report.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-synthetic-validation-package-root',
                    str(package_root),
                    '--partner-synthetic-validation-report-output',
                    str(report_json),
                    '--partner-synthetic-validation-report-markdown',
                    str(report_md),
                ]
            )
            payload = json.loads(report_json.read_text(encoding='utf-8'))
            report_markdown = report_md.read_text(encoding='utf-8')
            package_manifest_exists = (package_root / 'partner_source_manifest.json').exists()
            raw_source_dir_exists = (package_root / 'raw_sources').is_dir()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            payload['schema_version'],
            PARTNER_SYNTHETIC_VALIDATION_PACKAGE_SCHEMA_VERSION,
        )
        self.assertEqual(
            payload['decision'],
            'synthetic_partner_validation_package_structurally_passed_claims_blocked',
        )
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertTrue(package_manifest_exists)
        self.assertTrue(raw_source_dir_exists)
        self.assertIn('Synthetic Himalayan Partner Validation Package', report_markdown)

    def test_readiness_cli_can_write_partner_field_dictionary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            dictionary_json = root / 'partner_field_dictionary.json'
            dictionary_md = root / 'partner_field_dictionary.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-field-dictionary-output',
                    str(dictionary_json),
                    '--partner-field-dictionary-markdown',
                    str(dictionary_md),
                ]
            )
            payload = json.loads(dictionary_json.read_text(encoding='utf-8'))
            dictionary_markdown = dictionary_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_FIELD_DICTIONARY_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_field_dictionary_written_pending_partner_submission')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertIn('danger_level_1_to_5', {item['column'] for item in payload['field_definitions']})
        self.assertIn('Himalayan Partner Evidence Field Dictionary', dictionary_markdown)

    def test_readiness_cli_can_write_partner_sample_row_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output = root / 'readiness_contract.json'
            sample_json = root / 'partner_sample_row_pack.json'
            sample_md = root / 'partner_sample_row_pack.md'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(output),
                    '--partner-sample-row-pack-output',
                    str(sample_json),
                    '--partner-sample-row-pack-markdown',
                    str(sample_md),
                ]
            )
            payload = json.loads(sample_json.read_text(encoding='utf-8'))
            sample_markdown = sample_md.read_text(encoding='utf-8')

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload['schema_version'], PARTNER_SAMPLE_ROW_PACK_SCHEMA_VERSION)
        self.assertEqual(payload['decision'], 'partner_sample_row_pack_written_example_only')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertFalse(payload['sample_rows_are_evidence'])
        self.assertIn('Himalayan Partner Evidence Sample Row Pack', sample_markdown)

    def test_partner_evidence_templates_cover_every_requirement_and_fail_closed(self) -> None:
        payload = build_partner_evidence_template_manifest()

        self.assertEqual(payload['schema_version'], PARTNER_TEMPLATE_SCHEMA_VERSION)
        self.assertEqual(payload['validation_policy_version'], VALIDATION_POLICY_VERSION)
        self.assertIn('himalayan_accuracy_partner_evidence_templates_v1', DEPRECATED_SCHEMA_VERSIONS)
        self.assertIn('himalayan_accuracy_partner_evidence_templates_v2', DEPRECATED_SCHEMA_VERSIONS)
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(len(payload['templates']), len(REQUIREMENTS))
        station_template = next(
            template for template in payload['templates'] if template['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(station_template['filename'], 'station_metadata.csv')
        self.assertEqual(station_template['minimum_rows_for_availability'], 10)
        self.assertEqual(station_template['minimum_distinct_counts'], {'station_id': 10, 'region_key': 3})
        self.assertIn('license_scope', station_template['controlled_values'])
        self.assertIn('internal_research_validation', station_template['controlled_values']['license_scope'])
        self.assertIn('latitude', station_template['columns'])
        self.assertIn('elevation_m', station_template['columns'])
        self.assertIn('license_scope', station_template['columns'])
        danger_template = next(
            template for template in payload['templates'] if template['requirement_key'] == 'danger_labels_and_bulletins'
        )
        self.assertIn('avalanche_problem', danger_template['controlled_values'])
        self.assertIn('wind_slab', danger_template['controlled_values']['avalanche_problem'])
        self.assertIn('danger_scale_standard', danger_template['controlled_values'])
        self.assertIn('eaws_5_level', danger_template['controlled_values']['danger_scale_standard'])
        self.assertIn('label_source', danger_template['controlled_values'])
        self.assertIn('tidy_reanalysis', danger_template['controlled_values']['label_source'])
        self.assertIn('avalanche_regime', danger_template['controlled_values'])
        self.assertIn('dry_snow', danger_template['controlled_values']['avalanche_regime'])
        self.assertIn('forecast_cycle', danger_template['controlled_values'])
        self.assertIn('nowcast', danger_template['controlled_values']['forecast_cycle'])
        self.assertIn('danger_level_1_to_5', danger_template['columns'])
        self.assertIn('tidy_label_review_basis', danger_template['columns'])
        self.assertIn('nowcast_evidence_ref', danger_template['columns'])
        self.assertIn('observer_evidence_ref', danger_template['columns'])
        self.assertIn('forecast_issue_time', danger_template['columns'])
        self.assertIn('valid_at', danger_template['columns'])
        self.assertIn('critical_elevation_m', danger_template['columns'])
        holdout_template = next(
            template for template in payload['templates'] if template['requirement_key'] == 'independent_himalayan_holdout'
        )
        self.assertIn('label_source', holdout_template['columns'])
        self.assertIn('avalanche_regime', holdout_template['columns'])
        self.assertEqual(
            list(partner_template_columns(REQUIREMENTS[0])),
            station_template['columns'],
        )

    def test_partner_evidence_template_writer_outputs_csv_manifest_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload = write_partner_evidence_templates(root)
            station_csv = root / 'station_metadata.csv'
            top10_matrix_json = root / 'himalayan_top10_feature_gap_matrix.json'
            top10_matrix_md = root / 'himalayan_top10_feature_gap_matrix.md'
            local_holdout_protocol_json = root / 'himalayan_local_holdout_protocol.json'
            local_holdout_protocol_md = root / 'himalayan_local_holdout_protocol.md'
            local_holdout_leakage_audit_json = root / 'himalayan_local_holdout_leakage_audit.json'
            local_holdout_leakage_audit_md = root / 'himalayan_local_holdout_leakage_audit.md'
            local_holdout_prediction_template_json = root / 'himalayan_local_holdout_prediction_template.json'
            local_holdout_prediction_template_md = root / 'himalayan_local_holdout_prediction_template.md'
            local_holdout_prediction_template_csv = root / 'himalayan_local_holdout_predictions.csv'
            local_holdout_metric_report_json = root / 'himalayan_local_holdout_metric_report.json'
            local_holdout_metric_report_md = root / 'himalayan_local_holdout_metric_report.md'
            manifest_json = root / 'partner_evidence_template_manifest.json'
            manifest_md = root / 'partner_evidence_template_manifest.md'
            source_manifest_template_json = root / 'partner_source_manifest_template.json'
            source_manifest_template_md = root / 'partner_source_manifest_template.md'
            intake_checklist_json = root / 'partner_intake_checklist.json'
            intake_checklist_md = root / 'partner_intake_checklist.md'
            intake_dry_run_runbook_json = root / 'partner_intake_dry_run_runbook.json'
            intake_dry_run_runbook_md = root / 'partner_intake_dry_run_runbook.md'
            incoming_triage_runbook_json = root / 'partner_incoming_triage_runbook.json'
            incoming_triage_runbook_md = root / 'partner_incoming_triage_runbook.md'
            release_gate_pack_json = root / 'release_gate_attestation_template_pack.json'
            release_gate_pack_md = root / 'release_gate_attestation_template_pack.md'
            field_dictionary_json = root / 'partner_field_dictionary.json'
            field_dictionary_md = root / 'partner_field_dictionary.md'
            sample_row_pack_json = root / 'partner_sample_row_pack.json'
            sample_row_pack_md = root / 'partner_sample_row_pack.md'
            submission_quality_score_json = root / 'partner_submission_quality_score.json'
            submission_quality_score_md = root / 'partner_submission_quality_score.md'
            acceptance_checklist_json = root / 'partner_submission_acceptance_checklist.json'
            acceptance_checklist_md = root / 'partner_submission_acceptance_checklist.md'
            handoff_readme_json = root / 'partner_handoff_readme.json'
            handoff_readme_md = root / 'partner_handoff_readme.md'
            manifest_diff_json = root / 'partner_submission_manifest_diff.json'
            manifest_diff_md = root / 'partner_submission_manifest_diff.md'
            review_ledger_json = root / 'partner_submission_review_ledger.json'
            review_ledger_md = root / 'partner_submission_review_ledger.md'
            status_dashboard_json = root / 'partner_submission_status_dashboard.json'
            status_dashboard_md = root / 'partner_submission_status_dashboard.md'
            checksum_guide_json = root / 'partner_source_package_checksum_guide.json'
            checksum_guide_md = root / 'partner_source_package_checksum_guide.md'
            package_index_json = root / 'partner_package_index.json'
            package_index_md = root / 'partner_package_index.md'

            self.assertTrue(station_csv.exists())
            self.assertTrue(top10_matrix_json.exists())
            self.assertTrue(top10_matrix_md.exists())
            self.assertTrue(local_holdout_protocol_json.exists())
            self.assertTrue(local_holdout_protocol_md.exists())
            self.assertTrue(local_holdout_leakage_audit_json.exists())
            self.assertTrue(local_holdout_leakage_audit_md.exists())
            self.assertTrue(local_holdout_prediction_template_json.exists())
            self.assertTrue(local_holdout_prediction_template_md.exists())
            self.assertTrue(local_holdout_prediction_template_csv.exists())
            self.assertTrue(local_holdout_metric_report_json.exists())
            self.assertTrue(local_holdout_metric_report_md.exists())
            self.assertTrue(manifest_json.exists())
            self.assertTrue(manifest_md.exists())
            self.assertTrue(source_manifest_template_json.exists())
            self.assertTrue(source_manifest_template_md.exists())
            self.assertTrue(intake_checklist_json.exists())
            self.assertTrue(intake_checklist_md.exists())
            self.assertTrue(intake_dry_run_runbook_json.exists())
            self.assertTrue(intake_dry_run_runbook_md.exists())
            self.assertTrue(incoming_triage_runbook_json.exists())
            self.assertTrue(incoming_triage_runbook_md.exists())
            self.assertTrue(release_gate_pack_json.exists())
            self.assertTrue(release_gate_pack_md.exists())
            self.assertTrue(field_dictionary_json.exists())
            self.assertTrue(field_dictionary_md.exists())
            self.assertTrue(sample_row_pack_json.exists())
            self.assertTrue(sample_row_pack_md.exists())
            self.assertTrue(submission_quality_score_json.exists())
            self.assertTrue(submission_quality_score_md.exists())
            self.assertTrue(acceptance_checklist_json.exists())
            self.assertTrue(acceptance_checklist_md.exists())
            self.assertTrue(handoff_readme_json.exists())
            self.assertTrue(handoff_readme_md.exists())
            self.assertTrue(manifest_diff_json.exists())
            self.assertTrue(manifest_diff_md.exists())
            self.assertTrue(review_ledger_json.exists())
            self.assertTrue(review_ledger_md.exists())
            self.assertTrue(status_dashboard_json.exists())
            self.assertTrue(status_dashboard_md.exists())
            self.assertTrue(checksum_guide_json.exists())
            self.assertTrue(checksum_guide_md.exists())
            self.assertTrue(package_index_json.exists())
            self.assertTrue(package_index_md.exists())
            source_manifest_template = json.loads(source_manifest_template_json.read_text(encoding='utf-8'))
            intake_checklist = json.loads(intake_checklist_json.read_text(encoding='utf-8'))
            intake_dry_run_runbook = json.loads(intake_dry_run_runbook_json.read_text(encoding='utf-8'))
            incoming_triage_runbook = json.loads(incoming_triage_runbook_json.read_text(encoding='utf-8'))
            release_gate_pack = json.loads(release_gate_pack_json.read_text(encoding='utf-8'))
            field_dictionary = json.loads(field_dictionary_json.read_text(encoding='utf-8'))
            sample_row_pack = json.loads(sample_row_pack_json.read_text(encoding='utf-8'))
            submission_quality_score = json.loads(submission_quality_score_json.read_text(encoding='utf-8'))
            acceptance_checklist = json.loads(acceptance_checklist_json.read_text(encoding='utf-8'))
            handoff_readme = json.loads(handoff_readme_json.read_text(encoding='utf-8'))
            manifest_diff = json.loads(manifest_diff_json.read_text(encoding='utf-8'))
            review_ledger = json.loads(review_ledger_json.read_text(encoding='utf-8'))
            status_dashboard = json.loads(status_dashboard_json.read_text(encoding='utf-8'))
            checksum_guide = json.loads(checksum_guide_json.read_text(encoding='utf-8'))
            package_index = json.loads(package_index_json.read_text(encoding='utf-8'))
            top10_matrix = json.loads(top10_matrix_json.read_text(encoding='utf-8'))
            local_holdout_protocol = json.loads(local_holdout_protocol_json.read_text(encoding='utf-8'))
            local_holdout_leakage_audit = json.loads(
                local_holdout_leakage_audit_json.read_text(encoding='utf-8')
            )
            local_holdout_prediction_template = json.loads(
                local_holdout_prediction_template_json.read_text(encoding='utf-8')
            )
            local_holdout_metric_report = json.loads(
                local_holdout_metric_report_json.read_text(encoding='utf-8')
            )
            self.assertIn('station_id,region_key,latitude,longitude', station_csv.read_text(encoding='utf-8'))
            self.assertIn(
                'Himalayan Avalanche Prediction Top-10 Feature Gap Matrix',
                top10_matrix_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Local Holdout Evaluation Protocol',
                local_holdout_protocol_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Local Holdout Leakage Audit',
                local_holdout_leakage_audit_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Local Holdout Prediction Template',
                local_holdout_prediction_template_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'predicted_danger_level_1_to_4',
                local_holdout_prediction_template_csv.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Local Holdout Metric Report',
                local_holdout_metric_report_md.read_text(encoding='utf-8'),
            )
            self.assertIn('Himalayan Partner Evidence Templates', manifest_md.read_text(encoding='utf-8'))
            self.assertIn(
                'Himalayan Partner Source Manifest Template',
                source_manifest_template_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Evidence Intake Checklist',
                intake_checklist_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Intake Dry-Run Runbook',
                intake_dry_run_runbook_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Incoming Partner Package Triage Runbook',
                incoming_triage_runbook_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Release-Gate Attestation Template Pack',
                release_gate_pack_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Evidence Field Dictionary',
                field_dictionary_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Evidence Sample Row Pack',
                sample_row_pack_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Submission Quality Score',
                submission_quality_score_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Submission Acceptance Checklist',
                acceptance_checklist_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Evidence Handoff README',
                handoff_readme_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Submission Manifest Diff',
                manifest_diff_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Submission Review Ledger',
                review_ledger_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Submission Status Dashboard',
                status_dashboard_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Source Package Checksum Guide',
                checksum_guide_md.read_text(encoding='utf-8'),
            )
            self.assertIn(
                'Himalayan Partner Evidence Package Index',
                package_index_md.read_text(encoding='utf-8'),
            )
            self.assertIn('Minimum reviewed rows', manifest_md.read_text(encoding='utf-8'))
            self.assertIn('Minimum distinct coverage', manifest_md.read_text(encoding='utf-8'))
            self.assertIn('Minimum span coverage', manifest_md.read_text(encoding='utf-8'))
            self.assertIn('Controlled fields', manifest_md.read_text(encoding='utf-8'))
            self.assertEqual(source_manifest_template['schema_version'], PARTNER_SOURCE_MANIFEST_SCHEMA_VERSION)
            self.assertIn('sha256', source_manifest_template['required_source_fields'])
            self.assertEqual(intake_checklist['schema_version'], PARTNER_INTAKE_CHECKLIST_SCHEMA_VERSION)
            self.assertFalse(intake_checklist['production_scoring_allowed'])
            self.assertEqual(
                intake_dry_run_runbook['schema_version'],
                PARTNER_INTAKE_DRY_RUN_RUNBOOK_SCHEMA_VERSION,
            )
            self.assertFalse(intake_dry_run_runbook['production_scoring_allowed'])
            self.assertEqual(
                incoming_triage_runbook['schema_version'],
                PARTNER_INCOMING_TRIAGE_RUNBOOK_SCHEMA_VERSION,
            )
            self.assertFalse(incoming_triage_runbook['production_scoring_allowed'])
            self.assertFalse(incoming_triage_runbook['runbook_is_prediction_evidence'])
            self.assertEqual(
                release_gate_pack['schema_version'],
                RELEASE_GATE_ATTESTATION_TEMPLATE_PACK_SCHEMA_VERSION,
            )
            self.assertFalse(release_gate_pack['production_scoring_allowed'])
            self.assertEqual(field_dictionary['schema_version'], PARTNER_FIELD_DICTIONARY_SCHEMA_VERSION)
            self.assertFalse(field_dictionary['production_scoring_allowed'])
            self.assertEqual(sample_row_pack['schema_version'], PARTNER_SAMPLE_ROW_PACK_SCHEMA_VERSION)
            self.assertFalse(sample_row_pack['sample_rows_are_evidence'])
            self.assertEqual(
                submission_quality_score['schema_version'],
                PARTNER_SUBMISSION_QUALITY_SCORE_SCHEMA_VERSION,
            )
            self.assertTrue(submission_quality_score['quality_policy']['score_is_not_accuracy'])
            self.assertEqual(
                acceptance_checklist['schema_version'],
                PARTNER_SUBMISSION_ACCEPTANCE_CHECKLIST_SCHEMA_VERSION,
            )
            self.assertFalse(acceptance_checklist['production_scoring_allowed'])
            self.assertEqual(handoff_readme['schema_version'], PARTNER_HANDOFF_README_SCHEMA_VERSION)
            self.assertFalse(handoff_readme['production_scoring_allowed'])
            self.assertEqual(manifest_diff['schema_version'], PARTNER_SUBMISSION_MANIFEST_DIFF_SCHEMA_VERSION)
            self.assertEqual(manifest_diff['decision'], 'blocked_manifest_diff_current_package_incomplete')
            self.assertEqual(
                review_ledger['schema_version'],
                PARTNER_SUBMISSION_REVIEW_LEDGER_SCHEMA_VERSION,
            )
            self.assertFalse(review_ledger['production_scoring_allowed'])
            self.assertEqual(
                status_dashboard['schema_version'],
                PARTNER_SUBMISSION_STATUS_DASHBOARD_SCHEMA_VERSION,
            )
            self.assertFalse(status_dashboard['production_scoring_allowed'])
            self.assertEqual(
                checksum_guide['schema_version'],
                PARTNER_SOURCE_PACKAGE_CHECKSUM_GUIDE_SCHEMA_VERSION,
            )
            self.assertFalse(checksum_guide['production_scoring_allowed'])
            self.assertEqual(package_index['schema_version'], PARTNER_PACKAGE_INDEX_SCHEMA_VERSION)
            self.assertFalse(package_index['production_scoring_allowed'])
            self.assertEqual(
                top10_matrix['schema_version'],
                HIMALAYAN_TOP10_FEATURE_GAP_MATRIX_SCHEMA_VERSION,
            )
            self.assertFalse(top10_matrix['production_scoring_allowed'])
            self.assertEqual(
                local_holdout_protocol['schema_version'],
                HIMALAYAN_LOCAL_HOLDOUT_PROTOCOL_SCHEMA_VERSION,
            )
            self.assertFalse(local_holdout_protocol['production_scoring_allowed'])
            self.assertEqual(
                local_holdout_leakage_audit['schema_version'],
                HIMALAYAN_LOCAL_HOLDOUT_LEAKAGE_AUDIT_SCHEMA_VERSION,
            )
            self.assertFalse(local_holdout_leakage_audit['production_scoring_allowed'])
            self.assertEqual(
                local_holdout_prediction_template['schema_version'],
                HIMALAYAN_LOCAL_HOLDOUT_PREDICTION_TEMPLATE_SCHEMA_VERSION,
            )
            self.assertFalse(local_holdout_prediction_template['production_scoring_allowed'])
            self.assertFalse(local_holdout_prediction_template['template_is_prediction_evidence'])
            self.assertEqual(
                local_holdout_metric_report['schema_version'],
                HIMALAYAN_LOCAL_HOLDOUT_METRIC_REPORT_SCHEMA_VERSION,
            )
            self.assertFalse(local_holdout_metric_report['production_scoring_allowed'])
            self.assertFalse(local_holdout_metric_report['metric_report_is_prediction_evidence'])
            self.assertEqual(payload['usage_boundary'], 'research_validation_only')

    def test_partner_evidence_validation_blocks_missing_or_blank_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            payload = validate_partner_evidence_root(root)
            missing_payload = validate_partner_evidence_root(root / 'missing')

        self.assertEqual(payload['schema_version'], PARTNER_EVIDENCE_VALIDATION_SCHEMA_VERSION)
        self.assertEqual(payload['validation_policy_version'], VALIDATION_POLICY_VERSION)
        self.assertEqual(payload['decision'], 'blocked_pending_partner_evidence')
        self.assertFalse(payload['production_scoring_allowed'])
        self.assertFalse(payload['himalayan_accuracy_claim_allowed'])
        self.assertEqual(set(payload['status_overrides'].values()), {'partner_required'})
        self.assertTrue(all(report['decision'] == 'blocked_empty_partner_evidence_file' for report in payload['reports']))
        self.assertTrue(
            all(report['decision'] == 'missing_partner_evidence_file' for report in missing_payload['reports'])
        )

    def test_partner_evidence_validation_requires_reviewed_nonblank_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_path = self._write_complete_evidence_file(root)
            rows = station_path.read_text(encoding='utf-8').splitlines()
            station_path.write_text(rows[0] + '\n' + rows[1].replace('reviewed', 'pending') + '\n', encoding='utf-8')
            pending_payload = validate_partner_evidence_root(root)
            station_path.write_text(rows[0] + '\n' + rows[1].replace('station_id_value_0', '') + '\n', encoding='utf-8')
            incomplete_payload = validate_partner_evidence_root(root)
            station_path.write_text(
                rows[0] + '\n' + rows[1].replace('2026-01-01T12:00:00+00:00', '') + '\n',
                encoding='utf-8',
            )
            missing_reviewed_at_payload = validate_partner_evidence_root(root)

        pending_station = next(
            report for report in pending_payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        incomplete_station = next(
            report for report in incomplete_payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        missing_reviewed_at_station = next(
            report
            for report in missing_reviewed_at_payload['reports']
            if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(pending_station['decision'], 'blocked_unreviewed_partner_evidence_rows')
        self.assertEqual(incomplete_station['decision'], 'blocked_incomplete_partner_evidence_rows')
        self.assertEqual(missing_reviewed_at_station['decision'], 'blocked_incomplete_partner_evidence_rows')

    def test_station_metadata_reports_gpxyz_density_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            self._write_complete_evidence_file(root, requirement_index=0, row_count=10)
            payload = validate_partner_evidence_root(root)

        station_report = next(
            report for report in payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        diagnostics = station_report['coverage_diagnostics']
        self.assertEqual(diagnostics['diagnostic_type'], 'gpxyz_station_coverage')
        self.assertEqual(diagnostics['station_count'], 10)
        self.assertEqual(diagnostics['region_count'], 3)
        self.assertEqual(diagnostics['minimum_elevation_span_m'], 500.0)
        self.assertEqual(diagnostics['sparse_coverage_warnings'], [])
        self.assertIn('latitude_longitude_elevation', diagnostics['gpxyz_claim_boundary'])

    def test_partner_evidence_validation_rejects_invalid_domain_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_path = self._write_complete_evidence_file(root)
            rows = station_path.read_text(encoding='utf-8').splitlines()
            station_path.write_text(rows[0] + '\n' + rows[1].replace('31.25', '231.25') + '\n', encoding='utf-8')
            station_payload = validate_partner_evidence_root(root)
            danger_path = self._write_complete_evidence_file(root, requirement_index=3)
            danger_rows = danger_path.read_text(encoding='utf-8').splitlines()
            danger_path.write_text(danger_rows[0] + '\n' + danger_rows[1].replace(',1,', ',7,') + '\n', encoding='utf-8')
            danger_payload = validate_partner_evidence_root(root)
            sensing_path = self._write_complete_evidence_file(root, requirement_index=6)
            sensing_rows = sensing_path.read_text(encoding='utf-8').splitlines()
            sensing_path.write_text(
                sensing_rows[0] + '\n' + sensing_rows[1].replace('independent_holdout', 'training') + '\n',
                encoding='utf-8',
            )
            sensing_payload = validate_partner_evidence_root(root)
            station_path = self._write_complete_evidence_file(root)
            station_rows = station_path.read_text(encoding='utf-8').splitlines()
            station_path.write_text(
                station_rows[0] + '\n' + station_rows[1].replace('2026-01-01T12:00:00+00:00', 'not-a-date') + '\n',
                encoding='utf-8',
            )
            reviewed_at_payload = validate_partner_evidence_root(root)

        station_report = next(
            report for report in station_payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        danger_report = next(
            report for report in danger_payload['reports'] if report['requirement_key'] == 'danger_labels_and_bulletins'
        )
        sensing_report = next(
            report for report in sensing_payload['reports'] if report['requirement_key'] == 'remote_sensing_validation_scenes'
        )
        reviewed_at_report = next(
            report for report in reviewed_at_payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(station_report['decision'], 'blocked_invalid_partner_evidence_values')
        self.assertEqual(danger_report['decision'], 'blocked_invalid_partner_evidence_values')
        self.assertEqual(sensing_report['decision'], 'blocked_invalid_partner_evidence_values')
        self.assertEqual(reviewed_at_report['decision'], 'blocked_invalid_partner_evidence_values')
        self.assertGreaterEqual(station_report['invalid_value_count'], 1)
        self.assertEqual(station_report['invalid_value_examples'][0]['column'], 'latitude')
        self.assertGreaterEqual(reviewed_at_report['invalid_value_count'], 1)
        self.assertEqual(reviewed_at_report['invalid_value_examples'][0]['column'], 'reviewed_at')

    def test_partner_evidence_validation_rejects_uncontrolled_semantic_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            danger_path = self._write_complete_evidence_file(root, requirement_index=3)
            danger_rows = danger_path.read_text(encoding='utf-8').splitlines()
            danger_path.write_text(
                danger_rows[0] + '\n' + danger_rows[1].replace('wind_slab', 'mystery_problem') + '\n',
                encoding='utf-8',
            )
            danger_payload = validate_partner_evidence_root(root)
            terrain_path = self._write_complete_evidence_file(root, requirement_index=7)
            terrain_rows = terrain_path.read_text(encoding='utf-8').splitlines()
            terrain_path.write_text(
                terrain_rows[0] + '\n' + terrain_rows[1].replace('challenging', 'mega_steep') + '\n',
                encoding='utf-8',
            )
            terrain_payload = validate_partner_evidence_root(root)
            danger_path = self._write_complete_evidence_file(root, requirement_index=3)
            danger_rows = danger_path.read_text(encoding='utf-8').splitlines()
            danger_path.write_text(
                danger_rows[0] + '\n' + danger_rows[1].replace('tidy_reanalysis', 'raw_guess') + '\n',
                encoding='utf-8',
            )
            label_source_payload = validate_partner_evidence_root(root)
            danger_path = self._write_complete_evidence_file(root, requirement_index=3)
            danger_rows = danger_path.read_text(encoding='utf-8').splitlines()
            danger_path.write_text(
                danger_rows[0] + '\n' + danger_rows[1].replace('dry_snow', 'monsoon_slush') + '\n',
                encoding='utf-8',
            )
            regime_payload = validate_partner_evidence_root(root)

        danger_report = next(
            report for report in danger_payload['reports'] if report['requirement_key'] == 'danger_labels_and_bulletins'
        )
        terrain_report = next(
            report for report in terrain_payload['reports'] if report['requirement_key'] == 'terrain_ates_runout_validation'
        )
        label_source_report = next(
            report for report in label_source_payload['reports'] if report['requirement_key'] == 'danger_labels_and_bulletins'
        )
        regime_report = next(
            report for report in regime_payload['reports'] if report['requirement_key'] == 'danger_labels_and_bulletins'
        )
        self.assertEqual(danger_report['decision'], 'blocked_invalid_partner_evidence_values')
        self.assertEqual(danger_report['invalid_value_examples'][0]['column'], 'avalanche_problem')
        self.assertIn('controlled value', danger_report['invalid_value_examples'][0]['error'])
        self.assertEqual(terrain_report['decision'], 'blocked_invalid_partner_evidence_values')
        self.assertEqual(terrain_report['invalid_value_examples'][0]['column'], 'terrain_class')
        self.assertEqual(label_source_report['decision'], 'blocked_invalid_partner_evidence_values')
        self.assertEqual(label_source_report['invalid_value_examples'][0]['column'], 'label_source')
        self.assertEqual(regime_report['decision'], 'blocked_invalid_partner_evidence_values')
        self.assertEqual(regime_report['invalid_value_examples'][0]['column'], 'avalanche_regime')

    def test_partner_evidence_validation_rejects_invalid_license_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_path = self._write_complete_evidence_file(root)
            rows = station_path.read_text(encoding='utf-8').splitlines()
            station_path.write_text(
                rows[0] + '\n' + rows[1].replace('internal_research_validation', 'anything_goes') + '\n',
                encoding='utf-8',
            )
            payload = validate_partner_evidence_root(root)

        station_report = next(
            report for report in payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(station_report['decision'], 'blocked_invalid_partner_evidence_values')
        self.assertEqual(station_report['invalid_value_examples'][0]['column'], 'license_scope')

    def test_partner_evidence_validation_blocks_license_scope_without_research_validation_rights(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_path = self._write_complete_evidence_file(
                root,
                row_count=REQUIREMENTS[0].minimum_rows_for_availability,
            )
            self._rewrite_column(station_path, 'license_scope', 'pending_license_review')
            payload = validate_partner_evidence_root(root)

        station_report = next(
            report for report in payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(station_report['decision'], 'blocked_unsupported_partner_evidence_license_scope')
        self.assertEqual(station_report['unsupported_license_scope_count'], REQUIREMENTS[0].minimum_rows_for_availability)
        self.assertEqual(station_report['license_scope_check_status'], 'blocked_unsupported_scope')
        self.assertIn('pending_license_review', station_report['unsupported_license_scope_examples'])

    def test_partner_evidence_validation_requires_minimum_row_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_requirement = REQUIREMENTS[0]
            self._write_complete_evidence_file(
                root,
                requirement_index=0,
                row_count=station_requirement.minimum_rows_for_availability - 1,
            )
            payload = validate_partner_evidence_root(root)
            markdown = markdown_partner_evidence_validation(payload)

        station_report = next(
            report for report in payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(station_report['decision'], 'blocked_insufficient_partner_evidence_rows')
        self.assertEqual(station_report['status'], 'partner_required')
        self.assertEqual(station_report['minimum_row_count'], station_requirement.minimum_rows_for_availability)
        self.assertFalse(station_report['sufficient_row_count'])
        self.assertEqual(station_report['row_count_shortfall'], 1)
        self.assertIn('Row shortfall', markdown)

    def test_partner_evidence_validation_requires_distinct_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_requirement = REQUIREMENTS[0]
            self._write_complete_evidence_file(
                root,
                requirement_index=0,
                row_count=station_requirement.minimum_rows_for_availability,
                diverse=False,
            )
            payload = validate_partner_evidence_root(root)
            markdown = markdown_partner_evidence_validation(payload)

        station_report = next(
            report for report in payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(station_report['decision'], 'blocked_insufficient_partner_evidence_diversity')
        self.assertEqual(station_report['row_count_shortfall'], 0)
        self.assertEqual(station_report['distinct_counts']['station_id'], 1)
        self.assertEqual(station_report['distinct_count_shortfalls']['station_id'], 9)
        self.assertFalse(station_report['sufficient_distinct_coverage'])
        self.assertIn('Distinct shortfalls', markdown)

    def test_partner_evidence_validation_requires_temporal_coverage_span(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            weather_requirement = REQUIREMENTS[1]
            weather_path = self._write_complete_evidence_file(
                root,
                requirement_index=1,
                row_count=weather_requirement.minimum_rows_for_availability,
            )
            rows = weather_path.read_text(encoding='utf-8').splitlines()
            header = rows[0]
            columns = header.split(',')
            observed_at_idx = columns.index('observed_at')
            compressed_rows = []
            for idx, row in enumerate(rows[1:]):
                values = row.split(',')
                values[observed_at_idx] = f'2026-01-01T{idx % 24:02d}:00:00+00:00'
                compressed_rows.append(','.join(values))
            weather_path.write_text(header + '\n' + '\n'.join(compressed_rows) + '\n', encoding='utf-8')
            payload = validate_partner_evidence_root(root)
            markdown = markdown_partner_evidence_validation(payload)

        weather_report = next(
            report for report in payload['reports'] if report['requirement_key'] == 'weather_station_observations'
        )
        self.assertEqual(weather_report['decision'], 'blocked_insufficient_partner_evidence_temporal_coverage')
        self.assertEqual(weather_report['row_count_shortfall'], 0)
        self.assertTrue(weather_report['sufficient_distinct_coverage'])
        self.assertFalse(weather_report['sufficient_temporal_coverage'])
        self.assertGreater(weather_report['temporal_span_shortfalls']['observed_at'], 0)
        self.assertIn('Span shortfalls', markdown)

    def test_partner_evidence_validation_requires_numeric_coverage_span(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_requirement = REQUIREMENTS[0]
            station_path = self._write_complete_evidence_file(
                root,
                requirement_index=0,
                row_count=station_requirement.minimum_rows_for_availability,
            )
            rows = station_path.read_text(encoding='utf-8').splitlines()
            header = rows[0]
            columns = header.split(',')
            elevation_idx = columns.index('elevation_m')
            compressed_rows = []
            for idx, row in enumerate(rows[1:]):
                values = row.split(',')
                values[elevation_idx] = str(3200 + idx)
                compressed_rows.append(','.join(values))
            station_path.write_text(header + '\n' + '\n'.join(compressed_rows) + '\n', encoding='utf-8')
            payload = validate_partner_evidence_root(root)

        station_report = next(
            report for report in payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(station_report['decision'], 'blocked_insufficient_partner_evidence_numeric_coverage')
        self.assertEqual(station_report['row_count_shortfall'], 0)
        self.assertTrue(station_report['sufficient_distinct_coverage'])
        self.assertFalse(station_report['sufficient_numeric_coverage'])
        self.assertGreater(station_report['numeric_span_shortfalls']['elevation_m'], 0)

    def test_partner_evidence_validation_requires_fresh_review_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_requirement = REQUIREMENTS[0]
            self._write_complete_evidence_file(
                root,
                requirement_index=0,
                row_count=station_requirement.minimum_rows_for_availability,
            )
            stale_payload = validate_partner_evidence_root(
                root,
                generated_at=datetime(2027, 6, 1, tzinfo=timezone.utc),
            )
            future_payload = validate_partner_evidence_root(
                root,
                generated_at=datetime(2025, 12, 1, tzinfo=timezone.utc),
            )

        stale_station = next(
            report for report in stale_payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        future_station = next(
            report for report in future_payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(stale_station['decision'], 'blocked_stale_partner_evidence_review')
        self.assertEqual(stale_station['review_freshness_status'], 'blocked_stale_reviewed_at')
        self.assertEqual(stale_station['stale_review_row_count'], station_requirement.minimum_rows_for_availability)
        self.assertEqual(future_station['decision'], 'blocked_future_partner_evidence_review')
        self.assertEqual(future_station['review_freshness_status'], 'blocked_future_reviewed_at')
        self.assertEqual(future_station['future_review_row_count'], station_requirement.minimum_rows_for_availability)

    def test_partner_evidence_validation_requires_hash_qualified_source_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_requirement = REQUIREMENTS[0]
            station_path = self._write_complete_evidence_file(
                root,
                requirement_index=0,
                row_count=station_requirement.minimum_rows_for_availability,
            )
            self._rewrite_column(station_path, 'source_ref', 'reviewed-source-package')
            payload = validate_partner_evidence_root(root)

        station_report = next(
            report for report in payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(station_report['decision'], 'blocked_invalid_partner_evidence_values')
        self.assertEqual(station_report['source_ref_integrity_status'], 'blocked_unverified_source_refs')
        self.assertEqual(station_report['source_ref_issue_count'], station_requirement.minimum_rows_for_availability)
        self.assertEqual(station_report['invalid_value_examples'][0]['column'], 'source_ref')

    def test_partner_evidence_validation_requires_source_hash_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_requirement = REQUIREMENTS[0]
            self._write_complete_evidence_file(
                root,
                requirement_index=0,
                row_count=station_requirement.minimum_rows_for_availability,
            )
            missing_manifest_payload = validate_partner_evidence_root(root)
            incomplete_manifest_payload = validate_partner_evidence_root(
                root,
                partner_source_manifest=self._partner_source_manifest({'9' * 64}),
            )

        missing_manifest_station = next(
            report
            for report in missing_manifest_payload['reports']
            if report['requirement_key'] == 'station_metadata'
        )
        incomplete_manifest_station = next(
            report
            for report in incomplete_manifest_payload['reports']
            if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(missing_manifest_station['decision'], 'blocked_partner_source_manifest')
        self.assertEqual(
            missing_manifest_station['source_ref_manifest_status'],
            'blocked_manifest_missing_or_invalid',
        )
        self.assertEqual(incomplete_manifest_station['decision'], 'blocked_partner_source_manifest')
        self.assertEqual(
            incomplete_manifest_station['source_ref_manifest_status'],
            'blocked_missing_manifest_hashes',
        )

    def test_partner_evidence_validation_verifies_local_file_source_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            source_dir = root / 'raw_sources'
            source_dir.mkdir()
            source_file = source_dir / 'station_metadata_source.csv'
            source_file.write_text('station source fixture\n', encoding='utf-8')
            digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
            station_requirement = REQUIREMENTS[0]
            station_path = self._write_complete_evidence_file(
                root,
                requirement_index=0,
                row_count=station_requirement.minimum_rows_for_availability,
            )
            self._rewrite_column(
                station_path,
                'source_ref',
                f'file:raw_sources/station_metadata_source.csv#sha256={digest}',
            )
            payload = validate_partner_evidence_root(
                root,
                partner_source_manifest=self._partner_source_manifest({digest}),
            )

        station_report = next(
            report for report in payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(station_report['decision'], 'available_reviewed_partner_evidence')
        self.assertEqual(station_report['source_ref_integrity_status'], 'passed')
        self.assertEqual(station_report['source_ref_issue_count'], 0)
        self.assertEqual(
            station_report['source_ref_integrity_counts'],
            {'local_file': station_requirement.minimum_rows_for_availability},
        )

    def test_partner_evidence_validation_blocks_unresolved_or_mismatched_file_source_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            station_requirement = REQUIREMENTS[0]
            station_path = self._write_complete_evidence_file(
                root,
                requirement_index=0,
                row_count=station_requirement.minimum_rows_for_availability,
            )
            self._rewrite_column(
                station_path,
                'source_ref',
                'file:raw_sources/missing.csv#sha256=' + '1' * 64,
            )
            missing_payload = validate_partner_evidence_root(
                root,
                partner_source_manifest=self._partner_source_manifest({'1' * 64}),
            )
            source_dir = root / 'raw_sources'
            source_dir.mkdir()
            source_file = source_dir / 'station_metadata_source.csv'
            source_file.write_text('station source fixture\n', encoding='utf-8')
            self._rewrite_column(
                station_path,
                'source_ref',
                'file:raw_sources/station_metadata_source.csv#sha256=' + '2' * 64,
            )
            mismatch_payload = validate_partner_evidence_root(
                root,
                partner_source_manifest=self._partner_source_manifest({'2' * 64}),
            )

        missing_station = next(
            report for report in missing_payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        mismatch_station = next(
            report for report in mismatch_payload['reports'] if report['requirement_key'] == 'station_metadata'
        )
        self.assertEqual(missing_station['decision'], 'blocked_unverified_partner_evidence_source_refs')
        self.assertEqual(missing_station['source_ref_integrity_status'], 'blocked_unverified_source_refs')
        self.assertIn('does not resolve', missing_station['source_ref_issue_examples'][0]['error'])
        self.assertEqual(mismatch_station['decision'], 'blocked_unverified_partner_evidence_source_refs')
        self.assertIn('does not match', mismatch_station['source_ref_issue_examples'][0]['error'])

    def test_partner_evidence_validation_can_drive_contract_missing_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            for idx, requirement in enumerate(REQUIREMENTS):
                row_count = requirement.minimum_rows_for_availability
                if requirement.key == 'warning_region_polygons':
                    row_count = 3
                self._write_complete_evidence_file(
                    root,
                    requirement_index=idx,
                    row_count=row_count,
                )
            validation = validate_partner_evidence_root(
                root,
                partner_source_manifest=self._partner_source_manifest(),
            )
            contract = build_contract(
                status_overrides=validation['status_overrides'],
                partner_evidence_validation=validation,
            )
            markdown = markdown_partner_evidence_validation(validation)

        self.assertEqual(validation['decision'], 'all_partner_evidence_available')
        self.assertEqual(set(validation['status_overrides'].values()), {STATUS_AVAILABLE})
        self.assertEqual(contract['missing_requirements'], [])
        self.assertFalse(contract['himalayan_accuracy_claim_allowed'])
        self.assertEqual(set(contract['blocked_release_gates']), set(REQUIRED_RELEASE_GATES))
        self.assertIn('all_partner_evidence_available', markdown)

    def test_cli_accepts_structurally_complete_partner_package_but_blocks_claim_without_release_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            package_root = root / 'synthetic_partner_package'
            source_manifest_path = self._write_complete_synthetic_partner_package(package_root)
            contract_path = root / 'readiness_contract.json'
            evidence_validation_path = root / 'partner_evidence_validation.json'
            source_validation_path = root / 'partner_source_manifest_validation.json'

            exit_code = build_himalayan_contract_main(
                [
                    '--output',
                    str(contract_path),
                    '--partner-evidence-root',
                    str(package_root),
                    '--partner-source-manifest',
                    str(source_manifest_path),
                    '--partner-evidence-validation-output',
                    str(evidence_validation_path),
                    '--partner-source-manifest-validation-output',
                    str(source_validation_path),
                ]
            )
            contract = json.loads(contract_path.read_text(encoding='utf-8'))
            evidence_validation = json.loads(evidence_validation_path.read_text(encoding='utf-8'))
            source_validation = json.loads(source_validation_path.read_text(encoding='utf-8'))

        self.assertEqual(exit_code, 0)
        self.assertEqual(source_validation['decision'], 'partner_source_manifest_available')
        self.assertEqual(evidence_validation['decision'], 'all_partner_evidence_available')
        self.assertEqual(set(evidence_validation['status_overrides'].values()), {STATUS_AVAILABLE})
        self.assertEqual(contract['missing_requirements'], [])
        self.assertEqual(set(contract['blocked_release_gates']), set(REQUIRED_RELEASE_GATES))
        self.assertFalse(contract['himalayan_accuracy_claim_allowed'])
        self.assertFalse(contract['production_scoring_allowed'])

    def test_contract_rejects_stale_partner_evidence_validation_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            validation = validate_partner_evidence_root(root)

        stale_schema = dict(validation)
        stale_schema['schema_version'] = 'himalayan_accuracy_partner_evidence_validation_v1'
        with self.assertRaisesRegex(ValueError, 'schema mismatch'):
            build_contract(partner_evidence_validation=stale_schema)

        stale_policy = dict(validation)
        stale_policy['validation_policy_version'] = 'old_policy'
        with self.assertRaisesRegex(ValueError, 'policy mismatch'):
            build_contract(partner_evidence_validation=stale_policy)

    def test_partner_evidence_validation_blocks_orphan_station_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            self._write_complete_evidence_file(
                root,
                requirement_index=0,
                row_count=REQUIREMENTS[0].minimum_rows_for_availability,
            )
            weather_path = self._write_complete_evidence_file(
                root,
                requirement_index=1,
                row_count=REQUIREMENTS[1].minimum_rows_for_availability,
            )
            self._rewrite_column_values(weather_path, 'station_id', lambda idx: f'unknown_station_{idx % 3}')
            payload = validate_partner_evidence_root(
                root,
                partner_source_manifest=self._partner_source_manifest(),
            )
            markdown = markdown_partner_evidence_validation(payload)

        weather_report = next(
            report for report in payload['reports'] if report['requirement_key'] == 'weather_station_observations'
        )
        self.assertEqual(weather_report['decision'], 'blocked_partner_evidence_orphan_references')
        self.assertEqual(weather_report['status'], 'partner_required')
        self.assertEqual(weather_report['reference_check_status'], 'blocked_orphan_references')
        self.assertEqual(weather_report['reference_violations'][0]['target_requirement'], 'station_metadata')
        self.assertEqual(
            weather_report['reference_violations'][0]['missing_reference_examples'],
            ['unknown_station_0', 'unknown_station_1', 'unknown_station_2'],
        )
        self.assertIn('Reference check', markdown)

    def test_partner_evidence_validation_blocks_region_references_without_polygons(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write_partner_evidence_templates(root)
            self._write_complete_evidence_file(
                root,
                requirement_index=3,
                row_count=REQUIREMENTS[3].minimum_rows_for_availability,
            )
            payload = validate_partner_evidence_root(
                root,
                partner_source_manifest=self._partner_source_manifest(),
            )

        danger_report = next(
            report for report in payload['reports'] if report['requirement_key'] == 'danger_labels_and_bulletins'
        )
        self.assertEqual(danger_report['decision'], 'blocked_partner_evidence_reference_unavailable')
        self.assertEqual(danger_report['status'], 'partner_required')
        self.assertEqual(danger_report['reference_check_status'], 'blocked_reference_unavailable')
        self.assertEqual(danger_report['reference_violations'][0]['target_requirement'], 'warning_region_polygons')


class EventRatioTests(unittest.TestCase):
    def test_compute_event_ratio_bins_basic(self) -> None:
        probs = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
        events = [0, 0, 0, 1, 0, 1, 1, 1, 1, 1]
        bins = compute_event_ratio_bins(probs, events, n_bins=10)
        self.assertEqual(len(bins), 10)
        self.assertEqual(bins[0].n_predictions, 1)
        self.assertEqual(bins[0].n_events, 0)
        self.assertAlmostEqual(bins[0].event_ratio, 0.0)
        self.assertEqual(bins[9].n_predictions, 1)
        self.assertEqual(bins[9].n_events, 1)
        self.assertAlmostEqual(bins[9].event_ratio, 1.0)

    def test_event_ratio_monotonic_increase(self) -> None:
        probs = [0.05, 0.05, 0.15, 0.15, 0.25, 0.25, 0.35, 0.35, 0.45, 0.45,
                 0.55, 0.55, 0.65, 0.65, 0.75, 0.75, 0.85, 0.85, 0.95, 0.95]
        events = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                  1, 0, 1, 0, 1, 1, 1, 1, 1, 1]
        bins = compute_event_ratio_bins(probs, events, n_bins=10)
        payload = event_ratio_to_dict(bins)
        self.assertTrue(payload['discriminatory_skill_summary']['monotonic_increase'])

    def test_event_ratio_empty_input(self) -> None:
        bins = compute_event_ratio_bins([], [], n_bins=10)
        self.assertEqual(len(bins), 0)
        payload = event_ratio_to_dict(bins)
        self.assertEqual(payload['n_bins'], 0)

    def test_event_ratio_length_mismatch_raises(self) -> None:
        with self.assertRaisesRegex(ValueError, 'Length mismatch'):
            compute_event_ratio_bins([0.1, 0.2], [0], n_bins=10)

    def test_event_ratio_to_dict_schema(self) -> None:
        bins = compute_event_ratio_bins([0.1, 0.9], [0, 1], n_bins=10)
        payload = event_ratio_to_dict(bins)
        self.assertEqual(payload['schema_version'], 'event_ratio_validation_v1')
        self.assertIn('bins', payload)
        self.assertIn('discriminatory_skill_summary', payload)

    def test_markdown_event_ratio_report(self) -> None:
        bins = compute_event_ratio_bins([0.1, 0.9], [0, 1], n_bins=10)
        payload = event_ratio_to_dict(bins)
        md = markdown_event_ratio_report(payload)
        self.assertIn('# Event Ratio Validation Report', md)
        self.assertIn('| Bin | Prob Range', md)
        self.assertIn('Discriminatory Skill Summary', md)


if __name__ == '__main__':
    unittest.main()
