from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from typing import Any

from backend.common.avalanche_prone_terrain import APT_MAX_SLOPE_DEG, APT_MIN_SLOPE_DEG, APT_PROFILE, apply_apt_unified_metric
from backend.common.forecast_bulletins import build_forecast_bulletin
from backend.common.runout import build_runout_polygons
from backend.common.storage_io import storage_download_bytes, storage_upload_bytes, storage_upsert_json
from backend.common.supabase_io import patch_row_by_id, rest_get


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _gzipped_json_bytes(payload: Any) -> bytes:
    return gzip.compress(_json_bytes(payload))


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _split_storage_ref(storage_ref: str) -> tuple[str, str]:
    bucket, object_path = storage_ref.split('/', 1)
    return bucket, object_path


def _load_active_run(*, run_id: str | None, region_key: str | None) -> dict[str, Any]:
    if run_id:
        rows = rest_get(
            'forecast_runs',
            {
                'id': f'eq.{run_id}',
                'select': 'id,region_key,status,forecast_date,manifest_storage_ref,runout_storage_ref,model_metadata',
                'limit': '1',
            },
        )
    else:
        rows = rest_get(
            'forecast_runs',
            {
                'region_key': f'eq.{region_key}',
                'active': 'is.true',
                'select': 'id,region_key,status,forecast_date,manifest_storage_ref,runout_storage_ref,model_metadata',
                'limit': '1',
            },
        )
    if not rows:
        raise RuntimeError('active forecast_run not found')
    return rows[0]


def _download_manifest(manifest_storage_ref: str) -> dict[str, Any]:
    bucket, object_path = _split_storage_ref(manifest_storage_ref)
    return json.loads(storage_download_bytes(bucket=bucket, object_path=object_path).decode('utf-8'))


def _download_hour_payload(storage_ref: str) -> dict[str, Any]:
    bucket, object_path = _split_storage_ref(storage_ref)
    payload = storage_download_bytes(bucket=bucket, object_path=object_path)
    return json.loads(gzip.decompress(payload).decode('utf-8'))


def _region_status(cells: list[dict[str, Any]]) -> str:
    ready_count = sum(1 for cell in cells if cell.get('status') == 'ready')
    if ready_count == len(cells):
        return 'ready'
    if ready_count > 0:
        return 'partial'
    return 'stale'


