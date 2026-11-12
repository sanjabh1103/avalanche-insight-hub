"""Tests for authority registry (P3).

Tests verify that:
- Registered authorities can be verified
- Unregistered signers are rejected
- Inactive authorities are rejected
- Revoked approvals are rejected
- Expired approvals are rejected
- Track-specific authority is enforced
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone, timedelta

from backend.common.track_contracts.authority_registry import (
    ApprovalRecordV1,
    AuthorityRecord,
    AuthorityRegistry,
    AuthorityValidationError,
)


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


class TestAuthorityRecord(unittest.TestCase):

    def test_valid_authority_passes(self):
        auth = AuthorityRecord(
            authority_id="Partner_001",
            name="Dr. Smith",
            role="Lead Scientist",
            active=True,
            registered_at=_utc(2026, 1, 1),
            approved_tracks=("track1", "t2a"),
        )
        auth.validate()

    def test_authority_json_boolean_types_are_strict(self):
        data = AuthorityRecord(
            authority_id="Partner_001",
            name="Dr. Smith",
            role="Lead Scientist",
            active=True,
            registered_at=_utc(2026, 1, 1),
        ).to_dict()
        data["active"] = "false"
        with self.assertRaises(AuthorityValidationError):
            AuthorityRecord.from_dict(data)

    def test_empty_name_rejected(self):
        with self.assertRaises(AuthorityValidationError):
            AuthorityRecord(
                authority_id="Partner_001", name="", role="Lead Scientist",
                active=True, registered_at=_utc(2026, 1, 1),
            ).validate()

    def test_invalid_track_rejected(self):
        with self.assertRaises(AuthorityValidationError):
            AuthorityRecord(
                authority_id="Partner_001", name="Dr. Smith", role="Lead Scientist",
                active=True, registered_at=_utc(2026, 1, 1),
                approved_tracks=("track3",),
            ).validate()

    def test_empty_track_scope_never_means_allow_all(self):
        authority = AuthorityRecord(
            authority_id="Partner_001", name="Dr. Smith", role="Lead Scientist",
            active=True, registered_at=_utc(2026, 1, 1), approved_tracks=(),
        )

        self.assertFalse(authority.can_approve_track("track1"))
        self.assertFalse(authority.can_approve_track("t2a"))

    def test_is_active_at_checks_time(self):
        auth = AuthorityRecord(
            authority_id="Partner_001", name="Dr. Smith", role="Lead Scientist",
            active=True, registered_at=_utc(2026, 1, 1),
            deactivated_at=_utc(2026, 12, 31),
        )
        self.assertTrue(auth.is_active_at(_utc(2026, 6, 1)))
        self.assertFalse(auth.is_active_at(_utc(2027, 1, 1)))
        self.assertFalse(auth.is_active_at(_utc(2025, 12, 31)))


class TestAuthorityRegistry(unittest.TestCase):

    def _registry_with_smith(self) -> AuthorityRegistry:
        reg = AuthorityRegistry()
        reg.register(AuthorityRecord(
            authority_id="Partner_001",
            name="Dr. Smith",
            role="Lead Scientist",
            active=True,
            registered_at=_utc(2026, 1, 1),
            approved_tracks=("track1", "t2a"),
        ))
        return reg

    def test_registered_authority_verified(self):
        reg = self._registry_with_smith()
        authority = reg.verify_authority(
            signer_name="Dr. Smith",
            signer_role="Lead Scientist",
            approved_tracks=("t2a",),
            approved_at=_utc(2026, 8, 18, 6),
        )
        self.assertEqual(authority.name, "Dr. Smith")

    def test_unregistered_signer_rejected(self):
        """CRITICAL: a fake signer must NOT pass verification."""
        reg = self._registry_with_smith()
        with self.assertRaises(AuthorityValidationError):
            reg.verify_authority(
                signer_name="Dr. Fake",
                signer_role="Lead Scientist",
                approved_tracks=("t2a",),
                approved_at=_utc(2026, 8, 18, 6),
            )

    def test_wrong_role_rejected(self):
        reg = self._registry_with_smith()
        with self.assertRaises(AuthorityValidationError):
            reg.verify_authority(
                signer_name="Dr. Smith",
                signer_role="Intern",  # wrong role
                approved_tracks=("t2a",),
                approved_at=_utc(2026, 8, 18, 6),
            )

    def test_inactive_authority_rejected(self):
        reg = AuthorityRegistry()
        reg.register(AuthorityRecord(
            authority_id="Partner_002",
            name="Dr. Jones",
            role="Director",
            active=False,  # inactive
            registered_at=_utc(2026, 1, 1),
        ))
        with self.assertRaises(AuthorityValidationError):
            reg.verify_authority(
                signer_name="Dr. Jones",
                signer_role="Director",
                approved_tracks=("t2a",),
                approved_at=_utc(2026, 8, 18, 6),
            )

    def test_authority_not_yet_registered_rejected(self):
        """Authority registered AFTER approval date should fail."""
        reg = AuthorityRegistry()
        reg.register(AuthorityRecord(
            authority_id="Partner_003",
            name="Dr. Late",
            role="Lead Scientist",
            active=True,
            registered_at=_utc(2026, 9, 1),  # registered after approval
        ))
        with self.assertRaises(AuthorityValidationError):
            reg.verify_authority(
                signer_name="Dr. Late",
                signer_role="Lead Scientist",
                approved_tracks=("t2a",),
                approved_at=_utc(2026, 8, 18, 6),  # before registration
            )

    def test_track_not_authorized_rejected(self):
        """Authority who can only approve track1 cannot approve t2a."""
        reg = AuthorityRegistry()
        reg.register(AuthorityRecord(
            authority_id="Partner_004",
            name="Dr. Track1Only",
            role="Lead Scientist",
            active=True,
            registered_at=_utc(2026, 1, 1),
            approved_tracks=("track1",),  # can only approve track1
        ))
        with self.assertRaises(AuthorityValidationError):
            reg.verify_authority(
                signer_name="Dr. Track1Only",
                signer_role="Lead Scientist",
                approved_tracks=("t2a",),  # not authorized for t2a
                approved_at=_utc(2026, 8, 18, 6),
            )

    def test_revoked_approval_rejected(self):
        reg = self._registry_with_smith()
        reg.revoke_approval("Partner_approval_001")
        with self.assertRaises(AuthorityValidationError):
            reg.verify_approval_validity(
                "Partner_approval_001",
                approved_at=_utc(2026, 8, 18, 6),
            )

    def test_expired_approval_rejected(self):
        reg = AuthorityRegistry(approval_expiry_days=30)
        # Approval from 100 days ago
        with self.assertRaises(AuthorityValidationError):
            reg.verify_approval_validity(
                "Partner_approval_002",
                approved_at=_utc(2026, 4, 1),  # 100+ days ago
                check_time=_utc(2026, 8, 18),
            )

    def test_full_approval_verification_passes(self):
        reg = self._registry_with_smith()
        authority = reg.verify_approval(
            approval_id="Partner_approval_003",
            signer_name="Dr. Smith",
            signer_role="Lead Scientist",
            signature_hash="a" * 64,
            approved_tracks=("t2a",),
            approved_at=_utc(2026, 8, 18, 6),
        )
        self.assertEqual(authority.name, "Dr. Smith")

    def test_full_approval_verification_rejects_fake_signer(self):
        """CRITICAL: fake signer with valid-looking hash must be rejected."""
        reg = self._registry_with_smith()
        with self.assertRaises(AuthorityValidationError):
            reg.verify_approval(
                approval_id="Partner_approval_004",
                signer_name="Dr. Fake",
                signer_role="Lead Scientist",
                signature_hash="a" * 64,  # valid-looking hash
                approved_tracks=("t2a",),
                approved_at=_utc(2026, 8, 18, 6),
            )

    def test_registered_promotion_approval_requires_cryptographic_verification(self):
        reg = self._registry_with_smith()
        reg.register_approval(ApprovalRecordV1(
            approval_id="promo-001",
            authority_id="Partner_001",
            approved_tracks=("t2a",),
            approved_at=_utc(2026, 8, 18, 6),
            signature_hash="a" * 64,
            cryptographic_verified=False,
        ))
        with self.assertRaisesRegex(AuthorityValidationError, "cryptographic"):
            reg.verify_registered_approval("promo-001", "t2a")

    def test_registered_approval_requires_authority_track_scope(self):
        reg = AuthorityRegistry()
        reg.register(AuthorityRecord(
            authority_id="Partner_track1_only", name="Dr. Track1", role="Lead Scientist",
            active=True, registered_at=_utc(2026, 1, 1), approved_tracks=("track1",),
        ))
        with self.assertRaisesRegex(AuthorityValidationError, "cannot approve track"):
            reg.register_approval(ApprovalRecordV1(
                approval_id="promo-wrong-scope", authority_id="Partner_track1_only",
                approved_tracks=("t2a",), approved_at=_utc(2026, 8, 18, 6),
                signature_hash="a" * 64,
            ))

    def test_registered_approval_can_use_injected_verifier(self):
        reg = AuthorityRegistry(cryptographic_verifier=lambda approval: approval.approval_id == "promo-verified")
        reg.register(AuthorityRecord(
            authority_id="Partner_001", name="Dr. Smith", role="Lead Scientist",
            active=True, registered_at=_utc(2026, 1, 1), approved_tracks=("t2a",),
        ))
        reg.register_approval(ApprovalRecordV1(
            approval_id="promo-verified", authority_id="Partner_001",
            approved_tracks=("t2a",), approved_at=_utc(2026, 8, 18, 6),
            signature_hash="a" * 64,
        ))
        self.assertEqual(
            reg.verify_registered_approval("promo-verified", "t2a").approval_id,
            "promo-verified",
        )

    def test_registry_round_trip_preserves_rights_and_approval_state(self):
        reg = self._registry_with_smith()
        reg.register_approval(ApprovalRecordV1(
            approval_id="promo-002",
            authority_id="Partner_001",
            approved_tracks=("t2a",),
            approved_at=_utc(2026, 8, 18, 6),
            signature_hash="b" * 64,
            cryptographic_verified=True,
        ))
        reg.revoke_approval("old-approval")
        restored = AuthorityRegistry.from_dict(reg.to_dict())
        self.assertEqual(restored.authorities["Partner_001"].approved_tracks, ("track1", "t2a"))
        self.assertTrue(restored.approval_records["promo-002"].cryptographic_verified)
        self.assertIn("old-approval", restored.revoked_approvals)


if __name__ == "__main__":
    unittest.main()
