"""Tests for Partner_literature_matrix.py — P8: Literature-to-contract matrix.

P8 exit gate: A matrix exists with one row per paper, columns for
task, geography, prediction unit, inputs, danger scale, and
conformance status against the Partner 5-level contract.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from backend.common.Partner_literature_matrix import (
    LiteratureEntryV1,
    LITERATURE_MATRIX,
    build_literature_matrix,
    get_conformant_papers,
    get_partial_papers,
    get_non_conformant_papers,
    get_unverified_papers,
    build_matrix_summary,
    save_matrix_summary,
    load_matrix_summary,
)


class TestLiteratureMatrix(unittest.TestCase):
    """P8: The literature matrix has one row per paper with required columns."""

    def test_matrix_has_entries(self) -> None:
        matrix = build_literature_matrix()
        self.assertGreater(len(matrix), 0)

    def test_each_entry_has_all_fields(self) -> None:
        """P8 exit gate: each entry has task, geography, prediction_unit, inputs, danger_scale."""
        matrix = build_literature_matrix()
        for entry in matrix:
            self.assertIsNotNone(entry.paper_id)
            self.assertIsNotNone(entry.title)
            self.assertIsNotNone(entry.authors)
            self.assertGreater(entry.year, 2000)
            self.assertIsNotNone(entry.source)
            self.assertIsNotNone(entry.task)
            self.assertIsNotNone(entry.geography)
            self.assertIsNotNone(entry.prediction_unit)
            self.assertIsInstance(entry.inputs, list)
            self.assertGreater(len(entry.inputs), 0)
            self.assertIsNotNone(entry.danger_scale)
            self.assertIsNotNone(entry.conformance_status)
            self.assertIsNotNone(entry.conformance_notes)

    def test_entry_to_dict(self) -> None:
        entry = LITERATURE_MATRIX[0]
        d = entry.to_dict()
        self.assertIn('paper_id', d)
        self.assertIn('task', d)
        self.assertIn('geography', d)
        self.assertIn('prediction_unit', d)
        self.assertIn('inputs', d)
        self.assertIn('danger_scale', d)
        self.assertIn('conformance_status', d)

    def test_frozen_dataclass(self) -> None:
        entry = LITERATURE_MATRIX[0]
        with self.assertRaises((AttributeError, TypeError)):
            entry.task = 'modified'  # type: ignore[misc]


class TestConformanceClassification(unittest.TestCase):
    """P8: Papers are classified by conformance with the Partner 5-level contract."""

    def test_conformant_papers_are_verified(self) -> None:
        """Conformant papers must be verified AND use 5-level scale."""
        conformant = get_conformant_papers()
        for paper in conformant:
            self.assertEqual(paper.conformance_status, 'conformant')
            self.assertTrue(paper.verified, f'Conformant paper {paper.paper_id} must be verified')
            self.assertIn('5-level', paper.danger_scale)

    def test_partial_papers_are_verified(self) -> None:
        """Partial papers must be verified."""
        partial = get_partial_papers()
        for paper in partial:
            self.assertEqual(paper.conformance_status, 'partial')
            self.assertTrue(paper.verified, f'Partial paper {paper.paper_id} must be verified')

    def test_non_conformant_papers_are_verified(self) -> None:
        """Non-conformant papers must be verified."""
        non_conformant = get_non_conformant_papers()
        for paper in non_conformant:
            self.assertEqual(paper.conformance_status, 'non_conformant')
            self.assertTrue(paper.verified, f'Non-conformant paper {paper.paper_id} must be verified')

    def test_verified_plus_unverified_equals_total(self) -> None:
        """Every paper is either verified (conformant/partial/non_conformant) or unverified."""
        verified = len(get_conformant_papers()) + len(get_partial_papers()) + len(get_non_conformant_papers())
        unverified = len(get_unverified_papers())
        self.assertEqual(verified + unverified, len(LITERATURE_MATRIX))

    def test_unverified_papers_have_verified_false(self) -> None:
        """Unverified papers must have verified=False."""
        unverified = get_unverified_papers()
        for paper in unverified:
            self.assertFalse(paper.verified)
            self.assertEqual(paper.conformance_status, 'unverified')

    def test_swiss_reference_is_verified_and_non_conformant(self) -> None:
        """The Swiss RAvaFcast reference is verified and non-conformant."""
        non_conformant = get_non_conformant_papers()
        swiss = [p for p in non_conformant if 'perezguillén' in p.paper_id.lower()]
        self.assertGreater(len(swiss), 0, 'Swiss reference paper should be non-conformant')
        self.assertTrue(swiss[0].verified, 'Swiss reference must be verified')
        self.assertIn('4-level', swiss[0].danger_scale)

    def test_Partner_bulletin_is_verified_and_conformant(self) -> None:
        """The Partner operational bulletin is verified and conformant."""
        conformant = get_conformant_papers()
        bulletin = [p for p in conformant if 'bulletin' in p.paper_id.lower()]
        self.assertGreater(len(bulletin), 0, 'Partner bulletin paper should be conformant')
        self.assertTrue(bulletin[0].verified, 'Partner bulletin must be verified')
        self.assertIn('5-level', bulletin[0].danger_scale)

    def test_g9_unverified_entries_have_asserted_unverified_status(self) -> None:
        """G9: Unverified entries must have verification_status='asserted_unverified'."""
        unverified = get_unverified_papers()
        for paper in unverified:
            self.assertEqual(paper.verification_status, 'asserted_unverified',
                             f'{paper.paper_id} must have verification_status="asserted_unverified"')

    def test_g9_verified_entries_have_verified_status(self) -> None:
        """G9: Verified entries must have verification_status='verified'."""
        from backend.common.Partner_literature_matrix import LITERATURE_MATRIX
        for paper in LITERATURE_MATRIX:
            if paper.verified:
                self.assertEqual(paper.verification_status, 'verified',
                                 f'{paper.paper_id} must have verification_status="verified"')

    def test_g9_source_type_distinction(self) -> None:
        """G9: source_type must distinguish papers, datasets, and operational docs."""
        from backend.common.Partner_literature_matrix import LITERATURE_MATRIX
        source_types = {p.source_type for p in LITERATURE_MATRIX}
        self.assertIn('paper', source_types)
        self.assertIn('operational', source_types)
        self.assertIn('dataset', source_types)

    def test_g9_Partner_bulletin_is_operational_source(self) -> None:
        """G9: Partner bulletin must be classified as 'operational', not 'paper'."""
        from backend.common.Partner_literature_matrix import LITERATURE_MATRIX
        bulletin = [p for p in LITERATURE_MATRIX if 'bulletin' in p.paper_id.lower()]
        self.assertEqual(bulletin[0].source_type, 'operational')

    def test_g9_swiss_entry_is_dataset_source(self) -> None:
        """G9: Swiss EnviDat entry must be classified as 'dataset', not 'paper'."""
        from backend.common.Partner_literature_matrix import LITERATURE_MATRIX
        swiss = [p for p in LITERATURE_MATRIX if 'perezguillén' in p.paper_id.lower()]
        self.assertEqual(swiss[0].source_type, 'dataset')

    def test_source_binding_is_separate_from_bibliographic_verification(self) -> None:
        """A verified identity without verified bytes cannot drive a decision."""
        for entry in LITERATURE_MATRIX:
            if entry.source_binding_status != 'content_verified':
                self.assertFalse(entry.decision_usable)

    def test_operational_entry_has_explicit_fixture_binding(self) -> None:
        bulletin = [p for p in LITERATURE_MATRIX if p.paper_id == 'Partner_bulletin_2024'][0]
        self.assertTrue(bulletin.source_url)
        self.assertEqual(len(bulletin.source_hash or ''), 64)
        self.assertEqual(bulletin.source_binding_status, 'fixture_only')


class TestMatrixSummary(unittest.TestCase):
    """P8: Matrix summary for the Partner decision packet."""

    def test_summary_has_counts(self) -> None:
        summary = build_matrix_summary()
        self.assertEqual(summary['total_papers'], len(LITERATURE_MATRIX))
        # Verified + unverified = total
        self.assertEqual(
            summary['verified_count'] + summary['unverified_count'],
            summary['total_papers'],
        )
        # Conformant + partial + non_conformant = verified (NOT total)
        self.assertEqual(
            summary['conformant_count'] + summary['partial_count'] + summary['non_conformant_count'],
            summary['verified_count'],
        )

    def test_summary_has_unverified_count(self) -> None:
        """Summary must report unverified entries separately."""
        summary = build_matrix_summary()
        self.assertIn('unverified_count', summary)
        self.assertIn('unverified_papers', summary)
        self.assertGreater(summary['unverified_count'], 0,
                           'Should have unverified entries (fabricated entries were stripped)')
        self.assertIn('decision_eligible_count', summary)
        self.assertEqual(summary['decision_eligible_count'], 0)

    def test_summary_has_key_finding(self) -> None:
        summary = build_matrix_summary()
        self.assertIn('key_finding', summary)
        self.assertIn('5-level', summary['key_finding'])
        # Must mention unverified entries
        self.assertIn('unverified', summary['key_finding'].lower())

    def test_summary_has_danger_scales(self) -> None:
        summary = build_matrix_summary()
        self.assertIsInstance(summary['danger_scales_observed'], list)
        self.assertGreater(len(summary['danger_scales_observed']), 0)

    def test_summary_has_geographies(self) -> None:
        summary = build_matrix_summary()
        self.assertIsInstance(summary['geographies_covered'], list)
        self.assertGreater(len(summary['geographies_covered']), 0)

    def test_summary_has_input_types(self) -> None:
        summary = build_matrix_summary()
        self.assertIsInstance(summary['input_types_observed'], list)
        self.assertGreater(len(summary['input_types_observed']), 0)

    def test_summary_has_entries(self) -> None:
        summary = build_matrix_summary()
        self.assertEqual(len(summary['entries']), len(LITERATURE_MATRIX))


class TestSaveLoadSummary(unittest.TestCase):
    """P8: Summary persistence."""

    def test_save_and_load(self) -> None:
        summary = build_matrix_summary()
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = Path(f.name)
        try:
            save_matrix_summary(summary, path)
            loaded = load_matrix_summary(path)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded['total_papers'], len(LITERATURE_MATRIX))
        finally:
            path.unlink()

    def test_non_object_json_returns_structured_blocker(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as handle:
            path = Path(handle.name)
        try:
            path.write_text('[]', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, r'^E030_malformed_evidence:'):
                load_matrix_summary(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
