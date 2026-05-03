from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import requests
from rasterio.io import MemoryFile

from backend.common.sar_release_refs import load_reference_bundle
from backend.common.storage_io import storage_download_bytes, storage_upload_bytes
from backend.sar_release_manifest import ReleaseManifestOptions, build_release_manifest_from_reference_set
from backend.scripts.bootstrap_release_gate import load_rollout_env


DEFAULT_PREDICTION_MODEL_VERSION = 'sar_unet_resnet34_shadow_v1'


def apply_rollout_env(env_file: Path) -> dict[str, str]:
    env = load_rollout_env(env_file)
    missing: list[str] = []
    if not env.supabase_url:
        missing.append('SUPABASE_URL or VITE_SUPABASE_URL')
    if not env.supabase_service_role_key:
        missing.append('SUPABASE_SERVICE_ROLE_KEY')
    if not env.modal_worker_url:
        missing.append('MODAL_WORKER_URL')
    if not env.modal_worker_token:
        missing.append('MODAL_WORKER_TOKEN')
    if missing:
        raise ValueError(f'canary evaluate-release is blocked until required settings are present: {", ".join(missing)}')
    os.environ['SUPABASE_URL'] = env.supabase_url
    os.environ['SUPABASE_SERVICE_ROLE_KEY'] = env.supabase_service_role_key
    os.environ['MODAL_WORKER_URL'] = env.modal_worker_url
    os.environ['MODAL_WORKER_TOKEN'] = env.modal_worker_token
    return {
        'supabase_url': env.supabase_url,
        'modal_worker_url': env.modal_worker_url,
        'modal_worker_token': env.modal_worker_token,
    }


def build_zero_prediction_geotiff(truth_mask_bytes: bytes) -> bytes:
    with MemoryFile(truth_mask_bytes) as memory_file:
        with memory_file.open() as dataset:
            if int(dataset.count) != 1:
                raise ValueError(f'truth_mask GeoTIFF must contain exactly 1 band; found {dataset.count}')
            profile = dataset.profile.copy()
            zeros = np.zeros((dataset.height, dataset.width), dtype=np.dtype(dataset.dtypes[0]))
    profile.update(count=1)
    with MemoryFile() as output:
        with output.open(**profile) as dataset:
            dataset.write(zeros, 1)
        return output.read()


def _require_draft_reference_set(reference_set_key: str) -> dict[str, Any]:
    set_row, _items = load_reference_bundle(reference_set_key, authoritative_only=False, status=None)
    if bool(set_row.get('authoritative')):
        raise ValueError(f'reference set "{reference_set_key}" is authoritative; canary evaluation requires a draft set')
    if str(set_row.get('status') or '').strip().lower() == 'active':
        raise ValueError(f'reference set "{reference_set_key}" is active; canary evaluation requires a non-active set')
    return set_row


def build_canary_manifest(
    *,
    reference_set_key: str,
    prediction_model_version: str,
) -> dict[str, Any]:
    _require_draft_reference_set(reference_set_key)
    return build_release_manifest_from_reference_set(
        reference_set_key=reference_set_key,
        options=ReleaseManifestOptions(
            validate_refs=False,
            authoritative_only=False,
            prediction_model_version=prediction_model_version,
        ),
    )


def seed_zero_prediction_masks(manifest: dict[str, Any]) -> list[str]:
    uploaded_refs: list[str] = []
    scenes = manifest.get('scenes')
    if not isinstance(scenes, list) or not scenes:
        raise ValueError('canary manifest must include a non-empty scenes[] list')
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        truth_mask_ref = str(scene.get('truth_mask') or '').strip()
        prediction_mask_ref = str(scene.get('prediction_mask') or '').strip()
        if not truth_mask_ref or not truth_mask_ref.lower().endswith(('.tif', '.tiff')):
            raise ValueError(f'scene "{scene.get("scene_id")}" requires a GeoTIFF truth_mask for canary evaluation')
        if not prediction_mask_ref:
            raise ValueError(f'scene "{scene.get("scene_id")}" is missing prediction_mask')
        truth_bucket, truth_object_path = truth_mask_ref.split('/', 1)
        prediction_bucket, prediction_object_path = prediction_mask_ref.split('/', 1)
        truth_mask_bytes = storage_download_bytes(bucket=truth_bucket, object_path=truth_object_path)
        zero_geotiff = build_zero_prediction_geotiff(truth_mask_bytes)
        uploaded_refs.append(
            storage_upload_bytes(
                bucket=prediction_bucket,
                object_path=prediction_object_path,
                payload=zero_geotiff,
                content_type='image/tiff',
                upsert=True,
            )
        )
    return uploaded_refs


def post_evaluate_release(
    *,
    worker_url: str,
    worker_token: str,
    manifest: dict[str, Any],
    request_type: str = 'canary_evaluate_release',
) -> dict[str, Any]:
    payload = {
        **manifest,
        'request_type': request_type,
    }
    response = requests.post(
        worker_url.rstrip('/') + '/evaluate-release',
        headers={'Authorization': f'Bearer {worker_token}'},
        json=payload,
        timeout=180,
    )
    if not response.ok:
        raise RuntimeError(
            f'worker evaluate-release failed ({response.status_code}): {response.text}'
        )
    result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError('worker evaluate-release returned a non-object JSON payload')
    return result


def run_canary_evaluate_release(
    *,
    env_file: Path,
    reference_set_key: str,
    prediction_model_version: str = DEFAULT_PREDICTION_MODEL_VERSION,
) -> dict[str, Any]:
    env_values = apply_rollout_env(env_file)
    manifest = build_canary_manifest(
        reference_set_key=reference_set_key,
        prediction_model_version=prediction_model_version,
    )
    seed_zero_prediction_masks(manifest)
    return post_evaluate_release(
        worker_url=env_values['modal_worker_url'],
        worker_token=env_values['modal_worker_token'],
        manifest=manifest,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Seed zero-valued prediction masks and run draft canary evaluate-release')
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--reference-set-key', required=True)
    parser.add_argument('--prediction-model-version', default=DEFAULT_PREDICTION_MODEL_VERSION)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_canary_evaluate_release(
        env_file=args.env_file,
        reference_set_key=args.reference_set_key,
        prediction_model_version=args.prediction_model_version,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
