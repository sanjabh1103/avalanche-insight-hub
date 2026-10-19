"""Tests for SAR U-Net production gate evaluator."""
from __future__ import annotations

import json
import unittest

from backend.common.sar_unet_production_gate import (
    SarUnetGateResult,
    evaluate_sar_unet_quality_gate,
    evaluate_full_production_gate,
)


class EvaluateSarUnetQualityGateTests(unittest.TestCase):
    def test_passes_when_all_metrics_above_thresholds(self) -> None:
        result = evaluate_sar_unet_quality_gate({
            'iou': 0.55,
            'precision': 0.75,
            'recall': 0.65,
        })
        self.assertTrue(result.passed)
        self.assertEqual(result.recommendation, 'promote')
        self.assertEqual(len(result.failure_reasons), 0)

    def test_fails_on_low_iou(self) -> None:
        result = evaluate_sar_unet_quality_gate({
            'iou': 0.25,
            'precision': 0.75,
            'recall': 0.65,
        })
        self.assertFalse(result.passed)
        self.assertTrue(any('iou' in r for r in result.failure_reasons))
        self.assertEqual(result.recommendation, 'shadow')

    def test_fails_on_low_precision(self) -> None:
        result = evaluate_sar_unet_quality_gate({
            'iou': 0.55,
            'precision': 0.45,
            'recall': 0.65,
        })
        self.assertFalse(result.passed)
        self.assertTrue(any('precision' in r for r in result.failure_reasons))

    def test_fails_on_low_recall(self) -> None:
        result = evaluate_sar_unet_quality_gate({
            'iou': 0.55,
            'precision': 0.75,
            'recall': 0.30,
        })
        self.assertFalse(result.passed)
        self.assertTrue(any('recall' in r for r in result.failure_reasons))

    def test_fails_on_all_metrics_below(self) -> None:
        result = evaluate_sar_unet_quality_gate({
            'iou': 0.1,
            'precision': 0.2,
            'recall': 0.1,
        })
        self.assertFalse(result.passed)
        self.assertEqual(len(result.failure_reasons), 3)

    def test_computes_f1_correctly(self) -> None:
        result = evaluate_sar_unet_quality_gate({
            'iou': 0.55,
            'precision': 0.8,
            'recall': 0.6,
        })
        expected_f1 = 2 * 0.8 * 0.6 / (0.8 + 0.6)
        self.assertAlmostEqual(result.f1_score, round(expected_f1, 4), places=3)

    def test_zero_precision_recall_gives_zero_f1(self) -> None:
        result = evaluate_sar_unet_quality_gate({
            'iou': 0.0,
            'precision': 0.0,
            'recall': 0.0,
        })
        self.assertEqual(result.f1_score, 0.0)


class EvaluateFullProductionGateTests(unittest.TestCase):
    def test_overall_fails_when_sar_quality_fails(self) -> None:
        result = evaluate_full_production_gate(
            sar_metrics={'iou': 0.1, 'precision': 0.2, 'recall': 0.1},
            lstm_pss=0.5,
            lstm_brier=0.1,
            rf_pss=0.3,
            rf_brier=0.2,
            sar_release_gate_passed=True,
            sar_unet_promoted_count=100,
            sar_unet_promoted_region_count=5,
            sar_unet_promoted_scene_date_count=20,
        )
        self.assertFalse(result['overall_passed'])
        self.assertFalse(result['sar_unet_quality_gate']['passed'])
        self.assertEqual(result['recommendation'], 'shadow')

    def test_overall_fails_when_lstm_quality_fails(self) -> None:
        result = evaluate_full_production_gate(
            sar_metrics={'iou': 0.55, 'precision': 0.75, 'recall': 0.65},
            lstm_pss=0.2,
            lstm_brier=0.3,
            rf_pss=0.5,
            rf_brier=0.1,
            sar_release_gate_passed=True,
            sar_unet_promoted_count=100,
            sar_unet_promoted_region_count=5,
            sar_unet_promoted_scene_date_count=20,
        )
        self.assertFalse(result['overall_passed'])
        self.assertTrue(result['sar_unet_quality_gate']['passed'])
        self.assertFalse(result['shadow_quality_gate_passed'])

    def test_overall_passes_when_all_gates_pass(self) -> None:
        result = evaluate_full_production_gate(
            sar_metrics={'iou': 0.55, 'precision': 0.75, 'recall': 0.65},
            lstm_pss=0.5,
            lstm_brier=0.1,
            rf_pss=0.3,
            rf_brier=0.2,
            sar_release_gate_passed=True,
            sar_unet_promoted_count=100,
            sar_unet_promoted_region_count=5,
            sar_unet_promoted_scene_date_count=20,
        )
        self.assertTrue(result['overall_passed'])
        self.assertEqual(result['recommendation'], 'promote')


if __name__ == '__main__':
    unittest.main()
