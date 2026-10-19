from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.reproduction.himalayan_accuracy_contract import (
    STATUS_AVAILABLE,
    STATUS_NOT_APPLICABLE,
    build_contract,
    build_himalayan_boundary_readiness_report,
    build_himalayan_local_holdout_leakage_audit,
    build_himalayan_local_holdout_metric_report,
    build_himalayan_local_holdout_prediction_template,
    build_himalayan_local_holdout_protocol,
    build_himalayan_top10_feature_gap_matrix,
    build_partner_package_index,
    build_partner_source_manifest_starter,
    build_partner_submission_acceptance_checklist,
    build_partner_submission_manifest_diff,
    build_partner_submission_quality_score,
    build_partner_submission_review_ledger,
    build_partner_submission_status_dashboard,
    build_partner_submission_status_summary,
    load_not_applicable_waivers,
    load_partner_source_manifest,
    load_release_gate_attestations,
    load_status_overrides,
    markdown_contract,
    markdown_himalayan_boundary_readiness_report,
    markdown_himalayan_local_holdout_leakage_audit,
    markdown_himalayan_local_holdout_metric_report,
    markdown_himalayan_local_holdout_prediction_template,
    markdown_himalayan_local_holdout_protocol,
    markdown_himalayan_top10_feature_gap_matrix,
    markdown_partner_package_index,
    markdown_partner_evidence_validation,
    markdown_partner_intake_package_preflight,
    markdown_partner_source_manifest_starter,
    markdown_partner_source_manifest_validation,
    markdown_partner_submission_acceptance_checklist,
    markdown_partner_submission_manifest_diff,
    markdown_partner_submission_quality_score,
    markdown_partner_submission_review_ledger,
    markdown_partner_submission_status_dashboard,
    markdown_partner_submission_status_summary,
    validate_partner_evidence_root,
    validate_partner_intake_package_preflight,
    validate_partner_source_manifest,
    write_himalayan_local_holdout_prediction_template_csv,
)


TRIAGE_SUMMARY_SCHEMA_VERSION = 'himalayan_partner_package_triage_summary_v1'
TRIAGE_ARTIFACT_MANIFEST_SCHEMA_VERSION = 'himalayan_partner_triage_artifact_manifest_v1'

TRIAGE_ARTIFACT_PURPOSES = {
    'readiness_contract': 'Release-gated Himalayan readiness contract with production blocked.',
    'partner_intake_preflight': 'Required partner package file-presence check.',
    'partner_source_manifest_validation': 'Source owner, license, reviewer, freshness, and source package governance check.',
    'partner_source_manifest_starter': 'Fillable source-manifest starter inferred from source_ref values.',
    'partner_evidence_validation': 'Row/schema/coverage/review/license/source validation for the ten evidence CSVs.',
    'himalayan_top10_feature_gap_matrix': 'Current top-10 feature readiness matrix tied to evidence status.',
    'himalayan_local_holdout_protocol': 'Pre-registered independent holdout protocol and locked floors.',
    'himalayan_local_holdout_prediction_template': 'Prediction handoff schema for local holdout evaluation.',
    'himalayan_local_holdout_leakage_audit': 'Holdout independence and source-ref leakage audit.',
    'himalayan_local_holdout_metric_report': 'Local holdout metric report; only evaluates after leakage audit passes.',
    'partner_submission_manifest_diff': 'Required-file fingerprint and resubmission change tracking.',
    'partner_submission_summary': 'Combined first-blocker status across preflight, source, evidence, and readiness.',
    'partner_submission_quality_score': '100-point evidence-package quality score; not an accuracy metric.',
    'partner_submission_acceptance_checklist': 'Partner-side fix checklist before scientist or claim review.',
    'partner_submission_review_ledger': 'Append-only submission/resubmission review ledger.',
    'partner_package_index': 'Navigation map for partner-package artifacts and command sequence.',
    'partner_submission_status_dashboard': 'One-page operator/scientist status export.',
    'triage_source_traceability': 'Source-ref checksum plumb-through report across manifest and evidence CSVs.',
    'himalayan_boundary_readiness_report': 'Unified claim-state, D_tidy, GPxyz, holdout, uncertainty, and release-gate boundary report.',
    'triage_summary': 'One-command triage summary for the current run.',
    'himalayan_local_holdout_predictions': 'Header-only local holdout prediction CSV template.',
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Run one-command, research-only Himalayan partner package triage.'
    )
    parser.add_argument('--partner-package-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument(
        '--partner-source-manifest',
        type=Path,
        help='Defaults to <partner-package-root>/partner_source_manifest.json when present.',
    )
    parser.add_argument(
        '--status-overrides',
        type=Path,
        help='Optional JSON status overrides; available overrides still require reviewed evidence.',
    )
    parser.add_argument(
        '--not-applicable-waivers',
        type=Path,
        help='Optional JSON waiver payload for not_applicable overrides.',
    )
    parser.add_argument(
        '--release-gate-attestations',
        type=Path,
        help='Optional JSON release-gate attestations.',
    )
    parser.add_argument(
        '--local-holdout-predictions',
        type=Path,
        help='Optional predictions CSV; defaults to <partner-package-root>/himalayan_local_holdout_predictions.csv.',
    )
    parser.add_argument(
        '--previous-manifest-diff',
        type=Path,
        help='Optional previous partner_submission_manifest_diff.json for resubmission comparison.',
    )
    parser.add_argument(
        '--previous-review-ledger',
        type=Path,
        help='Optional previous partner_submission_review_ledger.json to append a new triage entry.',
    )
    return parser


