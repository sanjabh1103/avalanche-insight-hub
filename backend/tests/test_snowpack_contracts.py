"""Tests for snowpack execution and provenance contracts (Phase 1c + 1d)."""
from __future__ import annotations

import unittest

from backend.common.snowpack_contracts import (
    AvalancheEpisodeContract,
    ContractValidationError,
    EnsembleMemberContract,
    NativeEnsembleMemberLineageContract,
    ForecastSemanticsContract,
    ForcingManifestContract,
    InitialSnowStateContract,
    ProfileLayer,
    ProvenanceMetadata,
    SnowpackRunContract,
    ValidationReportContract,
    VerticalProfileContract,
    compute_artifact_hash,
    validate_execution_status,
    DRY_RUN_STATUSES,
    NATIVE_EXECUTION_STATUSES,
    VALID_EXECUTION_STATUSES,
    VALID_SOURCE_CLASSES,
    validate_native_ensemble_lineage,
)


def _valid_provenance(**overrides) -> ProvenanceMetadata:
    """Create a valid ProvenanceMetadata with optional overrides."""
    defaults = dict(
        source='open_meteo_archive',
        source_class='proxy',
        licence='CC-BY-4.0',
        timestamp='2026-01-15T00:00:00+00:00',
        units={'temperature': 'K'},
        hash='a' * 64,
        run_id='run_001',
    )
    defaults.update(overrides)
    return ProvenanceMetadata(**defaults)


class TestExecutionStatus(unittest.TestCase):
    """Test execution status semantics (Phase 1d)."""

    def test_all_valid_statuses_accepted(self) -> None:
        for status in VALID_EXECUTION_STATUSES:
            validate_execution_status(status, is_dry_run=False)

    def test_invalid_status_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            validate_execution_status('not_a_status')

    def test_completed_prohibited_for_dry_run(self) -> None:
        """Dry-run paths must not use 'completed' status."""
        with self.assertRaises(ContractValidationError):
            validate_execution_status('completed', is_dry_run=True)

    def test_running_prohibited_for_dry_run(self) -> None:
        """Dry-run paths must not use 'running' status."""
        with self.assertRaises(ContractValidationError):
            validate_execution_status('running', is_dry_run=True)

    def test_partial_prohibited_for_dry_run(self) -> None:
        """Dry-run paths must not use 'partial' status."""
        with self.assertRaises(ContractValidationError):
            validate_execution_status('partial', is_dry_run=True)

    def test_configuration_validated_allowed_for_dry_run(self) -> None:
        """Dry-run paths may use 'configuration_validated' status."""
        validate_execution_status('configuration_validated', is_dry_run=True)

    def test_dry_run_and_native_statuses_are_disjoint(self) -> None:
        """Dry-run and native execution statuses must not overlap."""
        self.assertEqual(DRY_RUN_STATUSES & NATIVE_EXECUTION_STATUSES, frozenset())


class TestProvenanceMetadata(unittest.TestCase):
    """Test provenance metadata validation."""

    def test_valid_provenance_accepted(self) -> None:
        _valid_provenance().validate()

    def test_invalid_source_class_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            _valid_provenance(source_class='invalid_class').validate()

    def test_missing_source_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            ProvenanceMetadata(
                source='', source_class='proxy', licence='CC-BY-4.0',
                timestamp='2026-01-15T00:00:00+00:00',
            ).validate()

    def test_missing_licence_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            _valid_provenance(licence='').validate()

    def test_invalid_timestamp_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            _valid_provenance(timestamp='not-a-date').validate()

    def test_missing_units_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            _valid_provenance(units={}).validate()

    def test_missing_hash_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            _valid_provenance(hash='').validate()

    def test_missing_run_id_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            _valid_provenance(run_id='').validate()

    def test_all_source_classes_valid(self) -> None:
        for sc in VALID_SOURCE_CLASSES:
            _valid_provenance(source_class=sc).validate()


