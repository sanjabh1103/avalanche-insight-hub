from __future__ import annotations

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