def _load_json_if_present(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def _write_json_and_markdown(
    output_root: Path,
    stem: str,
    payload: dict[str, Any],
    markdown: str,
) -> None:
    (output_root / f'{stem}.json').write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    (output_root / f'{stem}.md').write_text(markdown, encoding='utf-8')


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def build_triage_artifact_manifest(
    *,
    generated_at: datetime,
    output_root: Path,
    triage_summary: dict[str, Any],
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for stem, purpose in TRIAGE_ARTIFACT_PURPOSES.items():
        suffixes = ('csv',) if stem == 'himalayan_local_holdout_predictions' else ('json', 'md')
        for suffix in suffixes:
            path = output_root / f'{stem}.{suffix}'
            records.append(
                {
                    'path': str(path),
                    'filename': path.name,
                    'artifact_key': stem,
                    'format': suffix,
                    'purpose': purpose,
                    'present': path.exists(),
                    'size_bytes': path.stat().st_size if path.exists() else 0,
                    'sha256': _sha256_file(path),
                }
            )
    missing = [record['filename'] for record in records if not record['present']]
    return {
        'schema_version': TRIAGE_ARTIFACT_MANIFEST_SCHEMA_VERSION,
        'validation_policy_version': triage_summary['validation_policy_version'],
        'usage_boundary': triage_summary['usage_boundary'],
        'generated_at': generated_at.isoformat(),
        'output_root': str(output_root),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': (
            'triage_artifact_manifest_complete'
            if not missing
            else 'blocked_triage_artifact_manifest_missing_outputs'
        ),
        'artifact_count': len(records),
        'missing_artifact_count': len(missing),
        'missing_artifacts': missing,
        'artifacts': records,
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'The manifest inventories triage artifacts only. It is not model evidence, claim review, or production authorization.',
        },
    }


def _source_hashes_from_manifest(partner_source_manifest: dict[str, Any] | None) -> set[str]:
    if not partner_source_manifest:
        return set()
    hashes: set[str] = set()
    for source in partner_source_manifest.get('sources', []):
        if not isinstance(source, dict):
            continue
        digest = str(source.get('sha256') or '').strip()
        if digest:
            hashes.add(digest)
    return hashes


def _source_hashes_from_evidence_validation(evidence_validation: dict[str, Any]) -> set[str]:
    hashes: set[str] = set()
    for report in evidence_validation.get('reports', []):
        for digest in report.get('source_ref_hashes', []):
            text = str(digest or '').strip()
            if text:
                hashes.add(text)
    return hashes


def _evidence_reports_with_manifest_issues(evidence_validation: dict[str, Any]) -> list[str]:
    return [
        str(report.get('requirement_key'))
        for report in evidence_validation.get('reports', [])
        if report.get('source_ref_manifest_status') not in {'passed', 'not_available'}
    ]


