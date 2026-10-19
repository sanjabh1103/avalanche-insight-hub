"""P2.2: Schema/label drift detection utilities.

Produces a stable SHA-256 hash of the active FEATURE_COLUMNS and (when
Supabase is reachable) of the distinct verification_status + severity_label
values observed in the last 30 days. Inference compares the stored hash on
the loaded artifact against the current hash; a mismatch raises so the
GitHub Actions workflow can auto-dispatch a `train` run.

Feature_columns hash uses ordered(sorted) column names so re-ordering of
FEATURE_COLUMNS does NOT false-trigger; only semantic additions/removals do.
"""
from __future__ import annotations

import hashlib
import json
from typing import Sequence


def feature_columns_hash(feature_columns: Sequence[str]) -> str:
    sorted_cols = sorted(str(c) for c in feature_columns)
    payload = json.dumps(sorted_cols, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def label_schema_hash(verification_statuses: Sequence[str], severity_labels: Sequence[str]) -> str:
    vs = sorted({str(v) for v in verification_statuses})
    sl = sorted({str(s) for s in severity_labels})
    payload = json.dumps({'verification_status': vs, 'severity_label': sl}, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def detect_drift(
    *,
    stored_feature_hash: str | None,
    current_feature_hash: str,
    stored_label_hash: str | None,
    current_label_hash: str,
) -> dict[str, object]:
    feature_drift = bool(stored_feature_hash and stored_feature_hash != current_feature_hash)
    label_drift = bool(stored_label_hash and stored_label_hash != current_label_hash)
    return {
        'feature_drift_detected': feature_drift,
        'label_drift_detected': label_drift,
        'stored_feature_hash': stored_feature_hash,
        'current_feature_hash': current_feature_hash,
        'stored_label_hash': stored_label_hash,
        'current_label_hash': current_label_hash,
        'requires_retrain': feature_drift or label_drift,
    }
