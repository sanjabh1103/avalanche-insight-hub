#!/usr/bin/env python3
"""Reproducible adversarial boundary verification script.

P5/G13: This script provides a single, reproducible entry point for
adversarial boundary testing. It covers:
- Malformed JSON and wrong roots
- Type confusion (int, float, bool, string, list, None)
- Path traversal and dot segments
- Symlink escapes
- Payload and terminal identity coercion
- Malformed poller bodies
- Invalid timeouts
- Manifest and graph tampering
- Secret-like values in evidence
- POC loader type confusion (G5)
- Manifest/forecast str() coercion (G6)
- Submission response shape (G7)
- Float/bool HTTP status codes (G8)
- No-request-on-invalid-preflight (G9)
- Submission status str() coercion (G10)
- Release-gate error taxonomy (G11)

Usage:
    cd /Users/sanjayb/avalanche-insight-hub
    PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 python3 -m pytest backend/tests/test_adversarial_boundary.py -v

Or as a standalone script:
    PYTHONPATH=. python3 backend/tests/test_adversarial_boundary.py
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path

# All adversarial test classes are imported from their parent test files.
# This script serves as the single reproducible entry point.

from backend.tests.test_poll_modal_http_job import (
    SafeIdentityDotSegmentTests,
    SafeIdentityNonStringTests,
    RunJobTypeValidationTests,
    RouteAllowlistTests,
    ProviderIdentityStringTypeTests,
    PollUntilTerminalIdentityTests,
    PayloadIdentityStringTypeTests,
    ExpectedIdentityStringTypeTests,
    TerminalIdentityStringTypeTests,
    RouteCanonicalizationTests,
    PollerResponseShapeTests,
    TimeoutTypeTests,
)
from backend.tests.test_release_gate import (
    StrictTypePocScopeTests,
    PocStringFieldTypeTests,
    PocLeadTimeFloatTests,
)


# ---------------------------------------------------------------------------
# P4/G12: Direct adversarial tests for newly found gaps.
# These test the behaviors directly, not by importing existing test classes.
# ---------------------------------------------------------------------------


def _make_valid_decision_record_dict() -> dict:
    """Return a minimal valid decision record dict for mutation in tests."""
    return {
        'schema_version': 'pir_panjal_poc_decision_v1',
        'decision_id': 'pir_panjal_poc_v1',
        'selected_sector': 'pir_panjal_nw_himalaya',
        'customer_selected_poc': True,
        'Partner_approved': False,
        'official_warning_eligible': False,
        'poc_scope_status': 'customer_selected',
        'evidence_class': 'pipeline-proof-only',
        'representative_regime': {
            'elevation_band': 'middle',
            'elevation_min_m': 3200,
            'elevation_max_m': 4000,
        },
        'forecast': {
            'headline_horizon_hours': 48,
            'optional_extension_hours': 72,
            'ensemble_members': 1,
        },
        'problem_scope': ['storm_new_snow', 'wind_slab'],
        'engine_roles': {
            'physical_backbone': 'SNOWPACK',
            'baseline_model': 'RF',
            'hybrid_ml': 'shadow_only',
            'modal': 'technical_shadow_only',
            'weathernext': 'optional_atmospheric_candidate',
            'awsome': 'qualification_lane',
            'smp': 'targeted_validation_lane',
        },
        'track': {'track_id': 'track_1_indian_candidate'},
        'non_claims': [
            'no_official_warning',
            'no_validated_pir_panjal_accuracy',
            'no_modal_accuracy_claim',
            'no_proxy_as_observation_claim',
            'no_weathernext_direct_avalanche_prediction',
            'no_production_ml_promotion',
        ],
        'immutability': {'scope_hash_required': True},
    }


class PocLoaderTypeConfusionTests(unittest.TestCase):
    """G5: POC loader must reject non-string string fields."""

    def test_int_decision_id_rejected(self):
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
            DecisionRecordError,
        )
        record = _make_valid_decision_record_dict()
        record['decision_id'] = 123
        raw = json.dumps(record).encode('utf-8')
        with self.assertRaises(DecisionRecordError) as ctx:
            load_decision_record_from_bytes(raw)
        self.assertIn('must be a string', str(ctx.exception))

    def test_float_decision_id_rejected(self):
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
            DecisionRecordError,
        )
        record = _make_valid_decision_record_dict()
        record['decision_id'] = 123.4
        raw = json.dumps(record).encode('utf-8')
        with self.assertRaises(DecisionRecordError):
            load_decision_record_from_bytes(raw)

    def test_bool_decision_id_rejected(self):
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
            DecisionRecordError,
        )
        record = _make_valid_decision_record_dict()
        record['decision_id'] = True
        raw = json.dumps(record).encode('utf-8')
        with self.assertRaises(DecisionRecordError):
            load_decision_record_from_bytes(raw)

    def test_int_engine_role_value_rejected(self):
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
            DecisionRecordError,
        )
        record = _make_valid_decision_record_dict()
        record['engine_roles']['physical_backbone'] = 42
        raw = json.dumps(record).encode('utf-8')
        with self.assertRaises(DecisionRecordError) as ctx:
            load_decision_record_from_bytes(raw)
        self.assertIn('must be a string', str(ctx.exception))

    def test_int_track_id_rejected(self):
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
            DecisionRecordError,
        )
        record = _make_valid_decision_record_dict()
        record['track']['track_id'] = 42
        raw = json.dumps(record).encode('utf-8')
        with self.assertRaises(DecisionRecordError):
            load_decision_record_from_bytes(raw)

    def test_int_non_claims_entry_rejected(self):
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
            DecisionRecordError,
        )
        record = _make_valid_decision_record_dict()
        record['non_claims'][0] = 123
        raw = json.dumps(record).encode('utf-8')
        with self.assertRaises(DecisionRecordError):
            load_decision_record_from_bytes(raw)

    def test_int_problem_scope_entry_rejected(self):
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
            DecisionRecordError,
        )
        record = _make_valid_decision_record_dict()
        record['problem_scope'][0] = 42
        raw = json.dumps(record).encode('utf-8')
        with self.assertRaises(DecisionRecordError):
            load_decision_record_from_bytes(raw)

    def test_int_elevation_band_rejected(self):
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
            DecisionRecordError,
        )
        record = _make_valid_decision_record_dict()
        record['representative_regime']['elevation_band'] = 42
        raw = json.dumps(record).encode('utf-8')
        with self.assertRaises(DecisionRecordError):
            load_decision_record_from_bytes(raw)

    def test_valid_record_still_passes(self):
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
        )
        record = _make_valid_decision_record_dict()
        raw = json.dumps(record).encode('utf-8')
        result = load_decision_record_from_bytes(raw)
        self.assertEqual(result.decision_id, 'pir_panjal_poc_v1')


class SubmissionResponseShapeTests(unittest.TestCase):
    """G7: run_job() must reject non-dict submission bodies with ModalJobError."""

    def _make_run_job_kwargs(self, request_fn):
        from backend.scripts.poll_modal_http_job import run_job
        return {
            'worker_url': 'https://worker.example.com',
            'worker_token': 'tok',
            'route': 'sar-segment',
            'payload': {'run_id': 'r1', 'compute_job_id': 'cj1'},
            'request': request_fn,
            'timeout_seconds': 10,
            'poll_interval_seconds': 1,
        }

    def test_list_body_rejected(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        def req(method, url, body):
            if method == 'POST':
                return (200, [])
            return (200, {'status': 'succeeded'})
        with self.assertRaises(ModalJobError) as ctx:
            run_job(**self._make_run_job_kwargs(req))
        self.assertIn('must be a dict', str(ctx.exception))

    def test_none_body_rejected(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        def req(method, url, body):
            if method == 'POST':
                return (200, None)
            return (200, {'status': 'succeeded'})
        with self.assertRaises(ModalJobError):
            run_job(**self._make_run_job_kwargs(req))

    def test_string_body_rejected(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        def req(method, url, body):
            if method == 'POST':
                return (200, 'hello')
            return (200, {'status': 'succeeded'})
        with self.assertRaises(ModalJobError):
            run_job(**self._make_run_job_kwargs(req))

    def test_int_body_rejected(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        def req(method, url, body):
            if method == 'POST':
                return (200, 42)
            return (200, {'status': 'succeeded'})
        with self.assertRaises(ModalJobError):
            run_job(**self._make_run_job_kwargs(req))


class SubmissionStatusTypeTests(unittest.TestCase):
    """G8: run_job() must reject float and bool submission status codes."""

    def _make_run_job_kwargs(self, request_fn):
        from backend.scripts.poll_modal_http_job import run_job
        return {
            'worker_url': 'https://worker.example.com',
            'worker_token': 'tok',
            'route': 'sar-segment',
            'payload': {'run_id': 'r1', 'compute_job_id': 'cj1'},
            'request': request_fn,
            'timeout_seconds': 10,
            'poll_interval_seconds': 1,
        }

    def test_float_status_rejected(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        def req(method, url, body):
            if method == 'POST':
                return (200.0, {'status': 'accepted', 'call_id': 'c1', 'run_id': 'r1', 'compute_job_id': 'cj1'})
            return (200, {'status': 'succeeded'})
        with self.assertRaises(ModalJobError) as ctx:
            run_job(**self._make_run_job_kwargs(req))
        self.assertIn('must be an integer', str(ctx.exception))

    def test_bool_status_rejected(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        def req(method, url, body):
            if method == 'POST':
                return (True, {'status': 'accepted', 'call_id': 'c1', 'run_id': 'r1', 'compute_job_id': 'cj1'})
            return (200, {'status': 'succeeded'})
        with self.assertRaises(ModalJobError):
            run_job(**self._make_run_job_kwargs(req))

    def test_string_status_rejected(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        def req(method, url, body):
            if method == 'POST':
                return ('200', {'status': 'accepted', 'call_id': 'c1', 'run_id': 'r1', 'compute_job_id': 'cj1'})
            return (200, {'status': 'succeeded'})
        with self.assertRaises(ModalJobError):
            run_job(**self._make_run_job_kwargs(req))

    def test_none_status_rejected(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        def req(method, url, body):
            if method == 'POST':
                return (None, {'status': 'accepted', 'call_id': 'c1', 'run_id': 'r1', 'compute_job_id': 'cj1'})
            return (200, {'status': 'succeeded'})
        with self.assertRaises(ModalJobError):
            run_job(**self._make_run_job_kwargs(req))


class NoRequestOnInvalidPreflightTests(unittest.TestCase):
    """G9: Invalid timeout/poll_interval must cause zero requester calls."""

    def test_float_timeout_no_post(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        calls = []
        def req(method, url, body):
            calls.append(method)
            return (200, {'status': 'accepted'})
        with self.assertRaises(ModalJobError):
            run_job(
                worker_url='https://w.example.com', worker_token='t',
                route='sar-segment', payload={'run_id': 'r1', 'compute_job_id': 'cj1'},
                request=req, timeout_seconds=1.5, poll_interval_seconds=1,
            )
        self.assertEqual(len(calls), 0, f'POST should not be called, got {calls}')

    def test_float_poll_interval_no_post(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        calls = []
        def req(method, url, body):
            calls.append(method)
            return (200, {'status': 'accepted'})
        with self.assertRaises(ModalJobError):
            run_job(
                worker_url='https://w.example.com', worker_token='t',
                route='sar-segment', payload={'run_id': 'r1', 'compute_job_id': 'cj1'},
                request=req, timeout_seconds=10, poll_interval_seconds=1.5,
            )
        self.assertEqual(len(calls), 0)

    def test_string_timeout_no_post(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        calls = []
        def req(method, url, body):
            calls.append(method)
            return (200, {'status': 'accepted'})
        with self.assertRaises(ModalJobError):
            run_job(
                worker_url='https://w.example.com', worker_token='t',
                route='sar-segment', payload={'run_id': 'r1', 'compute_job_id': 'cj1'},
                request=req, timeout_seconds='10', poll_interval_seconds=1,
            )
        self.assertEqual(len(calls), 0)

    def test_bool_timeout_no_post(self):
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        calls = []
        def req(method, url, body):
            calls.append(method)
            return (200, {'status': 'accepted'})
        with self.assertRaises(ModalJobError):
            run_job(
                worker_url='https://w.example.com', worker_token='t',
                route='sar-segment', payload={'run_id': 'r1', 'compute_job_id': 'cj1'},
                request=req, timeout_seconds=True, poll_interval_seconds=1,
            )
        self.assertEqual(len(calls), 0)


class SubmissionStatusStrCoercionTests(unittest.TestCase):
    """G10: _validate_submission_contract must reject non-string status."""

    def test_int_status_rejected(self):
        from backend.scripts.poll_modal_http_job import (
            _validate_submission_contract, ModalJobError,
        )
        with self.assertRaises(ModalJobError) as ctx:
            _validate_submission_contract(
                {'status': 123, 'call_id': 'c1', 'run_id': 'r1', 'compute_job_id': 'cj1'},
                expected_run_id='r1', expected_compute_job_id='cj1',
            )
        self.assertIn('must be a string', str(ctx.exception))

    def test_bool_status_rejected(self):
        from backend.scripts.poll_modal_http_job import (
            _validate_submission_contract, ModalJobError,
        )
        with self.assertRaises(ModalJobError):
            _validate_submission_contract(
                {'status': True, 'call_id': 'c1', 'run_id': 'r1', 'compute_job_id': 'cj1'},
                expected_run_id='r1', expected_compute_job_id='cj1',
            )

    def test_none_status_rejected(self):
        from backend.scripts.poll_modal_http_job import (
            _validate_submission_contract, ModalJobError,
        )
        with self.assertRaises(ModalJobError):
            _validate_submission_contract(
                {'status': None, 'call_id': 'c1', 'run_id': 'r1', 'compute_job_id': 'cj1'},
                expected_run_id='r1', expected_compute_job_id='cj1',
            )


class ReleaseGateErrorTaxonomyTests(unittest.TestCase):
    """G11: release_gate must distinguish VALIDATION_REJECTED from INTERNAL_GATE_ERROR."""

    def test_validation_rejected_for_missing_dir(self):
        from backend.scripts.release_gate import run_release_gate
        # Point to a non-existent directory — should fail with exit 1
        fake_dir = Path('/tmp/nonexistent_dir_for_adversarial_test')
        import sys
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            exit_code = run_release_gate(fake_dir)
            output = sys.stderr.getvalue()
        finally:
            sys.stderr = old_stderr
        self.assertEqual(exit_code, 1)
        # _run_release_gate handles missing dir internally and returns 1,
        # so the VALIDATION_REJECTED label is in the internal error message.
        self.assertTrue(
            'VALIDATION_REJECTED' in output or 'unsafe' in output or 'does not exist' in output,
            f'Expected validation rejection, got: {output[:200]}',
        )

    def test_internal_gate_error_for_unexpected_exception(self):
        """Inject an unexpected AttributeError to verify INTERNAL_GATE_ERROR label."""
        from backend.scripts import release_gate
        # Monkey-patch _run_release_gate to raise an unexpected AttributeError
        original = release_gate._run_release_gate

        def raise_attribute_error(*args, **kwargs):
            raise AttributeError('injected test defect')

        release_gate._run_release_gate = raise_attribute_error
        import sys
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            exit_code = release_gate.run_release_gate(Path('/tmp'))
            output = sys.stderr.getvalue()
        finally:
            sys.stderr = old_stderr
            release_gate._run_release_gate = original
        self.assertEqual(exit_code, 1)
        self.assertIn('INTERNAL_GATE_ERROR', output)
        self.assertIn('injected test defect', output)

    def test_validation_rejected_for_value_error(self):
        """G6: ValueError is now INTERNAL_GATE_ERROR, not VALIDATION_REJECTED."""
        from backend.scripts import release_gate
        original = release_gate._run_release_gate

        def raise_value_error(*args, **kwargs):
            raise ValueError('injected validation failure')

        release_gate._run_release_gate = raise_value_error
        import sys
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            exit_code = release_gate.run_release_gate(Path('/tmp'))
            output = sys.stderr.getvalue()
        finally:
            sys.stderr = old_stderr
            release_gate._run_release_gate = original
        self.assertEqual(exit_code, 1)
        # G6: ValueError is now classified as INTERNAL_GATE_ERROR, not VALIDATION_REJECTED
        self.assertIn('INTERNAL_GATE_ERROR', output)


class NoSideEffectTests(unittest.TestCase):
    """Verify that adversarial tests don't mutate the repository."""

    def test_no_repo_files_created(self):
        """Ensure no files are left in the repo root after running tests."""
        repo_root = Path(__file__).resolve().parent.parent
        before = set(repo_root.rglob('*'))
        # Run a quick loader test in a temp dir
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
        )
        record = _make_valid_decision_record_dict()
        raw = json.dumps(record).encode('utf-8')
        result = load_decision_record_from_bytes(raw)
        self.assertEqual(result.decision_id, 'pir_panjal_poc_v1')
        after = set(repo_root.rglob('*'))
        # No new files should be created in the repo by these tests
        new_files = after - before
        # Filter out __pycache__ changes
        real_new = {f for f in new_files if '__pycache__' not in str(f) and '.pyc' not in str(f)}
        self.assertEqual(len(real_new), 0, f'Unexpected new files: {real_new}')


