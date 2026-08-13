"""Tests for F19: Continuous Learning Loop."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from backend.common.continuous_learning import (
    AUTO_LABEL_MIN_CONFIDENCE,
    AutoLabel,
    AutoLabelResult,
    LABEL_SOURCE_FIELD_REPORT,
    LABEL_SOURCE_SAR,
    LABEL_SOURCE_SEISMIC,
    LABEL_SOURCE_SYNTHETIC,
    EXCLUDED_LABEL_SOURCES,
    HUMAN_REVIEW_PENDING,
    VERIFICATION_BASIS_NONE,
    add_to_training_manifest,
    auto_label_field_report,
    auto_label_sar_detection,
    auto_label_seismic_event,
    get_auto_label_audit_trail,
    process_detections_for_learning,
    rotate_audit_file_if_needed,
    verify_auto_label_audit_chain,
)
from backend.common.label_governance import (
    AUTO_LABEL_MIN_CONFIDENCE as GOV_MIN_CONFIDENCE,
    AUTO_LABEL_SOURCES,
    is_auto_label_eligible,
)


class AutoLabelSarDetectionTests(unittest.TestCase):
    """Tests for SAR detection auto-labeling."""

    def test_auto_label_sar_high_confidence(self) -> None:
        detection = {
            'id': 'sar_001',
            'lat': 32.0,
            'lng': 78.0,
            'confidence': 0.9,
            'timestamp': '2026-06-25T10:00:00Z',
            'scene_id': 'S1_20260625',
        }
        label = auto_label_sar_detection(detection=detection, region_key='pir_panjal')
        self.assertIsNotNone(label)
        self.assertEqual(label.source, LABEL_SOURCE_SAR)
        self.assertEqual(label.label, 1)
        self.assertEqual(label.region_key, 'pir_panjal')
        self.assertLess(label.confidence, 0.9)  # Weighted down
        self.assertIn('detection_id', label.metadata)

    def test_auto_label_sar_low_confidence(self) -> None:
        detection = {
            'lat': 32.0,
            'lng': 78.0,
            'confidence': 0.2,
        }
        label = auto_label_sar_detection(detection=detection, region_key='test')
        self.assertIsNone(label)

    def test_auto_label_sar_missing_confidence(self) -> None:
        detection = {'lat': 32.0, 'lng': 78.0}
        label = auto_label_sar_detection(detection=detection, region_key='test')
        self.assertIsNone(label)


class AutoLabelSeismicEventTests(unittest.TestCase):
    """Tests for seismic event auto-labeling."""

    def test_auto_label_seismic_high_magnitude(self) -> None:
        event = {
            'id': 'usgs_001',
            'magnitude': 5.5,
            'lat': 33.0,
            'lng': 76.0,
            'timestamp': '2026-06-25T08:00:00Z',
            'depth_km': 10.0,
        }
        labels = auto_label_seismic_event(event=event, region_key='shamshabari')
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0].source, LABEL_SOURCE_SEISMIC)
        self.assertEqual(labels[0].label, 1)

    def test_auto_label_seismic_low_magnitude(self) -> None:
        event = {
            'magnitude': 3.0,
            'lat': 33.0,
            'lng': 76.0,
        }
        labels = auto_label_seismic_event(event=event, region_key='test')
        self.assertEqual(len(labels), 0)

    def test_auto_label_seismic_with_cells(self) -> None:
        event = {
            'id': 'usgs_002',
            'magnitude': 5.0,
            'lat': 33.0,
            'lng': 76.0,
            'timestamp': '2026-06-25T08:00:00Z',
        }
        cells = [
            {'lat': 33.1, 'lng': 76.1, 'seismic_amplification': 0.95},
            {'lat': 33.2, 'lng': 76.2, 'seismic_amplification': 0.5},
            {'lat': 33.3, 'lng': 76.3, 'seismic_amplification': 0.0},
        ]
        labels = auto_label_seismic_event(event=event, region_key='test', cells_with_amplification=cells)
        # Cell with 0.3 amplification may be below AUTO_LABEL_MIN_CONFIDENCE
        self.assertGreaterEqual(len(labels), 1)
        for label in labels:
            self.assertEqual(label.source, LABEL_SOURCE_SEISMIC)


class AutoLabelFieldReportTests(unittest.TestCase):
    """Tests for field report auto-labeling."""

    def test_auto_label_field_report_avalanche_observed(self) -> None:
        report = {
            'id': 'fr_001',
            'lat': 32.0,
            'lng': 78.0,
            'avalanche_observed': True,
            'timestamp': '2026-06-25T09:00:00Z',
            'observer': 'patrol_team_a',
        }
        label = auto_label_field_report(report=report, region_key='pir_panjal')
        self.assertIsNotNone(label)
        self.assertEqual(label.source, LABEL_SOURCE_FIELD_REPORT)
        self.assertEqual(label.label, 1)
        self.assertGreater(label.confidence, 0.8)

    def test_auto_label_field_report_no_avalanche(self) -> None:
        report = {
            'id': 'fr_002',
            'lat': 32.0,
            'lng': 78.0,
            'avalanche_observed': False,
            'timestamp': '2026-06-25T09:00:00Z',
        }
        label = auto_label_field_report(report=report, region_key='test')
        self.assertIsNotNone(label)
        self.assertEqual(label.label, 0)


class TrainingManifestTests(unittest.TestCase):
    """Tests for training manifest audit trail."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.manifest_path = Path(self.tmpdir) / 'audit.jsonl'

    def test_add_to_manifest_and_read(self) -> None:
        label = AutoLabel(
            label_id='test_001',
            source=LABEL_SOURCE_SAR,
            timestamp='2026-06-25T10:00:00Z',
            lat=32.0,
            lng=78.0,
            label=1,
            confidence=0.85,
            region_key='test',
            metadata={'detection_id': 'det_001'},
        )
        result = add_to_training_manifest(label, self.manifest_path)
        self.assertTrue(result)

        entries = get_auto_label_audit_trail(self.manifest_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['label_id'], 'test_001')
        self.assertEqual(entries[0]['source'], LABEL_SOURCE_SAR)

    def test_read_empty_manifest(self) -> None:
        entries = get_auto_label_audit_trail(self.manifest_path)
        self.assertEqual(len(entries), 0)

    def test_filter_by_source(self) -> None:
        for i in range(3):
            label = AutoLabel(
                label_id=f'test_{i}',
                source=LABEL_SOURCE_SAR if i < 2 else LABEL_SOURCE_SEISMIC,
                timestamp='2026-06-25T10:00:00Z',
                lat=32.0,
                lng=78.0,
                label=1,
                confidence=0.8,
                region_key='test',
            )
            add_to_training_manifest(label, self.manifest_path)

        sar_entries = get_auto_label_audit_trail(self.manifest_path, source=LABEL_SOURCE_SAR)
        self.assertEqual(len(sar_entries), 2)

    def test_filter_by_region(self) -> None:
        for region in ['pir_panjal', 'shamshabari', 'pir_panjal']:
            label = AutoLabel(
                label_id=f'test_{region}',
                source=LABEL_SOURCE_SAR,
                timestamp='2026-06-25T10:00:00Z',
                lat=32.0,
                lng=78.0,
                label=1,
                confidence=0.8,
                region_key=region,
            )
            add_to_training_manifest(label, self.manifest_path)

        pp_entries = get_auto_label_audit_trail(self.manifest_path, region_key='pir_panjal')
        self.assertEqual(len(pp_entries), 2)

    def test_manifest_entries_are_hash_chained_with_retention(self) -> None:
        first = AutoLabel(
            label_id='chain_001',
            source=LABEL_SOURCE_SAR,
            timestamp='2026-06-25T10:00:00Z',
            lat=32.0,
            lng=78.0,
            label=1,
            confidence=0.8,
            region_key='test',
        )
        second = AutoLabel(
            label_id='chain_002',
            source=LABEL_SOURCE_SEISMIC,
            timestamp='2026-06-25T11:00:00Z',
            lat=33.0,
            lng=77.0,
            label=1,
            confidence=0.7,
            region_key='test',
        )
        self.assertTrue(add_to_training_manifest(first, self.manifest_path))
        self.assertTrue(add_to_training_manifest(second, self.manifest_path))

        entries = get_auto_label_audit_trail(self.manifest_path)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['audit_schema_version'], 'auto_label_audit_v2')
        self.assertEqual(entries[0]['previous_hash'], '0' * 64)
        self.assertRegex(entries[0]['entry_hash'], r'^[0-9a-f]{64}$')
        self.assertEqual(entries[1]['previous_hash'], entries[0]['entry_hash'])
        self.assertIn('retention_until', entries[0])

        verification = verify_auto_label_audit_chain(self.manifest_path)
        self.assertTrue(verification['valid'])
        self.assertEqual(verification['hashed_entries'], 2)
        self.assertEqual(verification['legacy_entries'], 0)

    def test_audit_chain_detects_tampering(self) -> None:
        label = AutoLabel(
            label_id='tamper_001',
            source=LABEL_SOURCE_SAR,
            timestamp='2026-06-25T10:00:00Z',
            lat=32.0,
            lng=78.0,
            label=1,
            confidence=0.8,
            region_key='test',
        )
        self.assertTrue(add_to_training_manifest(label, self.manifest_path))

        entry = json.loads(self.manifest_path.read_text(encoding='utf-8').strip())
        entry['confidence'] = 0.1
        self.manifest_path.write_text(json.dumps(entry) + '\n', encoding='utf-8')

        verification = verify_auto_label_audit_chain(self.manifest_path)
        self.assertFalse(verification['valid'])
        self.assertEqual(verification['failures'][0]['reason'], 'entry_hash_mismatch')


