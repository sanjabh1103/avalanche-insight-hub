"""Tests for CAP release approval module."""
from __future__ import annotations

import os
import unittest

from backend.common.cap_release_approval import (
    ReleaseApproval,
    request_approval,
    approve_release,
    reject_release,
    check_release_approved,
    CAP_RELEASE_APPROVAL_ENABLED,
)


class TestRequestApproval(unittest.TestCase):
    def test_creates_pending(self):
        approval = request_approval('cap_001', '<alert>test</alert>')
        self.assertEqual(approval.cap_alert_id, 'cap_001')
        self.assertEqual(approval.status, 'pending')

    def test_stores_xml_hash(self):
        approval = request_approval('cap_001', '<alert>test</alert>')
        self.assertIn('cap_alert_xml_hash', approval.metadata)


class TestApproveRelease(unittest.TestCase):
    def test_approve_sets_fields(self):
        approval = request_approval('cap_001')
        approved = approve_release(approval, 'user_1', 'Dr. Test', 'SLF')
        self.assertEqual(approved.status, 'approved')
        self.assertEqual(approved.approver_id, 'user_1')
        self.assertEqual(approved.approver_name, 'Dr. Test')
        self.assertEqual(approved.authority_org, 'SLF')
        self.assertIsNotNone(approved.signature)
        self.assertIsNotNone(approved.approval_timestamp)
        self.assertIsNotNone(approved.release_artifact_ref)
        self.assertIsNotNone(approved.audit_event_id)

    def test_to_dict(self):
        approval = request_approval('cap_001')
        approved = approve_release(approval, 'user_1', 'Dr. Test', 'SLF')
        d = approved.to_dict()
        self.assertEqual(d['status'], 'approved')
        self.assertEqual(d['approver_name'], 'Dr. Test')


class TestRejectRelease(unittest.TestCase):
    def test_reject_sets_fields(self):
        approval = request_approval('cap_001')
        rejected = reject_release(approval, 'user_1', 'Dr. Test', 'SLF', 'Data stale')
        self.assertEqual(rejected.status, 'rejected')
        self.assertEqual(rejected.rejection_reason, 'Data stale')


class TestCheckReleaseApproved(unittest.TestCase):
    def setUp(self):
        os.environ['CAP_RELEASE_APPROVAL_ENABLED'] = 'true'
        import importlib
        import backend.common.cap_release_approval as mod
        importlib.reload(mod)
        self.mod = mod

    def tearDown(self):
        os.environ['CAP_RELEASE_APPROVAL_ENABLED'] = 'false'

    def test_disabled_always_approved(self):
        os.environ['CAP_RELEASE_APPROVAL_ENABLED'] = 'false'
        import importlib
        import backend.common.cap_release_approval as mod
        importlib.reload(mod)
        approved, reason = mod.check_release_approved(None)
        self.assertTrue(approved)
        self.assertIsNone(reason)

    def test_no_approval_record(self):
        approved, reason = self.mod.check_release_approved(None)
        self.assertFalse(approved)
        self.assertIn('no approval record', reason)

    def test_pending_not_approved(self):
        approval = self.mod.request_approval('cap_001')
        approved, reason = self.mod.check_release_approved(approval)
        self.assertFalse(approved)
        self.assertIn('pending', reason)

    def test_approved_with_valid_signature(self):
        approval = self.mod.request_approval('cap_001')
        approved = self.mod.approve_release(approval, 'user_1', 'Dr. Test', 'SLF')
        is_approved, reason = self.mod.check_release_approved(approved)
        self.assertTrue(is_approved)
        self.assertIsNone(reason)

    def test_rejected_not_approved(self):
        approval = self.mod.request_approval('cap_001')
        rejected = self.mod.reject_release(approval, 'user_1', 'Dr. Test', 'SLF', 'stale')
        is_approved, reason = self.mod.check_release_approved(rejected)
        self.assertFalse(is_approved)
        self.assertIn('rejected', reason)

    def test_tampered_signature_fails(self):
        approval = self.mod.request_approval('cap_001')
        approved = self.mod.approve_release(approval, 'user_1', 'Dr. Test', 'SLF')
        approved.signature = 'tampered_signature_123'
        is_approved, reason = self.mod.check_release_approved(approved)
        self.assertFalse(is_approved)
        self.assertIn('invalid signature', reason)


if __name__ == '__main__':
    unittest.main()