def _apply_hourly_transform(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [apply_apt_unified_metric(dict(cell)) for cell in cells]


def run(*, run_id: str | None, region_key: str | None, apply: bool) -> dict[str, Any]:
    os.environ.setdefault('SUPABASE_URL', os.environ.get('VITE_SUPABASE_URL', ''))
    active_run = _load_active_run(run_id=run_id, region_key=region_key)
    manifest = _download_manifest(str(active_run['manifest_storage_ref']))
    hour_rows = rest_get(
        'forecast_run_hours',
        {
            'forecast_run_id': f"eq.{active_run['id']}",
            'select': 'id,forecast_hour,storage_ref,valid_time',
            'order': 'forecast_hour.asc',
        },
    )
    hour_rows_by_hour = {int(row['forecast_hour']): row for row in hour_rows}

    manifest_hours = list(manifest.get('hours') or [])
    transformed_hours: list[tuple[int, dict[str, Any], bytes]] = []
    updated_manifest_hours: list[dict[str, Any]] = []
    first_hour_cells: list[dict[str, Any]] | None = None

    for manifest_hour in manifest_hours:
        forecast_hour = int(manifest_hour['forecastHour'])
        hour_payload = _download_hour_payload(str(manifest_hour['storageRef']))
        updated_cells = _apply_hourly_transform(list(hour_payload.get('cells') or []))
        if first_hour_cells is None:
            first_hour_cells = updated_cells
        updated_payload = {
            **hour_payload,
            'cells': updated_cells,
        }
        compressed = _gzipped_json_bytes(updated_payload)
        transformed_hours.append((forecast_hour, updated_payload, compressed))
        ready_cells = sum(1 for cell in updated_cells if cell.get('status') == 'ready')
        stale_cells = len(updated_cells) - ready_cells
        updated_manifest_hours.append({
            **manifest_hour,
            'cellCount': len(updated_cells),
            'readyCellCount': ready_cells,
            'staleCellCount': stale_cells,
            'payloadSha256': _sha256_hex(compressed),
        })

    if first_hour_cells is None:
        raise RuntimeError('manifest did not include any hour payloads')

    region_status = _region_status(first_hour_cells)
    bulletin = build_forecast_bulletin(rows=first_hour_cells, region_status=region_status)
    runout_polygons = build_runout_polygons(str(active_run['region_key']), first_hour_cells)
    runout_payload = {
        'schema_version': 'forecast-runouts/v1',
        'forecast_run_id': str(active_run['id']),
        'region_key': str(active_run['region_key']),
        'forecast_date': str(active_run['forecast_date']),
        'runout_polygons': runout_polygons,
    }
    runout_bytes = _gzipped_json_bytes(runout_payload)

    model_metadata = dict(active_run.get('model_metadata') or {})
    method_counts: dict[str, int] = {}
    for polygon in runout_polygons:
        method = str(polygon.get('method') or 'unknown')
        method_counts[method] = method_counts.get(method, 0) + 1
    model_metadata.update({
        'apt_profile': APT_PROFILE,
        'apt_min_slope_deg': APT_MIN_SLOPE_DEG,
        'apt_max_slope_deg': APT_MAX_SLOPE_DEG,
        'public_risk_metric': 'apt_gated_probability_risk_score_v1',
        'runout_method_counts': method_counts,
        'runout_method_sample': next((polygon.get('method') for polygon in runout_polygons if polygon.get('method') and polygon.get('method') != 'deferred_oom_guard'), None),
    })
    updated_manifest = {
        **manifest,
        'forecastBulletin': bulletin,
        'modelMetadata': model_metadata,
        'runoutStorageRef': str(active_run['runout_storage_ref']),
        'hours': updated_manifest_hours,
    }

    if apply:
        for forecast_hour, payload, compressed in transformed_hours:
            manifest_hour = next(hour for hour in updated_manifest_hours if int(hour['forecastHour']) == forecast_hour)
            bucket, object_path = _split_storage_ref(str(manifest_hour['storageRef']))
            storage_upload_bytes(
                bucket=bucket,
                object_path=object_path,
                payload=compressed,
                content_type='application/gzip',
                upsert=True,
            )
            run_hour_row = hour_rows_by_hour.get(forecast_hour)
            if run_hour_row is not None:
                patch_row_by_id(
                    'forecast_run_hours',
                    str(run_hour_row['id']),
                    {
                        'cell_count': len(payload['cells']),
                        'ready_cell_count': manifest_hour['readyCellCount'],
                        'stale_cell_count': manifest_hour['staleCellCount'],
                        'payload_sha256': manifest_hour['payloadSha256'],
                    },
                    returning='minimal',
                )

        runout_bucket, runout_object_path = _split_storage_ref(str(active_run['runout_storage_ref']))
        storage_upload_bytes(
            bucket=runout_bucket,
            object_path=runout_object_path,
            payload=runout_bytes,
            content_type='application/gzip',
            upsert=True,
        )

        manifest_bucket, manifest_object_path = _split_storage_ref(str(active_run['manifest_storage_ref']))
        storage_upsert_json(
            bucket=manifest_bucket,
            object_path=manifest_object_path,
            payload=updated_manifest,
            upsert=True,
        )
        patch_row_by_id(
            'forecast_runs',
            str(active_run['id']),
            {
                'forecast_bulletins': bulletin or {},
                'model_metadata': model_metadata,
            },
            returning='minimal',
        )

    return {
        'run_id': str(active_run['id']),
        'region_key': str(active_run['region_key']),
        'apt_profile': APT_PROFILE,
        'eligible_cell_count': (bulletin or {}).get('derived_from', {}).get('eligible_cell_count'),
        'selected_level_cell_count': (bulletin or {}).get('derived_from', {}).get('selected_level_cell_count'),
        'selected_level_cell_share': (bulletin or {}).get('derived_from', {}).get('selected_level_cell_share'),
        'danger_level': (bulletin or {}).get('danger_level'),
        'danger_label': (bulletin or {}).get('danger_label'),
        'apply': apply,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Backfill the unified APT-gated public hazard metric into an active forecast run.')
    parser.add_argument('--run-id', default=None)
    parser.add_argument('--region-key', default=None)
    parser.add_argument('--apt-min-slope', type=float, default=APT_MIN_SLOPE_DEG)
    parser.add_argument('--apt-max-slope', type=float, default=APT_MAX_SLOPE_DEG)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)

    if args.apt_min_slope != APT_MIN_SLOPE_DEG or args.apt_max_slope != APT_MAX_SLOPE_DEG:
        raise SystemExit('this script only supports the apt_30_50_v1 profile')
    if not args.run_id and not args.region_key:
        raise SystemExit('pass --run-id or --region-key')

    summary = run(run_id=args.run_id, region_key=args.region_key, apply=args.apply)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
