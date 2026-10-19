"""Tests for the shared release-bound state/forecast semantics boundary."""
from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from backend.common.snowpack_contracts import (
    ForecastSemanticsContract,
    InitialSnowStateContract,
    ProvenanceMetadata,
)
from backend.common.snowpack_release_semantics import (
    ReleaseSemanticsError,
    RUN_ID_PLACEHOLDER,
    bind_initial_state_to_run_id,
    forecast_semantics_envelope,
    initial_state_envelope,
    load_forecast_semantics_manifest,
    load_initial_state_manifest,
    sha256_bytes,
    snow_free_state_hash,
    validate_forcing_samples_against_forecast,
    validate_initial_state_binding,
    validate_release_semantics_context,
)


def _provenance(run_id: str = 'run_001') -> ProvenanceMetadata:
    return ProvenanceMetadata(
        source='operator-approved-input',
        source_class='direct',
        licence='operator-approved',
        timestamp='2026-01-15T00:00:00+00:00',
        units={'state': 'native'},
        hash='a' * 64,
        run_id=run_id,
    )


def _snow_free_state() -> InitialSnowStateContract:
    provisional = InitialSnowStateContract(
        state_id='state-001',
        state_type='snow_free',
        start_time='2026-01-15T00:00:00Z',
        source='operator-approved-input',
        state_sha256='0' * 64,
        provenance=_provenance(),
    )
    return replace(provisional, state_sha256=snow_free_state_hash(provisional))


def _forecast() -> ForecastSemanticsContract:
    return ForecastSemanticsContract(
        mode='forecast',
        source='wrf_candidate',
        forecast_cycle='2026-01-15T00:00:00Z',
        valid_from='2026-01-16T00:00:00Z',
        valid_to='2026-01-17T00:00:00Z',
        as_of='2026-01-15T00:00:00Z',
        lead_time_h=24,
        region_key='himalayas_nepal',
        elevation_band='lower',
        forcing_manifest_id='fm_001',
    )


class TestReleaseSemantics(unittest.TestCase):
    def test_run_id_placeholder_binds_and_rehashes_snow_free_state(self) -> None:
        state = replace(
            _snow_free_state(),
            provenance=replace(_snow_free_state().provenance, run_id=RUN_ID_PLACEHOLDER),
        )
        bound = bind_initial_state_to_run_id(state, 'poc-run-001')
        self.assertEqual(bound.provenance.run_id, 'poc-run-001')
        self.assertNotEqual(bound.state_sha256, state.state_sha256)
        validate_initial_state_binding(bound)

    def test_run_id_placeholder_rejects_empty_binding(self) -> None:
        state = replace(
            _snow_free_state(),
            provenance=replace(_snow_free_state().provenance, run_id=RUN_ID_PLACEHOLDER),
        )
        with self.assertRaises(ReleaseSemanticsError):
            bind_initial_state_to_run_id(state, '')

    def test_run_id_mismatch_without_placeholder_still_fails_closed(self) -> None:
        with self.assertRaises(ReleaseSemanticsError):
            bind_initial_state_to_run_id(_snow_free_state(), 'other-run')

    def test_valid_snow_free_manifest_is_hash_bound(self) -> None:
        state = _snow_free_state()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'initial-state.json'
            path.write_bytes(json.dumps(initial_state_envelope(state), sort_keys=True).encode())
            loaded, _ = load_initial_state_manifest(path)
            validate_initial_state_binding(loaded)

    def test_snow_free_self_consistent_wrong_hash_fails(self) -> None:
        state = _snow_free_state()
        bad = replace(state, state_sha256='b' * 64)
        with self.assertRaises(ReleaseSemanticsError):
            validate_initial_state_binding(bad)

    def test_profile_payload_hash_is_bound(self) -> None:
        payload = b'official-profile-bytes'
        state = InitialSnowStateContract(
            state_id='state-profile-001', state_type='profile',
            start_time='2026-01-15T00:00:00Z', source='snow-pit',
            state_sha256=sha256_bytes(payload), provenance=_provenance(),
            state_file_path='input-manifests/initial-state-payload/profile.sno',
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload_path = root / 'input-manifests/initial-state-payload/profile.sno'
            payload_path.parent.mkdir(parents=True)
            payload_path.write_bytes(payload)
            validate_initial_state_binding(state, bundle_root=root, payload_path=payload_path)
            payload_path.write_bytes(b'tampered')
            with self.assertRaises(ReleaseSemanticsError):
                validate_initial_state_binding(state, bundle_root=root, payload_path=payload_path)

    def test_forecast_context_is_bound(self) -> None:
        validate_release_semantics_context(
            state=_snow_free_state(), forecast=_forecast(), run_id='run_001',
            region_key='himalayas_nepal', elevation_band='lower',
            forcing_manifest_id='fm_001',
        )
        with self.assertRaises(ReleaseSemanticsError):
            validate_release_semantics_context(
                state=_snow_free_state(), forecast=_forecast(), run_id='other-run',
                region_key='himalayas_nepal', elevation_band='lower',
                forcing_manifest_id='fm_001',
            )

    def test_malformed_utf8_and_wrong_root_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.json'
            path.write_bytes(b'\xff\xfe')
            with self.assertRaises(ReleaseSemanticsError):
                load_forecast_semantics_manifest(path)

    def test_naive_provenance_timestamp_fails_closed(self) -> None:
        state = _snow_free_state()
        envelope = initial_state_envelope(state)
        envelope['contract']['provenance']['timestamp'] = '2026-01-15T00:00:00'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'initial-state.json'
            path.write_text(json.dumps(envelope), encoding='utf-8')
            with self.assertRaises(ReleaseSemanticsError):
                load_initial_state_manifest(path)
            path.write_text('[]', encoding='utf-8')
            with self.assertRaises(ReleaseSemanticsError):
                load_forecast_semantics_manifest(path)

    def test_forecast_envelope_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'forecast.json'
            path.write_text(json.dumps(forecast_semantics_envelope(_forecast())), encoding='utf-8')
            loaded, _ = load_forecast_semantics_manifest(path)
            self.assertEqual(loaded.forcing_manifest_id, 'fm_001')

    def test_forcing_window_binds_forecast_samples(self) -> None:
        result = validate_forcing_samples_against_forecast([
            {'time': '2026-01-15T00:00', 'forecast_cycle': '2026-01-15T00:00:00Z'},
            {'time': '2026-01-16T00:00', 'forecast_cycle': '2026-01-15T00:00:00Z'},
        ], _forecast())
        self.assertEqual(result['sample_count'], 2)
        self.assertTrue(result['naive_sample_timestamps_interpreted_as_utc'])

    def test_forcing_window_rejects_samples_after_valid_to(self) -> None:
        with self.assertRaises(ReleaseSemanticsError):
            validate_forcing_samples_against_forecast([
                {'time': '2026-01-18T00:00'},
            ], _forecast())

    def test_forcing_window_requires_forecast_sample(self) -> None:
        with self.assertRaises(ReleaseSemanticsError):
            validate_forcing_samples_against_forecast([
                {'time': '2026-01-15T00:00'},
            ], _forecast())

    def test_forcing_window_rejects_member_mismatch(self) -> None:
        forecast = replace(_forecast(), mode='ensemble', member_id='member-001')
        with self.assertRaises(ReleaseSemanticsError):
            validate_forcing_samples_against_forecast([
                {'time': '2026-01-16T00:00', 'member_id': 'member-002'},
            ], forecast)


if __name__ == '__main__':
    unittest.main()
