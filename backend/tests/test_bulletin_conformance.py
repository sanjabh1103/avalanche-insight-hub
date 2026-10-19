"""Tests for the manual bulletin conformance command."""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from backend.scripts.bulletin_conformance import run_conformance


class TestBulletinConformance(unittest.TestCase):
    @patch('backend.common.Partner_bulletin_adapter.list_recent_bulletins')
    def test_no_bulletins_found(self, mock_list: MagicMock) -> None:
        mock_list.return_value = []
        report = run_conformance(days=7)
        self.assertEqual(report['exit_code'], 2)
        self.assertEqual(report['status'], 'no_bulletins_found')

    @patch('backend.common.Partner_bulletin_adapter.fetch_bulletin')
    def test_complete_bulletin(self, mock_fetch: MagicMock) -> None:
        from backend.common.Partner_bulletin_adapter import ParseResult, PartnerBulletinRecord, PartnerBulletinRow
        from datetime import date
        record = PartnerBulletinRecord(
            bulletin_id='TEST_001',
            issue_date=date(2026, 4, 16),
            source_url='https://example.com/test.pdf',
            rows=[
                PartnerBulletinRow(district='Lahaul', altitude_band='3000-4000 m', danger_level=3),
            ],
        )
        result = ParseResult(
            record=record,
            is_complete=True,
            complete_row_count=1,
            parse_error=None,
            provenance_hash='abc123',
        )
        mock_fetch.return_value = result
        report = run_conformance(url='https://example.com/test.pdf')
        self.assertEqual(report['exit_code'], 0)
        self.assertTrue(report['is_complete'])
        self.assertEqual(report['complete_row_count'], 1)

    @patch('backend.common.Partner_bulletin_adapter.fetch_bulletin')
    def test_incomplete_bulletin(self, mock_fetch: MagicMock) -> None:
        from backend.common.Partner_bulletin_adapter import ParseResult, PartnerBulletinRecord
        record = PartnerBulletinRecord(
            bulletin_id='TEST_002',
            issue_date=None,
            source_url='https://example.com/bad.pdf',
            rows=[],
        )
        result = ParseResult(
            record=record,
            is_complete=False,
            complete_row_count=0,
            parse_error='issue_date_missing',
            provenance_hash='def456',
        )
        mock_fetch.return_value = result
        report = run_conformance(url='https://example.com/bad.pdf')
        self.assertEqual(report['exit_code'], 1)
        self.assertFalse(report['is_complete'])
        self.assertEqual(report['parse_error'], 'issue_date_missing')


if __name__ == '__main__':
    unittest.main()
