"""F19: Continuous Learning Loop.

Auto-feeds new SAR detections, seismic events, and field reports back into
the training dataset with full audit trail. Each auto-generated label includes
source, timestamp, confidence, and governance metadata.

Env flags:
  CONTINUOUS_LEARNING_ENABLED — master switch (default: true)
  AUTO_LABEL_MIN_CONFIDENCE — minimum confidence for auto-labels (default: 0.5)
"""
from __future__ import annotations

import json
import os
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from pathlib import Path

CONTINUOUS_LEARNING_ENABLED = os.getenv('CONTINUOUS_LEARNING_ENABLED', 'true').lower() not in {'0', 'false', 'off', 'no'}
AUTO_LABEL_MIN_CONFIDENCE = float(os.getenv('AUTO_LABEL_MIN_CONFIDENCE', '0.5'))

LABEL_SOURCE_SAR = 'sar_detection'
LABEL_SOURCE_SEISMIC = 'seismic_event'
LABEL_SOURCE_FIELD_REPORT = 'field_report'

# Wave D: verification-basis and review state constants
LABEL_SOURCE_SYNTHETIC = 'synthetic_scenario'
HUMAN_REVIEW_PENDING = 'pending'
HUMAN_REVIEW_REVIEWED = 'reviewed'
HUMAN_REVIEW_DISMISSED = 'dismissed'
VERIFICATION_BASIS_NONE = 'none'
VERIFICATION_BASIS_MULTI_SENSOR = 'multi_sensor_agreement'
VERIFICATION_BASIS_SINGLE_SENSOR = 'single_sensor'
VERIFICATION_BASIS_FIELD_VALIDATED = 'field_validated'

# Hard-excluded label sources — synthetic scenarios never enter truth labels
EXCLUDED_LABEL_SOURCES = frozenset({LABEL_SOURCE_SYNTHETIC})

AUTO_LABEL_SOURCE_WEIGHTS: dict[str, float] = {
    LABEL_SOURCE_SAR: 0.85,
    LABEL_SOURCE_SEISMIC: 0.70,
    LABEL_SOURCE_FIELD_REPORT: 0.95,
}

AUTO_LABEL_AUDIT_FILE = os.getenv('AUTO_LABEL_AUDIT_FILE', 'auto_label_audit.jsonl')
AUTO_LABEL_AUDIT_MAX_SIZE_MB = float(os.getenv('AUTO_LABEL_AUDIT_MAX_SIZE_MB', '10'))
AUTO_LABEL_AUDIT_MAX_GENERATIONS = int(os.getenv('AUTO_LABEL_AUDIT_MAX_GENERATIONS', '3'))
AUTO_LABEL_AUDIT_RETENTION_DAYS = int(os.getenv('AUTO_LABEL_AUDIT_RETENTION_DAYS', '180'))
AUTO_LABEL_AUDIT_SCHEMA_VERSION = 'auto_label_audit_v2'
AUTO_LABEL_AUDIT_GENESIS_HASH = '0' * 64


def rotate_audit_file_if_needed(
    manifest_path: str | Path | None = None,
) -> bool:
    """Rotate the audit trail file if it exceeds the max size threshold.

    Rotates: current -> .1, .1 -> .2, .2 -> .3 (dropped if at max generations).
    Safe: no-op if file doesn't exist, is under threshold, or rotation fails.

    Args:
        manifest_path: Path to audit file (uses default if None)

    Returns:
        True if rotation was performed, False otherwise
    """
    path = Path(manifest_path or AUTO_LABEL_AUDIT_FILE)
    try:
        if not path.exists():
            return False
        size_bytes = path.stat().st_size
        max_bytes = AUTO_LABEL_AUDIT_MAX_SIZE_MB * 1024 * 1024
        if size_bytes < max_bytes:
            return False
        max_gen = AUTO_LABEL_AUDIT_MAX_GENERATIONS
        for gen in range(max_gen, 0, -1):
            older = path.with_suffix(f'.{gen}')
            if gen == max_gen:
                if older.exists():
                    older.unlink()
            else:
                newer = path.with_suffix(f'.{gen}')
                if newer.exists():
                    older.rename(path.with_suffix(f'.{gen + 1}'))
        path.rename(path.with_suffix('.1'))
        return True
    except Exception:
        return False


def _parse_utc_datetime(value: str) -> datetime:
    normalized = value.replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _retention_until(created_at: str) -> str:
    created = _parse_utc_datetime(created_at)
    return (created + timedelta(days=AUTO_LABEL_AUDIT_RETENTION_DAYS)).isoformat()


