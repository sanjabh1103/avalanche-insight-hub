from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.common.supabase_io import patch_row_by_id, rest_get


def _filtered_linkage(linkage: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in linkage.items()
        if value is not None
    }


def merge_compute_job_result_linkage(
    *,
    compute_job_id: str,
    linkage: dict[str, Any],
) -> None:
    rows = rest_get(
        'compute_jobs',
        params={
            'id': f'eq.{compute_job_id}',
            'select': 'result',
            'limit': '1',
        },
    )
    existing_result = rows[0].get('result') if rows else {}
    merged_result = existing_result if isinstance(existing_result, dict) else {}
    merged_result = {
        **merged_result,
        **_filtered_linkage(linkage),
    }
    patch_row_by_id(
        'compute_jobs',
        compute_job_id,
        {'result': merged_result},
        returning='minimal',
        timeout_seconds=120,
    )


def _first_useful_worker_error(worker_result: dict[str, Any]) -> str | None:
    for key in ('error', 'error_message', 'detail', 'message', 'reason'):
        value = worker_result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ('stderr_tail', 'stdout_tail'):
        value = worker_result.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()
    return None


def merge_compute_job_terminal_result(
    *,
    compute_job_id: str,
    linkage: dict[str, Any],
    worker_result: dict[str, Any],
) -> None:
    rows = rest_get(
        'compute_jobs',
        params={
            'id': f'eq.{compute_job_id}',
            'select': 'result',
            'limit': '1',
        },
    )
    existing_result = rows[0].get('result') if rows else {}
    merged_result = existing_result if isinstance(existing_result, dict) else {}
    worker_completed_at = worker_result.get('completed_at')
    if not isinstance(worker_completed_at, str) or not worker_completed_at.strip():
        worker_completed_at = datetime.now(timezone.utc).isoformat()
    merged_result = {
        **merged_result,
        **_filtered_linkage(linkage),
        'workerResult': worker_result,
        'workerCompletedAt': worker_completed_at,
    }
    worker_status = str(worker_result.get('status') or '').strip().lower()
    compute_job_status = 'completed' if worker_status == 'ok' else 'failed'
    error_message = None if compute_job_status == 'completed' else (
        _first_useful_worker_error(worker_result) or 'worker execution failed'
    )
    patch_row_by_id(
        'compute_jobs',
        compute_job_id,
        {
            'status': compute_job_status,
            'result': merged_result,
            'error': error_message,
        },
        returning='minimal',
        timeout_seconds=120,
    )


def merge_forecast_run_model_metadata_linkage(
    *,
    forecast_run_id: str,
    linkage: dict[str, Any],
) -> None:
    rows = rest_get(
        'forecast_runs',
        params={
            'id': f'eq.{forecast_run_id}',
            'select': 'model_metadata',
            'limit': '1',
        },
    )
    existing_metadata = rows[0].get('model_metadata') if rows else {}
    merged_metadata = existing_metadata if isinstance(existing_metadata, dict) else {}
    merged_metadata = {
        **merged_metadata,
        **_filtered_linkage(linkage),
    }
    patch_row_by_id(
        'forecast_runs',
        forecast_run_id,
        {'model_metadata': merged_metadata},
        returning='minimal',
        timeout_seconds=120,
    )