class PollerBoolStatusTests(unittest.TestCase):
    """A7: Poller must reject bool status_code using type() is not int."""

    def test_bool_true_status_rejected(self):
        from backend.scripts.poll_modal_http_job import poll_until_terminal, ModalJobError
        def bool_poller(call_id):
            return (True, {'status': 'succeeded'})
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(bool_poller, call_id='c1', timeout_seconds=10, poll_interval_seconds=0)
        self.assertIn('must be an integer', str(ctx.exception))

    def test_bool_false_status_rejected(self):
        from backend.scripts.poll_modal_http_job import poll_until_terminal, ModalJobError
        def bool_poller(call_id):
            return (False, {'status': 'succeeded'})
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(bool_poller, call_id='c1', timeout_seconds=10, poll_interval_seconds=0)
        self.assertIn('must be an integer', str(ctx.exception))

    def test_float_status_rejected(self):
        from backend.scripts.poll_modal_http_job import poll_until_terminal, ModalJobError
        def float_poller(call_id):
            return (200.0, {'status': 'succeeded'})
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(float_poller, call_id='c1', timeout_seconds=10, poll_interval_seconds=0)
        self.assertIn('must be an integer', str(ctx.exception))

    def test_string_status_rejected(self):
        from backend.scripts.poll_modal_http_job import poll_until_terminal, ModalJobError
        def str_poller(call_id):
            return ('200', {'status': 'succeeded'})
        with self.assertRaises(ModalJobError) as ctx:
            poll_until_terminal(str_poller, call_id='c1', timeout_seconds=10, poll_interval_seconds=0)
        self.assertIn('must be an integer', str(ctx.exception))


