"""Tests for GEE regional batching module."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch, MagicMock

from backend.common.gee_regional_batch import (
    RegionalBatchConfig,
    RegionalBatchResult,
    estimate_eecu_cost,
    build_regional_collection,
    export_regional_stats,
    run_regional_batch,
    GEE_REGIONAL_BATCH_ENABLED,
)


class TestEstimateEECUCost(unittest.TestCase):
    def test_zero_collection(self):
        self.assertEqual(estimate_eecu_cost(0), 0.0)

    def test_positive_collection(self):
        cost = estimate_eecu_cost(100, scale_m=90, band_count=1)
        self.assertGreater(cost, 0)

    def test_scales_with_bands(self):
        cost1 = estimate_eecu_cost(100, band_count=1)
        cost4 = estimate_eecu_cost(100, band_count=4)
        self.assertGreater(cost4, cost1)


class TestRegionalBatchDisabled(unittest.TestCase):
    def setUp(self):
        os.environ['GEE_REGIONAL_BATCH_ENABLED'] = 'false'
        import importlib
        import backend.common.gee_regional_batch as mod
        importlib.reload(mod)
        self.mod = mod

    def test_build_returns_none_when_disabled(self):
        config = RegionalBatchConfig(
            region_bbox=(75, 30, 80, 35),
            date_start='2026-01-01',
            date_end='2026-01-31',
            collection_id='COPERNICUS/S2_SR_HARMONIZED',
        )
        result = self.mod.build_regional_collection(config)
        self.assertIsNone(result)

    def test_run_returns_empty_when_disabled(self):
        config = RegionalBatchConfig(
            region_bbox=(75, 30, 80, 35),
            date_start='2026-01-01',
            date_end='2026-01-31',
            collection_id='COPERNICUS/S2_SR_HARMONIZED',
        )
        result = self.mod.run_regional_batch('test_region', config, [])
        self.assertEqual(len(result.cell_stats), 0)
        self.assertEqual(result.total_eecu_cost, 0.0)
        self.assertIn('Decision-support', result.disclaimer)

    def test_export_returns_empty_when_no_collection(self):
        result = self.mod.export_regional_stats(None, [])
        self.assertEqual(result, [])


class TestRegionalBatchResultSerialization(unittest.TestCase):
    def test_to_dict(self):
        config = RegionalBatchConfig(
            region_bbox=(75, 30, 80, 35),
            date_start='2026-01-01',
            date_end='2026-01-31',
            collection_id='test',
        )
        result = RegionalBatchResult(
            region_key='r1',
            config=config,
            total_eecu_cost=1.5,
            scene_ids=['s1', 's2'],
        )
        d = result.to_dict()
        self.assertEqual(d['region_key'], 'r1')
        self.assertEqual(d['total_eecu_cost'], 1.5)
        self.assertEqual(len(d['scene_ids']), 2)
        self.assertIn('Decision-support', d['disclaimer'])


if __name__ == '__main__':
    unittest.main()
