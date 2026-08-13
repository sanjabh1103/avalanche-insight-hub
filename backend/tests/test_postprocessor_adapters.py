"""Tests for postprocessor adapter interfaces (Phase 8-prep)."""
from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from backend.common.postprocessor_adapters import (
    DefaultAggregateproAdapter,
    DefaultAvaproAdapter,
    DefaultQmahAdapter,
    PostprocessorResult,
    map_problem_to_local_terminology,
    PROBLEM_TYPE_MAPPING,
    POSTPROCESSOR_STATUS,
)


class TestPostprocessorResult(unittest.TestCase):
    """Test postprocessor result validation."""

    def _valid_result(self, **overrides) -> PostprocessorResult:
        defaults = dict(
            postprocessor='avapro',
            status='not_installed',
            is_advisory_only=True,
        )
        defaults.update(overrides)
        return PostprocessorResult(**defaults)

    def test_valid_result_accepted(self) -> None:
        errors = self._valid_result().validate()
        self.assertEqual(errors, [])

    def test_invalid_postprocessor_rejected(self) -> None:
        errors = self._valid_result(postprocessor='invalid').validate()
        self.assertTrue(any('postprocessor' in e for e in errors))

    def test_invalid_status_rejected(self) -> None:
        errors = self._valid_result(status='invalid_status').validate()
        self.assertTrue(any('status' in e for e in errors))

    def test_non_advisory_rejected(self) -> None:
        """Postprocessor outputs must always be advisory only."""
        errors = self._valid_result(is_advisory_only=False).validate()
        self.assertTrue(any('advisory' in e.lower() for e in errors))

    def test_output_paths_must_stay_inside_declared_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            safe = self._valid_result(output_paths=('native/profile.pro',))
            self.assertEqual(safe.validate_output_paths(root), [])
            traversal = self._valid_result(output_paths=('../outside.pro',))
            self.assertTrue(traversal.validate_output_paths(root))
            absolute = self._valid_result(output_paths=('/tmp/outside.pro',))
            self.assertTrue(absolute.validate_output_paths(root))

    def test_symlinked_output_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / f'{root.name}-outside.pro'
            outside.write_text('not an approved output', encoding='utf-8')
            link = root / 'profile.pro'
            link.symlink_to(outside)
            result = self._valid_result(output_paths=('profile.pro',))
            self.assertTrue(result.validate_output_paths(root))
            outside.unlink()


class TestDefaultAdapters(unittest.TestCase):
    """Test default adapter implementations."""

    def test_avapro_default_returns_not_installed(self) -> None:
        adapter = DefaultAvaproAdapter()
        result = adapter.run(
            pro_files=[Path('/fake/file.pro')],
            smet_files=[Path('/fake/file.smet')],
            region_key='himalayas_nepal',
            elevation_band='lower',
            aspect_class='N',
        )
        self.assertEqual(result.postprocessor, 'avapro')
        self.assertEqual(result.status, 'not_installed')
        self.assertTrue(result.is_advisory_only)

    def test_aggregatepro_default_returns_not_installed(self) -> None:
        adapter = DefaultAggregateproAdapter()
        result = adapter.run(
            pro_files=[Path('/fake/file.pro')],
            region_key='himalayas_nepal',
            climate_class='continental',
            elevation_band='lower',
            aspect_class='N',
            forecast_horizon_h=48,
        )
        self.assertEqual(result.postprocessor, 'aggregatepro')
        self.assertEqual(result.status, 'not_installed')

    def test_qmah_default_returns_shadow(self) -> None:
        """qmah must default to shadow/research mode."""
        adapter = DefaultQmahAdapter()
        result = adapter.run(
            pro_files=[Path('/fake/file.pro')],
            smet_files=[Path('/fake/file.smet')],
            region_key='himalayas_nepal',
            elevation_band='lower',
            aspect_class='N',
        )
        self.assertEqual(result.postprocessor, 'qmah')
        self.assertEqual(result.status, 'shadow')
        self.assertTrue(result.is_advisory_only)
        self.assertIn('shadow', result.error.lower())


class TestProblemTypeMapping(unittest.TestCase):
    """Test EAWS to Partner local terminology mapping."""

    def test_new_snow_maps_to_storm_slab(self) -> None:
        self.assertEqual(map_problem_to_local_terminology('new_snow'), 'storm_slab')

    def test_wind_slab_unchanged(self) -> None:
        self.assertEqual(map_problem_to_local_terminology('wind_slab'), 'wind_slab')

    def test_unknown_problem_passthrough(self) -> None:
        self.assertEqual(map_problem_to_local_terminology('unknown_type'), 'unknown_type')

    def test_all_four_problem_types_mapped(self) -> None:
        """All four EAWS problem types must have mappings."""
        for eaws_type in ('new_snow', 'wind_slab', 'persistent_weak_layer', 'wet_snow'):
            self.assertIn(eaws_type, PROBLEM_TYPE_MAPPING)


class TestPostprocessorStatus(unittest.TestCase):
    """Test postprocessor status values."""

    def test_all_statuses_defined(self) -> None:
        expected = {'not_installed', 'shadow', 'operational', 'failed', 'inputs_unavailable'}
        self.assertEqual(POSTPROCESSOR_STATUS, expected)


if __name__ == '__main__':
    unittest.main()