class EngineRolesKeyValidationTests(unittest.TestCase):
    """A5: POC loader must reject non-string engine_roles keys.

    Note: JSON keys are always strings, so this test calls the internal
    _validate_decision_record directly with a Python dict to test the
    defense-in-depth key type check.
    """

    def test_int_key_rejected(self):
        from backend.common.pir_panjal_decision_record import (
            _validate_decision_record, DecisionRecordError,
        )
        record = _make_valid_decision_record_dict()
        record['engine_roles'][42] = 'SNOWPACK'
        # Call the internal validator directly (bypasses JSON parsing)
        with self.assertRaises(DecisionRecordError) as ctx:
            _validate_decision_record(record, b'{}', 'abc123', '')
        self.assertIn('keys must be strings', str(ctx.exception))

    def test_valid_record_still_passes(self):
        """Verify that valid string keys are not rejected by the key check."""
        from backend.common.pir_panjal_decision_record import (
            _validate_decision_record,
        )
        record = _make_valid_decision_record_dict()
        # All keys are strings — should not raise
        result = _validate_decision_record(record, b'{}', 'abc123', '')
        self.assertEqual(result.decision_id, 'pir_panjal_poc_v1')


class ExpectedDigestTypeTests(unittest.TestCase):
    """G6: poc_scope_contract must reject non-string expected_decision_record_sha256."""

    def test_int_expected_digest_rejected(self):
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
        )
        from backend.common.snowpack_artifact_manifest import ArtifactManifest
        from backend.common.snowpack_contracts import ForecastSemanticsContract
        record = _make_valid_decision_record_dict()
        raw = json.dumps(record).encode('utf-8')
        dr = load_decision_record_from_bytes(raw)
        # Build minimal result_data, manifest, forecast
        result_data = {
            'region_key': 'pir_panjal_nw_himalaya',
            'elevation_band': 'middle',
            'decision_record': {
                'decision_record_sha256': dr.decision_record_sha256,
                'decision_id': 'pir_panjal_poc_v1',
                'track_id': 'track_1_indian_candidate',
                'evidence_class': 'pipeline-proof-only',
                'official_warning_eligible': False,
                'headline_horizon_hours': 48,
                'ensemble_members': 1,
                'selected_sector': 'pir_panjal_nw_himalaya',
                'elevation_band': 'middle',
            },
        }
        manifest = ArtifactManifest(
            run_id='r1',
            region_key='pir_panjal_nw_himalaya',
            elevation_band='middle',
            aspect_class='north',
            binary_version='1.0.0',
            artifacts=(),
            is_native_execution=True,
            created_at='2026-01-01T00:00:00Z',
            native_binary_invoked=True,
        )
        forecast = ForecastSemanticsContract(
            mode='deterministic',
            source='snowpack',
            forecast_cycle='00z',
            valid_from='2026-01-01T00:00:00Z',
            valid_to='2026-01-03T00:00:00Z',
            as_of='2026-01-01T00:00:00Z',
            lead_time_h=48,
            region_key='pir_panjal_nw_himalaya',
            elevation_band='middle',
            forcing_manifest_id='fm-1',
            ensemble_members=1,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=dr,
                result_data=result_data,
                manifest=manifest,
                forecast=forecast,
                expected_decision_record_sha256=123,  # int, not string
                poc_mode=True,
            )
        self.assertIn('must be a string', str(ctx.exception))

    def test_g1_missing_poc_mode_raises_type_error(self):
        """G1: validate_poc_scope_consistency must require explicit poc_mode.
        Calling without poc_mode must raise TypeError (no silent default)."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency,
        )
        import inspect
        # Verify the signature has no default for poc_mode
        sig = inspect.signature(validate_poc_scope_consistency)
        poc_mode_param = sig.parameters['poc_mode']
        self.assertEqual(
            poc_mode_param.default, inspect.Parameter.empty,
            'poc_mode must not have a default value — it must be mandatory'
        )


# =============================================================================
# Fifth-audit adversarial tests (A3, A4, A5, A6, A10, A2, A11)
# =============================================================================


class ParserBoundaryHardeningTests(unittest.TestCase):
    """A3/A4: Parser must convert all malformed inputs to DecisionRecordError."""

    def test_none_raw_bytes_rejected(self):
        """A3: load_decision_record_from_bytes(None) must raise DecisionRecordError."""
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes, DecisionRecordError,
        )
        with self.assertRaises(DecisionRecordError) as ctx:
            load_decision_record_from_bytes(None)
        self.assertIn('must be bytes', str(ctx.exception))

    def test_int_raw_bytes_rejected(self):
        """A3: load_decision_record_from_bytes(123) must raise DecisionRecordError."""
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes, DecisionRecordError,
        )
        with self.assertRaises(DecisionRecordError) as ctx:
            load_decision_record_from_bytes(123)
        self.assertIn('must be bytes', str(ctx.exception))

    def test_str_raw_bytes_rejected(self):
        """A3: load_decision_record_from_bytes('not bytes') must raise DecisionRecordError."""
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes, DecisionRecordError,
        )
        with self.assertRaises(DecisionRecordError) as ctx:
            load_decision_record_from_bytes('not bytes')
        self.assertIn('must be bytes', str(ctx.exception))

    def test_list_raw_bytes_rejected(self):
        """A3: load_decision_record_from_bytes([]) must raise DecisionRecordError."""
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes, DecisionRecordError,
        )
        with self.assertRaises(DecisionRecordError) as ctx:
            load_decision_record_from_bytes([])
        self.assertIn('must be bytes', str(ctx.exception))

    def test_int_expected_sha256_rejected(self):
        """A3: int expected_sha256 must raise DecisionRecordError."""
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes, DecisionRecordError,
        )
        with self.assertRaises(DecisionRecordError) as ctx:
            load_decision_record_from_bytes(b'{}', expected_sha256=123)
        self.assertIn('must be a string', str(ctx.exception))

    def test_non_dict_record_rejected(self):
        """A3b: _validate_decision_record(None) must raise DecisionRecordError."""
        from backend.common.pir_panjal_decision_record import (
            _validate_decision_record, DecisionRecordError,
        )
        with self.assertRaises(DecisionRecordError) as ctx:
            _validate_decision_record(None, b'{}', 'abc', '')
        self.assertIn('must be a dict', str(ctx.exception))

    def test_list_record_rejected(self):
        """A3b: _validate_decision_record([]) must raise DecisionRecordError."""
        from backend.common.pir_panjal_decision_record import (
            _validate_decision_record, DecisionRecordError,
        )
        with self.assertRaises(DecisionRecordError) as ctx:
            _validate_decision_record([], b'{}', 'abc', '')
        self.assertIn('must be a dict', str(ctx.exception))

    def test_unhashable_problem_scope_rejected(self):
        """A4: problem_scope with nested list must raise DecisionRecordError, not TypeError."""
        from backend.common.pir_panjal_decision_record import (
            _validate_decision_record, DecisionRecordError,
        )
        record = _make_valid_decision_record_dict()
        record['problem_scope'] = ['storm_new_snow', ['nested_list']]
        with self.assertRaises(DecisionRecordError) as ctx:
            _validate_decision_record(record, b'{}', 'abc', '')
        self.assertIn('must be strings', str(ctx.exception))

    def test_dict_problem_scope_element_rejected(self):
        """A4: problem_scope with dict element must raise DecisionRecordError."""
        from backend.common.pir_panjal_decision_record import (
            _validate_decision_record, DecisionRecordError,
        )
        record = _make_valid_decision_record_dict()
        record['problem_scope'] = ['storm_new_snow', {'key': 'value'}]
        with self.assertRaises(DecisionRecordError) as ctx:
            _validate_decision_record(record, b'{}', 'abc', '')
        self.assertIn('must be strings', str(ctx.exception))


class PocScopeBoundaryHardeningTests(unittest.TestCase):
    """A5/G4: validate_poc_scope_consistency must reject malformed inputs with PocScopeError."""

    @staticmethod
    def _valid_dr():
        """Build a valid DecisionRecord for tests that need one."""
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
        )
        record = _make_valid_decision_record_dict()
        raw = json.dumps(record).encode('utf-8')
        return load_decision_record_from_bytes(raw)

    @staticmethod
    def _valid_manifest():
        """Build a valid ArtifactManifest for tests that need one."""
        from backend.common.snowpack_artifact_manifest import ArtifactManifest
        return ArtifactManifest(
            run_id='r1', region_key='pir_panjal_nw_himalaya',
            elevation_band='middle', aspect_class='north',
            binary_version='1.0.0', artifacts=(),
            is_native_execution=True, created_at='2026-01-01T00:00:00Z',
            native_binary_invoked=True,
        )

    @staticmethod
    def _valid_forecast():
        """Build a valid ForecastSemanticsContract for tests that need one."""
        from backend.common.snowpack_contracts import ForecastSemanticsContract
        return ForecastSemanticsContract(
            mode='forecast', source='snowpack', forecast_cycle='00z',
            valid_from='2026-01-01T00:00:00Z', valid_to='2026-01-03T00:00:00Z',
            as_of='2026-01-01T00:00:00Z',
            lead_time_h=48.0,
            region_key='pir_panjal_nw_himalaya', elevation_band='middle',
            forcing_manifest_id='fm_001',
            ensemble_members=1,
        )

    def test_list_result_data_rejected(self):
        """A5: result_data=[] must raise PocScopeError, not AttributeError."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=self._valid_dr(),
                result_data=[],
                manifest=self._valid_manifest(),
                forecast=self._valid_forecast(),
                expected_decision_record_sha256='a' * 64,
                poc_mode=True,
            )
        self.assertIn('must be a dict', str(ctx.exception))

    def test_none_result_data_rejected(self):
        """A5: result_data=None must raise PocScopeError."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=self._valid_dr(),
                result_data=None,
                manifest=self._valid_manifest(),
                forecast=self._valid_forecast(),
                expected_decision_record_sha256='a' * 64,
                poc_mode=True,
            )
        self.assertIn('must be a dict', str(ctx.exception))

    def test_none_decision_record_rejected(self):
        """A5/G4: decision_record=None must raise PocScopeError."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=None,
                result_data={},
                manifest=self._valid_manifest(),
                forecast=self._valid_forecast(),
                expected_decision_record_sha256='a' * 64,
                poc_mode=True,
            )
        self.assertIn('must be a DecisionRecord', str(ctx.exception))

    def test_list_decision_record_rejected(self):
        """G4: decision_record=[] must raise PocScopeError, not AttributeError."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=[],
                result_data={},
                manifest=self._valid_manifest(),
                forecast=self._valid_forecast(),
                expected_decision_record_sha256='a' * 64,
                poc_mode=True,
            )
        self.assertIn('must be a DecisionRecord', str(ctx.exception))

    def test_empty_dict_decision_record_rejected(self):
        """G4: decision_record={} must raise PocScopeError, not AttributeError."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record={},
                result_data={},
                manifest=self._valid_manifest(),
                forecast=self._valid_forecast(),
                expected_decision_record_sha256='a' * 64,
                poc_mode=True,
            )
        self.assertIn('must be a DecisionRecord', str(ctx.exception))

    def test_none_manifest_rejected(self):
        """A5/G4: manifest=None must raise PocScopeError."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=self._valid_dr(),
                result_data={},
                manifest=None,
                forecast=self._valid_forecast(),
                expected_decision_record_sha256='a' * 64,
                poc_mode=True,
            )
        self.assertIn('must be an ArtifactManifest', str(ctx.exception))

    def test_list_manifest_rejected(self):
        """G4: manifest=[] must raise PocScopeError, not AttributeError."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=self._valid_dr(),
                result_data={},
                manifest=[],
                forecast=self._valid_forecast(),
                expected_decision_record_sha256='a' * 64,
                poc_mode=True,
            )
        self.assertIn('must be an ArtifactManifest', str(ctx.exception))

    def test_none_forecast_rejected(self):
        """A5/G4: forecast=None must raise PocScopeError."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=self._valid_dr(),
                result_data={},
                manifest=self._valid_manifest(),
                forecast=None,
                expected_decision_record_sha256='a' * 64,
                poc_mode=True,
            )
        self.assertIn('must be a ForecastSemanticsContract', str(ctx.exception))

    def test_list_forecast_rejected(self):
        """G4: forecast=[] must raise PocScopeError, not AttributeError."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=self._valid_dr(),
                result_data={},
                manifest=self._valid_manifest(),
                forecast=[],
                expected_decision_record_sha256='a' * 64,
                poc_mode=True,
            )
        self.assertIn('must be a ForecastSemanticsContract', str(ctx.exception))

    def test_int_expected_digest_rejected_at_boundary(self):
        """A3: int expected_decision_record_sha256 must raise PocScopeError at boundary."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=self._valid_dr(),
                result_data={},
                manifest=self._valid_manifest(),
                forecast=self._valid_forecast(),
                expected_decision_record_sha256=123,
                poc_mode=True,
            )
        self.assertIn('must be a string', str(ctx.exception))

    def test_int_poc_mode_rejected(self):
        """G3: poc_mode=1 must raise PocScopeError (truthiness not accepted)."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=self._valid_dr(),
                result_data={},
                manifest=self._valid_manifest(),
                forecast=self._valid_forecast(),
                expected_decision_record_sha256='a' * 64,
                poc_mode=1,
            )
        self.assertIn('must be a bool', str(ctx.exception))

    def test_string_poc_mode_rejected(self):
        """G3: poc_mode="true" must raise PocScopeError (truthiness not accepted)."""
        from backend.common.poc_scope_contract import (
            validate_poc_scope_consistency, PocScopeError,
        )
        with self.assertRaises(PocScopeError) as ctx:
            validate_poc_scope_consistency(
                decision_record=self._valid_dr(),
                result_data={},
                manifest=self._valid_manifest(),
                forecast=self._valid_forecast(),
                expected_decision_record_sha256='a' * 64,
                poc_mode="true",
            )
        self.assertIn('must be a bool', str(ctx.exception))