def build_triage_source_traceability(
    *,
    generated_at: datetime,
    partner_package_root: Path,
    partner_source_manifest: dict[str, Any] | None,
    source_manifest_validation: dict[str, Any],
    evidence_validation: dict[str, Any],
    readiness_contract: dict[str, Any],
    triage_summary: dict[str, Any],
) -> dict[str, Any]:
    declared_manifest_hashes = _source_hashes_from_manifest(partner_source_manifest)
    valid_manifest_hashes = set(source_manifest_validation.get('valid_source_hashes', []))
    evidence_hashes = _source_hashes_from_evidence_validation(evidence_validation)
    evidence_missing_from_manifest = sorted(evidence_hashes - valid_manifest_hashes)
    manifest_unused_by_evidence = sorted(valid_manifest_hashes - evidence_hashes)
    manifest_issues = _evidence_reports_with_manifest_issues(evidence_validation)
    synthetic_fixture_detected = (partner_package_root / 'SYNTHETIC_DO_NOT_SUBMIT.md').exists()
    safety_locks = {
        'readiness_contract_production_scoring_allowed': bool(
            readiness_contract.get('production_scoring_allowed')
        ),
        'readiness_contract_himalayan_accuracy_claim_allowed': bool(
            readiness_contract.get('himalayan_accuracy_claim_allowed')
        ),
        'triage_summary_production_scoring_allowed': bool(
            triage_summary.get('production_scoring_allowed')
        ),
        'triage_summary_himalayan_accuracy_claim_allowed': bool(
            triage_summary.get('himalayan_accuracy_claim_allowed')
        ),
    }
    safety_locks_passed = not any(safety_locks.values())
    perfect_match = (
        source_manifest_validation.get('decision') == 'partner_source_manifest_available'
        and declared_manifest_hashes == valid_manifest_hashes == evidence_hashes
        and not manifest_issues
    )
    if perfect_match and safety_locks_passed:
        decision = 'source_traceability_passed_perfect_match_claims_blocked'
    elif not safety_locks_passed:
        decision = 'blocked_source_traceability_safety_lock_violation'
    elif evidence_missing_from_manifest or manifest_issues:
        decision = 'blocked_source_traceability_manifest_mismatch'
    elif source_manifest_validation.get('decision') != 'partner_source_manifest_available':
        decision = 'blocked_source_traceability_source_manifest_unavailable'
    else:
        decision = 'source_traceability_passed_with_unused_manifest_sources'
    return {
        'schema_version': 'himalayan_partner_source_traceability_v1',
        'validation_policy_version': readiness_contract['validation_policy_version'],
        'usage_boundary': readiness_contract['usage_boundary'],
        'generated_at': generated_at.isoformat(),
        'partner_package_root': str(partner_package_root),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': decision,
        'synthetic_fixture_detected': synthetic_fixture_detected,
        'source_manifest_decision': source_manifest_validation.get('decision'),
        'evidence_validation_decision': evidence_validation.get('decision'),
        'source_hash_counts': {
            'declared_manifest_hashes': len(declared_manifest_hashes),
            'valid_manifest_hashes': len(valid_manifest_hashes),
            'evidence_source_ref_hashes': len(evidence_hashes),
            'evidence_missing_from_manifest': len(evidence_missing_from_manifest),
            'manifest_unused_by_evidence': len(manifest_unused_by_evidence),
            'evidence_reports_with_manifest_issues': len(manifest_issues),
        },
        'source_hashes': {
            'declared_manifest_hashes': sorted(declared_manifest_hashes),
            'valid_manifest_hashes': sorted(valid_manifest_hashes),
            'evidence_source_ref_hashes': sorted(evidence_hashes),
            'evidence_missing_from_manifest': evidence_missing_from_manifest,
            'manifest_unused_by_evidence': manifest_unused_by_evidence,
            'evidence_reports_with_manifest_issues': manifest_issues,
        },
        'safety_locks': safety_locks,
        'safety_locks_passed': safety_locks_passed,
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'This report verifies checksum traceability only. Synthetic or traceability-pass status cannot authorize claims or production scoring.',
        },
    }


