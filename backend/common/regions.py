from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class Region:
    name: str
    bbox: tuple[float, float, float, float]
    center: tuple[float, float]
    zoom: int
    timezone_name: str = 'UTC'

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
            )
        )
    return regions
