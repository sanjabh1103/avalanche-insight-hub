"""Tests for G8: Validation spine (EAWS review ledger + calibration drift)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path


class EAWSReviewLedgerTests(unittest.TestCase):
    """Tests for EAWS review ledger round-trip and validation."""

    def test_record_round_trip_append_load(self) -> None:
        """Record can be appended and loaded back."""
        from backend.common.eaws_review_ledger import make_record, append_review_record, load_review_ledger

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = str(Path(tmpdir) / 'ledger.jsonl')
            record = make_record(
                forecast_run_id='RUN-001',
                cell_id='cell_0_0',
                stability_class='poor',
                frequency_class='occasional',
                expected_size_class=3,
                evidence_source='field_observation',
                reviewer='scientist_1',
                confidence=0.85,
                notes='Weak layer observed at 45cm',
            )
            record_id = append_review_record(path=ledger_path, record=record)
            self.assertEqual(record_id, record.record_id)

            loaded = load_review_ledger(path=ledger_path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].forecast_run_id, 'RUN-001')
            self.assertEqual(loaded[0].stability_class, 'poor')
            self.assertEqual(loaded[0].expected_size_class, 3)
            self.assertEqual(loaded[0].notes, 'Weak layer observed at 45cm')

    def test_invalid_stability_class_rejected(self) -> None:
        """Invalid stability class raises ValueError."""
        from backend.common.eaws_review_ledger import make_record, append_review_record

        record = make_record(
            forecast_run_id='RUN-001',
            cell_id='cell_0_0',
            stability_class='excellent',  # Invalid
            frequency_class='occasional',
            expected_size_class=3,
            evidence_source='field_observation',
            reviewer='scientist_1',
            confidence=0.85,
        )
        with self.assertRaises(ValueError) as ctx:
            append_review_record(path='/tmp/test_ledger.jsonl', record=record)
        self.assertIn('stability_class', str(ctx.exception))

    def test_invalid_size_class_rejected(self) -> None:
        """Invalid expected_size_class raises ValueError."""
        from backend.common.eaws_review_ledger import make_record, append_review_record

        record = make_record(
            forecast_run_id='RUN-001',
            cell_id='cell_0_0',
            stability_class='poor',
            frequency_class='occasional',
            expected_size_class=6,  # Invalid (must be 1-5)
            evidence_source='field_observation',
            reviewer='scientist_1',
            confidence=0.85,
        )
        with self.assertRaises(ValueError) as ctx:
            append_review_record(path='/tmp/test_ledger.jsonl', record=record)
        self.assertIn('expected_size_class', str(ctx.exception))

    def test_multiple_records_append_load(self) -> None:
        """Multiple records can be appended and loaded in order."""
        from backend.common.eaws_review_ledger import make_record, append_review_record, load_review_ledger

        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = str(Path(tmpdir) / 'ledger.jsonl')
            for i in range(3):
                record = make_record(
                    forecast_run_id=f'RUN-{i:03d}',
                    cell_id=f'cell_{i}_0',
                    stability_class='fair',
                    frequency_class='rare',
                    expected_size_class=2,
                    evidence_source='remote_sensing',
                    reviewer='scientist_2',
                    confidence=0.70,
                )
                append_review_record(path=ledger_path, record=record)

            loaded = load_review_ledger(path=ledger_path)
            self.assertEqual(len(loaded), 3)
            self.assertEqual(loaded[0].forecast_run_id, 'RUN-000')
            self.assertEqual(loaded[2].forecast_run_id, 'RUN-002')


class CalibrationDriftTests(unittest.TestCase):
    """Tests for calibration drift report computation."""

    def test_breach_true_when_coverage_gap_exceeds_threshold(self) -> None:
        """breach=True when coverage gap > 0.1 across 3 runs."""
        from backend.common.calibration_drift import compute_drift_report

        history = [
            {'run_id': 'R1', 'empirical_coverage': 0.95, 'held_out_coverage': 0.95, 'alpha': 0.1},
            {'run_id': 'R2', 'empirical_coverage': 0.93, 'held_out_coverage': 0.93, 'alpha': 0.1},
            {'run_id': 'R3', 'empirical_coverage': 0.70, 'held_out_coverage': 0.70, 'alpha': 0.1},
        ]
        report = compute_drift_report(history)
        self.assertTrue(report['breach'])
        self.assertIsNotNone(report['latest_gap'])
        self.assertGreater(report['latest_gap'], 0.1)

    def test_breach_false_for_healthy_series(self) -> None:
        """breach=False when coverage is close to target (1-alpha)."""
        from backend.common.calibration_drift import compute_drift_report

        history = [
            {'run_id': 'R1', 'empirical_coverage': 0.91, 'held_out_coverage': 0.91, 'alpha': 0.1},
            {'run_id': 'R2', 'empirical_coverage': 0.89, 'held_out_coverage': 0.89, 'alpha': 0.1},
            {'run_id': 'R3', 'empirical_coverage': 0.90, 'held_out_coverage': 0.90, 'alpha': 0.1},
        ]
        report = compute_drift_report(history)
        self.assertFalse(report['breach'])
        self.assertLessEqual(report['latest_gap'], 0.1)

    def test_empty_history_returns_insufficient_data(self) -> None:
        """Empty history returns trend='insufficient_data'."""
        from backend.common.calibration_drift import compute_drift_report

        report = compute_drift_report([])
        self.assertEqual(report['trend'], 'insufficient_data')
        self.assertFalse(report['breach'])

    def test_two_records_returns_insufficient_data(self) -> None:
        """Fewer than 3 records returns trend='insufficient_data'."""
        from backend.common.calibration_drift import compute_drift_report

        history = [
            {'run_id': 'R1', 'empirical_coverage': 0.90, 'alpha': 0.1},
            {'run_id': 'R2', 'empirical_coverage': 0.91, 'alpha': 0.1},
        ]
        report = compute_drift_report(history)
        self.assertEqual(report['trend'], 'insufficient_data')

    def test_worsening_trend_detected(self) -> None:
        """Worsening trend when gap increases across runs."""
        from backend.common.calibration_drift import compute_drift_report

        history = [
            {'run_id': 'R1', 'empirical_coverage': 0.90, 'alpha': 0.1},
            {'run_id': 'R2', 'empirical_coverage': 0.85, 'alpha': 0.1},
            {'run_id': 'R3', 'empirical_coverage': 0.75, 'alpha': 0.1},
        ]
        report = compute_drift_report(history)
        self.assertEqual(report['trend'], 'worsening')

    def test_append_and_load_history(self) -> None:
        """Calibration history can be appended and loaded."""
        from backend.common.calibration_drift import append_calibration_history, load_calibration_history

        with tempfile.TemporaryDirectory() as tmpdir:
            hist_path = str(Path(tmpdir) / 'history.jsonl')
            for i in range(3):
                append_calibration_history(path=hist_path, record={
                    'run_id': f'R{i}',
                    'empirical_coverage': 0.90 + i * 0.01,
                    'alpha': 0.1,
                })
            loaded = load_calibration_history(path=hist_path)
            self.assertEqual(len(loaded), 3)
            self.assertEqual(loaded[0]['run_id'], 'R0')

    def test_append_skips_silently_when_path_unset(self) -> None:
        """append_calibration_history skips silently when no path configured."""
        from backend.common.calibration_drift import append_calibration_history

        old = os.environ.get('CALIBRATION_HISTORY_PATH')
        os.environ['CALIBRATION_HISTORY_PATH'] = ''
        try:
            # Should not raise
            append_calibration_history(record={'run_id': 'R1', 'alpha': 0.1})
        finally:
            if old is None:
                os.environ.pop('CALIBRATION_HISTORY_PATH', None)
            else:
                os.environ['CALIBRATION_HISTORY_PATH'] = old


class TestDriftAlertAndGate(unittest.TestCase):
    """G-09: Test drift alert status and gate evaluation."""

    def _make_history(self, gaps: list[float]) -> list[dict]:
        """Create history records with given coverage gaps from target 0.9."""
        return [
            {'run_id': f'R{i+1}', 'empirical_coverage': 0.9 - g, 'held_out_coverage': 0.9 - g, 'alpha': 0.1}
            for i, g in enumerate(gaps)
        ]

    def test_no_drift_alert_when_gap_small(self):
        """Alert status is 'none' when drift gap is below alert threshold."""
        from backend.common.calibration_drift import compute_drift_report, evaluate_drift_alert
        history = self._make_history([0.01, 0.02, 0.03])
        report = compute_drift_report(history)
        alert = evaluate_drift_alert(report)
        self.assertEqual(alert.alert_status, 'none')

    def test_warning_alert_when_gap_exceeds_alert_threshold(self):
        """Alert status is 'warning' when drift gap exceeds 0.1 but below 0.2."""
        from backend.common.calibration_drift import compute_drift_report, evaluate_drift_alert
        history = self._make_history([0.01, 0.05, 0.15])
        report = compute_drift_report(history)
        alert = evaluate_drift_alert(report)
        self.assertEqual(alert.alert_status, 'warning')

    def test_critical_alert_when_gap_exceeds_block_threshold(self):
        """Alert status is 'critical' when drift gap exceeds 0.2."""
        from backend.common.calibration_drift import compute_drift_report, evaluate_drift_alert
        history = self._make_history([0.01, 0.1, 0.25])
        report = compute_drift_report(history)
        alert = evaluate_drift_alert(report)
        self.assertEqual(alert.alert_status, 'critical')

    def test_gate_blocks_on_critical_drift(self):
        """Gate fails when alert is critical."""
        from backend.common.calibration_drift import compute_drift_report, evaluate_drift_gate
        history = self._make_history([0.01, 0.1, 0.25])
        report = compute_drift_report(history)
        gate = evaluate_drift_gate(report)
        self.assertFalse(gate.gate_passed)
        self.assertEqual(gate.gate_reason, 'drift_blocks_publication')

    def test_gate_passes_with_warning(self):
        """Gate passes with 'warning_allowed' when alert is warning."""
        from backend.common.calibration_drift import compute_drift_report, evaluate_drift_gate
        history = self._make_history([0.01, 0.05, 0.15])
        report = compute_drift_report(history)
        gate = evaluate_drift_gate(report)
        self.assertTrue(gate.gate_passed)
        self.assertEqual(gate.gate_reason, 'warning_allowed')

    def test_gate_passes_no_drift(self):
        """Gate passes with 'no_drift' when drift is within range."""
        from backend.common.calibration_drift import compute_drift_report, evaluate_drift_gate
        history = self._make_history([0.01, 0.02, 0.03])
        report = compute_drift_report(history)
        gate = evaluate_drift_gate(report)
        self.assertTrue(gate.gate_passed)
        self.assertEqual(gate.gate_reason, 'no_drift')

    def test_gate_passes_insufficient_data(self):
        """Gate passes with 'insufficient_data' when history is too short."""
        from backend.common.calibration_drift import compute_drift_report, evaluate_drift_gate
        report = compute_drift_report([])
        gate = evaluate_drift_gate(report)
        self.assertTrue(gate.gate_passed)
        self.assertEqual(gate.gate_reason, 'insufficient_data')

    def test_scheduled_report_generates_all_fields(self):
        """G-09: generate_scheduled_drift_report produces drift_report, alert, and gate."""
        from backend.common.calibration_drift import (
            append_calibration_history, generate_scheduled_drift_report,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            hist_path = str(Path(tmpdir) / 'history.jsonl')
            for i in range(5):
                append_calibration_history(
                    path=hist_path,
                    record={'run_id': f'R{i+1}', 'empirical_coverage': 0.89 - i * 0.02, 'alpha': 0.1},
                )
            report = generate_scheduled_drift_report(hist_path)
            self.assertIn('drift_report', report)
            self.assertIn('alert', report)
            self.assertIn('gate', report)
            self.assertEqual(report['history_length'], 5)
            self.assertIn('generated_at', report)
            self.assertIn('retention_limit', report)

    def test_retention_limit_trims_old_records(self):
        """G-09: load_calibration_history applies retention limit."""
        from backend.common.calibration_drift import (
            append_calibration_history, load_calibration_history, DRIFT_RETENTION_RUNS,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            hist_path = str(Path(tmpdir) / 'history.jsonl')
            # Write more records than the retention limit
            for i in range(DRIFT_RETENTION_RUNS + 10):
                append_calibration_history(
                    path=hist_path,
                    record={'run_id': f'R{i+1}', 'alpha': 0.1},
                )
            loaded = load_calibration_history(hist_path)
            self.assertEqual(len(loaded), DRIFT_RETENTION_RUNS)

    def test_deterministic_drift_fixture_produces_expected_gate(self):
        """G-09: A deterministic drift fixture produces the expected alert/gate outcome."""
        from backend.common.calibration_drift import compute_drift_report, evaluate_drift_alert, evaluate_drift_gate
        # Deterministic fixture: 3 runs with increasing drift
        history = [
            {'run_id': 'R1', 'empirical_coverage': 0.90, 'held_out_coverage': 0.90, 'alpha': 0.1},
            {'run_id': 'R2', 'empirical_coverage': 0.85, 'held_out_coverage': 0.85, 'alpha': 0.1},
            {'run_id': 'R3', 'empirical_coverage': 0.70, 'held_out_coverage': 0.70, 'alpha': 0.1},
        ]
        report = compute_drift_report(history)
        alert = evaluate_drift_alert(report)
        gate = evaluate_drift_gate(report, alert)
        # Gap is 0.2 (target 0.9, actual 0.7) -> critical
        self.assertEqual(alert.alert_status, 'critical')
        self.assertFalse(gate.gate_passed)
        self.assertEqual(gate.gate_reason, 'drift_blocks_publication')
        self.assertEqual(report['trend'], 'worsening')

    def test_default_history_path_is_set(self):
        """G-09: Default CALIBRATION_HISTORY_PATH is set to config directory, not empty."""
        from backend.common.calibration_drift import _default_history_path
        path = _default_history_path()
        self.assertTrue(path)
        self.assertIn('calibration_history', path)
        self.assertIn('config', path)

    def test_validation_spine_failure_blocks_publication(self):
        """G-15: A failed validation spine gate must block publication via PublicationEvidence."""
        from backend.common.release_policy import PublicationEvidence, evaluate_publication_evidence, BASELINE_MODEL_TYPE
        # When validation_spine_passed=False, publication must be blocked
        evidence = PublicationEvidence(
            model_type=BASELINE_MODEL_TYPE,
            model_version='v1',
            uq_passed=True,
            provenance_verified=True,
            validation_spine_passed=False,
            eaws_reviewed=True,
        )
        decision = evaluate_publication_evidence(evidence)
        self.assertFalse(decision.allowed, 'Failed validation spine must block publication')
        self.assertIn('validation_spine', decision.blocking_reason or '')

    def test_validation_spine_pass_allows_publication(self):
        """G-15: When all gates pass including validation spine, publication is allowed."""
        from backend.common.release_policy import PublicationEvidence, evaluate_publication_evidence, BASELINE_MODEL_TYPE
        evidence = PublicationEvidence(
            model_type=BASELINE_MODEL_TYPE,
            model_version='v1',
            uq_passed=True,
            provenance_verified=True,
            validation_spine_passed=True,
            eaws_reviewed=True,
        )
        decision = evaluate_publication_evidence(evidence)
        self.assertTrue(decision.allowed, 'All gates passing should allow publication')
        self.assertEqual(decision.artifact_mode, 'technical_artifact')


if __name__ == '__main__':
    unittest.main()