class ProcessDetectionsForLearningTests(unittest.TestCase):
    """Tests for batch processing of detections."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.manifest_path = Path(self.tmpdir) / 'audit.jsonl'

    def test_process_all_sources(self) -> None:
        result = process_detections_for_learning(
            sar_detections=[
                {'id': 's1', 'lat': 32, 'lng': 78, 'confidence': 0.9, 'timestamp': '2026-06-25T10:00:00Z'},
            ],
            seismic_events=[
                {'id': 'e1', 'magnitude': 5.0, 'lat': 33, 'lng': 76, 'timestamp': '2026-06-25T08:00:00Z'},
            ],
            field_reports=[
                {'id': 'f1', 'lat': 32, 'lng': 78, 'avalanche_observed': True, 'timestamp': '2026-06-25T09:00:00Z'},
            ],
            region_key='test',
            manifest_path=self.manifest_path,
        )
        self.assertGreater(result.labels_created, 0)
        self.assertEqual(len(result.audit_entries), result.labels_created)

    def test_process_empty_detections(self) -> None:
        result = process_detections_for_learning(
            region_key='test',
            manifest_path=self.manifest_path,
        )
        self.assertEqual(result.labels_created, 0)
        self.assertEqual(result.labels_skipped, 0)

    def test_process_low_confidence_skipped(self) -> None:
        result = process_detections_for_learning(
            sar_detections=[
                {'id': 's1', 'lat': 32, 'lng': 78, 'confidence': 0.1},
            ],
            region_key='test',
            manifest_path=self.manifest_path,
        )
        self.assertEqual(result.labels_created, 0)
        self.assertGreater(result.labels_skipped, 0)
        self.assertIn('sar_low_confidence', result.skip_reasons)


class LabelGovernanceAutoLabelTests(unittest.TestCase):
    """Tests for auto-label eligibility in label governance."""

    def test_auto_label_eligible_high_confidence(self) -> None:
        record = {'source': 'sar_detection', 'confidence': 0.8}
        self.assertTrue(is_auto_label_eligible(record))

    def test_auto_label_not_eligible_low_confidence(self) -> None:
        record = {'source': 'sar_detection', 'confidence': 0.2}
        self.assertFalse(is_auto_label_eligible(record))

    def test_non_auto_label_always_eligible(self) -> None:
        record = {'source': 'field_report', 'confidence': 0.3}
        self.assertTrue(is_auto_label_eligible(record))

    def test_auto_label_no_confidence(self) -> None:
        record = {'source': 'seismic_event'}
        self.assertFalse(is_auto_label_eligible(record))

    def test_auto_label_sources_set(self) -> None:
        self.assertIn('sar_detection', AUTO_LABEL_SOURCES)
        self.assertIn('seismic_event', AUTO_LABEL_SOURCES)
        self.assertIn('auto_field_report', AUTO_LABEL_SOURCES)


class TestAuditRotation(unittest.TestCase):
    """Tests for audit trail file rotation."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.manifest_path = Path(self.tmpdir) / 'audit.jsonl'

    def _write_large_file(self, path: Path, size_mb: float) -> None:
        """Write a file of approximately size_mb megabytes."""
        chunk = '{"test": true}\n' * 1000
        target_bytes = int(size_mb * 1024 * 1024)
        with open(path, 'w', encoding='utf-8') as f:
            written = 0
            while written < target_bytes:
                f.write(chunk)
                written += len(chunk)

    def test_no_rotation_under_threshold(self) -> None:
        """Small file should not trigger rotation."""
        self.manifest_path.write_text('{"test": true}\n', encoding='utf-8')
        result = rotate_audit_file_if_needed(self.manifest_path)
        self.assertFalse(result)
        self.assertTrue(self.manifest_path.exists())
        self.assertFalse(self.manifest_path.with_suffix('.1').exists())

    def test_rotation_when_exceeds_threshold(self) -> None:
        """File exceeding threshold should be rotated to .1."""
        import backend.common.continuous_learning as cl
        original_max = cl.AUTO_LABEL_AUDIT_MAX_SIZE_MB
        cl.AUTO_LABEL_AUDIT_MAX_SIZE_MB = 0.001  # 1 KB threshold
        try:
            self._write_large_file(self.manifest_path, 0.01)  # 10 KB
            result = rotate_audit_file_if_needed(self.manifest_path)
            self.assertTrue(result)
            self.assertFalse(self.manifest_path.exists())
            self.assertTrue(self.manifest_path.with_suffix('.1').exists())
        finally:
            cl.AUTO_LABEL_AUDIT_MAX_SIZE_MB = original_max

    def test_multi_generation_rotation(self) -> None:
        """Existing .1 should be pushed to .2 during rotation."""
        import backend.common.continuous_learning as cl
        original_max = cl.AUTO_LABEL_AUDIT_MAX_SIZE_MB
        cl.AUTO_LABEL_AUDIT_MAX_SIZE_MB = 0.001
        try:
            # Create .1 archive
            archive_1 = self.manifest_path.with_suffix('.1')
            archive_1.write_text('{"old": true}\n', encoding='utf-8')
            # Create large current file
            self._write_large_file(self.manifest_path, 0.01)
            result = rotate_audit_file_if_needed(self.manifest_path)
            self.assertTrue(result)
            self.assertFalse(self.manifest_path.exists())
            self.assertTrue(self.manifest_path.with_suffix('.1').exists())
            self.assertTrue(self.manifest_path.with_suffix('.2').exists())
        finally:
            cl.AUTO_LABEL_AUDIT_MAX_SIZE_MB = original_max

    def test_max_generations_dropped(self) -> None:
        """File at max generation should be dropped during rotation."""
        import backend.common.continuous_learning as cl
        original_max = cl.AUTO_LABEL_AUDIT_MAX_SIZE_MB
        original_gen = cl.AUTO_LABEL_AUDIT_MAX_GENERATIONS
        cl.AUTO_LABEL_AUDIT_MAX_SIZE_MB = 0.001
        cl.AUTO_LABEL_AUDIT_MAX_GENERATIONS = 3
        try:
            # Create .1, .2, .3 archives
            for gen in range(1, 4):
                p = self.manifest_path.with_suffix(f'.{gen}')
                p.write_text(f'{{"gen": {gen}}}\n', encoding='utf-8')
            # Create large current file
            self._write_large_file(self.manifest_path, 0.01)
            result = rotate_audit_file_if_needed(self.manifest_path)
            self.assertTrue(result)
            # .3 should have been dropped (no .4 created)
            self.assertFalse(self.manifest_path.with_suffix('.4').exists())
            # .1, .2, .3 should exist (current -> .1, .1 -> .2, .2 -> .3)
            self.assertTrue(self.manifest_path.with_suffix('.1').exists())
            self.assertTrue(self.manifest_path.with_suffix('.2').exists())
            self.assertTrue(self.manifest_path.with_suffix('.3').exists())
        finally:
            cl.AUTO_LABEL_AUDIT_MAX_SIZE_MB = original_max
            cl.AUTO_LABEL_AUDIT_MAX_GENERATIONS = original_gen


