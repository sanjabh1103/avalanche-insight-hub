from __future__ import annotations

import gzip
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.common.release_policy import evaluate_release_decision, is_research_gate_enabled, PublicationEvidence, evaluate_publication_evidence
from backend.common.storage_io import storage_upload_bytes, storage_upsert_json
from backend.common.supabase_io import patch_row_by_id, rest_insert, rest_rpc

FORECAST_PRODUCTS_BUCKET = 'forecast-products'
FORECAST_MANIFEST_SCHEMA = 'forecast-run-manifest/v1'


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _gzipped_json_bytes(payload: Any) -> bytes:
    return gzip.compress(_json_bytes(payload))


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _storage_prefix(*, hazard_type: str, region_key: str, run_id: str) -> str:
    return f'{hazard_type}/{region_key}/{run_id}'


def _derive_valid_window(
    *,
    forecast_date: str,
    issue_slot: str,
    cadence_hours: int,
    horizon_hours: int,
) -> tuple[datetime, datetime]:
    """Derive a deterministic UTC valid window for legacy callers.

    The active daily-inference path supplies this window through
    ``ForecastCadenceContext``. Direct callers still receive the same
    persisted contract instead of creating a nullable publication row.
    """
    try:
        base_date = datetime.fromisoformat(str(forecast_date)[:10]).date()
    except ValueError as exc:
        raise ValueError(f'forecast_date must begin with an ISO date, got {forecast_date!r}') from exc
    valid_from = datetime(
        base_date.year,
        base_date.month,
        base_date.day,
        int(issue_slot),
        0,
        0,
        tzinfo=timezone.utc,
    )
    valid_to = valid_from + timedelta(hours=max(1, int(horizon_hours)))
    return valid_from, valid_to


def _record_event(
    *,
    run_id: str,
    stage: str,
    status: str,
    detail: dict[str, Any] | None = None,
) -> None:
    rest_insert(
        'forecast_publication_events',
        [{
            'forecast_run_id': run_id,
            'stage': stage,
            'status': status,
            'detail': detail or {},
        }],
        returning='minimal',
    )