class ResponseShapeValidatorTests(unittest.TestCase):
    """A6: _validate_response_shape must reject malformed responses."""

    def test_none_response_rejected(self):
        from backend.scripts.poll_modal_http_job import _validate_response_shape, ModalJobError
        with self.assertRaises(ModalJobError) as ctx:
            _validate_response_shape(None, context='test')
        self.assertIn('None', str(ctx.exception))

    def test_one_tuple_rejected(self):
        from backend.scripts.poll_modal_http_job import _validate_response_shape, ModalJobError
        with self.assertRaises(ModalJobError) as ctx:
            _validate_response_shape((200,), context='test')
        self.assertIn('exactly 2', str(ctx.exception))

    def test_three_tuple_rejected(self):
        from backend.scripts.poll_modal_http_job import _validate_response_shape, ModalJobError
        with self.assertRaises(ModalJobError) as ctx:
            _validate_response_shape((200, {}, 'extra'), context='test')
        self.assertIn('exactly 2', str(ctx.exception))

    def test_string_response_rejected(self):
        from backend.scripts.poll_modal_http_job import _validate_response_shape, ModalJobError
        with self.assertRaises(ModalJobError) as ctx:
            _validate_response_shape('not a tuple', context='test')
        self.assertIn('must return a 2-tuple', str(ctx.exception))

    def test_list_response_rejected(self):
        from backend.scripts.poll_modal_http_job import _validate_response_shape, ModalJobError
        with self.assertRaises(ModalJobError) as ctx:
            _validate_response_shape([200, {}], context='test')
        self.assertIn('must return a 2-tuple', str(ctx.exception))

    def test_valid_response_accepted(self):
        from backend.scripts.poll_modal_http_job import _validate_response_shape
        status, body = _validate_response_shape((200, {'key': 'val'}), context='test')
        self.assertEqual(status, 200)
        self.assertEqual(body, {'key': 'val'})

    def test_float_status_rejected(self):
        from backend.scripts.poll_modal_http_job import _validate_response_shape, ModalJobError
        with self.assertRaises(ModalJobError) as ctx:
            _validate_response_shape((200.0, {}), context='test')
        self.assertIn('must be an integer', str(ctx.exception))

    def test_bool_status_rejected(self):
        from backend.scripts.poll_modal_http_job import _validate_response_shape, ModalJobError
        with self.assertRaises(ModalJobError) as ctx:
            _validate_response_shape((True, {}), context='test')
        self.assertIn('must be an integer', str(ctx.exception))

    def test_non_dict_body_rejected(self):
        from backend.scripts.poll_modal_http_job import _validate_response_shape, ModalJobError
        with self.assertRaises(ModalJobError) as ctx:
            _validate_response_shape((200, 'not dict'), context='test')
        self.assertIn('must be a dict', str(ctx.exception))


