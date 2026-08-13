from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from backend.common.artifacts import DEFAULT_ARTIFACT_ROOT


@dataclass(frozen=True)
class Settings:
    supabase_url: str | None
    supabase_service_role_key: str | None
    artifact_root: Path
    samples_per_region: int
    seed: int
    forecast_horizon_hours: int
    grid_size: int
    hazard_type: str
    dry_run: bool
    edge_mode: bool
    local_db_url: str | None
    local_model_weights_path: str | None
    edge_sar_cache_dir: str | None
    pilot_grid_resolution_m: int | None
    research_model_gate_enabled: bool


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {'0', 'false', 'off', 'no'}


def load_settings() -> Settings:
    return Settings(
        supabase_url=os.environ.get('SUPABASE_URL'),
        supabase_service_role_key=os.environ.get('SUPABASE_SERVICE_ROLE_KEY'),
        artifact_root=Path(os.environ.get('ARTIFACT_ROOT', str(DEFAULT_ARTIFACT_ROOT))),
        samples_per_region=int(os.environ.get('SAMPLES_PER_REGION', '500')),
        seed=int(os.environ.get('ML_SEED', '42')),
        forecast_horizon_hours=int(os.environ.get('FORECAST_HORIZON_HOURS', '72')),
        grid_size=int(os.environ.get('GRID_SIZE', '20')),
        hazard_type=os.environ.get('HAZARD_TYPE', 'avalanche'),
        dry_run=_bool_env('DRY_RUN', False),
        edge_mode=_bool_env('EDGE_MODE', False),
        local_db_url=os.environ.get('LOCAL_DB_URL'),
        local_model_weights_path=os.environ.get('LOCAL_MODEL_WEIGHTS_PATH'),
        edge_sar_cache_dir=os.environ.get('EDGE_SAR_CACHE_DIR'),
        pilot_grid_resolution_m=int(os.environ['PILOT_GRID_RESOLUTION_M']) if os.environ.get('PILOT_GRID_RESOLUTION_M') else None,
        research_model_gate_enabled=_bool_env('RESEARCH_MODEL_GATE_ENABLED', True),
    )