def publish_forecast_run(
    *,
    hazard_type: str,
    region_key: str,
    region_name: str,
    forecast_date: str,
    horizon_hours: int,
    grid_size: int,
    bbox: list[float],
    status: str,
    weather_summary: dict[str, Any],
    forecast_bulletins: dict[str, Any] | None,
    model_metadata: dict[str, Any],
    hourly_grids: list[list[dict[str, object]]],
    runout_polygons: list[dict[str, object]],
    issue_slot: str = '06',
    cadence_hours: int = 24,
    valid_from: str | None = None,
    valid_to: str | None = None,
    source_as_of: str | None = None,
    issue_time: str | None = None,
    source_as_of_inferred: bool | None = None,
) -> dict[str, Any] | bool:
    issue_time = issue_time or datetime.now(timezone.utc).isoformat()
    if cadence_hours not in {6, 24}:
        raise ValueError(f'cadence_hours must be 6 or 24, got {cadence_hours}')
    if cadence_hours == 6 and issue_slot not in {'00', '06', '12', '18'}:
        raise ValueError(f'issue_slot {issue_slot!r} is invalid for six-hour cadence')
    if cadence_hours == 24 and issue_slot != '06':
        raise ValueError('daily cadence requires issue_slot=06')
    if (valid_from is None) != (valid_to is None):
        raise ValueError('valid_from and valid_to must be supplied together')
    issue_time_dt = datetime.fromisoformat(issue_time.replace('Z', '+00:00'))
    if issue_time_dt.tzinfo is None or issue_time_dt.utcoffset() != timedelta(0):
        raise ValueError('issue_time must be timezone-aware UTC')
    if valid_from is None and valid_to is None:
        derived_valid_from, derived_valid_to = _derive_valid_window(
            forecast_date=forecast_date,
            issue_slot=issue_slot,
            cadence_hours=cadence_hours,
            horizon_hours=horizon_hours,
        )
        valid_from = derived_valid_from.isoformat()
        valid_to = derived_valid_to.isoformat()
    valid_from_dt = datetime.fromisoformat(valid_from.replace('Z', '+00:00')) if valid_from else None
    valid_to_dt = datetime.fromisoformat(valid_to.replace('Z', '+00:00')) if valid_to else None
    for label, value in (('valid_from', valid_from_dt), ('valid_to', valid_to_dt)):
        if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
            raise ValueError(f'{label} must be timezone-aware UTC')
    if valid_from_dt is not None and valid_to_dt is not None and valid_to_dt <= valid_from_dt:
        raise ValueError('valid_to must be later than valid_from')
    source_as_of_was_inferred = source_as_of is None
    source_as_of = source_as_of or issue_time
    if source_as_of_inferred is None:
        source_as_of_inferred = source_as_of_was_inferred
    source_as_of_dt = datetime.fromisoformat(source_as_of.replace('Z', '+00:00'))
    if source_as_of_dt.tzinfo is None or source_as_of_dt.utcoffset() != timedelta(0):
        raise ValueError('source_as_of must be timezone-aware UTC')
    if source_as_of_dt > issue_time_dt:
        raise ValueError('source_as_of cannot be later than issue_time')
    inserted = rest_insert('forecast_runs', [{
        'hazard_type': hazard_type,
        'region_key': region_key,
        'region_name': region_name,
        'forecast_date': forecast_date,
        'issue_time': issue_time,
        'horizon_hours': horizon_hours,
        'grid_size': grid_size,
        'bbox': bbox,
        'status': 'building',
        'publication_status': 'building',
        'model_metadata': model_metadata,
        'weather_summary': weather_summary,
        'forecast_bulletins': forecast_bulletins or {},
        'issue_slot': issue_slot,
        'cadence_hours': cadence_hours,
        'valid_from': valid_from,
        'valid_to': valid_to,
        'source_as_of': source_as_of,
    }])
    if not inserted or not inserted[0].get('id'):
        raise RuntimeError('failed to create forecast_run row')
    run_id = str(inserted[0]['id'])
    prefix = _storage_prefix(hazard_type=hazard_type, region_key=region_key, run_id=run_id)
    _record_event(
        run_id=run_id,
        stage='building',
        status='ok',
        detail={'issue_time': issue_time, 'horizon_hours': horizon_hours, 'grid_size': grid_size},
    )

    try:
        hour_rows: list[dict[str, Any]] = []
        manifest_hours: list[dict[str, Any]] = []
        for forecast_hour, cells in enumerate(hourly_grids):
            valid_time = (
                (valid_from_dt or datetime.fromisoformat(issue_time.replace('Z', '+00:00')))
                .replace(microsecond=0)
                + timedelta(hours=forecast_hour)
            ).isoformat()
            hour_payload = {
                'schema_version': 'forecast-hour/v1',
                'forecast_run_id': run_id,
                'region_key': region_key,
                'forecast_date': forecast_date,
                'forecast_hour': forecast_hour,
                'valid_time': valid_time,
                'cells': cells,
            }
            compressed = _gzipped_json_bytes(hour_payload)
            object_path = f'{prefix}/hours/hour-{forecast_hour:03d}.json.gz'
            storage_ref = storage_upload_bytes(
                bucket=FORECAST_PRODUCTS_BUCKET,
                object_path=object_path,
                payload=compressed,
                content_type='application/gzip',
            )
            ready_cells = sum(1 for cell in cells if cell.get('status') == 'ready')
            stale_cells = len(cells) - ready_cells
            sha = _sha256_hex(compressed)
            hour_rows.append({
                'forecast_run_id': run_id,
                'forecast_hour': forecast_hour,
                'valid_time': hour_payload['valid_time'],
                'storage_ref': storage_ref,
                'cell_count': len(cells),
                'ready_cell_count': ready_cells,
                'stale_cell_count': stale_cells,
                'payload_sha256': sha,
            })
            manifest_hours.append({
                'forecastHour': forecast_hour,
                'validTime': hour_payload['valid_time'],
                'storageRef': storage_ref,
                'cellCount': len(cells),
                'readyCellCount': ready_cells,
                'staleCellCount': stale_cells,
                'payloadSha256': sha,
            })

        runout_payload = {
            'schema_version': 'forecast-runouts/v1',
            'forecast_run_id': run_id,
            'region_key': region_key,
            'forecast_date': forecast_date,
            'runout_polygons': runout_polygons,
        }
        runout_bytes = _gzipped_json_bytes(runout_payload)
        runout_storage_ref = storage_upload_bytes(
            bucket=FORECAST_PRODUCTS_BUCKET,
            object_path=f'{prefix}/runouts.json.gz',
            payload=runout_bytes,
            content_type='application/gzip',
        )
        _record_event(
            run_id=run_id,
            stage='artifacts_written',
            status='ok',
            detail={
                'manifest_hours': len(manifest_hours),
                'runout_count': len(runout_polygons),
                'runout_storage_ref': runout_storage_ref,
            },
        )

        try:
            rest_insert('forecast_run_hours', hour_rows, returning='minimal', timeout_seconds=120)
        except Exception as exc:
            print(f'[forecast_pub] forecast_run_hours insert failed: {exc}', file=sys.stderr)
            patch_row_by_id(
                'forecast_runs',
                run_id,
                {'status': 'failed', 'error_message': f'forecast_run_hours insert failed: {exc}'},
            )
            _record_event(
                run_id=run_id,
                stage='forecast_run_hours_insert',
                status='error',
                detail={'error': str(exc)},
            )
            return False
        manifest = {
            'schemaVersion': FORECAST_MANIFEST_SCHEMA,
            'forecastRunId': run_id,
            'hazardType': hazard_type,
            'regionKey': region_key,
            'regionName': region_name,
            'forecastDate': forecast_date,
            'issueTime': issue_time,
            'horizonHours': horizon_hours,
            'gridSize': grid_size,
            'bbox': bbox,
            'status': status,
            'weatherSummary': weather_summary,
            'forecastBulletin': forecast_bulletins,
            'modelMetadata': model_metadata,
            'runoutStorageRef': runout_storage_ref,
            'hours': manifest_hours,
            'issueSlot': issue_slot,
            'cadenceHours': cadence_hours,
            'validFrom': valid_from,
            'validTo': valid_to,
            'sourceAsOf': source_as_of,
            'sourceAsOfInferred': bool(source_as_of_inferred),
        }
        manifest_storage_ref = storage_upsert_json(
            bucket=FORECAST_PRODUCTS_BUCKET,
            object_path=f'{prefix}/manifest.json',
            payload=manifest,
        )
        model_metadata_with_run_refs = {
            **model_metadata,
            'forecast_run_id': run_id,
            'manifest_storage_ref': manifest_storage_ref,
            'runout_storage_ref': runout_storage_ref,
        }
        patch_row_by_id(
            'forecast_runs',
            run_id,
            {
                'manifest_storage_ref': manifest_storage_ref,
                'runout_storage_ref': runout_storage_ref,
                'status': 'building',
                'publication_status': 'validated',
                'forecast_bulletins': forecast_bulletins or {},
                'model_metadata': model_metadata_with_run_refs,
            },
            returning='minimal',
        )
        _record_event(
            run_id=run_id,
            stage='validated',
            status='ok',
            detail={'manifest_storage_ref': manifest_storage_ref},
        )
        return {
            'forecast_run_id': run_id,
            'manifest_storage_ref': manifest_storage_ref,
            'runout_storage_ref': runout_storage_ref,
            'hours': manifest_hours,
        }
    except Exception as exc:
        patch_row_by_id(
            'forecast_runs',
            run_id,
            {
                'status': 'failed',
                'publication_status': 'failed',
            },
            returning='minimal',
        )
        _record_event(
            run_id=run_id,
            stage='failed',
            status='failed',
            detail={'error': str(exc)},
        )
        raise