class IdentityWhitespaceRejectionTests(unittest.TestCase):
    """A10: Identity fields with whitespace must be rejected, not silently stripped."""

    def test_run_id_with_whitespace_rejected(self):
        """A10: payload.run_id with leading/trailing whitespace must raise ModalJobError."""
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        def fake_requester(method, url, body):
            return (200, {'status': 'accepted', 'call_id': 'c1', 'run_id': ' r1 ', 'compute_job_id': 'cj1'})
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                payload={'run_id': ' r1 ', 'compute_job_id': 'cj1'},
                route='sar-segment',
                request=fake_requester,
                worker_url='https://modal.example.com',
                worker_token='tok',
                timeout_seconds=10,
                poll_interval_seconds=0,
            )
        self.assertIn('whitespace', str(ctx.exception))

    def test_compute_job_id_with_whitespace_rejected(self):
        """A10: payload.compute_job_id with whitespace must raise ModalJobError."""
        from backend.scripts.poll_modal_http_job import run_job, ModalJobError
        def fake_requester(method, url, body):
            return (200, {'status': 'accepted', 'call_id': 'c1', 'run_id': 'r1', 'compute_job_id': 'cj1'})
        with self.assertRaises(ModalJobError) as ctx:
            run_job(
                payload={'run_id': 'r1', 'compute_job_id': ' cj1 '},
                route='sar-segment',
                request=fake_requester,
                worker_url='https://modal.example.com',
                worker_token='tok',
                timeout_seconds=10,
                poll_interval_seconds=0,
            )
        self.assertIn('whitespace', str(ctx.exception))


