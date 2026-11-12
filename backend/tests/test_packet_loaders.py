"""Tests for executable Partner packet loaders (P2).

Tests verify that:
- Complete synthetic fixtures pass structural validation
- Incomplete, unsigned, stale, wrong-track, wrong-rights, malformed-geometry,
  and wrong-time packets fail closed
- Track-specific requirements are enforced (t2a needs forcing, track1 needs station)
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.common.track_contracts.packet_loaders import (
    ApprovalPacketV1,
    ReferenceUnitV1,
    IssueValidityRuleV1,
    RightsManifestV1,
    ForcingSourceManifestV1,
    StationAnchorManifestV1,
    TrackPreflightContextV1,
    PacketValidationError,
)


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


_VALID_HEX = "a" * 64


class TestApprovalPacketV1(unittest.TestCase):

    def _valid(self, **overrides) -> ApprovalPacketV1:
        defaults = dict(
            approval_id="Partner_m0_m1_001",
            scope="m0_m1_combined",
            signer="Dr. Smith",
            signer_role="Lead Scientist",
            signature_hash=_VALID_HEX,
            approved_at=_utc(2026, 8, 18, 6),
            approved_tracks=("track1", "t2a"),
        )
        defaults.update(overrides)
        return ApprovalPacketV1(**defaults)

    def test_valid_passes(self):
        self._valid().validate()

    def test_rejects_unsigned(self):
        with self.assertRaises(PacketValidationError):
            self._valid(signer="").validate()

    def test_rejects_invalid_scope(self):
        with self.assertRaises(PacketValidationError):
            self._valid(scope="m2_training").validate()

    def test_rejects_non_hex_signature(self):
        with self.assertRaises(PacketValidationError):
            self._valid(signature_hash="z" * 64).validate()

    def test_rejects_empty_tracks(self):
        with self.assertRaises(PacketValidationError):
            self._valid(approved_tracks=()).validate()

    def test_rejects_invalid_track(self):
        with self.assertRaises(PacketValidationError):
            self._valid(approved_tracks=("track3",)).validate()


class TestReferenceUnitV1(unittest.TestCase):

    def _valid(self, **overrides) -> ReferenceUnitV1:
        defaults = dict(
            reference_unit_name="pir_panjal_sector_a",
            latitude=34.021875,
            longitude=74.347536111,
            elevation_m=3730.0,
            elevation_band="3000-4000m",
            aspect_applicability="all",
            geometry_hash=_VALID_HEX,
            coordinate_system="EPSG:4326",
            approved_by="Dr. Smith",
            approved_at=_utc(2026, 8, 18, 6),
        )
        defaults.update(overrides)
        return ReferenceUnitV1(**defaults)

    def test_valid_passes(self):
        self._valid().validate()

    def test_rejects_bad_latitude(self):
        with self.assertRaises(PacketValidationError):
            self._valid(latitude=91.0).validate()

    def test_rejects_bad_longitude(self):
        with self.assertRaises(PacketValidationError):
            self._valid(longitude=181.0).validate()

    def test_rejects_negative_elevation(self):
        with self.assertRaises(PacketValidationError):
            self._valid(elevation_m=-100.0).validate()

    def test_rejects_unsigned(self):
        with self.assertRaises(PacketValidationError):
            self._valid(approved_by="").validate()

    def test_rejects_non_hex_geometry(self):
        with self.assertRaises(PacketValidationError):
            self._valid(geometry_hash="xyz").validate()


class TestIssueValidityRuleV1(unittest.TestCase):

    def _valid(self, **overrides) -> IssueValidityRuleV1:
        defaults = dict(
            issue_cadence_hours=6,
            issue_slots_utc=(0, 6, 12, 18),
            validity_window_hours=24,
            timezone="UTC",
            horizon_hours=72,
            approved_by="Dr. Smith",
            approved_at=_utc(2026, 8, 18, 6),
        )
        defaults.update(overrides)
        return IssueValidityRuleV1(**defaults)

    def test_valid_passes(self):
        self._valid().validate()

    def test_rejects_non_utc_timezone(self):
        with self.assertRaises(PacketValidationError):
            self._valid(timezone="IST").validate()

    def test_rejects_bad_cadence(self):
        with self.assertRaises(PacketValidationError):
            self._valid(issue_cadence_hours=7).validate()

    def test_rejects_bad_slot(self):
        with self.assertRaises(PacketValidationError):
            self._valid(issue_slots_utc=(0, 25)).validate()


class TestRightsManifestV1(unittest.TestCase):

    def _valid(self, **overrides) -> RightsManifestV1:
        defaults = dict(
            data_source="Partner bulletin archive",
            rights_holder="Partner",
            permitted_uses=("ml_training_track1", "ml_training_t2a"),
            prohibited_uses=("public_disclosure",),
            license_review_id="license_001",
            license_review_status="approved",
            approved_by="Dr. Smith",
            approved_at=_utc(2026, 8, 18, 6),
        )
        defaults.update(overrides)
        return RightsManifestV1(**defaults)

    def test_valid_passes(self):
        self._valid().validate()

    def test_rejects_pending_rights(self):
        with self.assertRaises(PacketValidationError):
            self._valid(license_review_status="pending").validate()

    def test_rejects_invalid_use(self):
        with self.assertRaises(PacketValidationError):
            self._valid(permitted_uses=("ml_training_track3",)).validate()


class TestForcingSourceManifestV1(unittest.TestCase):

    def _valid(self, **overrides) -> ForcingSourceManifestV1:
        defaults = dict(
            provider="Open-Meteo",
            model_id="gfs_seamless",
            run_id_format="YYYY-MM-DDTHH:MM UTC",
            native_resolution_m=3000.0,
            assimilation_disclosure="GFS assimilates observations; not observation-free",
            source_hash=_VALID_HEX,
            license_review_id="license_002",
            license_review_status="approved",
            permitted_track="t2a",
            approved_by="Dr. Smith",
            approved_at=_utc(2026, 8, 18, 6),
        )
        defaults.update(overrides)
        return ForcingSourceManifestV1(**defaults)

    def test_valid_passes(self):
        self._valid().validate()

    def test_rejects_wrong_track(self):
        with self.assertRaises(PacketValidationError):
            self._valid(permitted_track="track3").validate()

    def test_rejects_pending_license(self):
        with self.assertRaises(PacketValidationError):
            self._valid(license_review_status="pending").validate()


class TestStationAnchorManifestV1(unittest.TestCase):

    def _valid(self, **overrides) -> StationAnchorManifestV1:
        defaults = dict(
            station_id="aws_001",
            latitude=34.02,
            longitude=74.35,
            elevation_m=3500.0,
            station_type="aws",
            source_hash=_VALID_HEX,
            license_review_status="approved",
            permitted_track="track1",
            approved_by="Dr. Smith",
            approved_at=_utc(2026, 8, 18, 6),
        )
        defaults.update(overrides)
        return StationAnchorManifestV1(**defaults)

    def test_valid_passes(self):
        self._valid().validate()

    def test_rejects_t2a_track(self):
        """Station sources are only for Track 1, not T2A."""
        with self.assertRaises(PacketValidationError):
            self._valid(permitted_track="t2a").validate()

    def test_rejects_invalid_station_type(self):
        with self.assertRaises(PacketValidationError):
            self._valid(station_type="satellite").validate()


class TestTrackPreflightContextV1(unittest.TestCase):

    def _valid_t2a(self, **overrides) -> TrackPreflightContextV1:
        approval = ApprovalPacketV1(
            approval_id="Partner_001", scope="m0_m1_combined",
            signer="Dr. Smith", signer_role="Lead Scientist",
            signature_hash=_VALID_HEX, approved_at=_utc(2026, 8, 18, 6),
            approved_tracks=("track1", "t2a"),
        )
        ref_unit = ReferenceUnitV1(
            reference_unit_name="pir_panjal", latitude=34.02, longitude=74.35,
            elevation_m=3730.0, elevation_band="3000-4000m",
            aspect_applicability="all", geometry_hash=_VALID_HEX,
            coordinate_system="EPSG:4326", approved_by="Dr. Smith",
            approved_at=_utc(2026, 8, 18, 6),
        )
        issue_rule = IssueValidityRuleV1(
            issue_cadence_hours=6, issue_slots_utc=(0, 6, 12, 18),
            validity_window_hours=24, timezone="UTC", horizon_hours=72,
            approved_by="Dr. Smith", approved_at=_utc(2026, 8, 18, 6),
        )
        rights = RightsManifestV1(
            data_source="Partner", rights_holder="Partner",
            permitted_uses=("ml_training_t2a",),
            prohibited_uses=(), license_review_id="lic_001",
            license_review_status="approved",
            approved_by="Dr. Smith", approved_at=_utc(2026, 8, 18, 6),
        )
        forcing = ForcingSourceManifestV1(
            provider="Open-Meteo", model_id="gfs_seamless",
            run_id_format="YYYY-MM-DDTHH:MM UTC", native_resolution_m=3000.0,
            assimilation_disclosure="assimilates obs",
            source_hash=_VALID_HEX, license_review_id="lic_002",
            license_review_status="approved", permitted_track="t2a",
            approved_by="Dr. Smith", approved_at=_utc(2026, 8, 18, 6),
        )
        defaults = dict(
            track="t2a", approval=approval, reference_unit=ref_unit,
            issue_validity_rule=issue_rule, rights=rights,
            label_inventory_hash=_VALID_HEX, split_manifest_hash=_VALID_HEX,
            forcing_source=forcing, station_source=None,
        )
        defaults.update(overrides)
        return TrackPreflightContextV1(**defaults)

    def test_valid_t2a_passes(self):
        self._valid_t2a().validate()

    def test_t2a_without_forcing_rejected(self):
        with self.assertRaises(PacketValidationError):
            self._valid_t2a(forcing_source=None).validate()

    def test_t2a_with_station_rejected(self):
        """T2A must not have station sources."""
        station = StationAnchorManifestV1(
            station_id="aws_001", latitude=34.02, longitude=74.35,
            elevation_m=3500.0, station_type="aws",
            source_hash=_VALID_HEX, license_review_status="approved",
            permitted_track="track1", approved_by="Dr. Smith",
            approved_at=_utc(2026, 8, 18, 6),
        )
        with self.assertRaises(PacketValidationError):
            self._valid_t2a(station_source=station).validate()

    def test_approval_not_covering_track_rejected(self):
        with self.assertRaises(PacketValidationError):
            self._valid_t2a(
                approval=ApprovalPacketV1(
                    approval_id="Partner_002", scope="m0_m1_combined",
                    signer="Dr. Smith", signer_role="Lead Scientist",
                    signature_hash=_VALID_HEX, approved_at=_utc(2026, 8, 18, 6),
                    approved_tracks=("track1",),  # doesn't include t2a
                )
            ).validate()

    def test_track1_without_station_rejected(self):
        """Track 1 requires station source."""
        t2a_ctx = self._valid_t2a()
        with self.assertRaises(PacketValidationError):
            TrackPreflightContextV1(
                track="track1",
                approval=t2a_ctx.approval,
                reference_unit=t2a_ctx.reference_unit,
                issue_validity_rule=t2a_ctx.issue_validity_rule,
                rights=t2a_ctx.rights,
                label_inventory_hash=_VALID_HEX,
                split_manifest_hash=_VALID_HEX,
                forcing_source=t2a_ctx.forcing_source,
                station_source=None,  # missing for track1
            ).validate()


class TestPacketRoundTrip(unittest.TestCase):
    """Test that all packets can round-trip through to_dict()/from_dict()."""

    def test_approval_packet_round_trip(self):
        packet = TestApprovalPacketV1()._valid()
        d = packet.to_dict()
        restored = ApprovalPacketV1.from_dict(d)
        self.assertEqual(restored.approval_id, packet.approval_id)
        self.assertEqual(restored.signer, packet.signer)
        self.assertEqual(restored.approved_tracks, packet.approved_tracks)

    def test_reference_unit_round_trip(self):
        packet = TestReferenceUnitV1()._valid()
        d = packet.to_dict()
        restored = ReferenceUnitV1.from_dict(d)
        self.assertEqual(restored.reference_unit_name, packet.reference_unit_name)
        self.assertEqual(restored.latitude, packet.latitude)

    def test_issue_validity_rule_round_trip(self):
        packet = TestIssueValidityRuleV1()._valid()
        d = packet.to_dict()
        restored = IssueValidityRuleV1.from_dict(d)
        self.assertEqual(restored.issue_cadence_hours, packet.issue_cadence_hours)
        self.assertEqual(restored.issue_slots_utc, packet.issue_slots_utc)

    def test_rights_manifest_round_trip(self):
        packet = TestRightsManifestV1()._valid()
        d = packet.to_dict()
        restored = RightsManifestV1.from_dict(d)
        self.assertEqual(restored.data_source, packet.data_source)
        self.assertEqual(restored.permitted_uses, packet.permitted_uses)

    def test_forcing_source_round_trip(self):
        packet = TestForcingSourceManifestV1()._valid()
        d = packet.to_dict()
        restored = ForcingSourceManifestV1.from_dict(d)
        self.assertEqual(restored.provider, packet.provider)
        self.assertEqual(restored.permitted_track, packet.permitted_track)

    def test_station_anchor_round_trip(self):
        packet = TestStationAnchorManifestV1()._valid()
        d = packet.to_dict()
        restored = StationAnchorManifestV1.from_dict(d)
        self.assertEqual(restored.station_id, packet.station_id)
        self.assertEqual(restored.permitted_track, packet.permitted_track)

    def test_track_preflight_context_round_trip(self):
        ctx = TestTrackPreflightContextV1()._valid_t2a()
        d = ctx.to_dict()
        restored = TrackPreflightContextV1.from_dict(d)
        self.assertEqual(restored.track, ctx.track)
        self.assertEqual(restored.approval.approval_id, ctx.approval.approval_id)
        self.assertIsNotNone(restored.forcing_source)
        self.assertIsNone(restored.station_source)

    def test_wrong_schema_rejected(self):
        """from_dict must reject wrong schema versions."""
        packet = TestApprovalPacketV1()._valid()
        d = packet.to_dict()
        d['schema'] = 'wrong_schema_v2'
        with self.assertRaises(PacketValidationError):
            ApprovalPacketV1.from_dict(d)

    def test_missing_field_rejected(self):
        """from_dict must reject missing required fields."""
        packet = TestApprovalPacketV1()._valid()
        d = packet.to_dict()
        del d['signer']
        with self.assertRaises(PacketValidationError):
            ApprovalPacketV1.from_dict(d)

    def test_unknown_field_rejected(self):
        """CRITICAL: from_dict must reject unknown fields, not silently ignore them."""
        packet = TestApprovalPacketV1()._valid()
        d = packet.to_dict()
        d['unknown_malicious_field'] = 'should be rejected'
        with self.assertRaises(PacketValidationError):
            ApprovalPacketV1.from_dict(d)

    def test_unknown_field_in_reference_unit_rejected(self):
        packet = TestReferenceUnitV1()._valid()
        d = packet.to_dict()
        d['extra_field'] = 'malicious'
        with self.assertRaises(PacketValidationError):
            ReferenceUnitV1.from_dict(d)

    def test_unknown_field_in_rights_rejected(self):
        packet = TestRightsManifestV1()._valid()
        d = packet.to_dict()
        d['secret_override'] = True
        with self.assertRaises(PacketValidationError):
            RightsManifestV1.from_dict(d)

    def test_unknown_field_in_forcing_source_rejected(self):
        packet = TestForcingSourceManifestV1()._valid()
        d = packet.to_dict()
        d['bypass_validation'] = True
        with self.assertRaises(PacketValidationError):
            ForcingSourceManifestV1.from_dict(d)

    def test_unknown_field_in_preflight_context_rejected(self):
        ctx = TestTrackPreflightContextV1()._valid_t2a()
        d = ctx.to_dict()
        d['override_gate'] = True
        with self.assertRaises(PacketValidationError):
            TrackPreflightContextV1.from_dict(d)

    def test_non_object_payloads_use_structured_blocker(self):
        cases = (
            (ApprovalPacketV1.from_dict, []),
            (ReferenceUnitV1.from_dict, []),
            (IssueValidityRuleV1.from_dict, []),
            (RightsManifestV1.from_dict, []),
            (ForcingSourceManifestV1.from_dict, []),
            (StationAnchorManifestV1.from_dict, []),
            (TrackPreflightContextV1.from_dict, []),
        )
        for loader, payload in cases:
            with self.subTest(loader=loader.__qualname__):
                with self.assertRaisesRegex(PacketValidationError, r'^E030_malformed_packet:'):
                    loader(payload)


if __name__ == "__main__":
    unittest.main()
