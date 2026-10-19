"""Tests for the evidence-loop report export CLI."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.scripts.evaluate_evidence_loop import main


def _prediction(day: int, evidence_available: bool = True) -> dict:
    return {
        'forecast_date': f'2026-01-{day:02d}',
        'lat': 35.0,
        'lng': 76.0,
        'probability': 0.8 if day % 2 else 0.2,
        'evidence_available': evidence_available,
        'feature_snapshot_sha256': 'a' * 64,
        'evidence_replay_sha256': 'b' * 64,
    }


class TestEvidenceLoopCli(unittest.TestCase):
    def test_exports_temporal_report_and_never_promotes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictions_path = root / 'predictions.json'
            events_path = root / 'events.json'
            output_path = root / 'report.json'
            predictions_path.write_text(json.dumps({'predictions': [_prediction(day) for day in range(1, 8)]}))
            events_path.write_text(json.dumps({'events': [{
                'timestamp': '2026-01-03T12:00:00Z',
                'location': 'POINT(76.0 35.0)',
                'source_identifier': 'official-event-1',
                'source_hash': 'c' * 64,
            }]}))

            self.assertEqual(main([
                '--predictions', str(predictions_path),
                '--events', str(events_path),
                '--output', str(output_path),
                '--n-splits', '2',
            ]), 0)
            report = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(report['schema_version'], 'evidence-loop-report/v1')
            self.assertIn('fold_boundaries', report)
            self.assertIn('baseline_metrics', report)
            self.assertIn('verification_gated_metrics', report)
            self.assertFalse(report['can_promote_model'])
            self.assertTrue(report['evaluation_only'])

    def test_writes_blocked_report_when_independent_labels_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            predictions_path = root / 'predictions.json'
            events_path = root / 'events.json'
            output_path = root / 'report.json'
            predictions_path.write_text(json.dumps([_prediction(day) for day in range(1, 4)]))
            events_path.write_text('[]')

            self.assertEqual(main([
                '--predictions', str(predictions_path),
                '--events', str(events_path),
                '--output', str(output_path),
            ]), 0)
            report = json.loads(output_path.read_text(encoding='utf-8'))
            self.assertEqual(report['blocked_reason'], 'insufficient_independent_labels')
            self.assertFalse(report['can_promote_model'])


if __name__ == '__main__':
    unittest.main()
