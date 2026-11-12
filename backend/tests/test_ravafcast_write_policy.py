"""Fail-closed tests for the six-hour RAvaFcast write policy."""
from __future__ import annotations

import argparse
import os
import unittest
from unittest.mock import patch

from backend.daily_inference import _enforce_ravafcast_reference_write_policy


class RavafcastReferenceWritePolicyTests(unittest.TestCase):
    def test_six_hour_defaults_to_dry_run(self) -> None:
        args = argparse.Namespace(dry_run=False)
        with patch.dict(os.environ, {'RAVAFCAST_CADENCE_HOURS': '6'}, clear=False):
            for key in ('RAVAFCAST_REFERENCE_TARGET', 'RAVAFCAST_REFERENCE_WRITE_APPROVED'):
                os.environ.pop(key, None)
            result = _enforce_ravafcast_reference_write_policy(args)
        self.assertTrue(result['forced_dry_run'])
        self.assertFalse(result['write_allowed'])
        self.assertTrue(args.dry_run)

    def test_production_target_is_never_allowed(self) -> None:
        args = argparse.Namespace(dry_run=False)
        with patch.dict(os.environ, {
            'RAVAFCAST_CADENCE_HOURS': '6',
            'RAVAFCAST_REFERENCE_TARGET': 'production',
            'RAVAFCAST_REFERENCE_WRITE_APPROVED': 'true',
        }, clear=False):
            result = _enforce_ravafcast_reference_write_policy(args)
        self.assertFalse(result['write_allowed'])
        self.assertTrue(result['forced_dry_run'])
        self.assertTrue(args.dry_run)

    def test_staging_requires_explicit_approval(self) -> None:
        args = argparse.Namespace(dry_run=False)
        with patch.dict(os.environ, {
            'RAVAFCAST_CADENCE_HOURS': '6',
            'RAVAFCAST_REFERENCE_TARGET': 'staging',
            'RAVAFCAST_REFERENCE_WRITE_APPROVED': 'true',
        }, clear=False):
            result = _enforce_ravafcast_reference_write_policy(args)
        self.assertTrue(result['write_allowed'])
        self.assertFalse(result['forced_dry_run'])
        self.assertFalse(args.dry_run)

    def test_daily_cadence_does_not_force_reference_dry_run(self) -> None:
        args = argparse.Namespace(dry_run=False)
        with patch.dict(os.environ, {
            'RAVAFCAST_CADENCE_HOURS': '24',
            'RAVAFCAST_REFERENCE_TARGET': 'production',
            'RAVAFCAST_REFERENCE_WRITE_APPROVED': 'false',
        }, clear=False):
            result = _enforce_ravafcast_reference_write_policy(args)
        self.assertFalse(result['forced_dry_run'])
        self.assertFalse(result['write_allowed'])
        self.assertFalse(args.dry_run)


if __name__ == '__main__':
    unittest.main()
