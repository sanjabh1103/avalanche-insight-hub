from __future__ import annotations

import argparse
import json
from typing import Any

from backend.common.supabase_io import (
    fetch_latest_model_status_row,
    has_supabase_credentials,
    patch_latest_model_status_row,
)


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fetch_model_status_row() -> dict[str, Any]:
    if not has_supabase_credentials():
        raise RuntimeError('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required')
    row = fetch_latest_model_status_row()
    if not row:
        raise RuntimeError('model_status row not found')
    return row


def _candidate_blockers(candidate: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if not bool(candidate.get('enabled')):
        blockers.append('candidate_not_enabled')
    if not bool(candidate.get('ready_for_activation')):
        blockers.append(str(candidate.get('blocked_gate') or 'candidate_not_ready'))
    gates = _as_dict(candidate.get('gates'))
    if not bool(gates.get('shadow_quality_gate_passed')):
        blockers.append('shadow_quality_gate')
    if not bool(gates.get('sar_release_gate_passed')):
        blockers.append('sar_release_gate')
    if not bool(gates.get('sar_volume_gate_passed')):
        blockers.append('sar_volume_gate')
    if not bool(gates.get('production_eligibility_gate_passed')):
        blockers.append('production_eligibility_gate')
    deduped: list[str] = []
    for blocker in blockers:
        if blocker not in deduped:
            deduped.append(blocker)
    return deduped


def activate_dynamic_model_candidate(
    *,
    execute_activation: bool,
    required_candidate_version: str | None = None,
) -> dict[str, Any]:
    row = _fetch_model_status_row()
    candidate = _as_dict(row.get('dynamic_model_candidate'))
    if not candidate:
        raise RuntimeError('dynamic_model_candidate is empty; train a candidate before activation')
    candidate_type = str(candidate.get('dynamic_model_type') or 'mts_lstm_v1')
    candidate_version = str(candidate.get('dynamic_model_version') or 'unknown')
    if required_candidate_version and candidate_version != required_candidate_version:
        raise RuntimeError(
            f'candidate version mismatch: expected {required_candidate_version}, found {candidate_version}'
        )
    blockers = _candidate_blockers(candidate)
    already_active = (
        str(row.get('active_model_type') or '') == candidate_type
        and str(row.get('active_model_version') or '') == candidate_version
    )
    result = {
        'status': 'ok',
        'candidate_type': candidate_type,
        'candidate_version': candidate_version,
        'ready_for_activation': bool(candidate.get('ready_for_activation')),
        'already_active': already_active,
        'blockers': blockers,
        'execute_activation': execute_activation,
        'action': 'noop' if already_active else 'activate' if execute_activation and not blockers else 'dry_run',
    }
    if blockers or already_active or not execute_activation:
        return result
    patch_latest_model_status_row(
        {
            'active_model_type': candidate_type,
            'active_model_version': candidate_version,
            'promotion_gate_passed': True,
            'shadow_mode_active': False,
        },
    )
    result['activation_applied'] = True
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Dry-run or explicitly activate the current MTS-LSTM candidate scorer',
    )
    parser.add_argument('--execute-activation', action='store_true', help='Actually activate the candidate scorer')
    parser.add_argument('--required-candidate-version', default='', help='Optional safety pin for the expected candidate version')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = activate_dynamic_model_candidate(
        execute_activation=bool(args.execute_activation),
        required_candidate_version=str(args.required_candidate_version or '').strip() or None,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