class TestForcingManifestContract(unittest.TestCase):
    """Test forcing manifest contract."""

    def _valid_manifest(self, **overrides) -> ForcingManifestContract:
        defaults = dict(
            region_key='himalayas_nepal',
            elevation_band='lower',
            aspect_class='N',
            forecast_horizon_h=48,
            variables=('TA', 'RH', 'VW', 'ISWR', 'ILWR', 'PSUM'),
            smet_file_path='/data/nepal_lower_N.smet',
            provenance=_valid_provenance(),
        )
        defaults.update(overrides)
        return ForcingManifestContract(**defaults)

    def test_valid_manifest_accepted(self) -> None:
        self._valid_manifest().validate()

    def test_missing_variable_group_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._valid_manifest(variables=('TA', 'RH', 'VW')).validate()

    def test_official_snowpack_alternatives_accepted(self) -> None:
        self._valid_manifest(
            variables=('TA', 'RH', 'VW', 'RSWR', 'TSS', 'HS'),
        ).validate()

    def test_incomplete_forcing_rejected(self) -> None:
        """Incomplete forcing must be rejected, not silently filled."""
        with self.assertRaises(ContractValidationError):
            self._valid_manifest(is_complete=False).validate()

    def test_invalid_aspect_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._valid_manifest(aspect_class='NE').validate()

    def test_forecast_semantics_must_match_forcing_context(self) -> None:
        semantics = ForecastSemanticsContract(
            mode='forecast',
            source='wrf_candidate',
            forecast_cycle='2026-01-15T00:00:00Z',
            valid_from='2026-01-16T00:00:00Z',
            valid_to='2026-01-17T00:00:00Z',
            as_of='2026-01-15T00:00:00Z',
            lead_time_h=24,
            region_key='himalayas_nepal',
            elevation_band='lower',
            forcing_manifest_id='manifest_001',
        )
        self._valid_manifest(
            forecast_semantics=semantics,
        ).validate()

    def test_forecast_semantics_rejects_lead_time_mismatch(self) -> None:
        semantics = ForecastSemanticsContract(
            mode='forecast', source='wrf_candidate',
            forecast_cycle='2026-01-15T00:00:00Z',
            valid_from='2026-01-16T00:00:00Z',
            valid_to='2026-01-17T00:00:00Z',
            as_of='2026-01-15T00:00:00Z', lead_time_h=48,
            region_key='himalayas_nepal', elevation_band='lower',
            forcing_manifest_id='manifest_001',
        )
        with self.assertRaises(ContractValidationError):
            semantics.validate()


