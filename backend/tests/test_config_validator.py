"""Tests for canonical region registry validation (Phase 1a).

Ensures config/regions.json remains the single source of truth and
config/awsome_regions.yaml stays in sync with it.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from backend.common.config_validator import (
    HIMALAYAN_REGION_KEYS,
    PORTABILITY_ONLY_REGION_KEYS,
    classify_region_scope,
    get_himalayan_regions,
    get_portability_regions,
    validate_awsome_regions_sync,
)
from backend.common.regions import load_regions, repo_root


class TestAwsomeRegionsSync(unittest.TestCase):
    """Validate that awsome_regions.yaml is in sync with regions.json."""

    def test_real_configs_are_in_sync(self) -> None:
        """The actual repo configs must pass validation."""
        result = validate_awsome_regions_sync()
        self.assertTrue(
            result.valid,
            f'Config drift detected:\n' + '\n'.join(result.errors),
        )

    def test_all_regions_have_awsome_entry(self) -> None:
        """Every region in regions.json must have an AWSOME entry."""
        result = validate_awsome_regions_sync()
        regions_json = repo_root() / 'config' / 'regions.json'
        regions = load_regions(regions_json)
        region_keys = {r.key for r in regions}
        self.assertEqual(set(result.region_keys), region_keys)

    def test_missing_awsome_entry_is_detected(self) -> None:
        """A region missing from awsome_regions.yaml must be flagged."""
        regions_json = repo_root() / 'config' / 'regions.json'
        awsome_yaml = repo_root() / 'config' / 'awsome_regions.yaml'

        with TemporaryDirectory() as tmp:
            tmp_awsome = Path(tmp) / 'awsome_regions.yaml'
            with open(awsome_yaml) as f:
                cfg = yaml.safe_load(f)
            # Remove one region
            del cfg['himalayas_nepal']
            with open(tmp_awsome, 'w') as f:
                yaml.dump(cfg, f)

            result = validate_awsome_regions_sync(
                regions_path=regions_json,
                awsome_path=tmp_awsome,
            )
            self.assertFalse(result.valid)
            self.assertTrue(
                any('himalayas_nepal' in e for e in result.errors),
                f'Missing region not detected: {result.errors}',
            )

    def test_orphaned_awsome_entry_is_detected(self) -> None:
        """An AWSOME key with no matching region must be flagged."""
        regions_json = repo_root() / 'config' / 'regions.json'
        awsome_yaml = repo_root() / 'config' / 'awsome_regions.yaml'

        with TemporaryDirectory() as tmp:
            tmp_awsome = Path(tmp) / 'awsome_regions.yaml'
            with open(awsome_yaml) as f:
                cfg = yaml.safe_load(f)
            cfg['nonexistent_region'] = {'center': [0, 0], 'elevation_min': 0, 'elevation_max': 0}
            with open(tmp_awsome, 'w') as f:
                yaml.dump(cfg, f)

            result = validate_awsome_regions_sync(
                regions_path=regions_json,
                awsome_path=tmp_awsome,
            )
            self.assertFalse(result.valid)
            self.assertTrue(
                any('nonexistent_region' in e for e in result.errors),
                f'Orphaned key not detected: {result.errors}',
            )

    def test_center_drift_produces_warning(self) -> None:
        """Center coordinate drift must produce a warning (not error)."""
        regions_json = repo_root() / 'config' / 'regions.json'
        awsome_yaml = repo_root() / 'config' / 'awsome_regions.yaml'

        with TemporaryDirectory() as tmp:
            tmp_awsome = Path(tmp) / 'awsome_regions.yaml'
            with open(awsome_yaml) as f:
                cfg = yaml.safe_load(f)
            cfg['himalayas_nepal']['center'] = [99.0, 99.0]
            with open(tmp_awsome, 'w') as f:
                yaml.dump(cfg, f)

            result = validate_awsome_regions_sync(
                regions_path=regions_json,
                awsome_path=tmp_awsome,
            )
            self.assertTrue(result.valid)  # Warnings don't fail validation
            self.assertTrue(
                any('himalayas_nepal' in w and 'drift' in w for w in result.warnings),
                f'Center drift not warned: {result.warnings}',
            )


class TestHimalayanScopeClassification(unittest.TestCase):
    """Test Himalayan vs portability-only region classification."""

    def test_five_himalayan_regions_exist(self) -> None:
        """Exactly 5 Himalayan regions must be classified."""
        himalayan = get_himalayan_regions()
        self.assertEqual(len(himalayan), 5, f'Expected 5 Himalayan regions, got {himalayan}')

    def test_seven_portability_regions_exist(self) -> None:
        """Exactly 7 portability-only regions must be classified."""
        portability = get_portability_regions()
        self.assertEqual(len(portability), 7, f'Expected 7 portability regions, got {portability}')

    def test_all_real_regions_are_classified(self) -> None:
        """Every region in regions.json must be classified as himalayan or portability_only."""
        regions_json = repo_root() / 'config' / 'regions.json'
        regions = load_regions(regions_json)
        for r in regions:
            scope = classify_region_scope(r.key)
            self.assertIn(
                scope,
                ('himalayan', 'portability_only'),
                f'Region "{r.key}" is unclassified ({scope})',
            )

    def test_himalayan_and_portability_are_disjoint(self) -> None:
        """Himalayan and portability sets must not overlap."""
        self.assertEqual(HIMALAYAN_REGION_KEYS & PORTABILITY_ONLY_REGION_KEYS, frozenset())

    def test_nepal_is_himalayan(self) -> None:
        """Nepal must be classified as Himalayan (Tier A)."""
        self.assertEqual(classify_region_scope('himalayas_nepal'), 'himalayan')

    def test_karakoram_key_with_ampersand(self) -> None:
        """Karakoram & Ladakh key with ampersand must be classified correctly."""
        self.assertEqual(classify_region_scope('karakoram_&_ladakh'), 'himalayan')


if __name__ == '__main__':
    unittest.main()