def _canonical_audit_payload(entry: dict[str, Any]) -> str:
    payload = {key: value for key, value in entry.items() if key != 'entry_hash'}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _compute_audit_entry_hash(entry: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_audit_payload(entry).encode('utf-8')).hexdigest()


def _legacy_entry_hash(entry: dict[str, Any], previous_hash: str) -> str:
    legacy_entry = dict(entry)
    legacy_entry.setdefault('previous_hash', previous_hash)
    return _compute_audit_entry_hash(legacy_entry)


def _last_audit_entry_hash(path: Path) -> str:
    if not path.exists():
        return AUTO_LABEL_AUDIT_GENESIS_HASH

    last_hash = AUTO_LABEL_AUDIT_GENESIS_HASH
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entry_hash = entry.get('entry_hash')
                if isinstance(entry_hash, str) and entry_hash:
                    last_hash = entry_hash
                else:
                    last_hash = _legacy_entry_hash(entry, last_hash)
    except Exception:
        return AUTO_LABEL_AUDIT_GENESIS_HASH
    return last_hash


def verify_auto_label_audit_chain(
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Verify tamper-evident hashes in the auto-label audit manifest.

    Legacy entries without hash fields are accepted and counted separately so
    older manifests remain readable. Hashed entries must link to the immediately
    preceding entry hash and must match their canonical payload hash.
    """
    path = Path(manifest_path or AUTO_LABEL_AUDIT_FILE)
    result: dict[str, Any] = {
        'valid': True,
        'entries_checked': 0,
        'hashed_entries': 0,
        'legacy_entries': 0,
        'failures': [],
    }
    if not path.exists():
        return result

    expected_previous = AUTO_LABEL_AUDIT_GENESIS_HASH
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f, start=1):
                raw = line.strip()
                if not raw:
                    continue
                result['entries_checked'] += 1
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    result['valid'] = False
                    result['failures'].append({'line': line_number, 'reason': 'invalid_json'})
                    continue

                entry_hash = entry.get('entry_hash')
                previous_hash = entry.get('previous_hash')
                if not isinstance(entry_hash, str) or not entry_hash:
                    result['legacy_entries'] += 1
                    expected_previous = _legacy_entry_hash(entry, expected_previous)
                    continue

                result['hashed_entries'] += 1
                if previous_hash != expected_previous:
                    result['valid'] = False
                    result['failures'].append({
                        'line': line_number,
                        'reason': 'previous_hash_mismatch',
                        'expected': expected_previous,
                        'actual': previous_hash,
                    })

                recomputed = _compute_audit_entry_hash(entry)
                if entry_hash != recomputed:
                    result['valid'] = False
                    result['failures'].append({
                        'line': line_number,
                        'reason': 'entry_hash_mismatch',
                        'expected': recomputed,
                        'actual': entry_hash,
                    })

                expected_previous = entry_hash
    except Exception as exc:
        result['valid'] = False
        result['failures'].append({'line': None, 'reason': 'read_failed', 'error': str(exc)})

    return result


@dataclass(frozen=True)
class AutoLabel:
    """An auto-generated training label."""
    label_id: str
    source: str  # 'sar_detection', 'seismic_event', 'field_report'
    timestamp: str
    lat: float
    lng: float
    label: int  # 1 = avalanche occurred, 0 = no avalanche
    confidence: float
    region_key: str
    metadata: dict[str, Any] = field(default_factory=dict)
    governance_version: str = 'auto_label_v1'
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verification_basis: str = VERIFICATION_BASIS_NONE
    human_review_state: str = HUMAN_REVIEW_PENDING


@dataclass(frozen=True)
class AutoLabelResult:
    """Result of auto-labeling operation."""
    labels_created: int
    labels_skipped: int
    skip_reasons: list[str]
    audit_entries: list[AutoLabel]


def auto_label_sar_detection(
    *,
    detection: dict[str, Any],
    region_key: str,
) -> AutoLabel | None:
    """Create a training label from a SAR avalanche detection.

    Args:
        detection: SAR detection dict with lat, lng, confidence, timestamp
        region_key: Region key for the detection

    Returns:
        AutoLabel if confidence meets threshold, None otherwise
    """
    confidence = float(detection.get('confidence', 0.0))
    if confidence < AUTO_LABEL_MIN_CONFIDENCE:
        return None

    lat = float(detection.get('lat', 0.0))
    lng = float(detection.get('lng', 0.0))
    timestamp = str(detection.get('timestamp', datetime.now(timezone.utc).isoformat()))
    detection_id = str(detection.get('id', f'sar_{timestamp}_{lat}_{lng}'))

    return AutoLabel(
        label_id=f'auto_sar_{detection_id}',
        source=LABEL_SOURCE_SAR,
        timestamp=timestamp,
        lat=lat,
        lng=lng,
        label=1,  # SAR detection = avalanche occurred
        confidence=confidence * AUTO_LABEL_SOURCE_WEIGHTS[LABEL_SOURCE_SAR],
        region_key=region_key,
        metadata={
            'detection_id': detection_id,
            'scene_id': detection.get('scene_id'),
            'detection_method': detection.get('method', 'sar_unet'),
            'original_confidence': confidence,
        },
    )


def auto_label_seismic_event(
    *,
    event: dict[str, Any],
    region_key: str,
    cells_with_amplification: list[dict[str, Any]] | None = None,
) -> list[AutoLabel]:
    """Create training labels from a seismic event.

    Seismic events create labels for cells that received amplification,
    since post-tremor avalanche risk is elevated.

    Args:
        event: Seismic event dict with magnitude, timestamp, lat, lng
        region_key: Region key
        cells_with_amplification: List of cells that received seismic amplification

    Returns:
        List of AutoLabel objects
    """
    labels: list[AutoLabel] = []
    magnitude = float(event.get('magnitude', 0.0))
    if magnitude < 4.0:
        return labels

    event_timestamp = str(event.get('timestamp', datetime.now(timezone.utc).isoformat()))
    event_id = str(event.get('id', f'seismic_{event_timestamp}'))

    # If no cells provided, create a single label at epicenter
    if not cells_with_amplification:
        lat = float(event.get('lat', 0.0))
        lng = float(event.get('lng', 0.0))
        confidence = min(0.5 + magnitude * 0.05, 0.9)
        labels.append(AutoLabel(
            label_id=f'auto_seismic_{event_id}',
            source=LABEL_SOURCE_SEISMIC,
            timestamp=event_timestamp,
            lat=lat,
            lng=lng,
            label=1,
            confidence=confidence,
            region_key=region_key,
            metadata={
                'event_id': event_id,
                'magnitude': magnitude,
                'depth_km': event.get('depth_km'),
            },
        ))
        return labels

    # Create labels for amplified cells
    for cell in cells_with_amplification:
        amplification = float(cell.get('seismic_amplification', 0.0))
        if amplification <= 0:
            continue
        lat = float(cell.get('lat', 0.0))
        lng = float(cell.get('lng', 0.0))
        confidence = min(amplification * 0.7, 0.85)
        if confidence < AUTO_LABEL_MIN_CONFIDENCE:
            continue
        labels.append(AutoLabel(
            label_id=f'auto_seismic_{event_id}_{lat}_{lng}',
            source=LABEL_SOURCE_SEISMIC,
            timestamp=event_timestamp,
            lat=lat,
            lng=lng,
            label=1,
            confidence=confidence,
            region_key=region_key,
            metadata={
                'event_id': event_id,
                'magnitude': magnitude,
                'amplification': amplification,
            },
        ))

    return labels


def auto_label_field_report(
    *,
    report: dict[str, Any],
    region_key: str,
) -> AutoLabel | None:
    """Create a training label from a field report.

    Args:
        report: Field report dict with lat, lng, avalanche_observed, timestamp
        region_key: Region key

    Returns:
        AutoLabel if report indicates avalanche observation
    """
    avalanche_observed = bool(report.get('avalanche_observed', False))
    if not avalanche_observed:
        # Field report without avalanche observation = negative label
        label = 0
        confidence = 0.8 * AUTO_LABEL_SOURCE_WEIGHTS[LABEL_SOURCE_FIELD_REPORT]
    else:
        label = 1
        confidence = 0.95 * AUTO_LABEL_SOURCE_WEIGHTS[LABEL_SOURCE_FIELD_REPORT]

    lat = float(report.get('lat', 0.0))
    lng = float(report.get('lng', 0.0))
    timestamp = str(report.get('timestamp', datetime.now(timezone.utc).isoformat()))
    report_id = str(report.get('id', f'fr_{timestamp}_{lat}_{lng}'))

    return AutoLabel(
        label_id=f'auto_fr_{report_id}',
        source=LABEL_SOURCE_FIELD_REPORT,
        timestamp=timestamp,
        lat=lat,
        lng=lng,
        label=label,
        confidence=confidence,
        region_key=region_key,
        metadata={
            'report_id': report_id,
            'observer': report.get('observer'),
            'avalanche_type': report.get('avalanche_type'),
            'size': report.get('size'),
        },
    )


def add_to_training_manifest(
    label: AutoLabel,
    manifest_path: str | Path | None = None,
) -> bool:
    """Append an auto-label to the training manifest with audit trail.

    Args:
        label: AutoLabel to add
        manifest_path: Path to audit file (uses default if None)

    Returns:
        True if successfully appended
    """
    if not CONTINUOUS_LEARNING_ENABLED:
        return False

    # Wave D: hard-exclude synthetic scenarios from truth labels
    if label.source in EXCLUDED_LABEL_SOURCES:
        return False

    path = Path(manifest_path or AUTO_LABEL_AUDIT_FILE)
    rotate_audit_file_if_needed(path)
    try:
        with open(path, 'a', encoding='utf-8') as f:
            entry = {
                'audit_schema_version': AUTO_LABEL_AUDIT_SCHEMA_VERSION,
                'label_id': label.label_id,
                'source': label.source,
                'timestamp': label.timestamp,
                'lat': label.lat,
                'lng': label.lng,
                'label': label.label,
                'confidence': label.confidence,
                'region_key': label.region_key,
                'metadata': label.metadata,
                'governance_version': label.governance_version,
                'created_at': label.created_at,
                'retention_until': _retention_until(label.created_at),
                'verification_basis': label.verification_basis,
                'human_review_state': label.human_review_state,
            }
            entry['previous_hash'] = _last_audit_entry_hash(path)
            entry['entry_hash'] = _compute_audit_entry_hash(entry)
            f.write(json.dumps(entry, sort_keys=True) + '\n')
        return True
    except Exception:
        return False


def get_auto_label_audit_trail(
    manifest_path: str | Path | None = None,
    *,
    source: str | None = None,
    region_key: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Read auto-label audit trail from manifest file.

    Args:
        manifest_path: Path to audit file
        source: Filter by source type
        region_key: Filter by region
        limit: Maximum entries to return

    Returns:
        List of audit entries as dicts
    """
    path = Path(manifest_path or AUTO_LABEL_AUDIT_FILE)
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if source and entry.get('source') != source:
                    continue
                if region_key and entry.get('region_key') != region_key:
                    continue
                entries.append(entry)
                if len(entries) >= limit:
                    break
    except Exception:
        pass

    return entries


def process_detections_for_learning(
    *,
    sar_detections: list[dict[str, Any]] | None = None,
    seismic_events: list[dict[str, Any]] | None = None,
    field_reports: list[dict[str, Any]] | None = None,
    region_key: str = 'unknown',
    manifest_path: str | Path | None = None,
) -> AutoLabelResult:
    """Process all new detections for continuous learning.

    Args:
        sar_detections: List of SAR detection dicts
        seismic_events: List of seismic event dicts
        field_reports: List of field report dicts
        region_key: Region key for all detections
        manifest_path: Path to audit manifest

    Returns:
        AutoLabelResult with counts and entries
    """
    if not CONTINUOUS_LEARNING_ENABLED:
        return AutoLabelResult(
            labels_created=0,
            labels_skipped=0,
            skip_reasons=['continuous_learning_disabled'],
            audit_entries=[],
        )

    labels_created = 0
    labels_skipped = 0
    skip_reasons: list[str] = []
    audit_entries: list[AutoLabel] = []

    # Process SAR detections
    for detection in sar_detections or []:
        label = auto_label_sar_detection(detection=detection, region_key=region_key)
        if label is not None:
            if add_to_training_manifest(label, manifest_path):
                labels_created += 1
                audit_entries.append(label)
            else:
                labels_skipped += 1
                skip_reasons.append('manifest_write_failed')
        else:
            labels_skipped += 1
            skip_reasons.append('sar_low_confidence')

    # Process seismic events
    for event in seismic_events or []:
        labels = auto_label_seismic_event(event=event, region_key=region_key)
        for label in labels:
            if add_to_training_manifest(label, manifest_path):
                labels_created += 1
                audit_entries.append(label)
            else:
                labels_skipped += 1
                skip_reasons.append('manifest_write_failed')
        if not labels:
            labels_skipped += 1
            skip_reasons.append('seismic_below_threshold')

    # Process field reports
    for report in field_reports or []:
        label = auto_label_field_report(report=report, region_key=region_key)
        if label is not None:
            if add_to_training_manifest(label, manifest_path):
                labels_created += 1
                audit_entries.append(label)
            else:
                labels_skipped += 1
                skip_reasons.append('manifest_write_failed')
        else:
            labels_skipped += 1
            skip_reasons.append('field_report_no_data')

    return AutoLabelResult(
        labels_created=labels_created,
        labels_skipped=labels_skipped,
        skip_reasons=skip_reasons,
        audit_entries=audit_entries,
    )