def markdown_triage_source_traceability(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Source Traceability',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This report checks SHA-256 plumb-through from `partner_source_manifest.json` to evidence CSV `source_ref` values. It is not model evidence.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Synthetic fixture detected | `{str(payload['synthetic_fixture_detected']).lower()}` |",
        f"| Safety locks passed | `{str(payload['safety_locks_passed']).lower()}` |",
        f"| Source manifest decision | `{payload['source_manifest_decision']}` |",
        f"| Evidence validation decision | `{payload['evidence_validation_decision']}` |",
        '',
        '## Source Hash Counts',
        '',
        '| Count | Value |',
        '|---|---:|',
    ]
    for key, value in payload['source_hash_counts'].items():
        lines.append(f'| `{key}` | {value} |')
    lines.extend(['', '## Safety Locks', '', '| Lock | Value |', '|---|---:|'])
    for key, value in payload['safety_locks'].items():
        lines.append(f'| `{key}` | `{str(value).lower()}` |')
    lines.append('')
    return '\n'.join(lines)


def markdown_triage_artifact_manifest(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Triage Artifact Manifest',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This manifest records the files emitted by the one-command triage wrapper with sizes and SHA-256 digests. It is provenance only.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| Artifact count | {payload['artifact_count']} |",
        f"| Missing artifacts | {payload['missing_artifact_count']} |",
        '',
        '## Artifacts',
        '',
        '| Artifact | Format | Present | Size bytes | SHA-256 | Purpose |',
        '|---|---|---:|---:|---|---|',
    ]
    for record in payload['artifacts']:
        sha = record['sha256'] or 'missing'
        lines.append(
            f"| `{record['filename']}` | `{record['format']}` | "
            f"`{str(record['present']).lower()}` | {record['size_bytes']} | `{sha}` | {record['purpose']} |"
        )
    lines.append('')
    return '\n'.join(lines)


def _derive_status_overrides(
    *,
    requested_overrides: dict[str, str],
    evidence_validation: dict[str, Any],
) -> dict[str, str]:
    evidence_statuses = dict(evidence_validation.get('status_overrides', {}))
    invalid_available_overrides = [
        key
        for key, value in requested_overrides.items()
        if value == STATUS_AVAILABLE and evidence_statuses.get(key) != STATUS_AVAILABLE
    ]
    if invalid_available_overrides:
        raise ValueError(
            'cannot mark Himalayan evidence available without reviewed partner evidence files: '
            f'{invalid_available_overrides}'
        )
    not_applicable_overrides = {
        key: value for key, value in requested_overrides.items() if value == STATUS_NOT_APPLICABLE
    }
    return {**evidence_statuses, **not_applicable_overrides}


def _first_blocker(summary: dict[str, Any]) -> str | None:
    return summary.get('first_blocker') or None


def build_triage_summary(
    *,
    generated_at: datetime,
    partner_package_root: Path,
    output_root: Path,
    intake_preflight: dict[str, Any],
    source_manifest_validation: dict[str, Any],
    evidence_validation: dict[str, Any],
    readiness_contract: dict[str, Any],
    leakage_audit: dict[str, Any],
    metric_report: dict[str, Any],
    submission_summary: dict[str, Any],
    quality_score: dict[str, Any],
    acceptance_checklist: dict[str, Any],
    dashboard: dict[str, Any],
) -> dict[str, Any]:
    first_blocker = _first_blocker(submission_summary)
    if acceptance_checklist.get('claim_review_ready') is True:
        decision = 'triage_complete_claim_review_ready_release_gate_review_required'
    elif acceptance_checklist.get('scientist_review_ready') is True:
        decision = 'triage_complete_scientist_review_ready_release_gates_pending'
    else:
        decision = 'triage_complete_partner_action_required'
    return {
        'schema_version': TRIAGE_SUMMARY_SCHEMA_VERSION,
        'validation_policy_version': readiness_contract['validation_policy_version'],
        'usage_boundary': readiness_contract['usage_boundary'],
        'generated_at': generated_at.isoformat(),
        'partner_package_root': str(partner_package_root),
        'output_root': str(output_root),
        'production_scoring_allowed': False,
        'himalayan_accuracy_claim_allowed': False,
        'decision': decision,
        'first_blocker': first_blocker,
        'referenced_decisions': {
            'intake_preflight': intake_preflight['decision'],
            'source_manifest_validation': source_manifest_validation['decision'],
            'partner_evidence_validation': evidence_validation['decision'],
            'readiness_contract': readiness_contract['decision'],
            'local_holdout_leakage_audit': leakage_audit['decision'],
            'local_holdout_metric_report': metric_report['decision'],
            'submission_summary': submission_summary['decision'],
            'quality_score': quality_score['decision'],
            'acceptance_checklist': acceptance_checklist['decision'],
            'status_dashboard': dashboard['decision'],
        },
        'score': {
            'partner_submission_quality_score': quality_score['score'],
            'max_score': quality_score['max_score'],
            'readiness_band': quality_score['readiness_band'],
        },
        'next_actions': submission_summary.get('next_actions', []) or dashboard.get('next_actions', []),
        'claim_boundary': {
            'himalayan_accuracy_claim_allowed': False,
            'production_scoring_allowed': False,
            'reason': 'This wrapper triages partner evidence only. It does not run production scoring, authorize deployment, or make a Himalayan accuracy claim.',
        },
    }


