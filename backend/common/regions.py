from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List


@dataclass(frozen=True)
class Region:
    name: str
    bbox: tuple[float, float, float, float]
    center: tuple[float, float]
    zoom: int
    timezone_name: str = 'UTC'
    zone_type: str | None = None
    climate_class: str | None = None
    elevation_min: int | None = None
    elevation_max: int | None = None
    season_start: str | None = None
    lapse_rate_c_per_m: float | None = None

    @property
    def key(self) -> str:
        return self.name.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_')


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_regions(path: Path | None = None) -> List[Region]:
    regions_path = path or repo_root() / 'config' / 'regions.json'
    data = json.loads(regions_path.read_text(encoding='utf-8'))
    regions: list[Region] = []
    for entry in data:
        regions.append(
            Region(
                name=entry['name'],
                bbox=tuple(entry['bbox']),
                center=tuple(entry['center']),
                zoom=int(entry['zoom']),
                timezone_name=str(entry.get('timezone_name') or 'UTC'),
                zone_type=entry.get('zone_type'),
                climate_class=entry.get('climate_class'),
                elevation_min=int(entry['elevation_min']) if entry.get('elevation_min') is not None else None,
                elevation_max=int(entry['elevation_max']) if entry.get('elevation_max') is not None else None,
                season_start=entry.get('season_start'),
                lapse_rate_c_per_m=float(entry['lapse_rate_c_per_m']) if entry.get('lapse_rate_c_per_m') is not None else None,
            )
        )
    return regions


@lru_cache(maxsize=1)
def _load_zone_overrides(path: Path | None = None) -> Dict[str, Dict[str, Any]]:
    overrides_path = path or (repo_root() / 'config' / 'himalayan_zone_overrides.toml')
    if not overrides_path.exists():
        return {}
    with overrides_path.open('rb') as f:
        data = tomllib.load(f)
    return {key: dict(val) for key, val in data.items()}


def get_zone_override(region: Region, overrides_path: Path | None = None) -> Dict[str, Any]:
    """Return COSIPY/SNOWPACK parameter overrides for a region's zone_type.

    Returns an empty dict if the region has no zone_type or no overrides
    are found, ensuring backward compatibility for existing regions.
    """
    if not region.zone_type:
        return {}
    overrides = _load_zone_overrides(overrides_path)
    return dict(overrides.get(region.zone_type, {}))