class TestSyntheticExclusionAndVerificationBasis(unittest.TestCase):
    """Wave D: synthetic scenario exclusion and verification_basis/human_review_state."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manifest_path = Path(self.tmpdir) / 'test_audit.jsonl'

    def test_synthetic_source_in_excluded_set(self):
        self.assertIn(LABEL_SOURCE_SYNTHETIC, EXCLUDED_LABEL_SOURCES)

    def test_synthetic_label_rejected_from_manifest(self):
        label = AutoLabel(
            label_id='synthetic_001',
            source=LABEL_SOURCE_SYNTHETIC,
            timestamp='2026-07-04T12:00:00Z',
            lat=39.5,
            lng=-106.5,
            label=1,
            confidence=0.99,
            region_key='test',
        )
        result = add_to_training_manifest(label, self.manifest_path)
        self.assertFalse(result)
        # Manifest should not exist or be empty
        if self.manifest_path.exists():
            lines = self.manifest_path.read_text().strip()
            self.assertEqual(lines, '')

    def test_real_label_accepted_with_verification_basis(self):
        label = AutoLabel(
            label_id='sar_001',
            source=LABEL_SOURCE_SAR,
            timestamp='2026-07-04T12:00:00Z',
            lat=39.5,
            lng=-106.5,
            label=1,
            confidence=0.85,
            region_key='test',
        )
        result = add_to_training_manifest(label, self.manifest_path)
        self.assertTrue(result)
        entries = get_auto_label_audit_trail(self.manifest_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['verification_basis'], VERIFICATION_BASIS_NONE)
        self.assertEqual(entries[0]['human_review_state'], HUMAN_REVIEW_PENDING)

    def test_auto_label_defaults_verification_basis_none(self):
        label = AutoLabel(
            label_id='test_001',
            source=LABEL_SOURCE_SAR,
            timestamp='2026-07-04T12:00:00Z',
            lat=39.5,
            lng=-106.5,
            label=1,
            confidence=0.85,
            region_key='test',
        )
        self.assertEqual(label.verification_basis, VERIFICATION_BASIS_NONE)
        self.assertEqual(label.human_review_state, HUMAN_REVIEW_PENDING)


if __name__ == '__main__':
    unittest.main()