class TestNativeEnsembleLineageContract(unittest.TestCase):
    """Test native member lineage and bounded development/verification batches."""

    def _member(self, index: int, **overrides) -> NativeEnsembleMemberLineageContract:
        run_id = f"run-{index:03d}"
        defaults = dict(
            member_id=f"member-{index:03d}",
            source="open_meteo_nwp",
            forecast_cycle="2026-01-15T00:00:00Z",
            lead_time_h=24.0,
            region_key="himalayas_nepal",
            elevation_band="lower",
            forcing_manifest_id=f"forcing-{index:03d}",
            geometry_manifest_id="geometry-001",
            initial_state_manifest_id="state-001",
            snowpack_run_id=run_id,
            output_manifest_id=f"output-{index:03d}",
            provenance=_valid_provenance(run_id=run_id),
        )
        defaults.update(overrides)
        return NativeEnsembleMemberLineageContract(**defaults)

    def test_valid_member_binds_all_lineage_ids(self) -> None:
        self._member(1).validate()

    def test_missing_lineage_id_fails_closed(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._member(1, output_manifest_id="").validate()

    def test_provenance_run_id_must_match_snowpack_run(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._member(1, provenance=_valid_provenance(run_id="other-run")).validate()

    def test_development_requires_exactly_three_unique_members(self) -> None:
        members = tuple(self._member(index) for index in range(1, 4))
        validate_native_ensemble_lineage(members, stage="development")
        with self.assertRaises(ContractValidationError):
            validate_native_ensemble_lineage(members[:2], stage="development")
        with self.assertRaises(ContractValidationError):
            validate_native_ensemble_lineage(
                members[:2] + (self._member(1, output_manifest_id="output-999"),),
                stage="development",
            )

    def test_verification_requires_ten_to_twenty_members(self) -> None:
        members = tuple(self._member(index) for index in range(1, 11))
        validate_native_ensemble_lineage(members, stage="verification")
        with self.assertRaises(ContractValidationError):
            validate_native_ensemble_lineage(members[:3], stage="verification")

    def test_batch_context_and_initial_state_must_match(self) -> None:
        members = tuple(self._member(index) for index in range(1, 4))
        altered = self._member(3, elevation_band="middle")
        with self.assertRaises(ContractValidationError):
            validate_native_ensemble_lineage(members[:2] + (altered,), stage="development")


class TestSnowpackRunContract(unittest.TestCase):
    """Test SNOWPACK run contract with execution status semantics."""

    def _valid_run(self, **overrides) -> SnowpackRunContract:
        defaults = dict(
            run_id='run_001',
            region_key='himalayas_nepal',
            elevation_band='lower',
            aspect_class='N',
            slope_angle=35.0,
            forcing_manifest_id='manifest_001',
            execution_status='planned',
            provenance=_valid_provenance(),
        )
        defaults.update(overrides)
        return SnowpackRunContract(**defaults)

    def test_valid_run_accepted(self) -> None:
        self._valid_run().validate()

    def test_completed_requires_output_paths(self) -> None:
        """'completed' status requires non-empty output_paths."""
        with self.assertRaises(ContractValidationError):
            self._valid_run(execution_status='completed').validate()

    def test_completed_with_outputs_accepted(self) -> None:
        self._valid_run(
            execution_status='completed',
            output_paths=('/output/run_001.pro',),
            binary_version='snowpack-3.7.0',
        ).validate()

    def test_dry_run_completed_rejected(self) -> None:
        """Dry-run path cannot have 'completed' status."""
        with self.assertRaises(ContractValidationError):
            self._valid_run(
                execution_status='completed',
                is_dry_run=True,
                output_paths=('/output/run_001.pro',),
            ).validate()

    def test_dry_run_configuration_validated_accepted(self) -> None:
        self._valid_run(
            execution_status='configuration_validated',
            is_dry_run=True,
        ).validate()

    def test_native_release_requires_initial_state_and_forecast_semantics(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._valid_run(
                execution_status='completed',
                output_paths=('/output/run_001.pro',),
                binary_version='snowpack-3.7.0',
            ).validate_for_native_release()

    def test_native_release_accepts_explicit_state_and_forecast_contracts(self) -> None:
        state = InitialSnowStateContract(
            state_id='state-001', state_type='snow_free',
            start_time='2026-01-15T00:00:00Z', source='operator-approved-input',
            state_sha256='b' * 64, provenance=_valid_provenance(),
        )
        forecast = ForecastSemanticsContract(
            mode='forecast', source='wrf_candidate',
            forecast_cycle='2026-01-15T00:00:00Z',
            valid_from='2026-01-16T00:00:00Z',
            valid_to='2026-01-17T00:00:00Z',
            as_of='2026-01-15T00:00:00Z', lead_time_h=24,
            region_key='himalayas_nepal', elevation_band='lower',
            forcing_manifest_id='manifest_001',
        )
        self._valid_run(
            execution_status='completed',
            output_paths=('/output/run_001.pro',),
            binary_version='snowpack-3.7.0',
            initial_state=state,
            forecast_semantics=forecast,
        ).validate_for_native_release()

    def test_initial_profile_state_requires_profile_path(self) -> None:
        state = InitialSnowStateContract(
            state_id='state-001', state_type='profile',
            start_time='2026-01-15T00:00:00Z', source='snow-pit',
            state_sha256='b' * 64, provenance=_valid_provenance(),
        )
        with self.assertRaises(ContractValidationError):
            state.validate()


class TestVerticalProfileContract(unittest.TestCase):
    """Test vertical profile contract with profile preservation."""

    def _valid_layer(self, **overrides) -> ProfileLayer:
        defaults = dict(
            depth_m=0.5,
            thickness_m=0.1,
            grain_type='faceted',
            grain_size_mm=2.0,
            density_kgm3=300.0,
            temperature_k=265.0,
            liquid_water_content_pct=0.0,
        )
        defaults.update(overrides)
        return ProfileLayer(**defaults)

    def _valid_profile(self, **overrides) -> VerticalProfileContract:
        layers = (self._valid_layer(), self._valid_layer(depth_m=0.6))
        defaults = dict(
            profile_id='profile_001',
            region_key='himalayas_nepal',
            elevation_band='lower',
            aspect_class='N',
            timestamp='2026-01-15T00:00:00+00:00',
            depth_reference='ground',
            observation_method='snowpack_native',
            layers=layers,
            provenance=_valid_provenance(source_class='derived'),
        )
        defaults.update(overrides)
        return VerticalProfileContract(**defaults)

    def test_valid_profile_accepted(self) -> None:
        self._valid_profile().validate()

    def test_empty_layers_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._valid_profile(layers=()).validate()

    def test_invalid_depth_reference_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._valid_profile(depth_reference='middle').validate()

    def test_proxy_method_requires_proxy_source_class(self) -> None:
        """Proxy observation_method must have proxy/derived/synthetic source_class."""
        with self.assertRaises(ContractValidationError):
            self._valid_profile(
                observation_method='proxy',
                provenance=_valid_provenance(source_class='direct'),
            ).validate()

    def test_proxy_method_with_proxy_source_accepted(self) -> None:
        self._valid_profile(
            observation_method='proxy',
            provenance=_valid_provenance(source_class='proxy'),
        ).validate()

    def test_backward_compatible_scalar_proxies_preserved(self) -> None:
        """Profile can carry backward-compatible scalar proxies alongside layers."""
        profile = self._valid_profile(
            estimated_shear_strength_kpa=5.0,
            snow_settlement_index=0.7,
        )
        self.assertEqual(profile.estimated_shear_strength_kpa, 5.0)
        self.assertEqual(profile.snow_settlement_index, 0.7)
        self.assertGreater(len(profile.layers), 0)


class TestAvalancheEpisodeContract(unittest.TestCase):
    """Test avalanche episode contract."""

    def _valid_episode(self, **overrides) -> AvalancheEpisodeContract:
        defaults = dict(
            episode_id='ep_001',
            problem_type='wind_slab',
            region_key='himalayas_nepal',
            elevation_band='middle',
            aspect_class='N',
            first_detection='2026-01-15T06:00:00+00:00',
            persistence_h=12,
            peak_probability=0.7,
            expected_decay_h=24,
            source_members=('member_01', 'member_02'),
            confidence=0.6,
            coverage=0.5,
        )
        defaults.update(overrides)
        return AvalancheEpisodeContract(**defaults)

    def test_valid_episode_accepted(self) -> None:
        self._valid_episode().validate()

    def test_official_warning_rejected(self) -> None:
        """Episodes must not be presented as official warnings."""
        with self.assertRaises(ContractValidationError):
            self._valid_episode(is_official_warning=True).validate()

    def test_invalid_problem_type_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._valid_episode(problem_type='invalid_type').validate()

    def test_probability_out_of_range_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._valid_episode(peak_probability=1.5).validate()

    def test_first_detection_must_be_timezone_aware_utc(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._valid_episode(first_detection='2026-01-15T06:00:00').validate()

    def test_persistence_and_decay_must_be_non_negative_and_positive(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._valid_episode(persistence_h=-1).validate()
        with self.assertRaises(ContractValidationError):
            self._valid_episode(expected_decay_h=0).validate()

    def test_source_members_must_be_non_empty_strings(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._valid_episode(source_members=('member_01', '')).validate()


class TestValidationReportContract(unittest.TestCase):
    """Test validation report contract."""

    def _valid_report(self, **overrides) -> ValidationReportContract:
        defaults = dict(
            report_id='report_001',
            region_key='himalayas_nepal',
            validation_type='physical',
            metrics={'mae': 0.15, 'rmse': 0.22},
            paired_coverage=0.85,
            provenance=_valid_provenance(),
        )
        defaults.update(overrides)
        return ValidationReportContract(**defaults)

    def test_valid_physical_report_accepted(self) -> None:
        self._valid_report().validate()

    def test_probabilistic_without_label_approval_rejected(self) -> None:
        """Probabilistic validation requires Partner label approval."""
        with self.assertRaises(ContractValidationError):
            self._valid_report(
                validation_type='probabilistic',
                is_label_approved=False,
            ).validate()

    def test_probabilistic_with_label_approval_accepted(self) -> None:
        self._valid_report(
            validation_type='probabilistic',
            is_label_approved=True,
        ).validate()

    def test_invalid_validation_type_rejected(self) -> None:
        with self.assertRaises(ContractValidationError):
            self._valid_report(validation_type='hybrid').validate()


class TestComputeArtifactHash(unittest.TestCase):
    """Test artifact hash computation."""

    def test_string_hash(self) -> None:
        h = compute_artifact_hash('test content')
        self.assertEqual(len(h), 64)  # SHA-256 hex

    def test_bytes_hash(self) -> None:
        h = compute_artifact_hash(b'test content')
        self.assertEqual(len(h), 64)

    def test_deterministic(self) -> None:
        h1 = compute_artifact_hash('same content')
        h2 = compute_artifact_hash('same content')
        self.assertEqual(h1, h2)

    def test_different_content_different_hash(self) -> None:
        h1 = compute_artifact_hash('content a')
        h2 = compute_artifact_hash('content b')
        self.assertNotEqual(h1, h2)


if __name__ == '__main__':
    unittest.main()
