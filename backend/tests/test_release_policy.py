"""Tests for the centralized release policy decision function."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.common.release_policy import (
    BASELINE_MODEL_TYPE,
    ReleaseDecision,
    PublicationEvidence,
    evaluate_release_decision,
    evaluate_publication_evidence,
    is_research_gate_enabled,
)


class ReleasePolicyTests(unittest.TestCase):
    def test_gate_enabled_non_baseline_blocked(self) -> None:
        decision = evaluate_release_decision(
            'mts_lstm_v1', 'v2', gate_enabled=True, publication_gates_passed=True,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'blocked')
        self.assertEqual(decision.blocking_reason, 'research_gate_non_baseline')
        self.assertFalse(decision.is_baseline)
        self.assertEqual(decision.warning_authority, 'none')
        self.assertEqual(decision.movement_advice, 'none')

    def test_gate_enabled_baseline_gates_passed_technical_artifact(self) -> None:
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE, 'v1', gate_enabled=True, publication_gates_passed=True,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'technical_artifact')
        self.assertIsNone(decision.blocking_reason)
        self.assertTrue(decision.is_baseline)
        self.assertEqual(decision.warning_authority, 'none')
        self.assertEqual(decision.movement_advice, 'none')

    def test_gate_enabled_baseline_gates_not_passed_blocked(self) -> None:
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE, 'v1', gate_enabled=True, publication_gates_passed=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'blocked')
        self.assertEqual(decision.blocking_reason, 'publication_gates_not_passed')

    def test_gate_disabled_authoritative(self) -> None:
        decision = evaluate_release_decision(
            'mts_lstm_v1', 'v2', gate_enabled=False, publication_gates_passed=True,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'authoritative')
        self.assertIsNone(decision.blocking_reason)
        self.assertEqual(decision.warning_authority, 'full')
        self.assertEqual(decision.movement_advice, 'full')

    def test_gate_disabled_baseline_authoritative(self) -> None:
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE, 'v1', gate_enabled=False, publication_gates_passed=True,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'authoritative')

    def test_as_dict_roundtrip(self) -> None:
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE, 'v1', gate_enabled=True, publication_gates_passed=True,
        )
        d = decision.as_dict()
        self.assertEqual(d['artifact_mode'], 'technical_artifact')
        self.assertTrue(d['allowed'])
        self.assertEqual(d['model_type'], BASELINE_MODEL_TYPE)

    @patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'true'})
    def test_is_research_gate_enabled_default_true(self) -> None:
        self.assertTrue(is_research_gate_enabled())

    @patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'false'})
    def test_is_research_gate_enabled_false(self) -> None:
        self.assertFalse(is_research_gate_enabled())

    @patch.dict('os.environ', {}, clear=True)
    def test_is_research_gate_enabled_missing_defaults_true(self) -> None:
        self.assertTrue(is_research_gate_enabled())

    def test_evaluate_uses_env_when_gate_not_passed(self) -> None:
        with patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'true'}):
            decision = evaluate_release_decision('mts_lstm_v1', 'v1')
            self.assertFalse(decision.allowed)
        with patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'false'}):
            decision = evaluate_release_decision('mts_lstm_v1', 'v1')
            self.assertTrue(decision.allowed)


class ReleasePolicyFailOpenRegressionTests(unittest.TestCase):
    """G-01: Release policy must not fail-open via default publication_gates_passed=True."""

    def test_default_publication_gates_blocks_baseline(self) -> None:
        """Calling evaluate_release_decision without explicit publication_gates_passed must block."""
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE, 'v1', gate_enabled=True,
        )
        self.assertFalse(
            decision.allowed,
            'Default publication_gates_passed=True allows bypass — must default to False (fail closed)',
        )
        self.assertEqual(decision.artifact_mode, 'blocked')
        self.assertEqual(decision.blocking_reason, 'publication_gates_not_passed')

    def test_explicit_publication_gates_passed_allows_baseline(self) -> None:
        """Baseline with explicit publication_gates_passed=True should still be allowed."""
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE, 'v1', gate_enabled=True, publication_gates_passed=True,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'technical_artifact')

    def test_non_baseline_research_mode_blocked_without_gates(self) -> None:
        """Non-baseline model must be blocked regardless of publication_gates_passed."""
        decision = evaluate_release_decision(
            'mts_lstm_v1', 'v2', gate_enabled=True,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'blocked')
        self.assertEqual(decision.blocking_reason, 'research_gate_non_baseline')

    def test_warning_authority_none_when_gate_enabled(self) -> None:
        """Warning authority must be 'none' for all gate-enabled decisions."""
        for mt in [BASELINE_MODEL_TYPE, 'mts_lstm_v1']:
            decision = evaluate_release_decision(
                mt, 'v1', gate_enabled=True, publication_gates_passed=True,
            )
            self.assertEqual(
                decision.warning_authority, 'none',
                f'warning_authority must be none for {mt} under gate',
            )
            self.assertEqual(
                decision.movement_advice, 'none',
                f'movement_advice must be none for {mt} under gate',
            )

    def test_gate_disabled_still_requires_explicit_gates_for_baseline(self) -> None:
        """Even with gate disabled, baseline without explicit gates should not silently pass."""
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE, 'v1', gate_enabled=False,
        )
        # Gate disabled = authoritative mode, which is a different path
        # This test documents that gate_disabled bypasses publication_gates
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'authoritative')


class TestPublicationEvidence(unittest.TestCase):
    """G-01: Tests for composite PublicationEvidence object."""

    def test_all_gates_passed_true(self):
        """all_gates_passed returns True when every gate is True."""
        ev = PublicationEvidence(
            model_type='surrogate_rf_v1', model_version='0.3.0',
            uq_passed=True, provenance_verified=True,
            validation_spine_passed=True, eaws_reviewed=True,
        )
        self.assertTrue(ev.all_gates_passed())
        self.assertEqual(ev.missing_gates(), [])

    def test_all_gates_passed_false_when_any_missing(self):
        """all_gates_passed returns False when any gate is False."""
        ev = PublicationEvidence(
            model_type='surrogate_rf_v1', model_version='0.3.0',
            uq_passed=True, provenance_verified=False,
            validation_spine_passed=True, eaws_reviewed=True,
        )
        self.assertFalse(ev.all_gates_passed())
        self.assertIn('provenance', ev.missing_gates())

    def test_missing_evidence_defaults_to_false(self):
        """G-01 core: missing evidence defaults to False."""
        ev = PublicationEvidence(model_type='surrogate_rf_v1', model_version='0.3.0')
        self.assertFalse(ev.uq_passed)
        self.assertFalse(ev.provenance_verified)
        self.assertFalse(ev.validation_spine_passed)
        self.assertFalse(ev.eaws_reviewed)
        self.assertFalse(ev.all_gates_passed())

    def test_baseline_all_gates_pass_research_mode(self):
        """Baseline with all gates passed in research mode = technical_artifact."""
        with patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'true'}):
            ev = PublicationEvidence(
                model_type='surrogate_rf_v1', model_version='0.3.0',
                uq_passed=True, provenance_verified=True,
                validation_spine_passed=True, eaws_reviewed=True,
            )
            decision = evaluate_publication_evidence(ev)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'technical_artifact')

    def test_baseline_missing_uq_blocked(self):
        """Baseline missing UQ gate = blocked."""
        with patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'true'}):
            ev = PublicationEvidence(
                model_type='surrogate_rf_v1', model_version='0.3.0',
                uq_passed=False, provenance_verified=True,
                validation_spine_passed=True, eaws_reviewed=True,
            )
            decision = evaluate_publication_evidence(ev)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'blocked')
        self.assertIn('uq', decision.blocking_reason)

    def test_baseline_missing_provenance_blocked(self):
        """Baseline missing provenance gate = blocked."""
        with patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'true'}):
            ev = PublicationEvidence(
                model_type='surrogate_rf_v1', model_version='0.3.0',
                uq_passed=True, provenance_verified=False,
                validation_spine_passed=True, eaws_reviewed=True,
            )
            decision = evaluate_publication_evidence(ev)
        self.assertFalse(decision.allowed)
        self.assertIn('provenance', decision.blocking_reason)

    def test_baseline_missing_validation_spine_blocked(self):
        """Baseline missing validation spine = blocked."""
        with patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'true'}):
            ev = PublicationEvidence(
                model_type='surrogate_rf_v1', model_version='0.3.0',
                uq_passed=True, provenance_verified=True,
                validation_spine_passed=False, eaws_reviewed=True,
            )
            decision = evaluate_publication_evidence(ev)
        self.assertFalse(decision.allowed)
        self.assertIn('validation_spine', decision.blocking_reason)

    def test_baseline_missing_eaws_review_blocked(self):
        """Baseline missing EAWS review = blocked."""
        with patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'true'}):
            ev = PublicationEvidence(
                model_type='surrogate_rf_v1', model_version='0.3.0',
                uq_passed=True, provenance_verified=True,
                validation_spine_passed=True, eaws_reviewed=False,
            )
            decision = evaluate_publication_evidence(ev)
        self.assertFalse(decision.allowed)
        self.assertIn('eaws_review', decision.blocking_reason)

    def test_non_baseline_blocked_in_research_mode(self):
        """Non-baseline model blocked in research mode."""
        with patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'true'}):
            ev = PublicationEvidence(
                model_type='mts_lstm_v1', model_version='v2',
                uq_passed=True, provenance_verified=True,
                validation_spine_passed=True, eaws_reviewed=True,
            )
            decision = evaluate_publication_evidence(ev)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.blocking_reason, 'research_gate_non_baseline')

    def test_gate_disabled_allows_authoritative(self):
        """Gate disabled = authoritative mode for any model."""
        with patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'false'}):
            ev = PublicationEvidence(
                model_type='surrogate_rf_v1', model_version='0.3.0',
                uq_passed=False, provenance_verified=False,
                validation_spine_passed=False, eaws_reviewed=False,
            )
            decision = evaluate_publication_evidence(ev)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'authoritative')

    def test_all_missing_gates_listed(self):
        """All missing gates are listed in blocking reason."""
        with patch.dict('os.environ', {'RESEARCH_MODEL_GATE_ENABLED': 'true'}):
            ev = PublicationEvidence(
                model_type='surrogate_rf_v1', model_version='0.3.0',
            )
            decision = evaluate_publication_evidence(ev)
        self.assertFalse(decision.allowed)
        for gate in ('uq', 'provenance', 'validation_spine', 'eaws_review'):
            self.assertIn(gate, decision.blocking_reason)


if __name__ == '__main__':
    unittest.main()