def markdown_triage_summary(payload: dict[str, Any]) -> str:
    lines = [
        '# Himalayan Partner Package Triage Summary',
        '',
        f"Decision: `{payload['decision']}`",
        '',
        'This is a one-command operator summary for incoming partner evidence. It is not a model accuracy result and does not authorize production scoring.',
        '',
        '| Gate | Value |',
        '|---|---:|',
        f"| Production scoring allowed | `{str(payload['production_scoring_allowed']).lower()}` |",
        f"| Himalayan accuracy claim allowed | `{str(payload['himalayan_accuracy_claim_allowed']).lower()}` |",
        f"| First blocker | `{payload['first_blocker'] or 'none'}` |",
        f"| Quality score | {payload['score']['partner_submission_quality_score']} / {payload['score']['max_score']} |",
        f"| Readiness band | `{payload['score']['readiness_band']}` |",
        '',
        '## Referenced Decisions',
        '',
        '| Artifact | Decision |',
        '|---|---|',
    ]
    for key, decision in payload['referenced_decisions'].items():
        lines.append(f'| `{key}` | `{decision}` |')
    lines.extend(['', '## Next Actions', ''])
    if payload['next_actions']:
        for action in payload['next_actions']:
            lines.append(f'- {action}')
    else:
        lines.append('- None')
    lines.append('')
    return '\n'.join(lines)


