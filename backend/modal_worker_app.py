from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable

from backend.common.config import load_settings
from backend.common.modal_execution_manifest import (
    MODAL_APP_NAME_DEFAULT as MANIFEST_APP_NAME_DEFAULT,
    build_execution_manifest,
    is_non_terminal,
    is_terminal_success,
    validate_manifest,
)
from backend.common.run_linkage import (
    merge_compute_job_result_linkage,
    merge_forecast_run_model_metadata_linkage,
)
from backend.common.supabase_io import has_supabase_credentials
from backend.sar_unet_worker import (
    SAR_UNET_SEGMENTATION_THRESHOLD,
    run_train_mtslstm,
    run_train_sar_unet,
    run_worker_request,
)
from backend.sar_unet_training import (
    build_sar_validation_error_diagnostics,
    evaluate_sar_checkpoint,
    evaluate_sar_checkpoint_scene_blended,
)

if str(os.environ.get('AVALANCHE_SKIP_MODAL_IMPORT') or '').strip().lower() in {'1', 'true', 'yes', 'on'}:
    modal = None
else:
    try:  # pragma: no cover - optional dependency for deployment only
        import modal
    except Exception:  # pragma: no cover - optional dependency
        modal = None

try:  # pragma: no cover - optional dependency for deployment only
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
except Exception:  # pragma: no cover - optional dependency
    FastAPI = None
    HTTPException = RuntimeError  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]
    JSONResponse = None  # type: ignore[assignment]

# Volume mount path — artifact root inside the Modal container.
# Matches ARTIFACT_ROOT env var so sar_unet_worker.py writes here automatically.
VOLUME_MOUNT = '/artifacts'
DEM_VOLUME_ROOT = f'{VOLUME_MOUNT}/dem'
MODEL_VOLUME_ROOT = f'{VOLUME_MOUNT}/models'
WORKER_TOKEN_ENV = 'MODAL_WORKER_TOKEN'
MODAL_APP_NAME = 'avalanche-modal-worker'
MODAL_REMOTE_SEGMENT_FUNCTION = 'sar_segment_remote'
MODAL_REMOTE_TRAIN_SAR_FUNCTION = 'train_sar_unet_remote'
MODAL_REMOTE_EVALUATE_SAR_CHECKPOINT_FUNCTION = 'evaluate_sar_checkpoint_remote'
MODAL_REMOTE_EVALUATE_RELEASE_FUNCTION = 'evaluate_release_remote'
MODAL_REMOTE_TRAIN_FUNCTION = 'train_mts_lstm_remote'
MODAL_REMOTE_INFER_FUNCTION = 'infer_mts_lstm_remote'
MODAL_PINNED_RUNTIME_PACKAGES = ('shap==0.51.0', 'scikit-learn==1.9.0')
MODAL_PINNED_MODAL_SDK = 'modal==0.73.83'
MODAL_PINNED_FASTAPI = 'fastapi[standard]==0.115.6'
MODAL_PINNED_PYARROW = 'pyarrow==25.0.0'
MODAL_PINNED_TORCH = 'torch==2.5.1'
MODAL_PINNED_TORCHVISION = 'torchvision==0.20.1'
MODAL_PINNED_TORCHAUDIO = 'torchaudio==2.5.1'
MODAL_RUNTIME_LOCK = 'backend/locks/modal-py312.txt'
MODAL_IMAGE_PYTHON_VERSION = '3.12'
MODAL_MIN_CONTAINERS = int(os.environ.get('MODAL_MIN_CONTAINERS', '0'))
MODAL_BUFFER_CONTAINERS = int(os.environ.get('MODAL_BUFFER_CONTAINERS', '0'))
MODAL_SCALEDOWN_WINDOW_SECONDS = int(os.environ.get('MODAL_SCALEDOWN_WINDOW_SECONDS', '30'))
MODAL_INFER_CPU = float(os.environ.get('MODAL_INFER_CPU', '4.0'))
MODAL_INFER_MEMORY_MB = int(os.environ.get('MODAL_INFER_MEMORY_MB', '8192'))

# Function-level runtime manifest: declares CPU vs GPU role, timeout, and
# resource allocation for each remote function. Exposed via the health endpoint
# and embedded in every execution manifest.
MODAL_FUNCTION_RUNTIME_MANIFEST: dict[str, dict[str, Any]] = {
    MODAL_REMOTE_SEGMENT_FUNCTION: {'device': 'gpu', 'gpu_type': 'T4', 'timeout_seconds': 1800, 'role': 'sar_segmentation'},
    MODAL_REMOTE_TRAIN_SAR_FUNCTION: {'device': 'gpu', 'gpu_type': 'T4', 'timeout_seconds': 14400, 'role': 'sar_training'},
    MODAL_REMOTE_EVALUATE_SAR_CHECKPOINT_FUNCTION: {'device': 'gpu', 'gpu_type': 'T4', 'timeout_seconds': 3600, 'role': 'sar_checkpoint_evaluation'},
    MODAL_REMOTE_EVALUATE_RELEASE_FUNCTION: {'device': 'cpu', 'cpu': MODAL_INFER_CPU, 'memory_mb': MODAL_INFER_MEMORY_MB, 'timeout_seconds': 3600, 'role': 'release_evaluation'},
    MODAL_REMOTE_TRAIN_FUNCTION: {'device': 'gpu', 'gpu_type': 'T4', 'timeout_seconds': 14400, 'role': 'mts_lstm_training'},
    MODAL_REMOTE_INFER_FUNCTION: {'device': 'cpu', 'cpu': MODAL_INFER_CPU, 'memory_mb': MODAL_INFER_MEMORY_MB, 'timeout_seconds': 3600, 'role': 'mts_lstm_inference'},
}


def _artifact_root() -> Path:
    env_root = os.environ.get('ARTIFACT_ROOT')
    if env_root:
        return Path(env_root)
    return load_settings().artifact_root


def _truthy(value: Any) -> bool:
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_path() -> Path | None:
    raw = os.environ.get('SAR_UNET_MODEL_PATH')
    return Path(raw) if raw else None


def _request_model_path(payload: dict[str, Any]) -> Path | None:
    raw = payload.get('model_path') or payload.get('checkpoint_path')
    if not isinstance(raw, str) or not raw.strip():
        return _model_path()
    path = Path(raw.strip())
    try:
        path.relative_to(VOLUME_MOUNT)
    except ValueError as exc:
        raise ValueError(f'Modal SAR model_path must be under {VOLUME_MOUNT}: {path}') from exc
    return path


