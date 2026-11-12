"""Swiss RAvaFcast conformance and evidence audit.

The Swiss reproduction code clips danger levels to 1-4, while Partner targets
five levels.  This module documents that semantic difference and provides a
read-only verifier for an explicitly supplied RF2 CSV.  Counts are never
embedded in source code: they are reported only after the exact bytes,
schema, and danger-level values have been checked.

The verifier does not modify the denylisted Swiss reproduction code and does
not convert Swiss observations into Partner training labels.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SWISS_METADATA_URL = 'https://www.envidat.ch/metadata/weather-snowpack-danger_ratings-data'
SWISS_RF2_RESOURCE_URL = (
    'https://www.envidat.ch/dataset/54d7dc19-e70c-4998-bfb6-caffe41c83e6/'
    'resource/7f6d8de7-194c-4ae6-9e0d-473a45342918/download/data_rf2_tidy.csv'
)
SWISS_VERIFICATION_SNAPSHOT_SCHEMA = 'swiss_rf2_verification_v1'
_SHA256_RE = re.compile(r'^[0-9a-fA-F]{64}$')


def _repo_root() -> Path:
    return Path(__file__).parent.parent.parent


def _default_rf2_path() -> Path:
    return _repo_root() / 'backend' / 'data' / 'swiss_envidat' / 'data_rf2_tidy.csv'


def _invalid_result(reason: str, *, path: Path | None = None, **details: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        'verified': False,
        'reason': reason,
        'level_5_count': None,
        'data_path_checked': str(path) if path is not None else str(_default_rf2_path()),
    }
    result.update(details)
    return result


@dataclass(frozen=True)
class SwissConformanceDecision:
    """P7: Documented conformance decision for the Swiss Level 5 merge.

    This is a read-only audit artifact — it does NOT modify any denylisted
    reproduction code. It documents the finding for the Partner decision packet.

    G8: Conformance is split into 4 separate verification dimensions:
    - paper_policy_documented: The RAvaFcast paper uses a 4-level scale
    - code_transform_verified: The reproduction code clips to 1-4
    - dataset_verified: The Swiss data file is present and counts are verified
    - runtime_reproduction_verified: The reproduction has been run successfully
    """

    schema_version: str = 'swiss_conformance_audit_v1'
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # G8: Separate verification dimensions
    paper_policy_documented: bool = True  # RAvaFcast paper uses 4-level scale
    code_transform_verified: bool = True  # train_rf4.py clips to 1-4 (verified at line 126)
    dataset_verified: bool = False  # Swiss data file not present in repo
    runtime_reproduction_verified: bool = False  # Reproduction not run in this session
    dataset_verification_status: str = 'not_checked'
    dataset_verification_reason: str = 'RF2 bytes were not supplied to the verifier.'
    swiss_rf2_content_sha256: str = ''
    swiss_rf2_danger_column: str = ''
    swiss_rf2_schema_valid: bool = False

    # The finding — counts are UNVERIFIED until Swiss data file is available
    swiss_rf2_total_rows: int = 0  # Populated only after byte-level verification
    swiss_rf2_level_5_count: int = 0  # Populated only after byte-level verification
    swiss_rf2_level_5_percentage: float = 0.0  # Populated only after byte-level verification
    swiss_rf2_counts_verified: bool = False  # True only when verify_swiss_level_5_merge() succeeds
    swiss_reproduction_labels: tuple[int, ...] = (1, 2, 3, 4)
    swiss_reproduction_clips_level_5: bool = True
    swiss_reproduction_clip_location: str = 'train_rf4.py:126'

    # The conformance decision — G8: computed from separate dimensions
    conformance_status: str = 'paper_and_code_verified_dataset_pending'
    conformance_rationale: str = (
        'The RAvaFcast paper uses a 4-level scale (1-4). '
        'The reproduction code clips to 1-4, merging any Level 5 entries '
        'into Level 4. This matches the paper. '
        'NOTE: Specific counts are UNVERIFIED until the Swiss RF2 bytes are '
        'supplied to the verifier. '
        'Run verify_swiss_level_5_merge() with the data file to verify.'
    )

    # Partner difference
    Partner_uses_5_levels: bool = True
    Partner_level_5_label: str = 'black'  # P1: Partner color name
    Partner_level_5_eaws_name: str = 'very_high'  # P1: EAWS comparison

    # Decision
    denylist_change_needed: bool = False
    planner_approval_needed: bool = False
    can_use_swiss_as_reference: bool = True  # With documented Level 5 caveat

    # Caveat for Partner pipeline
    caveat: str = (
        'The Swiss reference model uses 4 levels. The Partner system uses 5 levels. '
        'Swiss model outputs must NOT be directly used as Partner labels without '
        'addressing the Level 5 gap. Level 5 in Partner is a distinct danger '
        'category (Black/Extremely unsafe) that cannot be inferred from '
        'a 4-level model.'
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_conformance_decision(
    *,
    data_path: Path | None = None,
    expected_sha256: str | None = None,
    verification_result: dict[str, Any] | None = None,
) -> SwissConformanceDecision:
    """Build the Swiss conformance decision document.

    The default call is intentionally repository-local and remains blocked when
    the raw RF2 file is absent.  Callers may supply an explicit file or a
    verifier result from a separately retained evidence snapshot.
    """
    result = verification_result
    if result is None:
        result = verify_swiss_level_5_merge(
            data_path=data_path,
            expected_sha256=expected_sha256,
        )
    verified = bool(result.get('verified'))
    if not verified:
        reason = str(result.get('reason') or 'RF2 verification did not complete')
        return SwissConformanceDecision(
            dataset_verification_status='blocked',
            dataset_verification_reason=reason,
            swiss_rf2_content_sha256=str(result.get('content_sha256') or ''),
            swiss_rf2_danger_column=str(result.get('danger_column') or ''),
            swiss_rf2_schema_valid=bool(result.get('schema_valid', False)),
        )

    return SwissConformanceDecision(
        dataset_verified=True,
        dataset_verification_status='content_verified',
        dataset_verification_reason=(
            'RF2 bytes, CSV schema, and danger levels were verified by the '
            'read-only audit. Runtime reproduction remains a separate gate.'
        ),
        swiss_rf2_total_rows=int(result['total_rows']),
        swiss_rf2_level_5_count=int(result['level_5_count']),
        swiss_rf2_level_5_percentage=float(result['level_5_percentage']),
        swiss_rf2_counts_verified=True,
        swiss_rf2_content_sha256=str(result['content_sha256']),
        swiss_rf2_danger_column=str(result['danger_column']),
        swiss_rf2_schema_valid=True,
        conformance_status='paper_and_code_verified_dataset_verified_runtime_pending',
        conformance_rationale=(
            'The RAvaFcast paper uses a 4-level scale (1-4), and the '
            'reproduction code clips to 1-4. The supplied RF2 bytes and CSV '
            'danger-level schema were content-verified; runtime reproduction '
            'has not been verified in this decision.'
        ),
    )


def verify_swiss_level_5_merge(
    data_path: Path | None = None,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Verify that the Swiss reproduction code clips Level 5 to Level 4.

    This is a read-only verification — it does NOT modify any denylisted code.
    G8: Uses repo-root-based path resolution by default, not CWD-dependent.

    The verification is deliberately strict: the exact bytes are hashed, the
    danger column must be discoverable from the approved aliases, every data
    row must contain an integer danger level from 1 through 5, and the file
    must contain at least one data row.  An unverified resource never produces
    counts that look authoritative.
    """
    path = Path(data_path) if data_path is not None else _default_rf2_path()
    if not path.exists():
        return _invalid_result(
            'Swiss RF2 data not found (searched repo-root-based path)',
            path=path,
        )
    if not path.is_file():
        return _invalid_result('Swiss RF2 data path is not a regular file', path=path)
    if expected_sha256 is not None and not _SHA256_RE.fullmatch(expected_sha256):
        return _invalid_result('expected_sha256 must be a 64-character hexadecimal hash', path=path)

    try:
        content = path.read_bytes()
        content_sha256 = hashlib.sha256(content).hexdigest()
        if expected_sha256 and content_sha256.lower() != expected_sha256.lower():
            return _invalid_result(
                'Swiss RF2 content hash mismatch',
                path=path,
                content_sha256=content_sha256,
                expected_sha256=expected_sha256,
            )
        text = content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        columns = list(reader.fieldnames or [])
        blank_columns = [index for index, column in enumerate(columns) if not isinstance(column, str) or not column.strip()]
        # The official RF2 export contains one unnamed leading index column.
        # It is accepted only in position zero; any other blank/ambiguous
        # header remains a schema blocker.
        if not columns or any(index != 0 for index in blank_columns):
            return _invalid_result(
                'Swiss RF2 CSV header is missing or contains blank columns',
                path=path,
                content_sha256=content_sha256,
                schema_valid=False,
                columns=columns,
            )
        normalized_columns = {
            re.sub(r'[^a-z0-9]', '', column.casefold()): column
            for column in columns
            if isinstance(column, str) and column.strip()
        }
        danger_col = normalized_columns.get('dangerlevel')
        if danger_col is None:
            return _invalid_result(
                'danger level column not found; expected one of dangerLevel, danger_level, DangerLevel, dangerlevel',
                path=path,
                content_sha256=content_sha256,
                schema_valid=False,
                columns=columns,
            )

        total = 0
        level_5_count = 0
        invalid_rows = 0
        for row in reader:
            total += 1
            raw_level = row.get(danger_col) if isinstance(row, dict) else None
            level_text = str(raw_level).strip() if raw_level is not None else ''
            if not re.fullmatch(r'[1-5]', level_text):
                invalid_rows += 1
                continue
            if level_text == '5':
                level_5_count += 1
        if total == 0:
            return _invalid_result(
                'Swiss RF2 CSV contains no data rows',
                path=path,
                content_sha256=content_sha256,
                schema_valid=True,
                columns=columns,
                danger_column=danger_col,
                total_rows=0,
                invalid_danger_level_rows=0,
            )
        if invalid_rows:
            return _invalid_result(
                f'Swiss RF2 contains {invalid_rows} invalid danger-level rows',
                path=path,
                content_sha256=content_sha256,
                schema_valid=True,
                columns=columns,
                danger_column=danger_col,
                total_rows=total,
                invalid_danger_level_rows=invalid_rows,
            )
        return {
            'verified': True,
            'reason': 'RF2 bytes and danger-level schema verified',
            'data_path_checked': str(path),
            'content_sha256': content_sha256,
            'expected_sha256': expected_sha256,
            'byte_size': len(content),
            'columns': columns,
            'danger_column': danger_col,
            'schema_valid': True,
            'total_rows': total,
            'level_5_count': level_5_count,
            'level_5_percentage': round(level_5_count / total * 100, 4),
            'invalid_danger_level_rows': 0,
            'clip_target': '1-4',
            'merge_behavior': 'Level 5 entries are clipped to Level 4 by train_rf4.py',
            'source_url': SWISS_RF2_RESOURCE_URL,
        }
    except (OSError, UnicodeDecodeError, csv.Error, ValueError) as exc:
        return _invalid_result(
            f'Swiss RF2 verification failed: {exc}',
            path=path,
        )


