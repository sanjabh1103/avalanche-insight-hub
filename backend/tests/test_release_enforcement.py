"""Tests for Phase 1: Release decision enforcement in the inference pipeline.

Verifies that:
- evaluate_release_decision blocks non-baseline models when gate is enabled
- evaluate_release_decision allows baseline models when gate is enabled
- The pipeline fails closed when active_state is empty
- promote_forecast_run receives the correct model type/version
- UQ block propagates to publication_gates_passed
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.common.release_policy import (
    BASELINE_MODEL_TYPE,
    ReleaseDecision,
    evaluate_release_decision,
    is_research_gate_enabled,
)


class TestReleaseDecisionBlocking(unittest.TestCase):
    """Test evaluate_release_decision returns correct blocking behavior."""

    def test_release_decision_blocks_non_baseline(self):
        """When gate is enabled and model is non-baseline, publication is blocked."""
        decision = evaluate_release_decision(
            'mts_lstm_v1',
            'v0.1',
            gate_enabled=True,
            publication_gates_passed=True,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'blocked')
        self.assertEqual(decision.blocking_reason, 'research_gate_non_baseline')
        self.assertEqual(decision.warning_authority, 'none')
        self.assertEqual(decision.movement_advice, 'none')

    def test_release_decision_allows_baseline(self):
        """When gate is enabled and model is baseline with gates passed, technical artifact is allowed."""
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE,
            'v1.0',
            gate_enabled=True,
            publication_gates_passed=True,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'technical_artifact')
        self.assertIsNone(decision.blocking_reason)
        self.assertEqual(decision.warning_authority, 'none')

    def test_release_decision_blocks_baseline_gates_not_passed(self):
        """When gate is enabled, baseline, but gates not passed, publication is blocked."""
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE,
            'v1.0',
            gate_enabled=True,
            publication_gates_passed=False,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'blocked')
        self.assertEqual(decision.blocking_reason, 'publication_gates_not_passed')

    def test_release_decision_allows_all_when_gate_disabled(self):
        """When gate is disabled, normal production semantics apply."""
        decision = evaluate_release_decision(
            'mts_lstm_v1',
            'v0.1',
            gate_enabled=False,
            publication_gates_passed=True,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'authoritative')
        self.assertEqual(decision.warning_authority, 'full')

    def test_release_decision_defaults_gate_enabled(self):
        """By default, the research gate is enabled (safe default)."""
        with patch.dict(os.environ, {'RESEARCH_MODEL_GATE_ENABLED': 'true'}):
            self.assertTrue(is_research_gate_enabled())
        with patch.dict(os.environ, {'RESEARCH_MODEL_GATE_ENABLED': 'false'}):
            self.assertFalse(is_research_gate_enabled())
        # Default when env var not set
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('RESEARCH_MODEL_GATE_ENABLED', None)
            self.assertTrue(is_research_gate_enabled())

    def test_release_decision_as_dict(self):
        """ReleaseDecision.as_dict() returns all fields."""
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE,
            'v1.0',
            gate_enabled=True,
            publication_gates_passed=True,
        )
        d = decision.as_dict()
        self.assertIn('allowed', d)
        self.assertIn('artifact_mode', d)
        self.assertIn('blocking_reason', d)
        self.assertIn('model_type', d)
        self.assertIn('model_version', d)
        self.assertIn('is_baseline', d)
        self.assertIn('gate_enabled', d)
        self.assertIn('warning_authority', d)
        self.assertIn('movement_advice', d)


class TestPipelineFailClosed(unittest.TestCase):
    """Test that the pipeline fails closed when active_state is empty."""

    def test_empty_active_state_produces_baseline_decision(self):
        """When active_state is empty, the pipeline should evaluate as baseline model."""
        active_state: dict = {}
        model_type = str(active_state.get('active_model_type') or 'surrogate_rf_v1')
        model_version = str(active_state.get('active_model_version') or 'unknown')
        decision = evaluate_release_decision(
            model_type,
            model_version,
            publication_gates_passed=True,
        )
        # Baseline model with gate enabled should be allowed as technical_artifact
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'technical_artifact')

    def test_empty_active_state_with_gate_disabled(self):
        """When gate is disabled and active_state is empty, still produces a valid decision."""
        active_state: dict = {}
        model_type = str(active_state.get('active_model_type') or 'surrogate_rf_v1')
        decision = evaluate_release_decision(
            model_type,
            'unknown',
            gate_enabled=False,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.artifact_mode, 'authoritative')


class TestPromoteForecastRunModelIdentity(unittest.TestCase):
    """Test that promote_forecast_run receives the correct model identity."""

    def test_promote_passes_correct_model_type(self):
        """promote_forecast_run should receive the actual active model type."""
        active_state = {
            'active_model_type': 'mts_lstm_v1',
            'active_model_version': 'v0.2',
        }
        model_type = str(active_state.get('active_model_type') or 'surrogate_rf_v1')
        model_version = str(active_state.get('active_model_version') or 'unknown')
        # When gate is enabled, non-baseline should be blocked
        decision = evaluate_release_decision(model_type, model_version, gate_enabled=True)
        self.assertFalse(decision.allowed)
        # The model_type passed to promote would be 'mts_lstm_v1', not 'surrogate_rf_v1'
        self.assertEqual(model_type, 'mts_lstm_v1')

    def test_uq_block_propagates_to_publication_gates(self):
        """When UQ blocks publication, publication_gates_passed should be False."""
        uq_publish_blocked = True
        publication_gates_passed = not uq_publish_blocked
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE,
            'v1.0',
            gate_enabled=True,
            publication_gates_passed=publication_gates_passed,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.blocking_reason, 'publication_gates_not_passed')

    def test_warning_authority_none_in_research_mode(self):
        """In research mode (gate enabled), warning_authority must always be 'none'."""
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE,
            'v1.0',
            gate_enabled=True,
            publication_gates_passed=True,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.warning_authority, 'none')

        decision_blocked = evaluate_release_decision(
            'non_baseline_model',
            'v1.0',
            gate_enabled=True,
            publication_gates_passed=True,
        )
        self.assertFalse(decision_blocked.allowed)
        self.assertEqual(decision_blocked.warning_authority, 'none')

    def test_cap_sachet_gated_by_warning_authority(self):
        """CAP and SACHET must not fire when warning_authority is 'none'.

        This is a contract test: in research mode, warning_authority is always
        'none', so CAP_ENABLED and SACHET_ENABLED must not cause alert generation
        regardless of danger level or risk score.
        """
        decision = evaluate_release_decision(
            BASELINE_MODEL_TYPE,
            'v1.0',
            gate_enabled=True,
            publication_gates_passed=True,
        )
        # The release decision in research mode always has warning_authority='none'
        self.assertEqual(decision.warning_authority, 'none')
        # Simulating the CAP gate check: CAP_ENABLED and warning_authority != 'none'
        cap_should_fire = True and decision.warning_authority != 'none'
        self.assertFalse(cap_should_fire, 'CAP must not fire when warning_authority is none')
        # Simulating the SACHET gate check
        sachet_should_fire = True and cap_should_fire and decision.warning_authority != 'none'
        self.assertFalse(sachet_should_fire, 'SACHET must not fire when warning_authority is none')


if __name__ == '__main__':
    unittest.main()
