"""Tests for Partner_parallel_lanes.py — P9: Parallel lane preparation.

P9 exit gate: Both lanes are defined with their data sources, dependencies,
outputs, and blocking conditions.

G11: T2A is station-free (no SNOWPACK dependency). Track 1 REQUIRES Partner-approved
station/anchor data — it does NOT substitute public station sources.
G12: Lanes have granular permission fields (engineering_preparation_allowed,
feature_generation_allowed, training_allowed, evaluation_allowed).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from backend.common.Partner_parallel_lanes import (
    ParallelLaneV1,
    T2A_LANE,
    TRACK1_LANE,
    get_parallel_lanes,
    build_lane_summary,
    save_lane_summary,
    load_lane_summary,
)


class TestParallelLanes(unittest.TestCase):
    """P9: Both parallel lanes are properly defined."""

    def test_two_lanes_defined(self) -> None:
        lanes = get_parallel_lanes()
        self.assertEqual(len(lanes), 2)

    def test_t2a_lane_exists(self) -> None:
        self.assertEqual(T2A_LANE.track, 'T2A')
        self.assertEqual(T2A_LANE.lane_id, 'T2A_open_forcing_terrain_shadow')

    def test_track1_lane_exists(self) -> None:
        self.assertEqual(TRACK1_LANE.track, 'Track1')
        self.assertEqual(TRACK1_LANE.lane_id, 'Track1_station_snowpack')

    def test_each_lane_has_all_fields(self) -> None:
        """P9 exit gate: each lane has data_sources, dependencies, outputs, blocking_conditions."""
        for lane in get_parallel_lanes():
            self.assertIsNotNone(lane.lane_id)
            self.assertIsNotNone(lane.track)
            self.assertIsNotNone(lane.description)
            self.assertIsInstance(lane.data_sources, list)
            self.assertGreater(len(lane.data_sources), 0)
            self.assertIsInstance(lane.dependencies, list)
            self.assertGreater(len(lane.dependencies), 0)
            self.assertIsInstance(lane.outputs, list)
            self.assertGreater(len(lane.outputs), 0)
            self.assertIsInstance(lane.blocking_conditions, list)

    def test_g11_t2a_does_not_require_Partner_approval(self) -> None:
        """G11: T2A engineering preparation does not require Partner station approval."""
        self.assertFalse(T2A_LANE.Partner_approval_required)
        self.assertFalse(T2A_LANE.can_proceed,
                         'legacy can_proceed must not overstate specification-only preparation')

    def test_g11_track1_requires_Partner_approval(self) -> None:
        """G11: Track 1 REQUIRES Partner-approved station data — it is BLOCKED."""
        self.assertTrue(TRACK1_LANE.Partner_approval_required,
                        'Track 1 must require Partner approval for station/anchor data')
        self.assertFalse(TRACK1_LANE.can_proceed,
                         'Track 1 must be blocked until Partner provides approved station data')

    def test_g11_t2a_has_no_snowpack_dependency(self) -> None:
        """G11: T2A must NOT have SNOWPACK as a dependency — it is station-free."""
        for dep in T2A_LANE.dependencies:
            self.assertNotIn('SNOWPACK', dep,
                             f'T2A must not depend on SNOWPACK — it is station-free. Found: {dep}')
        for dep in T2A_LANE.data_sources:
            self.assertNotIn('SNOWPACK', dep,
                             f'T2A must not use SNOWPACK as a data source. Found: {dep}')

    def test_g11_track1_requires_Partner_station_data(self) -> None:
        """G11: Track 1 must require Partner-approved station data, not public substitutes."""
        # Must mention Partner-approved in data sources or dependencies
        all_text = ' '.join(TRACK1_LANE.data_sources + TRACK1_LANE.dependencies)
        self.assertIn('Partner', all_text,
                      'Track 1 must reference Partner-approved station data')
        # Must NOT say "Does NOT require Partner station data"
        self.assertNotIn('Does NOT require Partner', TRACK1_LANE.description,
                         'Track 1 must not claim Partner station data is unnecessary')

    def test_t2a_uses_public_data_sources(self) -> None:
        """T2A uses public data sources (ERA5, IMD, SRTM/ASTER)."""
        self.assertTrue(
            any('public' in s.lower() for s in T2A_LANE.data_sources),
            'T2A should have at least one explicitly public data source',
        )
        known_public = {'era5', 'imd', 'srtm', 'aster', 'dem', 'openstreetmap', 'noaa', 'isd'}
        for source in T2A_LANE.data_sources:
            self.assertTrue(
                any(kw in source.lower() for kw in known_public),
                f'T2A data source should reference a known public dataset: {source}',
            )

    def test_g11_track1_uses_Partner_and_public_sources(self) -> None:
        """G11: Track 1 uses Partner-approved station data plus public supplements."""
        # Must have Partner-approved station data
        self.assertTrue(
            any('Partner' in s for s in TRACK1_LANE.data_sources),
            'Track 1 must have Partner-approved station data as a source',
        )
        # May also have public supplements (ERA5, SNOWPACK)
        known_sources = {'era5', 'imd', 'srtm', 'aster', 'dem', 'openstreetmap',
                         'noaa', 'isd', 'published', 'snowpack', 'codebase', 'Partner'}
        for source in TRACK1_LANE.data_sources:
            self.assertTrue(
                any(kw in source.lower() for kw in known_sources),
                f'Track1 data source should reference a known dataset: {source}',
            )

    def test_outputs_are_features_not_labels(self) -> None:
        """P9: Lane outputs are features (model inputs), NOT labels."""
        for lane in get_parallel_lanes():
            for output in lane.outputs:
                self.assertNotIn('label', output.lower(),
                                 f'{lane.lane_id} output mentions labels: {output}')
                self.assertNotIn('danger_level', output.lower(),
                                 f'{lane.lane_id} output mentions danger_level: {output}')

    def test_frozen_dataclass(self) -> None:
        with self.assertRaises((AttributeError, TypeError)):
            T2A_LANE.track = 'modified'  # type: ignore[misc]

    def test_g12_lanes_have_granular_permissions(self) -> None:
        """G12: Each lane must have granular permission fields."""
        for lane in get_parallel_lanes():
            self.assertTrue(hasattr(lane, 'engineering_preparation_allowed'))
            self.assertTrue(hasattr(lane, 'feature_generation_allowed'))
            self.assertTrue(hasattr(lane, 'training_allowed'))
            self.assertTrue(hasattr(lane, 'evaluation_allowed'))

    def test_g12_t2a_allows_engineering_preparation(self) -> None:
        """G12: T2A allows engineering preparation (public data, no Partner approval needed)."""
        self.assertTrue(T2A_LANE.engineering_preparation_allowed)

    def test_n8_t2a_feature_generation_allowed(self) -> None:
        """N8: T2A's feature_generation_allowed must be explicitly tested."""
        # T2A uses public data but feature generation is False by default
        # because no executable data pipeline exists yet (is_specification=True)
        self.assertFalse(T2A_LANE.feature_generation_allowed,
                         'T2A feature_generation_allowed is False — no executable pipeline exists')

    def test_g12_track1_allows_engineering_preparation_only(self) -> None:
        """G12: Track 1 allows engineering preparation but NOT feature generation."""
        self.assertTrue(TRACK1_LANE.engineering_preparation_allowed)
        self.assertFalse(TRACK1_LANE.feature_generation_allowed)
        self.assertFalse(TRACK1_LANE.training_allowed)
        self.assertFalse(TRACK1_LANE.evaluation_allowed)

    def test_legacy_permissions_match_authoritative_granular_permissions(self) -> None:
        for lane in get_parallel_lanes():
            self.assertEqual(lane.can_proceed, lane.feature_generation_allowed)