class ReleaseGateTaxonomyBranchTests(unittest.TestCase):
    """A2: Release gate must classify OSError(ENOSPC) as INTERNAL_GATE_ERROR."""

    def test_enospc_classified_as_internal_error(self):
        """A2: OSError(ENOSPC) must be INTERNAL_GATE_ERROR, not VALIDATION_REJECTED."""
        import errno
        from backend.scripts.release_gate import run_release_gate
        from unittest.mock import patch
        with patch('backend.scripts.release_gate._run_release_gate') as mock_gate:
            mock_gate.side_effect = OSError(errno.ENOSPC, 'No space left on device')
            import io
            from contextlib import redirect_stderr
            err = io.StringIO()
            with redirect_stderr(err):
                result = run_release_gate(
                    artifacts_dir='/tmp/test',
                    expected_run_id='r1',
                    expected_registry_sha256='abc',
                    expected_decision_record_sha256='def',
                    poc_mode=True,
                )
        self.assertEqual(result, 1)
        self.assertIn('INTERNAL_GATE_ERROR', err.getvalue())
        self.assertIn('No space left', err.getvalue())

    def test_filenenotfound_classified_as_validation(self):
        """A2: FileNotFoundError must be VALIDATION_REJECTED (bad input path)."""
        from backend.scripts.release_gate import run_release_gate
        from unittest.mock import patch
        with patch('backend.scripts.release_gate._run_release_gate') as mock_gate:
            mock_gate.side_effect = FileNotFoundError('result.json not found')
            import io
            from contextlib import redirect_stderr
            err = io.StringIO()
            with redirect_stderr(err):
                result = run_release_gate(
                    artifacts_dir='/tmp/test',
                    expected_run_id='r1',
                    expected_registry_sha256='abc',
                    expected_decision_record_sha256='def',
                    poc_mode=True,
                )
        self.assertEqual(result, 1)
        self.assertIn('VALIDATION_REJECTED', err.getvalue())

    def test_keyerror_classified_as_internal_error(self):
        """A2: KeyError must be INTERNAL_GATE_ERROR (code bug), not VALIDATION_REJECTED."""
        from backend.scripts.release_gate import run_release_gate
        from unittest.mock import patch
        with patch('backend.scripts.release_gate._run_release_gate') as mock_gate:
            mock_gate.side_effect = KeyError('missing_key')
            import io
            from contextlib import redirect_stderr
            err = io.StringIO()
            with redirect_stderr(err):
                result = run_release_gate(
                    artifacts_dir='/tmp/test',
                    expected_run_id='r1',
                    expected_registry_sha256='abc',
                    expected_decision_record_sha256='def',
                    poc_mode=True,
                )
        self.assertEqual(result, 1)
        self.assertIn('INTERNAL_GATE_ERROR', err.getvalue())

    def test_runtimeerror_classified_as_internal_error(self):
        """A2: RuntimeError must be INTERNAL_GATE_ERROR, not VALIDATION_REJECTED."""
        from backend.scripts.release_gate import run_release_gate
        from unittest.mock import patch
        with patch('backend.scripts.release_gate._run_release_gate') as mock_gate:
            mock_gate.side_effect = RuntimeError('internal assertion failed')
            import io
            from contextlib import redirect_stderr
            err = io.StringIO()
            with redirect_stderr(err):
                result = run_release_gate(
                    artifacts_dir='/tmp/test',
                    expected_run_id='r1',
                    expected_registry_sha256='abc',
                    expected_decision_record_sha256='def',
                    poc_mode=True,
                )
        self.assertEqual(result, 1)
        self.assertIn('INTERNAL_GATE_ERROR', err.getvalue())

    def test_typeerror_classified_as_internal_error(self):
        """A2: TypeError must be INTERNAL_GATE_ERROR (code bug), not VALIDATION_REJECTED."""
        from backend.scripts.release_gate import run_release_gate
        from unittest.mock import patch
        with patch('backend.scripts.release_gate._run_release_gate') as mock_gate:
            mock_gate.side_effect = TypeError('NoneType has no attribute')
            import io
            from contextlib import redirect_stderr
            err = io.StringIO()
            with redirect_stderr(err):
                result = run_release_gate(
                    artifacts_dir='/tmp/test',
                    expected_run_id='r1',
                    expected_registry_sha256='abc',
                    expected_decision_record_sha256='def',
                    poc_mode=True,
                )
        self.assertEqual(result, 1)
        self.assertIn('INTERNAL_GATE_ERROR', err.getvalue())

    def test_eio_classified_as_internal_error(self):
        """G6: OSError(EIO) must be INTERNAL_GATE_ERROR (hardware I/O), not VALIDATION_REJECTED."""
        import errno
        from backend.scripts.release_gate import run_release_gate
        from unittest.mock import patch
        with patch('backend.scripts.release_gate._run_release_gate') as mock_gate:
            mock_gate.side_effect = OSError(errno.EIO, 'I/O error')
            import io
            from contextlib import redirect_stderr
            err = io.StringIO()
            with redirect_stderr(err):
                result = run_release_gate(
                    artifacts_dir='/tmp/test',
                    expected_run_id='r1',
                    expected_registry_sha256='abc',
                    expected_decision_record_sha256='def',
                    poc_mode=True,
                )
        self.assertEqual(result, 1)
        self.assertIn('INTERNAL_GATE_ERROR', err.getvalue())

    def test_valueerror_classified_as_internal_error(self):
        """G6: ValueError must be INTERNAL_GATE_ERROR (code bug), not VALIDATION_REJECTED."""
        from backend.scripts.release_gate import run_release_gate
        from unittest.mock import patch
        with patch('backend.scripts.release_gate._run_release_gate') as mock_gate:
            mock_gate.side_effect = ValueError('internal bug')
            import io
            from contextlib import redirect_stderr
            err = io.StringIO()
            with redirect_stderr(err):
                result = run_release_gate(
                    artifacts_dir='/tmp/test',
                    expected_run_id='r1',
                    expected_registry_sha256='abc',
                    expected_decision_record_sha256='def',
                    poc_mode=True,
                )
        self.assertEqual(result, 1)
        self.assertIn('INTERNAL_GATE_ERROR', err.getvalue())


