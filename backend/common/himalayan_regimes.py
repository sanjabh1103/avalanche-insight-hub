"""Himalayan regime configuration loader (Phase 1b).

Loads and validates the Himalayan regime configuration from
config/himalayan_regimes.json. Each Himalayan zone has internal
elevation/process bands, climate class, seasonal phases, aspect classes,
expected problem types, calibration version, and observation coverage.

Per Imp_plan.md Phase 1b:
  - Add a Himalayan regime configuration containing: region, elevation band,
    climate class, season, aspect class, expected problem types, calibration
    version, observation coverage.
  - Western-Himalaya lower/middle/upper classifications must not be copied
    mechanically into Nepal.

This module is additive and does not modify any denylisted file.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.common.regions import repo_root


VALID_SEASONAL_PHASES = frozenset({
    'storm_new_snow',
    'wind_slab',
    'persistent_weak_layer',
    'wet_snow_rain_on_snow',
})

VALID_ASPECT_CLASSES = frozenset({'N', 'E', 'S', 'W'})

VALID_OBSERVATION_COVERAGE = frozenset({
    'dense',
    'moderate',
    'sparse',
    'very_sparse',
    'no_direct_observations',
})

VALID_PROBLEM_TYPES = frozenset({
    'storm_slab',
    'wind_slab',
    'persistent_weak_layer',
    'wet_snow',
})


@dataclass(frozen=True)
class ElevationBand:
    """Internal elevation band within a Himalayan regime."""
    name: str
    elevation_min_m: int
    elevation_max_m: int
    dominant_processes: tuple[str, ...]
    aspect_classes: tuple[str, ...]
    observation_coverage: str


@dataclass(frozen=True)
class HimalayanRegime:
    """Complete regime configuration for a Himalayan zone."""
    region_key: str
    tier: str
    climate_class: str
    seasonal_phases: tuple[str, ...]
    elevation_bands: tuple[ElevationBand, ...]
    expected_problem_types: tuple[str, ...]
    calibration_version: str
    notes: str = ''

    @property
    def band_names(self) -> tuple[str, ...]:
        return tuple(b.name for b in self.elevation_bands)

    def get_band(self, name: str) -> ElevationBand | None:
        for b in self.elevation_bands:
            if b.name == name:
                return b
        return None


class RegimeValidationError(Exception):
    """Raised when Himalayan regime configuration is invalid."""


def _parse_elevation_band(data: dict[str, Any]) -> ElevationBand:
    return ElevationBand(
        name=str(data['name']),
        elevation_min_m=int(data['elevation_min_m']),
        elevation_max_m=int(data['elevation_max_m']),
        dominant_processes=tuple(data.get('dominant_processes', [])),
        aspect_classes=tuple(data.get('aspect_classes', [])),
        observation_coverage=str(data.get('observation_coverage', 'no_direct_observations')),
    )


def _parse_regime(region_key: str, data: dict[str, Any]) -> HimalayanRegime:
    bands = tuple(_parse_elevation_band(b) for b in data.get('elevation_bands', []))
    return HimalayanRegime(
        region_key=region_key,
        tier=str(data.get('tier', 'B')),
        climate_class=str(data.get('climate_class', 'unknown')),
        seasonal_phases=tuple(data.get('seasonal_phases', [])),
        elevation_bands=bands,
        expected_problem_types=tuple(data.get('expected_problem_types', [])),
        calibration_version=str(data.get('calibration_version', 'candidate_v0')),
        notes=str(data.get('notes', '')),
    )


@lru_cache(maxsize=1)
def load_himalayan_regimes(path: Path | None = None) -> dict[str, HimalayanRegime]:
    """Load all Himalayan regime configurations.

    Returns a dict mapping region_key -> HimalayanRegime.
    """
    regimes_path = path or (repo_root() / 'config' / 'himalayan_regimes.json')
    if not regimes_path.exists():
        return {}
    data = json.loads(regimes_path.read_text(encoding='utf-8'))
    regimes: dict[str, HimalayanRegime] = {}
    for region_key, regime_data in data.get('regimes', {}).items():
        regimes[region_key] = _parse_regime(region_key, regime_data)
    return regimes


def get_regime(region_key: str, path: Path | None = None) -> HimalayanRegime | None:
    """Get the Himalayan regime for a specific region key."""
    regimes = load_himalayan_regimes(path)
    return regimes.get(region_key)


def validate_regime(regime: HimalayanRegime) -> list[str]:
    """Validate a single Himalayan regime. Returns list of error messages (empty = valid)."""
    errors: list[str] = []

    if regime.tier not in ('A', 'B'):
        errors.append(f'{regime.region_key}: tier must be A or B, got {regime.tier}')

    if not regime.elevation_bands:
        errors.append(f'{regime.region_key}: must have at least one elevation band')
    else:
        for band in regime.elevation_bands:
            if band.elevation_min_m >= band.elevation_max_m:
                errors.append(
                    f'{regime.region_key}/{band.name}: elevation_min ({band.elevation_min_m}) '
                    f'must be < elevation_max ({band.elevation_max_m})'
                )
            for proc in band.dominant_processes:
                if proc not in VALID_SEASONAL_PHASES:
                    errors.append(
                        f'{regime.region_key}/{band.name}: invalid dominant_process "{proc}"'
                    )
            for aspect in band.aspect_classes:
                if aspect not in VALID_ASPECT_CLASSES:
                    errors.append(
                        f'{regime.region_key}/{band.name}: invalid aspect_class "{aspect}"'
                    )
            if band.observation_coverage not in VALID_OBSERVATION_COVERAGE:
                errors.append(
                    f'{regime.region_key}/{band.name}: invalid observation_coverage '
                    f'"{band.observation_coverage}"'
                )

    for phase in regime.seasonal_phases:
        if phase not in VALID_SEASONAL_PHASES:
            errors.append(f'{regime.region_key}: invalid seasonal_phase "{phase}"')

    for pt in regime.expected_problem_types:
        if pt not in VALID_PROBLEM_TYPES:
            errors.append(f'{regime.region_key}: invalid expected_problem_type "{pt}"')

    # Check elevation bands are contiguous and non-overlapping
    if len(regime.elevation_bands) > 1:
        sorted_bands = sorted(regime.elevation_bands, key=lambda b: b.elevation_min_m)
        for i in range(len(sorted_bands) - 1):
            if sorted_bands[i].elevation_max_m != sorted_bands[i + 1].elevation_min_m:
                errors.append(
                    f'{regime.region_key}: elevation bands not contiguous between '
                    f'{sorted_bands[i].name} (max {sorted_bands[i].elevation_max_m}) and '
                    f'{sorted_bands[i + 1].name} (min {sorted_bands[i + 1].elevation_min_m})'
                )

    return errors


def validate_all_regimes(path: Path | None = None) -> list[str]:
    """Validate all Himalayan regimes. Returns list of error messages (empty = all valid)."""
    regimes = load_himalayan_regimes(path)
    all_errors: list[str] = []
    for region_key, regime in regimes.items():
        all_errors.extend(validate_regime(regime))
    return all_errors
