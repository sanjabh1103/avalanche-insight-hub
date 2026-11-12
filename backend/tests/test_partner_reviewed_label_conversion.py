"""Tests for Partner_reviewed_label_conversion.py — G5: Blocked conversion interface.

G5 exit gate: The interface is defined but BLOCKED. No code path converts
a public candidate to a training-eligible label without all required
Partner approval inputs.
"""
from __future__ import annotations

import unittest

from backend.common.Partner_reviewed_label_conversion import (
    CONVERSION_BLOCKED_REASON,
    CONVERSION_STATUS,
    PartnerApprovalInputsV1,
    ReviewedLabelConversionV1,
    get_conversion_status,
)


class TestConversionStatus(unittest.TestCase):
    """G5: The conversion status is always BLOCKED."""

    def test_conversion_status_is_blocked(self) -> None:
        status = get_conversion_status()
        self.assertEqual(status['status'], 'BLOCKED')

    def test_conversion_has_blocked_reason(self) -> None:
        status = get_conversion_status()
        self.assertIn('blocked_reason', status)
        self.assertIn('Partner', status['blocked_reason'])

    def test_conversion_interface_defined_but_not_implemented(self) -> None:
        status = get_conversion_status()
        self.assertTrue(status['interface_defined'])
        self.assertFalse(status['implementation_exists'])

    def test_conversion_lists_required_inputs(self) -> None:
        status = get_conversion_status()
        required = status['required_inputs']
        self.assertIn('approved_label_inventory', required)
        self.assertIn('approved_by', required)
        self.assertIn('signature', required)
        self.assertIn('rights_status (must be "approved")', required)


class TestPartnerApprovalInputs(unittest.TestCase):
    """G5: PartnerApprovalInputsV1 tracks missing inputs."""

    def test_empty_inputs_not_complete(self) -> None:
        inputs = PartnerApprovalInputsV1()
        self.assertFalse(inputs.is_complete)

    def test_empty_inputs_lists_all_missing(self) -> None:
        inputs = PartnerApprovalInputsV1()
        missing = inputs.missing_inputs
        self.assertGreater(len(missing), 10)
        self.assertIn('approved_label_inventory', missing)
        self.assertIn('approved_by', missing)
        self.assertIn('signature', missing)

    def test_partial_inputs_still_not_complete(self) -> None:
        inputs = PartnerApprovalInputsV1(
            approved_by='Dr. Test',
            rights_status='approved',
            quality_status='reviewed',
        )
        self.assertFalse(inputs.is_complete)
        missing = inputs.missing_inputs
        self.assertIn('approved_label_inventory', missing)
        self.assertIn('signature', missing)
        # Should NOT list fields that are provided
        self.assertNotIn('approved_by', missing)
        self.assertNotIn('rights_status (must be "approved", got "approved")', missing)

    def test_wrong_rights_status_blocks(self) -> None:
        inputs = PartnerApprovalInputsV1(
            approved_by='Dr. Test',
            rights_status='pending',  # Wrong — must be 'approved'
        )
        self.assertFalse(inputs.is_complete)
        missing = inputs.missing_inputs
        self.assertTrue(any('rights_status' in m for m in missing))

    def test_wrong_quality_status_blocks(self) -> None:
        inputs = PartnerApprovalInputsV1(
            approved_by='Dr. Test',
            quality_status='unreviewed',  # Wrong — must be 'reviewed'
        )
        self.assertFalse(inputs.is_complete)
        missing = inputs.missing_inputs
        self.assertTrue(any('quality_status' in m for m in missing))


class TestReviewedLabelConversionInterface(unittest.TestCase):
    """G5: The ReviewedLabelConversionV1 interface is abstract and blocked."""

    def test_cannot_instantiate_abstract_class(self) -> None:
        """The interface is abstract — cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            ReviewedLabelConversionV1()  # type: ignore[abstract]

    def test_interface_has_required_methods(self) -> None:
        """The interface defines can_convert, get_blocking_reasons, and convert."""
        self.assertTrue(hasattr(ReviewedLabelConversionV1, 'can_convert'))
        self.assertTrue(hasattr(ReviewedLabelConversionV1, 'get_blocking_reasons'))
        self.assertTrue(hasattr(ReviewedLabelConversionV1, 'convert'))


if __name__ == '__main__':
    unittest.main()