def attach_compatibility_forecast_grid(
    *,
    forecast_run_id: str,
    compatibility_forecast_grid_id: str,
) -> None:
    patch_row_by_id(
        'forecast_runs',
        forecast_run_id,
        {'compatibility_forecast_grid_id': compatibility_forecast_grid_id},
        returning='minimal',
    )


def _research_gate_enabled() -> bool:
    return is_research_gate_enabled()


def promote_forecast_run(*, forecast_run_id: str, model_type: str, model_version: str, publication_gates_passed: bool, evidence: PublicationEvidence | None = None) -> dict[str, Any] | None:
    gate_enabled = _research_gate_enabled()
    if evidence is not None:
        release_decision = evaluate_publication_evidence(evidence)
    else:
        release_decision = evaluate_release_decision(
            model_type,
            model_version,
            gate_enabled=gate_enabled,
            publication_gates_passed=publication_gates_passed,
        )
    if not release_decision.allowed:
        raise RuntimeError(
            f'promote_forecast_run blocked: {release_decision.blocking_reason}. '
            f'Model {model_type}/{model_version} cannot be promoted under current release policy.'
        )
    promoted = rest_rpc('promote_forecast_run', {'p_forecast_run_id': forecast_run_id}, timeout_seconds=120)
    _record_event(
        run_id=forecast_run_id,
        stage='published',
        status='ok',
        detail={
            'artifact_mode': release_decision.artifact_mode,
            'warning_authority': release_decision.warning_authority,
            'release_decision': release_decision.as_dict(),
        },
    )
    if isinstance(promoted, list):
        return promoted[0] if promoted and isinstance(promoted[0], dict) else None
    return promoted if isinstance(promoted, dict) else None