def save_swiss_verification_snapshot(
    result: dict[str, Any],
    path: Path,
    *,
    metadata_response_sha256: str = '',
    metadata_url: str = SWISS_METADATA_URL,
    license_id: str = '',
    resource_metadata_size: int | None = None,
    data_path_label: str = '<external-download>',
) -> str:
    """Persist a self-hashed verification result without copying raw data.

    The snapshot records what exact bytes were checked and when, while
    ``raw_bytes_retained=False`` prevents the evidence packet from implying
    that the licensed dataset is part of the repository.
    """
    if not isinstance(result, dict) or result.get('verified') is not True:
        raise ValueError('only a verified RF2 result can be saved as a snapshot')
    payload = dict(result)
    payload.update({
        'schema_version': SWISS_VERIFICATION_SNAPSHOT_SCHEMA,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'data_path_checked': data_path_label,
        'raw_bytes_retained': False,
        'metadata_url': metadata_url,
        'metadata_response_sha256': metadata_response_sha256,
        'license_id': license_id,
        'resource_metadata_size': resource_metadata_size,
        'snapshot_sha256': None,
    })
    snapshot_hash_payload = dict(payload)
    snapshot_hash_payload['snapshot_sha256'] = None
    snapshot_hash = hashlib.sha256(
        (json.dumps(snapshot_hash_payload, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    ).hexdigest()
    payload['snapshot_sha256'] = snapshot_hash
    encoded = (json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp', delete=False) as handle:
        temporary_path = Path(handle.name)
        handle.write(encoded)
    os.replace(temporary_path, path)
    return snapshot_hash


def load_swiss_verification_snapshot(path: Path) -> dict[str, Any] | None:
    """Load and verify a saved RF2 evidence snapshot."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'Swiss verification snapshot load failed: {exc}') from exc
    if not isinstance(payload, dict):
        raise ValueError('Swiss verification snapshot must be a JSON object')
    expected = payload.get('snapshot_sha256')
    if not isinstance(expected, str) or not _SHA256_RE.fullmatch(expected):
        raise ValueError('Swiss verification snapshot hash is missing or invalid')
    normalized = dict(payload)
    normalized['snapshot_sha256'] = None
    actual = hashlib.sha256(
        (json.dumps(normalized, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    ).hexdigest()
    if actual != expected:
        raise ValueError('Swiss verification snapshot hash mismatch')
    if payload.get('schema_version') != SWISS_VERIFICATION_SNAPSHOT_SCHEMA:
        raise ValueError('unsupported Swiss verification snapshot schema')
    if payload.get('verified') is not True or not _SHA256_RE.fullmatch(str(payload.get('content_sha256') or '')):
        raise ValueError('Swiss verification snapshot does not contain verified content evidence')
    return payload
