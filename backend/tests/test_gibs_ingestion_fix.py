"""Tests for gibs_ingestion.py fixes (emit_baseline_compatible_rows)."""
from __future__ import annotations

import unittest

from backend.common.gibs_ingestion import (
    GibsSnowCoverResult,
    GIBS_BASELINE_ENABLED,
    emit_baseline_compatible_rows,
)


class TestEmitBaselineRows(unittest.TestCase):
    def test_disabled_returns_empty(self):
        import backend.common.gibs_ingestion as gi
        original = gi.GIBS_BASELINE_ENABLED
        try:
            gi.GIBS_BASELINE_ENABLED = False
            results = emit_baseline_compatible_rows(
                [GibsSnowCoverResult(lat=39.5, lng=-106.5, date='2026-01-15', snow_cover_fraction=0.8, tile_url='http://example.com')],
                region_key='colorado_rockies',
            )
            self.assertEqual(results, [])
        finally:
            gi.GIBS_BASELINE_ENABLED = original

    def test_enabled_with_results(self):
        import backend.common.gibs_ingestion as gi
        original = gi.GIBS_BASELINE_ENABLED
        try:
            gi.GIBS_BASELINE_ENABLED = True
            results = [
                GibsSnowCoverResult(lat=39.5, lng=-106.5, date='2026-01-15', snow_cover_fraction=0.8, tile_url='http://example.com/tile1'),
                None,
                GibsSnowCoverResult(lat=39.6, lng=-106.6, date='2026-01-15', snow_cover_fraction=0.3, tile_url='http://example.com/tile2'),
            ]
            rows = emit_baseline_compatible_rows(
                results,
                region_key='colorado_rockies',
                cell_ids=['cell_0', 'cell_1', 'cell_2'],
            )
            self.assertEqual(len(rows), 2)  # None filtered out
            self.assertEqual(rows[0]['cell_id'], 'cell_0')
            self.assertEqual(rows[0]['sensor'], 'gibs_modis')
            self.assertEqual(rows[0]['snow_cover_fraction'], 0.8)
            self.assertEqual(rows[0]['region_key'], 'colorado_rockies')
            self.assertEqual(rows[1]['cell_id'], 'cell_2')
        finally:
            gi.GIBS_BASELINE_ENABLED = original

    def test_enabled_no_cell_ids(self):
        import backend.common.gibs_ingestion as gi
        original = gi.GIBS_BASELINE_ENABLED
        try:
            gi.GIBS_BASELINE_ENABLED = True
            rows = emit_baseline_compatible_rows(
                [GibsSnowCoverResult(lat=39.5, lng=-106.5, date='2026-01-15', snow_cover_fraction=0.5, tile_url='http://example.com')],
                region_key='test',
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['cell_id'], 'cell_0')
        finally:
            gi.GIBS_BASELINE_ENABLED = original


if __name__ == '__main__':
    unittest.main()