def run_triage(
    *,
    partner_package_root: Path,
    output_root: Path,
    partner_source_manifest_path: Path | None = None,
    status_overrides_path: Path | None = None,
    not_applicable_waivers_path: Path | None = None,
    release_gate_attestations_path: Path | None = None,
    local_holdout_predictions_path: Path | None = None,
    previous_manifest_diff_path: Path | None = None,
    previous_review_ledger_path: Path | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc)
    output_root.mkdir(parents=True, exist_ok=True)
    partner_source_manifest_path = partner_source_manifest_path or (
        partner_package_root / 'partner_source_manifest.json'
    )
    if not partner_source_manifest_path.exists():
        partner_source_manifest_path = None
    partner_source_manifest = load_partner_source_manifest(partner_source_manifest_path)
    requested_status_overrides = load_status_overrides(status_overrides_path)
    not_applicable_waivers = load_not_applicable_waivers(not_applicable_waivers_path)
    release_gate_attestations = load_release_gate_attestations(release_gate_attestations_path)

    intake_preflight = validate_partner_intake_package_preflight(
        partner_package_root,
        generated_at=generated_at,
    )
    source_manifest_validation = validate_partner_source_manifest(
        partner_source_manifest,
        generated_at=generated_at,
    )
    source_manifest_starter = build_partner_source_manifest_starter(
        partner_package_root,
        generated_at=generated_at,
    )
    evidence_validation = validate_partner_evidence_root(
        partner_package_root,
        generated_at=generated_at,
        partner_source_manifest=partner_source_manifest,
    )
    status_overrides = _derive_status_overrides(
        requested_overrides=requested_status_overrides,
        evidence_validation=evidence_validation,
    )
    readiness_contract = build_contract(
        status_overrides=status_overrides,
        generated_at=generated_at,
        partner_evidence_validation=evidence_validation,
        not_applicable_waivers=not_applicable_waivers,
        release_gate_attestations=release_gate_attestations,
    )
    top10_feature_gap_matrix = build_himalayan_top10_feature_gap_matrix(
        generated_at=generated_at,
        readiness_contract=readiness_contract,
    )
    holdout_protocol = build_himalayan_local_holdout_protocol(generated_at=generated_at)
    holdout_prediction_template = build_himalayan_local_holdout_prediction_template(
        generated_at=generated_at,
    )
    leakage_audit = build_himalayan_local_holdout_leakage_audit(
        partner_package_root,
        generated_at=generated_at,
        partner_source_manifest=partner_source_manifest,
        protocol=holdout_protocol,
    )
    local_holdout_predictions_path = local_holdout_predictions_path or (
        partner_package_root / 'himalayan_local_holdout_predictions.csv'
    )
    metric_report = build_himalayan_local_holdout_metric_report(
        partner_package_root,
        generated_at=generated_at,
        leakage_audit=leakage_audit,
        partner_source_manifest=partner_source_manifest,
        predictions_path=local_holdout_predictions_path,
        protocol=holdout_protocol,
    )
    previous_manifest_diff = _load_json_if_present(previous_manifest_diff_path)
    manifest_diff = build_partner_submission_manifest_diff(
        partner_package_root,
        previous_snapshot=previous_manifest_diff,
        generated_at=generated_at,
    )
    submission_summary = build_partner_submission_status_summary(
        generated_at=generated_at,
        intake_preflight=intake_preflight,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
    )
    quality_score = build_partner_submission_quality_score(
        generated_at=generated_at,
        intake_preflight=intake_preflight,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
    )
    acceptance_checklist = build_partner_submission_acceptance_checklist(
        generated_at=generated_at,
        quality_score=quality_score,
    )
    previous_review_ledger = _load_json_if_present(previous_review_ledger_path)
    review_ledger = build_partner_submission_review_ledger(
        generated_at=generated_at,
        package_root=partner_package_root,
        previous_ledger=previous_review_ledger,
        manifest_diff=manifest_diff,
        intake_preflight=intake_preflight,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
        quality_score=quality_score,
        acceptance_checklist=acceptance_checklist,
        submission_summary=submission_summary,
    )
    package_index = build_partner_package_index(generated_at=generated_at)
    dashboard = build_partner_submission_status_dashboard(
        generated_at=generated_at,
        package_index=package_index,
        review_ledger=review_ledger,
        submission_summary=submission_summary,
        quality_score=quality_score,
        acceptance_checklist=acceptance_checklist,
        top10_feature_gap_matrix=top10_feature_gap_matrix,
        readiness_contract=readiness_contract,
    )
    triage_summary = build_triage_summary(
        generated_at=generated_at,
        partner_package_root=partner_package_root,
        output_root=output_root,
        intake_preflight=intake_preflight,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
        leakage_audit=leakage_audit,
        metric_report=metric_report,
        submission_summary=submission_summary,
        quality_score=quality_score,
        acceptance_checklist=acceptance_checklist,
        dashboard=dashboard,
    )
    source_traceability = build_triage_source_traceability(
        generated_at=generated_at,
        partner_package_root=partner_package_root,
        partner_source_manifest=partner_source_manifest,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
        triage_summary=triage_summary,
    )
    boundary_readiness_report = build_himalayan_boundary_readiness_report(
        generated_at=generated_at,
        intake_preflight=intake_preflight,
        source_manifest_validation=source_manifest_validation,
        evidence_validation=evidence_validation,
        readiness_contract=readiness_contract,
        leakage_audit=leakage_audit,
        metric_report=metric_report,
        submission_summary=submission_summary,
        quality_score=quality_score,
        acceptance_checklist=acceptance_checklist,
        source_traceability=source_traceability,
    )

    _write_json_and_markdown(
        output_root,
        'readiness_contract',
        readiness_contract,
        markdown_contract(readiness_contract),
    )
    _write_json_and_markdown(
        output_root,
        'partner_intake_preflight',
        intake_preflight,
        markdown_partner_intake_package_preflight(intake_preflight),
    )
    _write_json_and_markdown(
        output_root,
        'partner_source_manifest_validation',
        source_manifest_validation,
        markdown_partner_source_manifest_validation(source_manifest_validation),
    )
    _write_json_and_markdown(
        output_root,
        'partner_source_manifest_starter',
        source_manifest_starter,
        markdown_partner_source_manifest_starter(source_manifest_starter),
    )
    _write_json_and_markdown(
        output_root,
        'partner_evidence_validation',
        evidence_validation,
        markdown_partner_evidence_validation(evidence_validation),
    )
    _write_json_and_markdown(
        output_root,
        'himalayan_top10_feature_gap_matrix',
        top10_feature_gap_matrix,
        markdown_himalayan_top10_feature_gap_matrix(top10_feature_gap_matrix),
    )
    _write_json_and_markdown(
        output_root,
        'himalayan_local_holdout_protocol',
        holdout_protocol,
        markdown_himalayan_local_holdout_protocol(holdout_protocol),
    )
    _write_json_and_markdown(
        output_root,
        'himalayan_local_holdout_prediction_template',
        holdout_prediction_template,
        markdown_himalayan_local_holdout_prediction_template(holdout_prediction_template),
    )
    write_himalayan_local_holdout_prediction_template_csv(
        output_root / 'himalayan_local_holdout_predictions.csv'
    )
    _write_json_and_markdown(
        output_root,
        'himalayan_local_holdout_leakage_audit',
        leakage_audit,
        markdown_himalayan_local_holdout_leakage_audit(leakage_audit),
    )
    _write_json_and_markdown(
        output_root,
        'himalayan_local_holdout_metric_report',
        metric_report,
        markdown_himalayan_local_holdout_metric_report(metric_report),
    )
    _write_json_and_markdown(
        output_root,
        'partner_submission_manifest_diff',
        manifest_diff,
        markdown_partner_submission_manifest_diff(manifest_diff),
    )
    _write_json_and_markdown(
        output_root,
        'partner_submission_summary',
        submission_summary,
        markdown_partner_submission_status_summary(submission_summary),
    )
    _write_json_and_markdown(
        output_root,
        'partner_submission_quality_score',
        quality_score,
        markdown_partner_submission_quality_score(quality_score),
    )
    _write_json_and_markdown(
        output_root,
        'partner_submission_acceptance_checklist',
        acceptance_checklist,
        markdown_partner_submission_acceptance_checklist(acceptance_checklist),
    )
    _write_json_and_markdown(
        output_root,
        'partner_submission_review_ledger',
        review_ledger,
        markdown_partner_submission_review_ledger(review_ledger),
    )
    _write_json_and_markdown(
        output_root,
        'partner_package_index',
        package_index,
        markdown_partner_package_index(package_index),
    )
    _write_json_and_markdown(
        output_root,
        'partner_submission_status_dashboard',
        dashboard,
        markdown_partner_submission_status_dashboard(dashboard),
    )
    _write_json_and_markdown(
        output_root,
        'triage_source_traceability',
        source_traceability,
        markdown_triage_source_traceability(source_traceability),
    )
    _write_json_and_markdown(
        output_root,
        'himalayan_boundary_readiness_report',
        boundary_readiness_report,
        markdown_himalayan_boundary_readiness_report(boundary_readiness_report),
    )
    _write_json_and_markdown(
        output_root,
        'triage_summary',
        triage_summary,
        markdown_triage_summary(triage_summary),
    )
    triage_artifact_manifest = build_triage_artifact_manifest(
        generated_at=generated_at,
        output_root=output_root,
        triage_summary=triage_summary,
    )
    _write_json_and_markdown(
        output_root,
        'triage_artifact_manifest',
        triage_artifact_manifest,
        markdown_triage_artifact_manifest(triage_artifact_manifest),
    )
    return triage_summary


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_triage(
        partner_package_root=args.partner_package_root,
        output_root=args.output_root,
        partner_source_manifest_path=args.partner_source_manifest,
        status_overrides_path=args.status_overrides,
        not_applicable_waivers_path=args.not_applicable_waivers,
        release_gate_attestations_path=args.release_gate_attestations,
        local_holdout_predictions_path=args.local_holdout_predictions,
        previous_manifest_diff_path=args.previous_manifest_diff,
        previous_review_ledger_path=args.previous_review_ledger,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
