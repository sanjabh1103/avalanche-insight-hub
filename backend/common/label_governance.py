from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp, log
from typing import Any


GOVERNANCE_VERSION = 'autonomous_label_governance_v2'
MIN_LABEL_CONFIDENCE = 0.45
MIN_CONFIDENCE_DECAY = 0.05
RECENCY_HALF_LIFE_DAYS = 30.0
TRAINING_WEIGHT_FLOOR = 0.1
TRAINING_WEIGHT_CEILING = 1.5
CORROBORATION_STEP = 0.15

SOURCE_WEIGHTS: dict[str, float] = {
    'field_report': 1.0,
    'field_report_offline_sync': 1.0,
    'gemini_news': 0.8,
    'newsdata_gemini': 0.8,
    'gee_sar': 0.9,
    'sentinel1_gee': 0.9,
    'sar_unet': 1.1,
    'historical_backfill_v2_local_topo': 0.85,
}


@dataclass(frozen=True)
class LabelGovernance:
    label_confidence: float
    confidence_decayed: float
    source_weight: float
    corroboration_weight: float
    recency_decay: float
    training_weight: float
    training_eligible: bool


def clamp(value: float, lower: float, upper: float) -> float:
    return float(max(lower, min(upper, value)))


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _coerce_numeric(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not numeric == numeric:  # NaN guard
        return None
    return numeric


def resolve_label_confidence(record: dict[str, Any]) -> float:
    metadata = record.get('metadata')
    metadata_governance = {}
    if isinstance(metadata, dict):
        raw_label_governance = metadata.get('label_governance')
        if isinstance(raw_label_governance, dict):
            metadata_governance = raw_label_governance

    for candidate in (
        record.get('label_confidence'),
        metadata_governance.get('label_confidence'),
        record.get('confidence'),
    ):
        numeric = _coerce_numeric(candidate)
        if numeric is not None:
            return clamp(numeric, 0.0, 1.0)
    return 0.5


def source_weight(source: str | None, fusion_source: str | None = None) -> float:
    for candidate in (source, fusion_source):
        key = str(candidate or '').strip().lower()
        if key in SOURCE_WEIGHTS:
            return SOURCE_WEIGHTS[key]
    return 0.75


def count_corroborating_sources(record: dict[str, Any]) -> int:
    corroboration_sources = set()
    metadata = record.get('metadata')
    if isinstance(metadata, dict):
        raw_sources = metadata.get('corroboration_sources')
        if isinstance(raw_sources, list):
            corroboration_sources.update(str(item).strip().lower() for item in raw_sources if item)
        raw_count = metadata.get('corroboration_count')
        if isinstance(raw_count, (int, float)) and raw_count > 0:
            return max(int(raw_count), len(corroboration_sources), 1)

    for field in ('source', 'fusion_source', 'source_model'):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            corroboration_sources.add(value.strip().lower())

    scene_ids = record.get('source_scene_ids')
    if isinstance(scene_ids, list) and scene_ids:
        corroboration_sources.add('scene_bundle')

    return max(len(corroboration_sources), 1)


def corroboration_weight(corroboration_count: int) -> float:
    return clamp(1.0 + max(0, corroboration_count - 1) * CORROBORATION_STEP, 1.0, 1.45)


def recency_decay(timestamp: datetime | None, *, reference_time: datetime | None = None) -> float:
    if timestamp is None:
        return 1.0
    ref = reference_time.astimezone(timezone.utc) if reference_time is not None else datetime.now(timezone.utc)
    age_days = max(0.0, (ref - timestamp).total_seconds() / 86400.0)
    return clamp(exp(-log(2) * age_days / RECENCY_HALF_LIFE_DAYS), 0.2, 1.0)


def confidence_decay(label_confidence: float, recency_decay_value: float) -> float:
    return clamp(label_confidence * recency_decay_value, MIN_CONFIDENCE_DECAY, 1.0)


def governance_refresh_needed(record: dict[str, Any], *, current_version: str = GOVERNANCE_VERSION) -> bool:
    version = str(record.get('governance_version') or '').strip()
    return version != current_version


def derive_label_governance(record: dict[str, Any], *, reference_time: datetime | None = None) -> LabelGovernance:
    label_conf = resolve_label_confidence(record)
    weight_from_source = source_weight(
        str(record.get('source') or '') or None,
        str(record.get('fusion_source') or '') or None,
    )
    corroboration_count = count_corroborating_sources(record)
    corroboration = corroboration_weight(corroboration_count)
    decay = recency_decay(parse_timestamp(record.get('timestamp')), reference_time=reference_time)
    decayed_confidence = confidence_decay(label_conf, decay)
    combined_weight = clamp(
        label_conf * weight_from_source * corroboration * decay,
        TRAINING_WEIGHT_FLOOR,
        TRAINING_WEIGHT_CEILING,
    )
    eligible = bool(record.get('training_eligible', True)) and label_conf >= MIN_LABEL_CONFIDENCE
    return LabelGovernance(
        label_confidence=label_conf,
        confidence_decayed=decayed_confidence,
        source_weight=weight_from_source,
        corroboration_weight=corroboration,
        recency_decay=decay,
        training_weight=combined_weight,
        training_eligible=eligible,
    )


def materialize_label_governance(
    record: dict[str, Any],
    *,
    reference_time: datetime | None = None,
    governed_at: datetime | None = None,
) -> dict[str, Any]:
    governance = derive_label_governance(record, reference_time=reference_time)
    materialized_at = governed_at.astimezone(timezone.utc) if governed_at is not None else datetime.now(timezone.utc)
    return {
        'label_confidence': governance.label_confidence,
        'training_weight': governance.training_weight,
        'training_eligible': governance.training_eligible,
        'confidence_decayed': governance.confidence_decayed,
        'governance_version': GOVERNANCE_VERSION,
        'governed_at': materialized_at.isoformat(),
    }