def _require_volume_path(payload: dict[str, Any], field_names: tuple[str, ...]) -> Path:
    raw: Any = None
    selected_field = field_names[0]
    for field_name in field_names:
        value = payload.get(field_name)
        if isinstance(value, str) and value.strip():
            raw = value.strip()
            selected_field = field_name
            break
    if not isinstance(raw, str) or not raw:
        raise ValueError(f'Modal request requires one of {", ".join(field_names)}')
    path = Path(raw)
    try:
        path.relative_to(VOLUME_MOUNT)
    except ValueError as exc:
        raise ValueError(f'Modal {selected_field} must be under {VOLUME_MOUNT}: {path}') from exc
    return path


def _dispatch_worker_request(mode: str, payload: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    return run_worker_request(
        mode,
        payload,
        artifact_root=_artifact_root(),
        model_path=_model_path(),
        device=os.environ.get('SAR_UNET_DEVICE', 'cpu'),
        threshold=float(os.environ.get('SAR_UNET_SEGMENTATION_THRESHOLD', str(SAR_UNET_SEGMENTATION_THRESHOLD))),
        hazard_type=str(payload.get('hazard_type') or settings.hazard_type or 'avalanche'),
        dry_run=str(payload.get('dry_run', '')).strip().lower() in {'1', 'true', 'yes', 'on'},
    )


def handle_sar_segment(payload: dict[str, Any]) -> dict[str, Any]:
    return _dispatch_worker_request('sar-segment', payload)


def handle_train_sar_unet(payload: dict[str, Any]) -> dict[str, Any]:
    return _dispatch_worker_request('train-sar-unet', payload)


def handle_train_mtslstm(payload: dict[str, Any]) -> dict[str, Any]:
    return _dispatch_worker_request('train-mtslstm', payload)


def handle_infer_mtslstm(payload: dict[str, Any]) -> dict[str, Any]:
    return _dispatch_worker_request('infer-mtslstm', payload)


def handle_evaluate_release(payload: dict[str, Any]) -> dict[str, Any]:
    return _dispatch_worker_request('evaluate-release', payload)


def run_remote_train_sar_unet(
    payload: dict[str, Any],
    *,
    artifact_root: Path,
    device: str,
    volume_reload: Callable[[], None] | None = None,
    volume_commit: Callable[[], None] | None = None,
) -> dict[str, Any]:
    started_at = _utc_now_iso()
    if volume_reload is not None:
        volume_reload()

    progress_callback: Callable[[dict[str, Any]], None] | None = None
    if volume_commit is not None:
        def _commit_progress(_: dict[str, Any]) -> None:
            volume_commit()

        progress_callback = _commit_progress

    report = run_train_sar_unet(
        payload,
        artifact_root=artifact_root,
        device=device,
        progress_callback=progress_callback,
    )
    committed = False
    if volume_commit is not None:
        volume_commit()
        committed = True
    artifact_dir = str(report.get('artifact_dir') or report.get('training_artifact_dir') or '')
    artifact_paths: list[Path | str] = [artifact_dir] if artifact_dir else []
    return _attach_execution_manifest(
        report,
        function_name=MODAL_REMOTE_TRAIN_SAR_FUNCTION,
        call_id=str(report.get('call_id') or report.get('function_call_id') or ''),
        started_at=started_at,
        request_payload=payload,
        gpu_configured='T4' if device == 'cuda' else '',
        artifact_paths=artifact_paths,
        volume_committed=committed,
    )


def run_remote_evaluate_sar_checkpoint(
    payload: dict[str, Any],
    *,
    artifact_root: Path,
    device: str,
    volume_reload: Callable[[], None] | None = None,
    volume_commit: Callable[[], None] | None = None,
) -> dict[str, Any]:
    started_at = _utc_now_iso()
    _require_volume_path(payload, ('training_manifest_path', 'training_manifest'))
    _require_volume_path(payload, ('checkpoint_path', 'model_checkpoint_path', 'initial_checkpoint_path'))
    if volume_reload is not None:
        volume_reload()
    if str(payload.get('diagnostics', '')).strip().lower() in {'1', 'true', 'yes', 'on'}:
        report = build_sar_validation_error_diagnostics(payload, artifact_root=artifact_root, device=device)
    elif (
        str(payload.get('scene_blended', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
        or str(payload.get('evaluation_mode') or '').strip() == 'scene_blended'
    ):
        report = evaluate_sar_checkpoint_scene_blended(payload, artifact_root=artifact_root, device=device)
    else:
        report = evaluate_sar_checkpoint(payload, artifact_root=artifact_root, device=device)
    committed = False
    if volume_commit is not None:
        volume_commit()
        committed = True
    return _attach_execution_manifest(
        report,
        function_name=MODAL_REMOTE_EVALUATE_SAR_CHECKPOINT_FUNCTION,
        call_id=str(report.get('call_id') or report.get('function_call_id') or ''),
        started_at=started_at,
        request_payload=payload,
        gpu_configured='T4' if device == 'cuda' else '',
        volume_committed=committed,
    )


def run_remote_evaluate_release(
    payload: dict[str, Any],
    *,
    artifact_root: Path,
    volume_reload: Callable[[], None] | None = None,
    volume_commit: Callable[[], None] | None = None,
) -> dict[str, Any]:
    started_at = _utc_now_iso()
    if volume_reload is not None:
        volume_reload()
    safe_payload = {**payload, 'dry_run': True}
    report = run_worker_request(
        'evaluate-release',
        safe_payload,
        artifact_root=artifact_root,
        model_path=_model_path(),
        device=os.environ.get('SAR_UNET_DEVICE', 'cpu'),
        threshold=float(os.environ.get('SAR_UNET_SEGMENTATION_THRESHOLD', str(SAR_UNET_SEGMENTATION_THRESHOLD))),
        hazard_type=str(safe_payload.get('hazard_type') or load_settings().hazard_type or 'avalanche'),
        dry_run=True,
    )
    committed = False
    if volume_commit is not None:
        volume_commit()
        committed = True
    return _attach_execution_manifest(
        report,
        function_name=MODAL_REMOTE_EVALUATE_RELEASE_FUNCTION,
        call_id=str(report.get('call_id') or report.get('function_call_id') or ''),
        started_at=started_at,
        request_payload=payload,
        gpu_configured='',
        volume_committed=committed,
    )


def run_remote_train_mtslstm(
    payload: dict[str, Any],
    *,
    artifact_root: Path,
    volume_reload: Callable[[], None] | None = None,
    volume_commit: Callable[[], None] | None = None,
) -> dict[str, Any]:
    started_at = _utc_now_iso()
    if volume_reload is not None:
        volume_reload()
    report = run_train_mtslstm(payload, artifact_root=artifact_root)
    committed = False
    if volume_commit is not None:
        volume_commit()
        committed = True
    artifact_dir = str(report.get('artifact_dir') or '')
    artifact_paths: list[Path | str] = [artifact_dir] if artifact_dir else []
    return _attach_execution_manifest(
        report,
        function_name=MODAL_REMOTE_TRAIN_FUNCTION,
        call_id=str(report.get('call_id') or report.get('function_call_id') or ''),
        started_at=started_at,
        request_payload=payload,
        gpu_configured='T4',
        artifact_paths=artifact_paths,
        volume_committed=committed,
    )


def run_remote_sar_segment(
    payload: dict[str, Any],
    *,
    artifact_root: Path,
    device: str,
    volume_reload: Callable[[], None] | None = None,
    volume_commit: Callable[[], None] | None = None,
) -> dict[str, Any]:
    started_at = _utc_now_iso()
    if volume_reload is not None:
        volume_reload()
    settings = load_settings()
    report = run_worker_request(
        'sar-segment',
        payload,
        artifact_root=artifact_root,
        model_path=_request_model_path(payload),
        device=device,
        threshold=float(payload.get('threshold') or os.environ.get('SAR_UNET_SEGMENTATION_THRESHOLD', str(SAR_UNET_SEGMENTATION_THRESHOLD))),
        hazard_type=str(payload.get('hazard_type') or settings.hazard_type or 'avalanche'),
        dry_run=str(payload.get('dry_run', '')).strip().lower() in {'1', 'true', 'yes', 'on'},
    )
    committed = False
    if volume_commit is not None:
        volume_commit()
        committed = True
    if _truthy(payload.get('compact_response')):
        compact = {
            'status': report.get('status'),
            'shadow_mode': report.get('shadow_mode'),
            'model_family': report.get('model_family'),
            'model_version': report.get('model_version'),
            'prediction_mask_dtype': report.get('prediction_mask_dtype'),
            'scene_count': report.get('scene_count'),
            'detections_count': report.get('detections_count'),
            'persisted_events': report.get('persisted_events'),
            'artifact_rows_persisted': report.get('artifact_rows_persisted'),
            'mask_asset_ref_count': len(report.get('mask_asset_refs') or []),
            'mask_asset_refs': report.get('mask_asset_refs') or [],
            'compact_response': True,
        }
        return _attach_execution_manifest(
            compact,
            function_name=MODAL_REMOTE_SEGMENT_FUNCTION,
            call_id=str(report.get('call_id') or ''),
            started_at=started_at,
            gpu_configured='T4' if device == 'cuda' else '',
            volume_committed=committed,
        )
    return _attach_execution_manifest(
        report,
        function_name=MODAL_REMOTE_SEGMENT_FUNCTION,
        call_id=str(report.get('call_id') or ''),
        started_at=started_at,
        request_payload=payload,
        gpu_configured='T4' if device == 'cuda' else '',
        volume_committed=committed,
    )


def run_remote_infer_mtslstm(
    payload: dict[str, Any],
    *,
    artifact_root: Path,
    volume_reload: Callable[[], None] | None = None,
    volume_commit: Callable[[], None] | None = None,
) -> dict[str, Any]:
    started_at = _utc_now_iso()
    if volume_reload is not None:
        volume_reload()
    report = handle_infer_mtslstm(payload)
    committed = False
    if volume_commit is not None:
        volume_commit()
        committed = True
    return _attach_execution_manifest(
        report,
        function_name=MODAL_REMOTE_INFER_FUNCTION,
        call_id=str(report.get('call_id') or ''),
        started_at=started_at,
        request_payload=payload,
        gpu_configured='',
        volume_committed=committed,
    )


def _require_modal() -> Any:
    if modal is None:
        raise RuntimeError('modal must be installed to submit or poll remote MTS-LSTM jobs')
    return modal


def _accepted_modal_job(call: Any, request_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = {
        'status': 'accepted',
        'call_id': str(call.object_id),
        'modal_call_id': str(call.object_id),
        'request_type': request_type,
        'runtime_provider': 'modal',
    }
    if isinstance(payload, dict):
        compute_job_id = payload.get('compute_job_id') or payload.get('job_id')
        if compute_job_id is not None and str(compute_job_id).strip():
            body['compute_job_id'] = str(compute_job_id).strip()
        run_id = payload.get('run_id')
        if run_id is not None and str(run_id).strip():
            body['run_id'] = str(run_id).strip()
        artifact_dir = payload.get('artifact_dir')
        if artifact_dir is not None and str(artifact_dir).strip():
            body['artifact_dir'] = str(artifact_dir).strip()
    return body


def _pending_modal_job(call_id: str, request_type: str) -> dict[str, Any]:
    return {
        'status': 'pending',
        'call_id': call_id,
        'modal_call_id': call_id,
        'request_type': request_type,
        'runtime_provider': 'modal',
    }


def _expired_modal_job(call_id: str, request_type: str) -> dict[str, Any]:
    return {
        'status': 'not_found',
        'call_id': call_id,
        'modal_call_id': call_id,
        'request_type': request_type,
        'runtime_provider': 'modal',
        'reason': 'result_expired',
    }


def _cancelled_modal_job(call_id: str, request_type: str) -> dict[str, Any]:
    return {
        'status': 'cancelled',
        'call_id': call_id,
        'modal_call_id': call_id,
        'request_type': request_type,
        'runtime_provider': 'modal',
        'reason': 'cancelled_by_user',
    }


def _classify_modal_poll_exception(
    modal_module: Any,
    exc: Exception,
    *,
    call_id: str,
    request_type: str,
) -> tuple[int, dict[str, Any]] | None:
    modal_exceptions = getattr(modal_module, 'exception', None)
    timeout_error = getattr(modal_exceptions, 'TimeoutError', None)
    connection_error = getattr(modal_exceptions, 'ConnectionError', None)
    output_expired_error = getattr(modal_exceptions, 'OutputExpiredError', None)
    remote_error = getattr(modal_exceptions, 'RemoteError', None)
    if isinstance(exc, TimeoutError) or (
        timeout_error is not None and isinstance(exc, timeout_error)
    ):
        return 202, _pending_modal_job(call_id, request_type)
    if connection_error is not None and isinstance(exc, connection_error):
        if 'deadline exceeded' in str(exc).strip().lower():
            return 202, _pending_modal_job(call_id, request_type)
    if output_expired_error is not None and isinstance(exc, output_expired_error):
        return 404, _expired_modal_job(call_id, request_type)
    if remote_error is not None and isinstance(exc, remote_error):
        if 'cancelled by user' in str(exc).strip().lower():
            return 409, _cancelled_modal_job(call_id, request_type)
    return None


def _extract_run_linkage(result: dict[str, Any], call_id: str) -> dict[str, Any]:
    compute_job_id = result.get('compute_job_id') or result.get('job_id')
    forecast_run_id = result.get('forecast_run_id')
    forecast_run_ids = result.get('forecast_run_ids')
    forecast_run_ids_by_region = result.get('forecast_run_ids_by_region')
    return {
        'modal_call_id': call_id,
        'compute_job_id': str(compute_job_id).strip() if compute_job_id is not None and str(compute_job_id).strip() else None,
        'artifact_dir': result.get('artifact_dir'),
        'forecast_run_id': forecast_run_id,
        'forecast_run_ids': forecast_run_ids if isinstance(forecast_run_ids, list) else [],
        'forecast_run_ids_by_region': forecast_run_ids_by_region if isinstance(forecast_run_ids_by_region, dict) else {},
    }


def _sync_modal_job_linkage_best_effort(result: dict[str, Any], call_id: str) -> None:
    if not has_supabase_credentials():
        return
    linkage = _extract_run_linkage(result, call_id)
    compute_job_id = linkage.get('compute_job_id')
    if isinstance(compute_job_id, str) and compute_job_id.strip():
        try:
            merge_compute_job_result_linkage(
                compute_job_id=compute_job_id,
                linkage=linkage,
            )
        except Exception:
            pass
    forecast_run_ids: list[str] = []
    forecast_run_id = linkage.get('forecast_run_id')
    if isinstance(forecast_run_id, str) and forecast_run_id.strip():
        forecast_run_ids.append(forecast_run_id)
    for item in linkage.get('forecast_run_ids') if isinstance(linkage.get('forecast_run_ids'), list) else []:
        if isinstance(item, str) and item.strip() and item not in forecast_run_ids:
            forecast_run_ids.append(item)
    for item in (linkage.get('forecast_run_ids_by_region') or {}).values() if isinstance(linkage.get('forecast_run_ids_by_region'), dict) else []:
        if isinstance(item, str) and item.strip() and item not in forecast_run_ids:
            forecast_run_ids.append(item)
    for run_id in forecast_run_ids:
        try:
            merge_forecast_run_model_metadata_linkage(
                forecast_run_id=run_id,
                linkage=linkage,
            )
        except Exception:
            pass


def _ok_modal_job(call_id: str, request_type: str, result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        body = {
            **result,
            'call_id': str(result.get('call_id') or call_id),
            'modal_call_id': str(result.get('modal_call_id') or call_id),
            'request_type': str(result.get('request_type') or request_type),
            'runtime_provider': str(result.get('runtime_provider') or 'modal'),
        }
        manifest = body.get('execution_manifest')
        if isinstance(manifest, dict):
            # G5: NEVER rewrite attestation fields. If the manifest's call_id
            # does not match the provider call_id, reject the job instead of
            # silently rewriting it.
            manifest_call_id = str(manifest.get('call_id') or '').strip()
            if manifest_call_id and manifest_call_id != call_id:
                body['status'] = 'error'
                body['reason'] = 'manifest_call_id_mismatch'
                body['manifest_errors'] = [
                    f'manifest call_id {manifest_call_id!r} does not match '
                    f'provider call_id {call_id!r}'
                ]
            elif is_terminal_success(str(body.get('status') or '')):
                manifest_errors = validate_manifest(
                    manifest,
                    expected_run_id=body.get('run_id'),
                    expected_call_id=call_id,
                    expected_compute_job_id=body.get('compute_job_id'),
                )
                if manifest_errors:
                    body['status'] = 'error'
                    body['reason'] = 'invalid_execution_manifest'
                    body['manifest_errors'] = manifest_errors
        elif is_terminal_success(str(body.get('status') or '')):
            body['status'] = 'error'
            body['reason'] = 'missing_execution_manifest'
        _sync_modal_job_linkage_best_effort(body, call_id)
        return body
    body = {
        'status': 'ok',
        'call_id': call_id,
        'modal_call_id': call_id,
        'request_type': request_type,
        'runtime_provider': 'modal',
        'result': result,
    }
    return body


def _attach_execution_manifest(
    result: dict[str, Any],
    *,
    function_name: str,
    call_id: str,
    started_at: str,
    request_payload: dict[str, Any] | None = None,
    gpu_configured: str = '',
    artifact_paths: list[Path | str] | None = None,
    volume_committed: bool = False,
) -> dict[str, Any]:
    """Attach a machine-verifiable execution manifest to a remote result."""
    request = request_payload or {}
    status = str(result.get('status') or 'ok')
    run_id = str(result.get('run_id') or request.get('run_id') or '')
    compute_job_id = str(result.get('compute_job_id') or request.get('compute_job_id') or request.get('job_id') or '')
    input_manifest_id = str(result.get('input_manifest_id') or request.get('input_manifest_id') or '')
    input_hash = str(result.get('input_manifest_hash') or request.get('input_manifest_hash') or '')
    model_version = str(result.get('model_version') or result.get('candidate_model_version') or request.get('model_version') or request.get('candidate_model_version') or '')
    shadow_mode = bool(result.get('shadow_mode', request.get('shadow_mode', True)))
    allow_publish = bool(result.get('allow_publish', request.get('allow_publish', False)))
    error_message = str(result.get('error') or result.get('reason') or '') if not is_terminal_success(status) else ''

    for field_name, value in {
        'run_id': run_id,
        'compute_job_id': compute_job_id,
        'input_manifest_id': input_manifest_id,
        'input_manifest_hash': input_hash,
    }.items():
        if value:
            result.setdefault(field_name, value)

    manifest = build_execution_manifest(
        function_name=function_name,
        call_id=call_id,
        terminal_status=status,
        started_at=started_at,
        run_id=run_id,
        compute_job_id=compute_job_id,
        input_manifest_id=input_manifest_id,
        input_manifest_hash=input_hash,
        source_commit=str(result.get('source_commit') or request.get('source_commit') or ''),
        model_version=model_version,
        shadow_mode=shadow_mode,
        allow_publish=allow_publish,
        gpu_configured=gpu_configured,
        artifact_paths=artifact_paths,
        artifact_root=str(request.get('artifact_root') or os.environ.get('ARTIFACT_ROOT') or ''),
        volume_name=str(request.get('volume_name') or os.environ.get('MODAL_VOLUME_NAME') or ''),
        volume_committed=volume_committed,
        error_message=error_message,
        extra_payload=result,
    )
    result['execution_manifest'] = manifest
    return result


def submit_train_sar_unet_job(payload: dict[str, Any]) -> dict[str, Any]:
    modal_module = _require_modal()
    train_function = modal_module.Function.from_name(MODAL_APP_NAME, MODAL_REMOTE_TRAIN_SAR_FUNCTION)
    call = train_function.spawn(payload)
    return _accepted_modal_job(call, 'train_sar_unet', payload)


async def submit_train_sar_unet_job_async(payload: dict[str, Any]) -> dict[str, Any]:
    modal_module = _require_modal()
    train_function = modal_module.Function.from_name(MODAL_APP_NAME, MODAL_REMOTE_TRAIN_SAR_FUNCTION)
    call = await train_function.spawn.aio(payload)
    return _accepted_modal_job(call, 'train_sar_unet', payload)


def poll_train_sar_unet_job(call_id: str) -> tuple[int, dict[str, Any]]:
    modal_module = _require_modal()
    function_call = modal_module.FunctionCall.from_id(call_id)
    try:
        result = function_call.get(timeout=0)
    except Exception as exc:
        handled = _classify_modal_poll_exception(
            modal_module,
            exc,
            call_id=call_id,
            request_type='train_sar_unet',
        )
        if handled is not None:
            return handled
        raise
    return 200, _ok_modal_job(call_id, 'train_sar_unet', result)


async def poll_train_sar_unet_job_async(call_id: str) -> tuple[int, dict[str, Any]]:
    modal_module = _require_modal()
    function_call = modal_module.FunctionCall.from_id(call_id)
    try:
        result = await function_call.get.aio(timeout=0)
    except Exception as exc:
        handled = _classify_modal_poll_exception(
            modal_module,
            exc,
            call_id=call_id,
            request_type='train_sar_unet',
        )
        if handled is not None:
            return handled
        raise
    return 200, _ok_modal_job(call_id, 'train_sar_unet', result)


def submit_train_mtslstm_job(payload: dict[str, Any]) -> dict[str, Any]:
    modal_module = _require_modal()
    train_function = modal_module.Function.from_name(MODAL_APP_NAME, MODAL_REMOTE_TRAIN_FUNCTION)
    call = train_function.spawn(payload)
    return _accepted_modal_job(call, 'train_mtslstm', payload)


async def submit_train_mtslstm_job_async(payload: dict[str, Any]) -> dict[str, Any]:
    modal_module = _require_modal()
    train_function = modal_module.Function.from_name(MODAL_APP_NAME, MODAL_REMOTE_TRAIN_FUNCTION)
    call = await train_function.spawn.aio(payload)
    return _accepted_modal_job(call, 'train_mtslstm', payload)


def poll_train_mtslstm_job(call_id: str) -> tuple[int, dict[str, Any]]:
    modal_module = _require_modal()
    function_call = modal_module.FunctionCall.from_id(call_id)
    try:
        result = function_call.get(timeout=0)
    except Exception as exc:
        handled = _classify_modal_poll_exception(
            modal_module,
            exc,
            call_id=call_id,
            request_type='train_mtslstm',
        )
        if handled is not None:
            return handled
        raise
    return 200, _ok_modal_job(call_id, 'train_mtslstm', result)


async def poll_train_mtslstm_job_async(call_id: str) -> tuple[int, dict[str, Any]]:
    modal_module = _require_modal()
    function_call = modal_module.FunctionCall.from_id(call_id)
    try:
        result = await function_call.get.aio(timeout=0)
    except Exception as exc:
        handled = _classify_modal_poll_exception(
            modal_module,
            exc,
            call_id=call_id,
            request_type='train_mtslstm',
        )
        if handled is not None:
            return handled
        raise
    return 200, _ok_modal_job(call_id, 'train_mtslstm', result)


def submit_infer_mtslstm_job(payload: dict[str, Any]) -> dict[str, Any]:
    modal_module = _require_modal()
    infer_function = modal_module.Function.from_name(MODAL_APP_NAME, MODAL_REMOTE_INFER_FUNCTION)
    call = infer_function.spawn(payload)
    return _accepted_modal_job(call, 'infer_mtslstm', payload)


async def submit_infer_mtslstm_job_async(payload: dict[str, Any]) -> dict[str, Any]:
    modal_module = _require_modal()
    infer_function = modal_module.Function.from_name(MODAL_APP_NAME, MODAL_REMOTE_INFER_FUNCTION)
    call = await infer_function.spawn.aio(payload)
    return _accepted_modal_job(call, 'infer_mtslstm', payload)


def poll_infer_mtslstm_job(call_id: str) -> tuple[int, dict[str, Any]]:
    modal_module = _require_modal()
    function_call = modal_module.FunctionCall.from_id(call_id)
    try:
        result = function_call.get(timeout=0)
    except Exception as exc:
        handled = _classify_modal_poll_exception(
            modal_module,
            exc,
            call_id=call_id,
            request_type='infer_mtslstm',
        )
        if handled is not None:
            return handled
        raise
    return 200, _ok_modal_job(call_id, 'infer_mtslstm', result)


async def poll_infer_mtslstm_job_async(call_id: str) -> tuple[int, dict[str, Any]]:
    modal_module = _require_modal()
    function_call = modal_module.FunctionCall.from_id(call_id)
    try:
        result = await function_call.get.aio(timeout=0)
    except Exception as exc:
        handled = _classify_modal_poll_exception(
            modal_module,
            exc,
            call_id=call_id,
            request_type='infer_mtslstm',
        )
        if handled is not None:
            return handled
        raise
    return 200, _ok_modal_job(call_id, 'infer_mtslstm', result)


def submit_sar_segment_job(payload: dict[str, Any]) -> dict[str, Any]:
    modal_module = _require_modal()
    function = modal_module.Function.from_name(MODAL_APP_NAME, MODAL_REMOTE_SEGMENT_FUNCTION)
    return _accepted_modal_job(function.spawn(payload), 'sar_segment', payload)


async def submit_sar_segment_job_async(payload: dict[str, Any]) -> dict[str, Any]:
    modal_module = _require_modal()
    function = modal_module.Function.from_name(MODAL_APP_NAME, MODAL_REMOTE_SEGMENT_FUNCTION)
    return _accepted_modal_job(await function.spawn.aio(payload), 'sar_segment', payload)


def poll_sar_segment_job(call_id: str) -> tuple[int, dict[str, Any]]:
    modal_module = _require_modal()
    function_call = modal_module.FunctionCall.from_id(call_id)
    try:
        result = function_call.get(timeout=0)
    except Exception as exc:
        handled = _classify_modal_poll_exception(modal_module, exc, call_id=call_id, request_type='sar_segment')
        if handled is not None:
            return handled
        raise
    return 200, _ok_modal_job(call_id, 'sar_segment', result)


async def poll_sar_segment_job_async(call_id: str) -> tuple[int, dict[str, Any]]:
    modal_module = _require_modal()
    function_call = modal_module.FunctionCall.from_id(call_id)
    try:
        result = await function_call.get.aio(timeout=0)
    except Exception as exc:
        handled = _classify_modal_poll_exception(modal_module, exc, call_id=call_id, request_type='sar_segment')
        if handled is not None:
            return handled
        raise
    return 200, _ok_modal_job(call_id, 'sar_segment', result)


def submit_evaluate_release_job(payload: dict[str, Any]) -> dict[str, Any]:
    modal_module = _require_modal()
    function = modal_module.Function.from_name(MODAL_APP_NAME, MODAL_REMOTE_EVALUATE_RELEASE_FUNCTION)
    return _accepted_modal_job(function.spawn(payload), 'evaluate_release', payload)


async def submit_evaluate_release_job_async(payload: dict[str, Any]) -> dict[str, Any]:
    modal_module = _require_modal()
    function = modal_module.Function.from_name(MODAL_APP_NAME, MODAL_REMOTE_EVALUATE_RELEASE_FUNCTION)
    return _accepted_modal_job(await function.spawn.aio(payload), 'evaluate_release', payload)


def poll_evaluate_release_job(call_id: str) -> tuple[int, dict[str, Any]]:
    modal_module = _require_modal()
    function_call = modal_module.FunctionCall.from_id(call_id)
    try:
        result = function_call.get(timeout=0)
    except Exception as exc:
        handled = _classify_modal_poll_exception(modal_module, exc, call_id=call_id, request_type='evaluate_release')
        if handled is not None:
            return handled
        raise
    return 200, _ok_modal_job(call_id, 'evaluate_release', result)


async def poll_evaluate_release_job_async(call_id: str) -> tuple[int, dict[str, Any]]:
    modal_module = _require_modal()
    function_call = modal_module.FunctionCall.from_id(call_id)
    try:
        result = await function_call.get.aio(timeout=0)
    except Exception as exc:
        handled = _classify_modal_poll_exception(modal_module, exc, call_id=call_id, request_type='evaluate_release')
        if handled is not None:
            return handled
        raise
    return 200, _ok_modal_job(call_id, 'evaluate_release', result)


def _route_handlers() -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    return {
        '/sar-segment': submit_sar_segment_job,
        '/train-sar-unet': submit_train_sar_unet_job,
        '/train-mtslstm': submit_train_mtslstm_job,
        '/infer-mtslstm': submit_infer_mtslstm_job,
        '/evaluate-release': submit_evaluate_release_job,
    }


def _expected_bearer_token() -> str:
    token = str(os.environ.get(WORKER_TOKEN_ENV) or '').strip()
    if not token:
        raise RuntimeError(f'{WORKER_TOKEN_ENV} must be configured for the Modal worker')
    return token


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    if not authorization_header:
        return None
    scheme, _, token = authorization_header.partition(' ')
    if scheme.lower() != 'bearer' or not token.strip():
        return None
    return token.strip()


def authorize_bearer_request(authorization_header: str | None) -> None:
    expected = _expected_bearer_token()
    supplied = _extract_bearer_token(authorization_header)
    if supplied != expected:
        raise PermissionError('missing or invalid worker bearer token')


def dispatch_modal_route(path: str, payload: dict[str, Any], *, authorization_header: str | None = None) -> tuple[int, dict[str, Any]]:
    try:
        authorize_bearer_request(authorization_header)
    except PermissionError as exc:
        return 401, {'status': 'unauthorized', 'reason': str(exc)}
    except RuntimeError as exc:
        return 503, {'status': 'misconfigured', 'reason': str(exc)}

    handler = _route_handlers().get(path)
    if handler is None:
        return 404, {'status': 'not_found', 'reason': f'unknown route "{path}"'}
    try:
        return 200, handler(payload)
    except Exception as exc:  # pragma: no cover - exercised via deployment, not unit tests
        return 500, {'status': 'error', 'reason': str(exc)}


def seed_dem_directory(source_root: Path, destination_root: Path) -> dict[str, Any]:
    destination_root.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0
    files_seeded: list[str] = []
    for path in sorted(source_root.glob('*.tif')):
        destination = destination_root / path.name
        if destination.exists() and destination.stat().st_size == path.stat().st_size:
            skipped += 1
            continue
        shutil.copy2(path, destination)
        copied += 1
        files_seeded.append(path.name)
    readme = source_root / 'README.md'
    if readme.exists():
        shutil.copy2(readme, destination_root / readme.name)
    return {
        'status': 'ok',
        'source_root': str(source_root),
        'destination_root': str(destination_root),
        'copied': copied,
        'skipped': skipped,
        'files_seeded': files_seeded,
    }


def normalize_model_volume_path(remote_model_path: str) -> str:
    candidate = PurePosixPath(str(remote_model_path or '').strip() or '/models/swin_transformer_v2_tiny.pt')
    if not candidate.is_absolute():
        candidate = PurePosixPath('/') / candidate
    if '..' in candidate.parts:
        raise ValueError(f'invalid remote model path "{remote_model_path}": parent traversal is not allowed')
    if len(candidate.parts) < 3 or candidate.parts[1] != 'models' or not candidate.name:
        raise ValueError(
            f'invalid remote model path "{remote_model_path}": expected an absolute path under /models/',
        )
    return candidate.as_posix()


def seed_model_volume_file(volume: Any, source_model_path: Path, *, remote_model_path: str) -> dict[str, Any]:
    source_model_path = source_model_path.expanduser().resolve()
    if not source_model_path.exists() or not source_model_path.is_file():
        raise FileNotFoundError(f'model checkpoint not found: {source_model_path}')
    remote_path = normalize_model_volume_path(remote_model_path)
    with volume.batch_upload(force=True) as batch:
        batch.put_file(source_model_path, remote_path)
    return {
        'status': 'ok',
        'source_model_path': str(source_model_path),
        'remote_model_path': remote_path,
        'runtime_model_path': str(PurePosixPath(MODEL_VOLUME_ROOT) / PurePosixPath(remote_path).relative_to('/models')),
        'bytes_uploaded': source_model_path.stat().st_size,
    }


def create_fastapi_app(volume_reload: Callable[[], None] | None = None, volume_commit: Callable[[], None] | None = None) -> Any:
    if FastAPI is None:
        raise RuntimeError('fastapi must be installed in the Modal image to serve the ASGI worker app')

    app = FastAPI(title='avalanche-modal-worker')

    @app.get('/health')
    async def health() -> dict[str, Any]:
        return {
            'status': 'ok',
            'app': MODAL_APP_NAME,
            'runtime_provider': 'modal',
            'worker_api': 'asgi',
            'python_version': MODAL_IMAGE_PYTHON_VERSION,
            'modal_sdk_pin': MODAL_PINNED_MODAL_SDK,
            'runtime_lock': MODAL_RUNTIME_LOCK,
            'torch_pin': MODAL_PINNED_TORCH,
            'actual_runtime_probe': 'execution_manifest',
            'gpu_functions': [
                MODAL_REMOTE_SEGMENT_FUNCTION,
                MODAL_REMOTE_TRAIN_SAR_FUNCTION,
                MODAL_REMOTE_EVALUATE_SAR_CHECKPOINT_FUNCTION,
                MODAL_REMOTE_TRAIN_FUNCTION,
            ],
            'cpu_dispatch_functions': [
                MODAL_REMOTE_EVALUATE_RELEASE_FUNCTION,
                MODAL_REMOTE_INFER_FUNCTION,
            ],
            'function_runtime_manifest': MODAL_FUNCTION_RUNTIME_MANIFEST,
            'routes': sorted(_route_handlers().keys()),
        }

    def _authorize_or_raise(authorization_header: str | None) -> None:
        try:
            authorize_bearer_request(authorization_header)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail={'status': 'unauthorized', 'reason': str(exc)}) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={'status': 'misconfigured', 'reason': str(exc)}) from exc

    async def _handle(request: Request, route: str, commit_after: bool) -> dict[str, Any]:
        _authorize_or_raise(request.headers.get('Authorization'))
        if volume_reload is not None:
            volume_reload()
        payload = await request.json()
        status_code, body = dispatch_modal_route(
            route,
            payload if isinstance(payload, dict) else {},
            authorization_header=request.headers.get('Authorization'),
        )
        if status_code == 200 and commit_after and volume_commit is not None:
            volume_commit()
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=body)
        return body

    @app.post('/sar-segment')
    async def sar_segment(request: Request) -> dict[str, Any]:
        _authorize_or_raise(request.headers.get('Authorization'))
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
        try:
            return await submit_sar_segment_job_async(payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={'status': 'misconfigured', 'reason': str(exc)}) from exc

    @app.get('/sar-segment/result/{call_id}')
    async def sar_segment_result(call_id: str, request: Request) -> Any:
        _authorize_or_raise(request.headers.get('Authorization'))
        try:
            status_code, body = await poll_sar_segment_job_async(call_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={'status': 'misconfigured', 'reason': str(exc)}) from exc
        if status_code == 202:
            return JSONResponse(status_code=202, content=body)
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=body)
        return body

    @app.post('/train-sar-unet')
    async def train_sar_unet_endpoint(request: Request) -> dict[str, Any]:
        _authorize_or_raise(request.headers.get('Authorization'))
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
        try:
            return await submit_train_sar_unet_job_async(payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={'status': 'misconfigured', 'reason': str(exc)}) from exc

    @app.get('/train-sar-unet/result/{call_id}')
    async def train_sar_unet_result(call_id: str, request: Request) -> Any:
        _authorize_or_raise(request.headers.get('Authorization'))
        try:
            status_code, body = await poll_train_sar_unet_job_async(call_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={'status': 'misconfigured', 'reason': str(exc)}) from exc
        if status_code == 202:
            return JSONResponse(status_code=202, content=body)
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=body)
        return body

    @app.post('/train-mtslstm')
    async def train_mtslstm(request: Request) -> dict[str, Any]:
        _authorize_or_raise(request.headers.get('Authorization'))
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
        try:
            return await submit_train_mtslstm_job_async(payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={'status': 'misconfigured', 'reason': str(exc)}) from exc

    @app.get('/train-mtslstm/result/{call_id}')
    async def train_mtslstm_result(call_id: str, request: Request) -> Any:
        _authorize_or_raise(request.headers.get('Authorization'))
        try:
            status_code, body = await poll_train_mtslstm_job_async(call_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={'status': 'misconfigured', 'reason': str(exc)}) from exc
        if status_code == 202:
            return JSONResponse(status_code=202, content=body)
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=body)
        return body

    @app.post('/infer-mtslstm')
    async def infer_mtslstm(request: Request) -> dict[str, Any]:
        _authorize_or_raise(request.headers.get('Authorization'))
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
        try:
            return await submit_infer_mtslstm_job_async(payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={'status': 'misconfigured', 'reason': str(exc)}) from exc

    @app.get('/infer-mtslstm/result/{call_id}')
    async def infer_mtslstm_result(call_id: str, request: Request) -> Any:
        _authorize_or_raise(request.headers.get('Authorization'))
        try:
            status_code, body = await poll_infer_mtslstm_job_async(call_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={'status': 'misconfigured', 'reason': str(exc)}) from exc
        if status_code == 202:
            return JSONResponse(status_code=202, content=body)
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=body)
        return body

    @app.post('/evaluate-release')
    async def evaluate_release(request: Request) -> dict[str, Any]:
        _authorize_or_raise(request.headers.get('Authorization'))
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
        try:
            return await submit_evaluate_release_job_async(payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={'status': 'misconfigured', 'reason': str(exc)}) from exc

    @app.get('/evaluate-release/result/{call_id}')
    async def evaluate_release_result(call_id: str, request: Request) -> Any:
        _authorize_or_raise(request.headers.get('Authorization'))
        try:
            status_code, body = await poll_evaluate_release_job_async(call_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={'status': 'misconfigured', 'reason': str(exc)}) from exc
        if status_code == 202:
            return JSONResponse(status_code=202, content=body)
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=body)
        return body

    return app


