"""Tests for benchmark package module."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from backend.common.benchmark_package import (
    BenchmarkConfig,
    BenchmarkReport,
    compute_brier_score,
    compute_calibration_error,
    compute_recall,
    compute_false_alarm_rate,
    compute_lead_time_hours,
    run_benchmark,
    export_report_json,
    export_report_markdown,
    compare_reports,
)


class TestBrierScore(unittest.TestCase):
    def test_perfect_predictions(self):
        self.assertAlmostEqual(compute_brier_score([1.0, 0.0], [1, 0]), 0.0)

    def test_worst_predictions(self):
        self.assertAlmostEqual(compute_brier_score([0.0, 1.0], [1, 0]), 1.0)

    def test_empty(self):
        self.assertEqual(compute_brier_score([], []), 0.0)

    def test_mismatched_lengths(self):
        self.assertEqual(compute_brier_score([0.5], [0, 1]), 0.0)


class TestCalibrationError(unittest.TestCase):
    def test_perfectly_calibrated(self):
        preds = [0.1, 0.3, 0.5, 0.7, 0.9]
        labels = [0, 0, 1, 1, 1]
        error = compute_calibration_error(preds, labels, n_bins=5)
        self.assertGreaterEqual(error, 0.0)

    def test_empty(self):
        self.assertEqual(compute_calibration_error([], []), 0.0)


class TestRecall(unittest.TestCase):
    def test_perfect_recall(self):
        self.assertAlmostEqual(compute_recall([0.8, 0.9], [1, 1]), 1.0)

    def test_zero_recall(self):
        self.assertAlmostEqual(compute_recall([0.2, 0.3], [1, 1]), 0.0)

    def test_no_positives(self):
        self.assertAlmostEqual(compute_recall([0.5, 0.5], [0, 0]), 0.0)


class TestFalseAlarmRate(unittest.TestCase):
    def test_zero_far(self):
        self.assertAlmostEqual(compute_false_alarm_rate([0.2, 0.3], [0, 0]), 0.0)

    def test_full_far(self):
        self.assertAlmostEqual(compute_false_alarm_rate([0.8, 0.9], [0, 0]), 1.0)

    def test_no_negatives(self):
        self.assertAlmostEqual(compute_false_alarm_rate([0.5, 0.5], [1, 1]), 0.0)


class TestLeadTime(unittest.TestCase):
    def test_positive_lead_time(self):
        preds = ['2026-01-10T06:00:00Z']
        events = ['2026-01-10T12:00:00Z']
        self.assertAlmostEqual(compute_lead_time_hours(preds, events), 6.0)

    def test_empty(self):
        self.assertEqual(compute_lead_time_hours([], []), 0.0)


class TestRunBenchmark(unittest.TestCase):
    def test_full_benchmark(self):
        config = BenchmarkConfig(name='test', region='test_region')
        preds = [0.8, 0.3, 0.6, 0.9, 0.2]
        labels = [1, 0, 1, 1, 0]
        pred_times = ['2026-01-10T06:00:00Z'] * 5
        event_times = ['2026-01-10T12:00:00Z'] * 5
        report = run_benchmark(config, preds, labels, prediction_times=pred_times, event_times=event_times)
        self.assertEqual(report.name, 'test')
        self.assertEqual(report.count, 5)
        self.assertGreater(report.brier_score, 0)
        self.assertGreaterEqual(report.recall, 0)
        self.assertAlmostEqual(report.lead_time_hours, 6.0)

    def test_empty_predictions(self):
        config = BenchmarkConfig(name='empty', region='r')
        report = run_benchmark(config, [], [])
        self.assertEqual(report.count, 0)
        self.assertEqual(report.brier_score, 0.0)


class TestExportReport(unittest.TestCase):
    def test_export_json(self):
        report = BenchmarkReport(name='test', region='r', timestamp='2026-01-15T00:00:00Z', count=5)
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = f.name
        export_report_json(report, path)
        with open(path) as f:
            data = json.load(f)
        os.unlink(path)
        self.assertEqual(data['name'], 'test')
        self.assertIn('disclaimer', data)

    def test_export_markdown(self):
        report = BenchmarkReport(name='test', region='r', timestamp='2026-01-15T00:00:00Z', count=5)
        with tempfile.NamedTemporaryFile(suffix='.md', delete=False) as f:
            path = f.name
        export_report_markdown(report, path)
        with open(path) as f:
            content = f.read()
        os.unlink(path)
        self.assertIn('Benchmark Report', content)
        self.assertIn('Brier Score', content)


class TestCompareReports(unittest.TestCase):
    def test_comparison(self):
        baseline = BenchmarkReport(name='b', region='r', timestamp='t', count=10, brier_score=0.25, recall=0.6)
        candidate = BenchmarkReport(name='c', region='r', timestamp='t', count=10, brier_score=0.20, recall=0.7)
        delta = compare_reports(baseline, candidate)
        self.assertAlmostEqual(delta['brier_score_delta'], -0.05)
        self.assertAlmostEqual(delta['recall_delta'], 0.1)


if __name__ == '__main__':
    unittest.main()
