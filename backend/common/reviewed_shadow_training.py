"""Strict preflight for reviewed, shadow-only training candidates.

This module does not train, promote, or alter public scores.  It mirrors the
database trigger contract so exported review packets can be audited locally
before any future shadow-training workflow consumes them.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Any

from backend.common.evidence_replay import replay_is_grounded_for_shadow_training


ALLOWED_MODEL_ERROR_VERDICTS = {
    'model_plausible',
    'model_false_positive',
    'model_false_negative',
    'model_miscalibrated',
}
ALLOWED_REVIEW_VERDICTS = {'accepted', 'rejected'}
AUTO_OR_SYNTHETIC_SIGNAL_KEYS = frozenset({
    'auto_label',
    'auto_labelled',
    'auto_labeled',
    'auto_generated',
    'synthetic',
    'synthetic_demo',
    'synthetic_inputs_present',
    'has_synthetic_evidence',
})
AUTO_OR_SYNTHETIC_SIGNAL_VALUES = frozenset({
    'synthetic_scenario',
    'machine_extracted_news_unreviewed',
    'auto_label',
    'auto_generated',
})


def _record(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


@dataclass(frozen=True)
class ShadowTrainingDecision:
    eligible: bool
    reasons: tuple[str, ...]
    candidate: dict[str, Any] | None = None


def _replay_from_case(case: Mapping[str, Any]) -> dict[str, Any]:
    cell_snapshot = _record(case.get('cell_snapshot'))
    evidence = _record(case.get('evidence'))
    return _record(cell_snapshot.get('evidence_replay')) or _record(evidence.get('evidence_replay'))


def _contains_auto_or_synthetic_signal(value: Any) -> bool:
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower()
            if key in AUTO_OR_SYNTHETIC_SIGNAL_KEYS and item not in (None, False, '', [], {}):
                return True
            if _contains_auto_or_synthetic_signal(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_contains_auto_or_synthetic_signal(item) for item in value)
    return isinstance(value, str) and value.strip().lower() in AUTO_OR_SYNTHETIC_SIGNAL_VALUES


def _priority(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def evaluate_reviewed_shadow_training_case(
    case: Mapping[str, Any],
    reviews: Sequence[Mapping[str, Any]],
) -> ShadowTrainingDecision:
    """Fail closed unless a reviewed case has grounded evidence and consensus."""
    case_record = _record(case)
    reasons: list[str] = []
    if case_record.get('status') != 'reviewed':
        reasons.append('case_not_reviewed')
    if case_record.get('case_origin') != 'forecast_publication':
        reasons.append('case_not_machine_materialized')
    if not case_record.get('forecast_run_id'):
        reasons.append('missing_forecast_run_id')
    if not case_record.get('region_key'):
        reasons.append('missing_region_key')
    if case_record.get('cell_row') is None or case_record.get('cell_col') is None:
        reasons.append('missing_cell_coordinates')

    replay = _replay_from_case(case_record)
    if not replay:
        reasons.append('missing_evidence_replay')
    elif not replay_is_grounded_for_shadow_training(replay, case=case_record):
        reasons.append('replay_not_grounded_or_not_fingerprinted')
    if _contains_auto_or_synthetic_signal({
        'evidence': _record(case_record.get('evidence')),
        'cell_snapshot': _record(case_record.get('cell_snapshot')),
        'model_metadata': _record(case_record.get('model_metadata')),
    }):
        reasons.append('auto_label_or_synthetic_signal_present')

    case_id = str(case_record.get('id') or '')
    case_reviews = [
        _record(review) for review in reviews
        if str(_record(review).get('case_id') or '') == case_id
    ]
    required_reviewers = 2 if case_record.get('requires_two_reviewers') is True or _priority(case_record.get('priority')) >= 5 else 1
    reviewer_ids = {str(review.get('reviewer_id')) for review in case_reviews if review.get('reviewer_id')}
    if len(reviewer_ids) < required_reviewers:
        reasons.append('insufficient_distinct_reviewers')
    verdicts = {str(review.get('verdict') or '') for review in case_reviews}
    if not verdicts or not verdicts <= ALLOWED_REVIEW_VERDICTS:
        reasons.append('review_verdict_not_training_eligible')
    if len(verdicts) > 1:
        reasons.append('reviewer_verdict_conflict')
    impacts = {str(review.get('claim_impact') or 'no_change') for review in case_reviews}
    if 'block' in impacts:
        reasons.append('claim_blocked')
    if any(review.get('label_quality_verdict') != 'label_reliable' for review in case_reviews):
        reasons.append('label_quality_not_reliable')
    if any(str(review.get('model_error_verdict') or '') not in ALLOWED_MODEL_ERROR_VERDICTS for review in case_reviews):
        reasons.append('model_error_verdict_not_training_eligible')

    if reasons:
        return ShadowTrainingDecision(False, tuple(dict.fromkeys(reasons)))

    raw_layers = _record(replay.get('raw_layers'))
    candidate = {
        'schema_version': 'reviewed-shadow-training-candidate/v1',
        'case_id': case_id,
        'case_origin': 'forecast_publication',
        'forecast_run_id': str(case_record['forecast_run_id']),
        'region_key': str(case_record['region_key']),
        'cell_row': int(case_record['cell_row']),
        'cell_col': int(case_record['cell_col']),
        'feature_snapshot_sha256': replay['feature_snapshot_sha256'],
        'evidence_replay_sha256': replay['replay_snapshot_sha256'],
        'feature_snapshot': raw_layers.get('feature_values') or {},
        'evidence_lineage': replay.get('lineage') or {},
        'review_ids': [str(review.get('id')) for review in case_reviews if review.get('id')],
        'review_summary': [
            {
                'reviewer_id': review.get('reviewer_id'),
                'verdict': review.get('verdict'),
                'label_quality_verdict': review.get('label_quality_verdict'),
                'model_error_verdict': review.get('model_error_verdict'),
            }
            for review in case_reviews
        ],
        'training_status': 'shadow_only',
        'production_eligible': False,
        'claim_boundary': 'reviewed_shadow_candidate_not_training_or_public_promotion',
    }
    return ShadowTrainingDecision(True, (), candidate)


def build_shadow_training_candidate_pack(
    cases: Sequence[Mapping[str, Any]],
    reviews: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    decisions = [evaluate_reviewed_shadow_training_case(case, reviews) for case in cases]
    candidates = [decision.candidate for decision in decisions if decision.candidate is not None]
    excluded = [
        {
            'case_id': str(_record(case).get('id') or ''),
            'reasons': list(decision.reasons),
        }
        for case, decision in zip(cases, decisions)
        if not decision.eligible
    ]
    return {
        'schema_version': 'reviewed-shadow-training-candidate-pack/v1',
        'summary': {
            'cases_checked': len(cases),
            'shadow_only_candidate_count': len(candidates),
            'excluded_count': len(excluded),
            'production_eligible_candidate_count': 0,
            'claim_boundary': 'shadow_candidates_are_not_training_or_public_promotion',
        },
        'candidates': candidates,
        'excluded': excluded,
    }