if modal is not None:  # pragma: no cover - exercised in deployment, not local tests
    app = modal.App(MODAL_APP_NAME)
    _artifact_volume = modal.Volume.from_name('avalanche-artifacts', create_if_missing=True)
    _secrets = [modal.Secret.from_name('avalanche-supabase-secrets')]

    image = (
        modal.Image.debian_slim(python_version=MODAL_IMAGE_PYTHON_VERSION)
        .apt_install('gdal-bin', 'libgdal-dev')
        .env({
            'ARTIFACT_ROOT': VOLUME_MOUNT,
            'DEM_ROOT': DEM_VOLUME_ROOT,
            'MODAL_APP_NAME': MODAL_APP_NAME,
            'MODAL_VOLUME_NAME': 'avalanche-artifacts',
            'MODAL_IMAGE_PYTHON_VERSION': MODAL_IMAGE_PYTHON_VERSION,
        })
        .pip_install_from_requirements(MODAL_RUNTIME_LOCK)
        .add_local_python_source('backend')
        .add_local_file('config/regions.json', remote_path='/root/config/regions.json')
        .add_local_file('config/risk_weights.json', remote_path='/root/config/risk_weights.json')
    )

    @app.function(
        image=image,
        secrets=_secrets,
        volumes={VOLUME_MOUNT: _artifact_volume},
        cpu=1.0,
        memory=1024,
        min_containers=MODAL_MIN_CONTAINERS,
        buffer_containers=MODAL_BUFFER_CONTAINERS,
        scaledown_window=MODAL_SCALEDOWN_WINDOW_SECONDS,
        timeout=1800,
    )
    @modal.asgi_app()
    def worker_api() -> Any:
        return create_fastapi_app(
            volume_reload=_artifact_volume.reload,
            volume_commit=_artifact_volume.commit,
        )

    @app.function(
        image=image,
        secrets=_secrets,
        volumes={VOLUME_MOUNT: _artifact_volume},
        gpu='T4',
        max_containers=1,
        min_containers=MODAL_MIN_CONTAINERS,
        buffer_containers=MODAL_BUFFER_CONTAINERS,
        scaledown_window=MODAL_SCALEDOWN_WINDOW_SECONDS,
        timeout=1800,
        retries=0,
    )
    def sar_segment_remote(request: dict[str, Any]) -> dict[str, Any]:
        return run_remote_sar_segment(
            request,
            artifact_root=Path(VOLUME_MOUNT),
            device='cuda',
            volume_reload=_artifact_volume.reload,
            volume_commit=_artifact_volume.commit,
        )

    @app.function(
        image=image,
        secrets=_secrets,
        volumes={VOLUME_MOUNT: _artifact_volume},
        gpu='T4',
        max_containers=1,
        min_containers=MODAL_MIN_CONTAINERS,
        buffer_containers=MODAL_BUFFER_CONTAINERS,
        scaledown_window=MODAL_SCALEDOWN_WINDOW_SECONDS,
        timeout=14400,
        retries=0,
    )
    def train_sar_unet_remote(request: dict[str, Any]) -> dict[str, Any]:
        return run_remote_train_sar_unet(
            request,
            artifact_root=Path(VOLUME_MOUNT),
            device='cuda',
            volume_reload=_artifact_volume.reload,
            volume_commit=_artifact_volume.commit,
        )

    @app.function(
        image=image,
        secrets=_secrets,
        volumes={VOLUME_MOUNT: _artifact_volume},
        gpu='T4',
        max_containers=1,
        min_containers=MODAL_MIN_CONTAINERS,
        buffer_containers=MODAL_BUFFER_CONTAINERS,
        scaledown_window=MODAL_SCALEDOWN_WINDOW_SECONDS,
        timeout=3600,
        retries=0,
    )
    def evaluate_sar_checkpoint_remote(request: dict[str, Any]) -> dict[str, Any]:
        return run_remote_evaluate_sar_checkpoint(
            request,
            artifact_root=Path(VOLUME_MOUNT),
            device='cuda',
            volume_reload=_artifact_volume.reload,
            volume_commit=_artifact_volume.commit,
        )

    @app.function(
        image=image,
        secrets=_secrets,
        volumes={VOLUME_MOUNT: _artifact_volume},
        cpu=MODAL_INFER_CPU,
        memory=MODAL_INFER_MEMORY_MB,
        max_containers=1,
        min_containers=MODAL_MIN_CONTAINERS,
        buffer_containers=MODAL_BUFFER_CONTAINERS,
        scaledown_window=MODAL_SCALEDOWN_WINDOW_SECONDS,
        timeout=3600,
        retries=0,
    )
    def evaluate_release_remote(request: dict[str, Any]) -> dict[str, Any]:
        return run_remote_evaluate_release(
            request,
            artifact_root=Path(VOLUME_MOUNT),
            volume_reload=_artifact_volume.reload,
            volume_commit=_artifact_volume.commit,
        )

    @app.function(
        image=image,
        secrets=_secrets,
        volumes={VOLUME_MOUNT: _artifact_volume},
        gpu='T4',
        max_containers=1,
        min_containers=MODAL_MIN_CONTAINERS,
        buffer_containers=MODAL_BUFFER_CONTAINERS,
        scaledown_window=MODAL_SCALEDOWN_WINDOW_SECONDS,
        timeout=14400,
        retries=0,
    )
    def train_mts_lstm_remote(request: dict[str, Any]) -> dict[str, Any]:
        return run_remote_train_mtslstm(
            request,
            artifact_root=Path(VOLUME_MOUNT),
            volume_reload=_artifact_volume.reload,
            volume_commit=_artifact_volume.commit,
        )

    @app.function(
        image=image,
        secrets=_secrets,
        volumes={VOLUME_MOUNT: _artifact_volume},
        cpu=MODAL_INFER_CPU,
        memory=MODAL_INFER_MEMORY_MB,
        max_containers=1,
        min_containers=MODAL_MIN_CONTAINERS,
        buffer_containers=MODAL_BUFFER_CONTAINERS,
        scaledown_window=MODAL_SCALEDOWN_WINDOW_SECONDS,
        timeout=3600,
        retries=0,
    )
    def infer_mts_lstm_remote(request: dict[str, Any]) -> dict[str, Any]:
        return run_remote_infer_mtslstm(
            request,
            artifact_root=Path(VOLUME_MOUNT),
            volume_reload=_artifact_volume.reload,
            volume_commit=_artifact_volume.commit,
        )

    @app.function(
        image=image,
        secrets=_secrets,
        volumes={VOLUME_MOUNT: _artifact_volume},
        min_containers=MODAL_MIN_CONTAINERS,
        buffer_containers=MODAL_BUFFER_CONTAINERS,
        scaledown_window=MODAL_SCALEDOWN_WINDOW_SECONDS,
        timeout=1800,
        retries=0,
    )
    def seed_dem_volume_files(files: list[tuple[str, bytes]]) -> dict[str, Any]:
        destination_root = Path(DEM_VOLUME_ROOT)
        destination_root.mkdir(parents=True, exist_ok=True)
        copied = 0
        skipped = 0
        files_seeded: list[str] = []
        for filename, payload in files:
            destination = destination_root / filename
            if destination.exists() and destination.stat().st_size == len(payload):
                skipped += 1
                continue
            destination.write_bytes(payload)
            copied += 1
            files_seeded.append(filename)
        _artifact_volume.commit()
        return {
            'status': 'ok',
            'destination_root': str(destination_root),
            'copied': copied,
            'skipped': skipped,
            'files_seeded': files_seeded,
        }

    @app.local_entrypoint()
    def seed_artifact_volume(
        source_root: str = 'backend/data/dem',
        source_model_path: str = '',
        remote_model_path: str = '/models/swin_transformer_v2_tiny.pt',
    ) -> None:
        if str(source_model_path).strip():
            result = seed_model_volume_file(
                _artifact_volume,
                Path(source_model_path),
                remote_model_path=remote_model_path,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return

        root = Path(source_root)
        files = [(path.name, path.read_bytes()) for path in sorted(root.glob('*.tif'))]
        readme = root / 'README.md'
        if readme.exists():
            files.append((readme.name, readme.read_bytes()))
        result = seed_dem_volume_files.remote(files)
        print(json.dumps(result, indent=2, sort_keys=True))

else:  # pragma: no cover - keeps imports safe when modal is unavailable locally
    app = None