class TestLaneSummary(unittest.TestCase):
    """P9: Lane summary for the Partner decision packet."""

    def test_g11_summary_reports_blocked_lanes(self) -> None:
        """G11: Summary must report that Track 1 is blocked."""
        summary = build_lane_summary()
        self.assertIn('lanes_blocked', summary)
        self.assertGreater(summary['lanes_blocked'], 0,
                           'At least one lane (Track 1) must be blocked')

    def test_g11_summary_does_not_claim_all_can_proceed(self) -> None:
        """G11: Summary must NOT claim all lanes can proceed."""
        summary = build_lane_summary()
        self.assertFalse(summary['all_can_proceed'],
                         'Not all lanes can proceed — Track 1 is blocked')

    def test_g12_summary_has_granular_counts(self) -> None:
        """G12: Summary must have granular permission counts."""
        summary = build_lane_summary()
        self.assertIn('engineering_preparation_allowed_count', summary)
        self.assertIn('feature_generation_allowed_count', summary)
        self.assertIn('training_allowed_count', summary)
        self.assertIn('evaluation_allowed_count', summary)

    def test_summary_reports_specification_status(self) -> None:
        """P9: The summary must report whether lanes are specification or implementation."""
        summary = build_lane_summary()
        self.assertIn('all_are_specification_only', summary)
        self.assertTrue(summary['all_are_specification_only'],
                        'All lanes must be marked as specification only')

    def test_lanes_marked_as_specification(self) -> None:
        """Each lane must have is_specification=True (no executable pipeline exists)."""
        for lane in get_parallel_lanes():
            self.assertTrue(lane.is_specification,
                            f'{lane.lane_id} must be marked as specification')

    def test_summary_has_two_lanes(self) -> None:
        summary = build_lane_summary()
        self.assertEqual(summary['total_lanes'], 2)

    def test_summary_has_key_finding(self) -> None:
        summary = build_lane_summary()
        self.assertIn('key_finding', summary)
        # G11: key finding should mention blocked lanes
        self.assertTrue('BLOCKED' in summary['key_finding'] or 'blocked' in summary['key_finding'],
                        'Key finding must mention blocked lanes')

    def test_save_and_load(self) -> None:
        summary = build_lane_summary()
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = Path(f.name)
        try:
            save_lane_summary(summary, path)
            loaded = load_lane_summary(path)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded['total_lanes'], 2)
        finally:
            path.unlink()

    def test_non_object_json_returns_structured_blocker(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as handle:
            path = Path(handle.name)
        try:
            path.write_text('[]', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, r'^E030_malformed_evidence:'):
                load_lane_summary(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