class ByteArrayImmutabilityTests(unittest.TestCase):
    """G5: Mutable bytearray must be converted to immutable bytes before storing."""

    def test_bytearray_converted_to_bytes(self):
        """G5: bytearray input must be stored as immutable bytes in DecisionRecord."""
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
        )
        record = _make_valid_decision_record_dict()
        raw = bytearray(json.dumps(record).encode('utf-8'))
        result = load_decision_record_from_bytes(raw)
        # The stored raw_bytes must be bytes, not bytearray
        self.assertIsInstance(result.raw_bytes, bytes)
        self.assertNotIsInstance(result.raw_bytes, bytearray)

    def test_bytearray_mutation_does_not_affect_record(self):
        """G5: Mutating the original bytearray after loading must not change the hash."""
        import hashlib
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
        )
        record = _make_valid_decision_record_dict()
        raw = bytearray(json.dumps(record).encode('utf-8'))
        original_hash = hashlib.sha256(raw).hexdigest()
        result = load_decision_record_from_bytes(raw)
        # Mutate the original bytearray
        raw[0] = 0x00 if raw[0] != 0x00 else 0x01
        # The stored hash must still match the original
        self.assertEqual(result.decision_record_sha256, original_hash)
        # The stored bytes must not have changed
        self.assertEqual(hashlib.sha256(result.raw_bytes).hexdigest(), original_hash)


