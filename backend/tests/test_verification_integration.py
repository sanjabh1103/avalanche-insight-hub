"""Integration tests for Wave D/E verification plan:
- CAP metadata blocked when freshness/lineage gates fail
- Great Himalaya dry-run with flags off byte-compatible
- Flags on producing packets
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch


class TestCAPPublicationGates(unittest.TestCase):
    """Verify CAP alert generation is blocked when gates fail."""

    def test_blocked_when_lineage_not_verified(self):
        from backend.common.cap_alert import check_cap_publication_gates
        allowed, reason = check_cap_publication_gates(
            source_freshness_hours={'sar': 12.0},
            lineage_verified=False,
        )
        self.assertFalse(allowed)
        self.assertIn('lineage', reason.lower())

    def test_blocked_when_synthetic_evidence(self):
        from backend.common.cap_alert import check_cap_publication_gates
        allowed, reason = check_cap_publication_gates(
            source_freshness_hours={'sar': 12.0},
            lineage_verified=True,
            has_synthetic_evidence=True,
        )
        self.assertFalse(allowed)
        self.assertIn('synthetic', reason.lower())

    def test_blocked_when_source_stale(self):
        from backend.common.cap_alert import check_cap_publication_gates
        allowed, reason = check_cap_publication_gates(
            source_freshness_hours={'sar': 96.0, 'optical': 12.0},
            lineage_verified=True,
            max_freshness_hours=72.0,
        )
        self.assertFalse(allowed)
        self.assertIn('stale', reason.lower())
        self.assertIn('sar', reason)

    def test_allowed_when_all_gates_pass(self):
        from backend.common.cap_alert import check_cap_publication_gates
        allowed, reason = check_cap_publication_gates(
            source_freshness_hours={'sar': 12.0, 'optical': 6.0},
            lineage_verified=True,
            has_synthetic_evidence=False,
        )
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_allowed_with_no_freshness_data(self):
        from backend.common.cap_alert import check_cap_publication_gates
        allowed, reason = check_cap_publication_gates(
            lineage_verified=True,
        )
        self.assertTrue(allowed)
        self.assertIsNone(reason)


class TestHimalayaDryRunFlagsOff(unittest.TestCase):
    """Verify flags-off byte-compatible behavior for Great Himalaya."""

    def test_flags_off_no_anomalies(self):
        os.environ['VERIFICATION_SPINE_ENABLED'] = 'false'
        os.environ['ACTIVE_LEARNING_ENABLED'] = 'false'
        try:
            from backend.common.anomaly_detector import detect_anomalies, SensorReading
            readings = {'weather': SensorReading(source='test', snow_depth_m=0.5)}
            flags, packet = detect_anomalies('cell_1', 'great_himalaya', readings)
            self.assertEqual(flags, [])
            self.assertEqual(packet.cell_id, 'cell_1')
        finally:
            pass

    def test_flags_off_active_learning_empty(self):
        os.environ['ACTIVE_LEARNING_ENABLED'] = 'false'
        try:
            from backend.common.active_learning import rank_cells_for_observation
            result = rank_cells_for_observation(
                [{'cell_id': 'c1', 'uncertainty': 0.5, 'anomaly_score': 0.3}],
                region_key='great_himalaya',
            )
            self.assertEqual(result, [])
        finally:
            pass

    def test_flags_off_Partner_disabled(self):
        os.environ['Partner_BULLETIN_VALIDATION_ENABLED'] = 'false'
        try:
            from backend.common.Partner_bulletin_adapter import Partner_BULLETIN_VALIDATION_ENABLED
            self.assertFalse(Partner_BULLETIN_VALIDATION_ENABLED)
        finally:
            pass


class TestFlagsOnProducingPackets(unittest.TestCase):
    """Verify flags-on produces verification packets."""

    def setUp(self):
        os.environ['VERIFICATION_SPINE_ENABLED'] = 'true'

    def tearDown(self):
        os.environ['VERIFICATION_SPINE_ENABLED'] = 'false'

    def test_flags_on_produces_verification_packet(self):
        from backend.common.anomaly_detector import detect_anomalies, SensorReading
        readings = {
            'weather': SensorReading(
                source='openmeteo',
                snow_depth_m=2.0,
                snow_cover_fraction=0.9,
                freshness_hours=6.0,
            ),
        }
        flags, packet = detect_anomalies(
            'cell_himalaya_1',
            'great_himalaya',
            readings,
            baseline_p25=0.3,
            baseline_p50=0.5,
            baseline_p75=0.7,
        )
        # Packet should be produced (may or may not have flags depending on readings)
        self.assertEqual(packet.cell_id, 'cell_himalaya_1')
        self.assertEqual(packet.region_key, 'great_himalaya')


class TestSyntheticExclusionIntegration(unittest.TestCase):
    """Verify synthetic scenarios are excluded from truth labels end-to-end."""

    def test_synthetic_label_never_added_to_manifest(self):
        from backend.common.continuous_learning import (
            AutoLabel,
            LABEL_SOURCE_SYNTHETIC,
            EXCLUDED_LABEL_SOURCES,
            add_to_training_manifest,
        )
        import tempfile
        from pathlib import Path

        tmpdir = tempfile.mkdtemp()
        manifest = Path(tmpdir) / 'audit.jsonl'

        label = AutoLabel(
            label_id='synth_001',
            source=LABEL_SOURCE_SYNTHETIC,
            timestamp='2026-07-04T12:00:00Z',
            lat=32.0,
            lng=77.0,
            label=1,
            confidence=0.99,
            region_key='great_himalaya',
        )

        result = add_to_training_manifest(label, manifest)
        self.assertFalse(result)
        self.assertIn(LABEL_SOURCE_SYNTHETIC, EXCLUDED_LABEL_SOURCES)


class TestValidationSpineIntegration(unittest.TestCase):
    """G-15/G-20: Verify EAWS review ledger and calibration drift are integrated via wrapper."""

    def _reload_and_check(self, env_overrides: dict, cells=None):
        """Reload verification modules with env overrides and run D gate via wrapper."""
        import importlib
        import backend.common.verification_contracts as vc_mod
        import backend.common.verification_exit_gates as veg_mod
        import backend.common.validation_spine_gates as vsg_mod
        with patch.dict('os.environ', env_overrides):
            importlib.reload(vc_mod)
            importlib.reload(veg_mod)
            importlib.reload(vsg_mod)
            result = vsg_mod.check_gate_d_production_with_validation_spine(
                cells=cells or [{'status': 'ready', 'verification_packet': {'anomaly_state': 'normal'}}],
            )
        # Restore modules
        importlib.reload(vc_mod)
        importlib.reload(veg_mod)
        importlib.reload(vsg_mod)
        return result

    def test_d_gate_includes_eaws_review_metric(self):
        """D gate metrics include eaws_review_records count."""
        result = self._reload_and_check({
            'VERIFICATION_SPINE_ENABLED': 'true',
            'GIBS_ENABLED': 'true',
            'S2_SNOW_ENABLED': 'true',
            'S1_DEPTH_ENABLED': 'true',
            'SNOW_DEPTH_FUSION_ENABLED': 'true',
            'VAE_ANOMALY_ENABLED': 'true',
            'ACTIVE_LEARNING_ENABLED': 'true',
            'EAWS_REVIEW_LEDGER_PATH': '/nonexistent/path/ledger.jsonl',
            'CALIBRATION_HISTORY_PATH': '',
        })
        self.assertIn('eaws_review_records', result.metrics)

    def test_d_gate_includes_drift_report_metric(self):
        """D gate metrics include drift_report."""
        result = self._reload_and_check({
            'VERIFICATION_SPINE_ENABLED': 'true',
            'GIBS_ENABLED': 'true',
            'S2_SNOW_ENABLED': 'true',
            'S1_DEPTH_ENABLED': 'true',
            'SNOW_DEPTH_FUSION_ENABLED': 'true',
            'VAE_ANOMALY_ENABLED': 'true',
            'ACTIVE_LEARNING_ENABLED': 'true',
            'EAWS_REVIEW_LEDGER_PATH': '/nonexistent/path/ledger.jsonl',
            'CALIBRATION_HISTORY_PATH': '',
        })
        self.assertIn('drift_report', result.metrics)

    def test_d_gate_warns_on_empty_eaws_ledger(self):
        """D gate warns when EAWS review ledger is empty."""
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            ledger_path = str(Path(tmpdir) / 'empty_ledger.jsonl')
            result = self._reload_and_check({
                'VERIFICATION_SPINE_ENABLED': 'true',
                'GIBS_ENABLED': 'true',
                'S2_SNOW_ENABLED': 'true',
                'S1_DEPTH_ENABLED': 'true',
                'SNOW_DEPTH_FUSION_ENABLED': 'true',
                'VAE_ANOMALY_ENABLED': 'true',
                'ACTIVE_LEARNING_ENABLED': 'true',
                'EAWS_REVIEW_LEDGER_PATH': ledger_path,
                'CALIBRATION_HISTORY_PATH': '',
            })
            self.assertTrue(any('EAWS review ledger is empty' in w for w in result.warnings))

    def test_d_gate_blocks_on_critical_drift(self):
        """D gate blocks when calibration drift gate fails (critical)."""
        import tempfile
        from pathlib import Path
        from backend.common.calibration_drift import append_calibration_history
        with tempfile.TemporaryDirectory() as tmpdir:
            hist_path = str(Path(tmpdir) / 'history.jsonl')
            for i, cov in enumerate([0.90, 0.85, 0.70]):
                append_calibration_history(path=hist_path, record={
                    'run_id': f'R{i+1}', 'empirical_coverage': cov, 'alpha': 0.1,
                })
            result = self._reload_and_check({
                'VERIFICATION_SPINE_ENABLED': 'true',
                'GIBS_ENABLED': 'true',
                'S2_SNOW_ENABLED': 'true',
                'S1_DEPTH_ENABLED': 'true',
                'SNOW_DEPTH_FUSION_ENABLED': 'true',
                'VAE_ANOMALY_ENABLED': 'true',
                'ACTIVE_LEARNING_ENABLED': 'true',
                'EAWS_REVIEW_LEDGER_PATH': '/nonexistent/path/ledger.jsonl',
                'CALIBRATION_HISTORY_PATH': hist_path,
            })
            self.assertFalse(result.passed)
            self.assertTrue(any('drift' in b.lower() for b in result.blockers))

    def test_wrapper_preserves_core_blockers(self):
        """Wrapper preserves core blockers (e.g. insufficient cells)."""
        result = self._reload_and_check(
            {
                'VERIFICATION_SPINE_ENABLED': 'true',
                'GIBS_ENABLED': 'true',
                'S2_SNOW_ENABLED': 'true',
                'S1_DEPTH_ENABLED': 'true',
                'SNOW_DEPTH_FUSION_ENABLED': 'true',
                'VAE_ANOMALY_ENABLED': 'true',
                'ACTIVE_LEARNING_ENABLED': 'true',
                'EAWS_REVIEW_LEDGER_PATH': '/nonexistent/path/ledger.jsonl',
                'CALIBRATION_HISTORY_PATH': '',
            },
            cells=[],
        )
        self.assertFalse(result.passed)
        self.assertTrue(any('cells processed' in b for b in result.blockers))

    def test_wrapper_returns_gate_result(self):
        """Wrapper returns a GateResult instance."""
        result = self._reload_and_check({
            'VERIFICATION_SPINE_ENABLED': 'true',
            'GIBS_ENABLED': 'true',
            'S2_SNOW_ENABLED': 'true',
            'S1_DEPTH_ENABLED': 'true',
            'SNOW_DEPTH_FUSION_ENABLED': 'true',
            'VAE_ANOMALY_ENABLED': 'true',
            'ACTIVE_LEARNING_ENABLED': 'true',
            'EAWS_REVIEW_LEDGER_PATH': '/nonexistent/path/ledger.jsonl',
            'CALIBRATION_HISTORY_PATH': '',
        })
        self.assertEqual(type(result).__name__, 'GateResult')
        self.assertTrue(hasattr(result, 'gate_name'))
        self.assertTrue(hasattr(result, 'passed'))
        self.assertTrue(hasattr(result, 'metrics'))
        self.assertTrue(hasattr(result, 'blockers'))
        self.assertTrue(hasattr(result, 'warnings'))

    def test_wrapper_preserves_spine_disabled_early_return(self):
        """Wrapper preserves core early-return when VERIFICATION_SPINE_ENABLED is false."""
        result = self._reload_and_check({'VERIFICATION_SPINE_ENABLED': 'false'})
        self.assertFalse(result.passed)
        self.assertTrue(any('VERIFICATION_SPINE_ENABLED is false' in b for b in result.blockers))
        # Should not have EAWS/drift metrics since core returned early
        self.assertNotIn('eaws_review_records', result.metrics)

    def test_core_gate_has_no_eaws_or_drift_metrics(self):
        """G-20: Core check_gate_d_production does NOT contain EAWS or drift metrics."""
        import importlib
        import backend.common.verification_contracts as vc_mod
        import backend.common.verification_exit_gates as veg_mod
        with patch.dict('os.environ', {
            'VERIFICATION_SPINE_ENABLED': 'true',
            'GIBS_ENABLED': 'true',
            'S2_SNOW_ENABLED': 'true',
            'S1_DEPTH_ENABLED': 'true',
            'SNOW_DEPTH_FUSION_ENABLED': 'true',
            'VAE_ANOMALY_ENABLED': 'true',
            'ACTIVE_LEARNING_ENABLED': 'true',
        }):
            importlib.reload(vc_mod)
            importlib.reload(veg_mod)
            core_result = veg_mod.check_gate_d_production(
                cells=[{'status': 'ready', 'verification_packet': {'anomaly_state': 'normal'}}],
            )
        importlib.reload(vc_mod)
        importlib.reload(veg_mod)
        self.assertNotIn('eaws_review_records', core_result.metrics)
        self.assertNotIn('drift_report', core_result.metrics)


if __name__ == '__main__':
    unittest.main()
