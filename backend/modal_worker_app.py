from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable

from backend.common.config import load_settings
from backend.sar_unet_worker import SAR_UNET_SEGMENTATION_THRESHOLD, run_worker_request

try:  # pragma: no cover - optional dependency for deployment only
    import modal
except Exception:  # pragma: no cover - optional dependency
    modal = None

try:  # pragma: no cover - optional dependency for deployment only
    from fastapi import FastAPI, HTTPException, Request
except Exception:  # pragma: no cover - optional dependency
    FastAPI = None
    HTTPException = RuntimeError  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]

# Volume mount path — artifact root inside the Modal container.
# Matches ARTIFACT_ROOT env var so sar_unet_worker.py writes here automatically.
VOLUME_MOUNT = '/artifacts'
DEM_VOLUME_ROOT = f'{VOLUME_MOUNT}/dem'
WORKER_TOKEN_ENV = 'MODAL_WORKER_TOKEN'


def _artifact_root() -> Path:
    env_root = os.environ.get('ARTIFACT_ROOT')
    if env_root:
        return Path(env_root)
    return load_settings().artifact_root


def _model_path() -> Path | None:
    raw = os.environ.get('SAR_UNET_MODEL_PATH')
    return Path(raw) if raw else None


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


def handle_train_mtslstm(payload: dict[str, Any]) -> dict[str, Any]:
    return _dispatch_worker_request('train-mtslstm', payload)


def handle_infer_mtslstm(payload: dict[str, Any]) -> dict[str, Any]:
    return _dispatch_worker_request('infer-mtslstm', payload)


def handle_evaluate_release(payload: dict[str, Any]) -> dict[str, Any]:
    return _dispatch_worker_request('evaluate-release', payload)


def _route_handlers() -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    return {
        '/sar-segment': handle_sar_segment,
        '/train-mtslstm': handle_train_mtslstm,
        '/infer-mtslstm': handle_infer_mtslstm,
        '/evaluate-release': handle_evaluate_release,
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


def create_fastapi_app(volume_reload: Callable[[], None] | None = None, volume_commit: Callable[[], None] | None = None) -> Any:
    if FastAPI is None:
        raise RuntimeError('fastapi must be installed in the Modal image to serve the ASGI worker app')

    app = FastAPI(title='avalanche-modal-worker')

    async def _handle(request: Request, route: str, commit_after: bool) -> dict[str, Any]:
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
        return await _handle(request, '/sar-segment', True)

    @app.post('/train-mtslstm')
    async def train_mtslstm(request: Request) -> dict[str, Any]:
        return await _handle(request, '/train-mtslstm', True)

    @app.post('/infer-mtslstm')
    async def infer_mtslstm(request: Request) -> dict[str, Any]:
        return await _handle(request, '/infer-mtslstm', True)

    @app.post('/evaluate-release')
    async def evaluate_release(request: Request) -> dict[str, Any]:
        return await _handle(request, '/evaluate-release', False)

    return app


if modal is not None:  # pragma: no cover - exercised in deployment, not local tests
    app = modal.App('avalanche-modal-worker')
    _artifact_volume = modal.Volume.from_name('avalanche-artifacts', create_if_missing=True)
    _secrets = [modal.Secret.from_name('avalanche-supabase-secrets')]

    image = (
        modal.Image.debian_slim(python_version='3.11')
        .apt_install('gdal-bin', 'libgdal-dev')
        .env({
            'ARTIFACT_ROOT': VOLUME_MOUNT,
            'DEM_ROOT': DEM_VOLUME_ROOT,
        })
        .pip_install_from_requirements('backend/requirements.txt')
        .pip_install('modal>=0.73.82', 'fastapi[standard]>=0.115.0')
        .run_commands('pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121')
        .add_local_python_source('backend')
        .add_local_file('config/regions.json', remote_path='/root/config/regions.json')
        .add_local_file('config/risk_weights.json', remote_path='/root/config/risk_weights.json')
    )

    @app.function(
        image=image,
        secrets=_secrets,
        volumes={VOLUME_MOUNT: _artifact_volume},
        gpu='T4',
        timeout=7200,
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
    def seed_dem_volume(source_root: str = 'backend/data/dem') -> None:
        root = Path(source_root)
        files = [(path.name, path.read_bytes()) for path in sorted(root.glob('*.tif'))]
        readme = root / 'README.md'
        if readme.exists():
            files.append((readme.name, readme.read_bytes()))
        result = seed_dem_volume_files.remote(files)
        print(json.dumps(result, indent=2, sort_keys=True))

else:  # pragma: no cover - keeps imports safe when modal is unavailable locally
    app = None