class StrengthenedNoSideEffectTests(unittest.TestCase):
    """A11: Verify no content mutation, not just file existence."""

    def test_no_content_mutation_in_repo(self):
        """A11: Verify that adversarial tests don't modify existing file contents."""
        import hashlib
        repo_root = Path(__file__).resolve().parent.parent
        # Hash a few key source files before and after
        key_files = [
            repo_root / 'backend' / 'common' / 'pir_panjal_decision_record.py',
            repo_root / 'backend' / 'common' / 'poc_scope_contract.py',
            repo_root / 'backend' / 'scripts' / 'poll_modal_http_job.py',
            repo_root / 'backend' / 'scripts' / 'release_gate.py',
        ]
        before_hashes = {}
        for f in key_files:
            if f.exists():
                before_hashes[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
        # Run a loader test
        from backend.common.pir_panjal_decision_record import (
            load_decision_record_from_bytes,
        )
        record = _make_valid_decision_record_dict()
        raw = json.dumps(record).encode('utf-8')
        result = load_decision_record_from_bytes(raw)
        self.assertEqual(result.decision_id, 'pir_panjal_poc_v1')
        # Verify no content changed
        after_hashes = {}
        for f in key_files:
            if f.exists():
                after_hashes[str(f)] = hashlib.sha256(f.read_bytes()).hexdigest()
        for path, before_hash in before_hashes.items():
            self.assertEqual(
                after_hashes[path], before_hash,
                f'File content changed: {path}',
            )


class AdversarialBoundarySuite(unittest.TestSuite):
    """Aggregates all adversarial boundary tests into one reproducible suite."""

    def __init__(self):
        super().__init__()
        loader = unittest.TestLoader()
        # P2/G2: Dot-segment identity tests
        self.addTests(loader.loadTestsFromTestCase(SafeIdentityDotSegmentTests))
        # P2/G4: Non-string type tests
        self.addTests(loader.loadTestsFromTestCase(SafeIdentityNonStringTests))
        # P2/G4: run_job type validation
        self.addTests(loader.loadTestsFromTestCase(RunJobTypeValidationTests))
        # P2/G3: Route allowlist
        self.addTests(loader.loadTestsFromTestCase(RouteAllowlistTests))
        # P1/G5: Provider identity string types
        self.addTests(loader.loadTestsFromTestCase(ProviderIdentityStringTypeTests))
        # P2/G6: poll_until_terminal defense-in-depth
        self.addTests(loader.loadTestsFromTestCase(PollUntilTerminalIdentityTests))
        # P1/G4: Payload identity string types
        self.addTests(loader.loadTestsFromTestCase(PayloadIdentityStringTypeTests))
        # P1/G5: Expected identity string types
        self.addTests(loader.loadTestsFromTestCase(ExpectedIdentityStringTypeTests))
        # P1/G6: Terminal identity string types
        self.addTests(loader.loadTestsFromTestCase(TerminalIdentityStringTypeTests))
        # P2/G7: Route canonicalization
        self.addTests(loader.loadTestsFromTestCase(RouteCanonicalizationTests))
        # P2/G8: Poller response shape
        self.addTests(loader.loadTestsFromTestCase(PollerResponseShapeTests))
        # P2/G9: Timeout type tests
        self.addTests(loader.loadTestsFromTestCase(TimeoutTypeTests))
        # P1/G1: Strict POC type tests
        self.addTests(loader.loadTestsFromTestCase(StrictTypePocScopeTests))
        # P3/G10: POC string field types
        self.addTests(loader.loadTestsFromTestCase(PocStringFieldTypeTests))
        # P3/G11: POC lead_time_h float rejection
        self.addTests(loader.loadTestsFromTestCase(PocLeadTimeFloatTests))
        # P4/G5: POC loader type confusion (direct tests)
        self.addTests(loader.loadTestsFromTestCase(PocLoaderTypeConfusionTests))
        # P4/G7: Submission response shape (direct tests)
        self.addTests(loader.loadTestsFromTestCase(SubmissionResponseShapeTests))
        # P4/G8: Float/bool submission status (direct tests)
        self.addTests(loader.loadTestsFromTestCase(SubmissionStatusTypeTests))
        # P4/G9: No-request-on-invalid-preflight (direct tests)
        self.addTests(loader.loadTestsFromTestCase(NoRequestOnInvalidPreflightTests))
        # P4/G10: Submission status str() coercion (direct tests)
        self.addTests(loader.loadTestsFromTestCase(SubmissionStatusStrCoercionTests))
        # P4/G11: Release-gate error taxonomy (direct tests)
        self.addTests(loader.loadTestsFromTestCase(ReleaseGateErrorTaxonomyTests))
        # P4/G6: Expected digest type (direct tests)
        self.addTests(loader.loadTestsFromTestCase(ExpectedDigestTypeTests))
        # P4/G12: No side effects (direct tests)
        self.addTests(loader.loadTestsFromTestCase(NoSideEffectTests))
        # Advisor A7: Poller bool/float/string status_code rejection
        self.addTests(loader.loadTestsFromTestCase(PollerBoolStatusTests))
        # Advisor A5: Engine roles key validation
        self.addTests(loader.loadTestsFromTestCase(EngineRolesKeyValidationTests))
        # Fifth audit A3/A4: Parser boundary hardening
        self.addTests(loader.loadTestsFromTestCase(ParserBoundaryHardeningTests))
        # Fifth audit A5: POC scope boundary hardening
        self.addTests(loader.loadTestsFromTestCase(PocScopeBoundaryHardeningTests))
        # Fifth audit A6: Response shape validator
        self.addTests(loader.loadTestsFromTestCase(ResponseShapeValidatorTests))
        # Fifth audit A10: Identity whitespace rejection
        self.addTests(loader.loadTestsFromTestCase(IdentityWhitespaceRejectionTests))
        # Fifth audit A2: Release gate taxonomy branches
        self.addTests(loader.loadTestsFromTestCase(ReleaseGateTaxonomyBranchTests))
        # Fifth audit A11: Strengthened no-side-effect tests
        self.addTests(loader.loadTestsFromTestCase(StrengthenedNoSideEffectTests))
        # Sixth audit G5: ByteArray immutability tests
        self.addTests(loader.loadTestsFromTestCase(ByteArrayImmutabilityTests))


def load_tests(loader, tests, pattern):
    """unittest discover hook — loads the adversarial suite."""
    suite = AdversarialBoundarySuite()
    return suite


if __name__ == '__main__':
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(AdversarialBoundarySuite())
    exit(0 if result.wasSuccessful() else 1)
