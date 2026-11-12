"""Tests for Partner_archive_discovery.py — P2: Archive discovery contract.

P2 exit gate: Archive accounting satisfies listed = candidate + excluded + malformed;
no "254 bulletins" claim remains.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from backend.common.Partner_archive_discovery import (
    PartnerArchiveEntryV1,
    Partner_ARCHIVE_DISCOVERY_ENABLED,
    KIND_BULLETIN,
    KIND_CLOSING_LETTER,
    KIND_BLANK,
    KIND_MALFORMED_DATE,
    KIND_INVALID_DOCUMENT,
    KIND_NONSTANDARD_FILENAME,
    KIND_PAGE_NOT_FOUND,
    STATUS_DISCOVERED,
    STATUS_EXCLUDED,
    STATUS_MALFORMED,
    classify_entry,
    parse_archive_date,
    parse_archive_page_html,
    build_archive_manifest,
    save_archive_manifest,
    load_archive_manifest,
    discover_archive,
)


class TestParseArchiveDate(unittest.TestCase):
    """Date parsing from archive table strings."""

    def test_dmy_format(self) -> None:
        self.assertEqual(parse_archive_date('15-01-2026'), date(2026, 1, 15))

    def test_ymd_format(self) -> None:
        self.assertEqual(parse_archive_date('2026-01-15'), date(2026, 1, 15))

    def test_malformed_year_0026(self) -> None:
        """The '20-03-0026' malformed date from the live archive must not parse."""
        self.assertIsNone(parse_archive_date('20-03-0026'))

    def test_empty_string(self) -> None:
        self.assertIsNone(parse_archive_date(''))

    def test_invalid_date(self) -> None:
        self.assertIsNone(parse_archive_date('31-02-2026'))  # Feb 31 doesn't exist

    def test_year_before_2000_rejected(self) -> None:
        self.assertIsNone(parse_archive_date('15-01-1999'))


class TestClassifyEntry(unittest.TestCase):
    """Classification of individual archive rows."""

    def test_standard_bulletin(self) -> None:
        entry = classify_entry(
            serial=1,
            title='Avalanche Warning Bulletin- 03 June 2026',
            date_str='03-06-2026',
            url='https://Partner.gov.in/Partner/sites/default/files/avalanche_warning_bulletin/Partner_AWB_03-Jun-2026.pdf',
            file_size='745.46 KB',
            page_number=0,
        )
        self.assertEqual(entry.entry_kind, KIND_BULLETIN)
        self.assertEqual(entry.discovery_status, STATUS_DISCOVERED)
        self.assertTrue(entry.is_bulletin)

    def test_closing_letter(self) -> None:
        entry = classify_entry(
            serial=1,
            title='Closing of Operational Avalanche Forecasting Services for the Winter Season 2025-26',
            date_str='03-06-2026',
            url='https://Partner.gov.in/Partner/sites/default/files/avalanche_warning_bulletin/NDMA_closingofwinter2025_26.pdf',
            file_size='409.91 KB',
            page_number=0,
        )
        self.assertEqual(entry.entry_kind, KIND_CLOSING_LETTER)
        self.assertEqual(entry.discovery_status, STATUS_EXCLUDED)

    def test_blank_entry(self) -> None:
        entry = classify_entry(
            serial=5, title='', date_str='', url='', file_size='', page_number=0,
        )
        self.assertEqual(entry.entry_kind, KIND_BLANK)
        self.assertEqual(entry.discovery_status, STATUS_EXCLUDED)

    def test_malformed_date(self) -> None:
        """The '20-03-0026' date from the live archive must be classified as malformed."""
        entry = classify_entry(
            serial=254,
            title='Avalanche Warning Bulletin- 20 March 2026',
            date_str='20-03-0026',
            url='https://Partner.gov.in/Partner/sites/default/files/avalanche_warning_bulletin/Partner_AWB_20-Mar-2026.pdf',
            file_size='841.23 KB',
            page_number=25,
        )
        self.assertEqual(entry.entry_kind, KIND_MALFORMED_DATE)
        self.assertEqual(entry.discovery_status, STATUS_MALFORMED)

    def test_nonstandard_filename(self) -> None:
        entry = classify_entry(
            serial=1,
            title='Some document',
            date_str='15-01-2026',
            url='https://Partner.gov.in/Partner/sites/default/files/avalanche_warning_bulletin/NDMA_special_notice.pdf',
            file_size='100 KB',
            page_number=0,
        )
        self.assertEqual(entry.entry_kind, KIND_NONSTANDARD_FILENAME)
        self.assertEqual(entry.discovery_status, STATUS_EXCLUDED)

    def test_non_pdf_url(self) -> None:
        entry = classify_entry(
            serial=1,
            title='Some document',
            date_str='15-01-2026',
            url='https://Partner.gov.in/some-page.html',
            file_size='100 KB',
            page_number=0,
        )
        self.assertEqual(entry.entry_kind, KIND_INVALID_DOCUMENT)
        self.assertEqual(entry.discovery_status, STATUS_EXCLUDED)

    def test_page_not_found(self) -> None:
        entry = classify_entry(
            serial=1,
            title='Page Not Found',
            date_str='15-01-2026',
            url='https://Partner.gov.in/not-found.pdf',
            file_size='0 KB',
            page_number=0,
        )
        self.assertEqual(entry.entry_kind, KIND_PAGE_NOT_FOUND)
        self.assertEqual(entry.discovery_status, STATUS_EXCLUDED)

    def test_no_url_with_title(self) -> None:
        entry = classify_entry(
            serial=1, title='Some title', date_str='15-01-2026',
            url='', file_size='100 KB', page_number=0,
        )
        self.assertEqual(entry.entry_kind, KIND_INVALID_DOCUMENT)
        self.assertEqual(entry.discovery_status, STATUS_EXCLUDED)


class TestPartnerArchiveEntryV1(unittest.TestCase):
    """Archive entry dataclass properties and serialization."""

    def test_to_dict(self) -> None:
        entry = PartnerArchiveEntryV1(
            serial=1, title='Test', posted_date='15-01-2026',
            source_url='https://example.com/test.pdf',
            entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED,
            page_number=0, file_size='100 KB',
        )
        d = entry.to_dict()
        self.assertEqual(d['serial'], 1)
        self.assertEqual(d['entry_kind'], KIND_BULLETIN)
        self.assertEqual(d['discovery_status'], STATUS_DISCOVERED)

    def test_is_bulletin_property(self) -> None:
        entry = PartnerArchiveEntryV1(
            serial=1, title='Test', posted_date='15-01-2026',
            source_url='https://example.com/test.pdf',
            entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED,
            page_number=0,
        )
        self.assertTrue(entry.is_bulletin)
        self.assertFalse(entry.is_excluded)
        self.assertFalse(entry.is_malformed)

    def test_is_excluded_property(self) -> None:
        entry = PartnerArchiveEntryV1(
            serial=1, title='Test', posted_date='15-01-2026',
            source_url=None,
            entry_kind=KIND_BLANK, discovery_status=STATUS_EXCLUDED,
            page_number=0,
        )
        self.assertFalse(entry.is_bulletin)
        self.assertTrue(entry.is_excluded)

    def test_is_malformed_property(self) -> None:
        entry = PartnerArchiveEntryV1(
            serial=1, title='Test', posted_date='20-03-0026',
            source_url='https://example.com/test.pdf',
            entry_kind=KIND_MALFORMED_DATE, discovery_status=STATUS_MALFORMED,
            page_number=0,
        )
        self.assertTrue(entry.is_malformed)

    def test_frozen_dataclass(self) -> None:
        """Archive entries are immutable."""
        entry = PartnerArchiveEntryV1(
            serial=1, title='Test', posted_date='15-01-2026',
            source_url='https://example.com/test.pdf',
            entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED,
            page_number=0,
        )
        with self.assertRaises((AttributeError, TypeError)):
            entry.serial = 999  # type: ignore[misc]


class TestParseArchivePageHtml(unittest.TestCase):
    """Parsing HTML from archive pages."""

    def test_parse_page_with_bulletins(self) -> None:
        html = """
        <table>
            <tr><th>S.No</th><th>Title</th><th>Date</th><th>Type/Size</th><th>Link</th></tr>
            <tr>
                <td>1</td>
                <td>Avalanche Warning Bulletin- 03 June 2026</td>
                <td>03-06-2026</td>
                <td>745.46 KB</td>
                <td><a href="/Partner/sites/default/files/avalanche_warning_bulletin/Partner_AWB_03-Jun-2026.pdf">View</a></td>
            </tr>
            <tr>
                <td>2</td>
                <td>Avalanche Warning Bulletin- 02 June 2026</td>
                <td>02-06-2026</td>
                <td>745.59 KB</td>
                <td><a href="/Partner/sites/default/files/avalanche_warning_bulletin/Partner_AWB_02-Jun-2026.pdf">View</a></td>
            </tr>
        </table>
        """
        entries = parse_archive_page_html(html, page_num=0)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].entry_kind, KIND_BULLETIN)
        self.assertEqual(entries[1].entry_kind, KIND_BULLETIN)

    def test_parse_page_with_closing_letter(self) -> None:
        html = """
        <table>
            <tr><th>S.No</th><th>Title</th><th>Date</th><th>Type/Size</th><th>Link</th></tr>
            <tr>
                <td>1</td>
                <td>Closing of Operational Avalanche Forecasting Services for the Winter Season 2025-26</td>
                <td>03-06-2026</td>
                <td>409.91 KB</td>
                <td><a href="/Partner/sites/default/files/avalanche_warning_bulletin/NDMA_closingofwinter2025_26.pdf">View</a></td>
            </tr>
        </table>
        """
        entries = parse_archive_page_html(html, page_num=0)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].entry_kind, KIND_CLOSING_LETTER)

    def test_parse_page_with_malformed_date(self) -> None:
        html = """
        <table>
            <tr><th>S.No</th><th>Title</th><th>Date</th><th>Type/Size</th><th>Link</th></tr>
            <tr>
                <td>254</td>
                <td>Avalanche Warning Bulletin- 20 March 2026</td>
                <td>20-03-0026</td>
                <td>841.23 KB</td>
                <td><a href="/Partner/sites/default/files/avalanche_warning_bulletin/Partner_AWB_20-Mar-2026.pdf">View</a></td>
            </tr>
        </table>
        """
        entries = parse_archive_page_html(html, page_num=25)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].entry_kind, KIND_MALFORMED_DATE)

    def test_parse_empty_page(self) -> None:
        entries = parse_archive_page_html('<html><body>No results</body></html>', page_num=99)
        self.assertEqual(entries, [])


class TestBuildArchiveManifest(unittest.TestCase):
    """Manifest building and accounting check."""

    def test_accounting_check_passes(self) -> None:
        """P2 exit gate: listed = candidate + excluded + malformed."""
        entries = [
            PartnerArchiveEntryV1(serial=1, title='B1', posted_date='01-01-2026',
                source_url='https://example.com/Partner_AWB_01-Jan-2026.pdf',
                entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED, page_number=0),
            PartnerArchiveEntryV1(serial=2, title='Closing', posted_date='02-01-2026',
                source_url='https://example.com/closing.pdf',
                entry_kind=KIND_CLOSING_LETTER, discovery_status=STATUS_EXCLUDED, page_number=0),
            PartnerArchiveEntryV1(serial=3, title='Bad date', posted_date='20-03-0026',
                source_url='https://example.com/Partner_AWB_20-Mar-2026.pdf',
                entry_kind=KIND_MALFORMED_DATE, discovery_status=STATUS_MALFORMED, page_number=0),
        ]
        manifest = build_archive_manifest(entries)
        self.assertTrue(manifest['accounting_check'])
        self.assertEqual(manifest['total_listed'], 3)
        self.assertEqual(manifest['total_candidate'], 1)
        self.assertEqual(manifest['total_excluded'], 1)
        self.assertEqual(manifest['total_malformed'], 1)

    def test_kind_counts(self) -> None:
        entries = [
            PartnerArchiveEntryV1(serial=1, title='B1', posted_date='01-01-2026',
                source_url='https://example.com/Partner_AWB_01-Jan-2026.pdf',
                entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED, page_number=0),
            PartnerArchiveEntryV1(serial=2, title='B2', posted_date='02-01-2026',
                source_url='https://example.com/Partner_AWB_02-Jan-2026.pdf',
                entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED, page_number=0),
            PartnerArchiveEntryV1(serial=3, title='', posted_date='',
                source_url=None,
                entry_kind=KIND_BLANK, discovery_status=STATUS_EXCLUDED, page_number=0),
        ]
        manifest = build_archive_manifest(entries)
        self.assertEqual(manifest['kind_counts'][KIND_BULLETIN], 2)
        self.assertEqual(manifest['kind_counts'][KIND_BLANK], 1)
        self.assertEqual(manifest['bulletin_count'], 2)

    def test_no_254_claim(self) -> None:
        """The manifest must not claim '254 bulletins' — it reports classified counts."""
        entries = [
            PartnerArchiveEntryV1(serial=1, title='B1', posted_date='01-01-2026',
                source_url='https://example.com/Partner_AWB_01-Jan-2026.pdf',
                entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED, page_number=0),
            PartnerArchiveEntryV1(serial=2, title='Closing', posted_date='02-01-2026',
                source_url='https://example.com/closing.pdf',
                entry_kind=KIND_CLOSING_LETTER, discovery_status=STATUS_EXCLUDED, page_number=0),
            PartnerArchiveEntryV1(serial=3, title='Bad', posted_date='20-03-0026',
                source_url='https://example.com/Partner_AWB_20-Mar-2026.pdf',
                entry_kind=KIND_MALFORMED_DATE, discovery_status=STATUS_MALFORMED, page_number=0),
        ]
        manifest = build_archive_manifest(entries)
        # The manifest reports total_listed (all rows) and bulletin_count (classified bulletins)
        # They are different numbers when there are non-bulletin entries
        self.assertEqual(manifest['total_listed'], 3)
        self.assertEqual(manifest['bulletin_count'], 1)
        self.assertNotEqual(manifest['total_listed'], manifest['bulletin_count'])


class TestG3ArchiveProvenance(unittest.TestCase):
    """G3: Archive manifest has page hashes, fetch failures, and completeness flag."""

    def test_g3_manifest_has_completeness_flag(self) -> None:
        """G3: Manifest must have a discovery_complete flag."""
        entries = [
            PartnerArchiveEntryV1(serial=1, title='B1', posted_date='01-01-2026',
                source_url='https://example.com/Partner_AWB_01-Jan-2026.pdf',
                entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED, page_number=0),
        ]
        manifest = build_archive_manifest(entries)
        self.assertIn('discovery_complete', manifest)
        self.assertIsInstance(manifest['discovery_complete'], bool)

    def test_g3_manifest_has_page_hashes(self) -> None:
        """G3: Manifest must have page_hashes field for source snapshot verification."""
        entries = [
            PartnerArchiveEntryV1(serial=1, title='B1', posted_date='01-01-2026',
                source_url='https://example.com/Partner_AWB_01-Jan-2026.pdf',
                entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED, page_number=0),
        ]
        manifest = build_archive_manifest(entries)
        self.assertIn('page_hashes', manifest)
        self.assertIn('page_hash_count', manifest)

    def test_g3_manifest_has_fetch_failures(self) -> None:
        """G3: Manifest must have fetch_failures field for error tracking."""
        entries = [
            PartnerArchiveEntryV1(serial=1, title='B1', posted_date='01-01-2026',
                source_url='https://example.com/Partner_AWB_01-Jan-2026.pdf',
                entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED, page_number=0),
        ]
        manifest = build_archive_manifest(entries)
        self.assertIn('fetch_failures', manifest)
        self.assertIn('fetch_failure_count', manifest)


class TestSaveLoadManifest(unittest.TestCase):
    """Manifest persistence for resumable discovery."""

    def test_save_and_load_manifest(self) -> None:
        entries = [
            PartnerArchiveEntryV1(serial=1, title='Test', posted_date='01-01-2026',
                source_url='https://example.com/test.pdf',
                entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED, page_number=0),
        ]
        manifest = build_archive_manifest(entries)
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = Path(f.name)
        try:
            save_archive_manifest(manifest, path)
            loaded = load_archive_manifest(path)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded['total_listed'], 1)
        finally:
            path.unlink()

    def test_load_nonexistent_returns_none(self) -> None:
        self.assertIsNone(load_archive_manifest(Path('/nonexistent/manifest.json')))

    def test_saved_manifest_is_self_hashed_and_tamper_evident(self) -> None:
        manifest = build_archive_manifest([])
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = Path(f.name)
        try:
            save_archive_manifest(manifest, path)
            loaded = load_archive_manifest(path)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertRegex(loaded['manifest_sha256'], r'^[0-9a-f]{64}$')
            tampered = dict(loaded)
            tampered['total_listed'] = 999
            path.write_text(json.dumps(tampered), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                load_archive_manifest(path)
        finally:
            path.unlink(missing_ok=True)


class TestDiscoverArchiveDisabled(unittest.TestCase):
    """Discovery respects the enabled flag."""

    def test_disabled_returns_empty(self) -> None:
        import backend.common.Partner_archive_discovery as mod
        original = mod.Partner_ARCHIVE_DISCOVERY_ENABLED
        try:
            mod.Partner_ARCHIVE_DISCOVERY_ENABLED = False
            result = discover_archive(max_pages=1)
            self.assertEqual(result, [])
            manifest = build_archive_manifest([])
            self.assertEqual(manifest['discovery_status'], 'disabled')
            self.assertFalse(manifest['discovery_complete'])
            self.assertEqual(manifest['stop_reason'], 'disabled')
        finally:
            mod.Partner_ARCHIVE_DISCOVERY_ENABLED = original

    def test_discovery_manifest_records_stop_reason_and_pages(self) -> None:
        import backend.common.Partner_archive_discovery as mod
        original = mod.Partner_ARCHIVE_DISCOVERY_ENABLED
        html = '''
        <table><tr><td>1</td><td>Avalanche Warning Bulletin</td><td>03-06-2026</td>
        <td>1 KB</td><td><a href="/Partner/sites/default/files/avalanche_warning_bulletin/Partner_AWB_03-Jun-2026.pdf">View</a></td></tr></table>
        '''
        try:
            mod.Partner_ARCHIVE_DISCOVERY_ENABLED = True
            with patch.object(mod, '_fetch_archive_page', side_effect=[
                (html, 'a' * 64, None),
                ('', 'b' * 64, None),
            ]):
                entries = discover_archive(max_pages=3, start_page=4)
            manifest = build_archive_manifest(entries)
            self.assertEqual(manifest['discovery_status'], 'complete')
            self.assertTrue(manifest['discovery_complete'])
            self.assertEqual(manifest['stop_reason'], 'empty_page')
            self.assertEqual(manifest['pages_attempted'], 2)
            self.assertEqual(manifest['page_hash_count'], 2)
        finally:
            mod.Partner_ARCHIVE_DISCOVERY_ENABLED = original


if __name__ == '__main__':
    unittest.main()
