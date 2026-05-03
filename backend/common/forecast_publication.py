from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

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
) -> dict[str, Any]:
    issue_time = datetime.now(timezone.utc).isoformat()
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
                datetime.fromisoformat(issue_time.replace('Z', '+00:00'))
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

        rest_insert('forecast_run_hours', hour_rows, returning='minimal', timeout_seconds=120)
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


def promote_forecast_run(*, forecast_run_id: str) -> None:
    rest_rpc('promote_forecast_run', {'p_forecast_run_id': forecast_run_id}, timeout_seconds=120)
    _record_event(
        run_id=forecast_run_id,
        stage='published',
        status='ok',
        detail={},
    )
