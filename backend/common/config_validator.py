"""Canonical region registry validation.

Ensures config/regions.json remains the single source of truth for region
definitions and that config/awsome_regions.yaml stays in sync with it.

Per Imp_plan.md Phase 1:
  - Make config/regions.json the canonical region registry.
  - Derive or validate config/awsome_regions.yaml from the canonical registry.

This module is additive — it does not modify any existing config file or
denylisted zone. It only validates and reports drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend.common.regions import load_regions, repo_root


@dataclass(frozen=True)
class ConfigValidationResult:
    """Result of canonical config validation."""
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    region_keys: tuple[str, ...] = ()
    awsome_keys: tuple[str, ...] = ()


def _region_key(name: str) -> str:
    """Convert a region name to its canonical key (matches Region.key property)."""
    return name.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_')


def validate_awsome_regions_sync(
    *,
    regions_path: Path | None = None,
    awsome_path: Path | None = None,
) -> ConfigValidationResult:
    """Validate that awsome_regions.yaml is in sync with regions.json.

    Checks:
      1. Every region in regions.json has a corresponding key in awsome_regions.yaml.
      2. Every key in awsome_regions.yaml corresponds to a region in regions.json.
      3. Center coordinates in awsome_regions.yaml match regions.json (warning only).

    Returns:
        ConfigValidationResult with errors (must fix) and warnings (should check).
    """
    regions_path = regions_path or (repo_root() / 'config' / 'regions.json')
    awsome_path = awsome_path or (repo_root() / 'config' / 'awsome_regions.yaml')

    errors: list[str] = []
    warnings: list[str] = []

    regions = load_regions(regions_path)
    region_keys = {_region_key(r.name) for r in regions}
    region_by_key = {_region_key(r.name): r for r in regions}

    if not awsome_path.exists():
        errors.append(f'awsome_regions.yaml not found at {awsome_path}')
        return ConfigValidationResult(
            valid=False,
            errors=tuple(errors),
            region_keys=tuple(sorted(region_keys)),
        )

    with open(awsome_path, encoding='utf-8') as f:
        awsome_config = yaml.safe_load(f) or {}

    awsome_keys = set(awsome_config.keys())

    # Check 1: every region has an AWSOME entry
    missing_in_awsome = region_keys - awsome_keys
    for key in sorted(missing_in_awsome):
        errors.append(f'Region "{key}" in regions.json has no entry in awsome_regions.yaml')

    # Check 2: every AWSOME entry corresponds to a region
    orphaned_in_awsome = awsome_keys - region_keys
    for key in sorted(orphaned_in_awsome):
        errors.append(f'awsome_regions.yaml key "{key}" has no matching region in regions.json')

    # Check 3: center coordinates match (warning only)
    for key in sorted(region_keys & awsome_keys):
        region = region_by_key[key]
        awsome_entry = awsome_config[key]
        awsome_center = awsome_entry.get('center')
        if awsome_center is not None:
            if len(awsome_center) != 2:
                warnings.append(f'"{key}" center has {len(awsome_center)} elements, expected 2')
            else:
                if abs(awsome_center[0] - region.center[0]) > 0.01 or abs(awsome_center[1] - region.center[1]) > 0.01:
                    warnings.append(
                        f'"{key}" center drift: regions.json={region.center}, '
                        f'awsome_regions.yaml={tuple(awsome_center)}'
                    )

    return ConfigValidationResult(
        valid=len(errors) == 0,
        errors=tuple(errors),
        warnings=tuple(warnings),
        region_keys=tuple(sorted(region_keys)),
        awsome_keys=tuple(sorted(awsome_keys)),
    )


# ---------------------------------------------------------------------------
# Himalayan scope classification
# ---------------------------------------------------------------------------

HIMALAYAN_REGION_KEYS: frozenset[str] = frozenset({
    'himalayas_nepal',
    'pir_panjal_nw_himalaya',
    'shamshabari_nw_himalaya',
    'great_himalaya_nw_himalaya',
    'karakoram_&_ladakh',
})

PORTABILITY_ONLY_REGION_KEYS: frozenset[str] = frozenset({
    'colorado_rockies',
    'swiss_alps',
    'french_alps',
    'andes_patagonia',
    'cascades_wa',
    'scandinavia_norway',
    'japanese_alps',
})


def classify_region_scope(region_key: str) -> str:
    """Classify a region as 'himalayan', 'portability_only', or 'unknown'."""
    if region_key in HIMALAYAN_REGION_KEYS:
        return 'himalayan'
    if region_key in PORTABILITY_ONLY_REGION_KEYS:
        return 'portability_only'
    return 'unknown'


def get_himalayan_regions() -> list[str]:
    """Return the list of Himalayan region keys (Tier A + Tier B)."""
    return sorted(HIMALAYAN_REGION_KEYS)


def get_portability_regions() -> list[str]:
    """Return the list of portability-only region keys (Tier C)."""
    return sorted(PORTABILITY_ONLY_REGION_KEYS)
