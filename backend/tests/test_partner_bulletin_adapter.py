"""Tests for Partner_bulletin_adapter.py."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from backend.common.Partner_bulletin_adapter import (
    PartnerBulletinRecord,
    PartnerBulletinRow,
    Partner_BULLETIN_VALIDATION_ENABLED,
    DANGER_LEVELS,
    parse_danger_level,
    parse_zone,
    parse_bulletin_date,
    parse_bulletin_text,
    parse_bulletin_rows,
    parse_bulletin_with_provenance,
    parse_district,
    parse_altitude_band,
    fetch_bulletin,
    list_recent_bulletins,
    _extract_pdf_text,
    verify_provenance_hash,
)


class TestParseDangerLevel(unittest.TestCase):
    def test_level_3(self):
        self.assertEqual(parse_danger_level('Danger Level: 3'), 3)

    def test_level_5(self):
        self.assertEqual(parse_danger_level('Avalanche Warning Level: 5'), 5)

    def test_level_2_of_5(self):
        self.assertEqual(parse_danger_level('Level: 2 of 5'), 2)

    def test_no_match(self):
        self.assertIsNone(parse_danger_level('No danger info here'))

    def test_out_of_range(self):
        self.assertIsNone(parse_danger_level('Danger Level: 7'))


class TestParseZone(unittest.TestCase):
    def test_zone(self):
        self.assertEqual(parse_zone('Zone: Great Himalaya\nNext line'), 'Great Himalaya')

    def test_sector(self):
        self.assertEqual(parse_zone('Sector: Pir Panjal\n'), 'Pir Panjal')

    def test_no_match(self):
        self.assertIsNone(parse_zone('Avalanche warning bulletin for today'))


class TestParseBulletinDate(unittest.TestCase):
    def test_dmy_format(self):
        self.assertEqual(parse_bulletin_date('15/01/2026'), date(2026, 1, 15))

    def test_ymd_format(self):
        self.assertEqual(parse_bulletin_date('2026-01-15'), date(2026, 1, 15))

    def test_no_match(self):
        self.assertIsNone(parse_bulletin_date('No date here'))


class TestParseBulletinText(unittest.TestCase):
    def test_full_parse(self):
        text = 'Partner Avalanche Warning Bulletin\nDate: 15/01/2026\nZone: Great Himalaya\nDanger Level: 4\nValid until: 18/01/2026'
        record = parse_bulletin_text(text, 'Partner_AWB_20260115', source_url='https://Partner.gov.in/Partner_AWB_20260115.pdf')
        self.assertEqual(record.bulletin_id, 'Partner_AWB_20260115')
        self.assertEqual(record.issue_date, date(2026, 1, 15))
        self.assertEqual(record.danger_level, 4)
        self.assertEqual(record.danger_level_label, 'very_high')
        self.assertEqual(record.zone, 'Great Himalaya')
        self.assertEqual(record.source_url, 'https://Partner.gov.in/Partner_AWB_20260115.pdf')


class TestPartnerBulletinRecord(unittest.TestCase):
    def test_to_dict(self):
        record = PartnerBulletinRecord(
            bulletin_id='Partner_AWB_001',
            issue_date=date(2026, 1, 15),
            danger_level=3,
            danger_level_label='high',
            zone='Great Himalaya',
        )
        d = record.to_dict()
        self.assertEqual(d['bulletin_id'], 'Partner_AWB_001')
        self.assertEqual(d['danger_level'], 3)
        self.assertEqual(d['provenance'], 'Partner_public_bulletin')


class TestDisabled(unittest.TestCase):
    def test_fetch_returns_none_when_disabled(self):
        import backend.common.Partner_bulletin_adapter as da
        original = da.Partner_BULLETIN_VALIDATION_ENABLED
        try:
            da.Partner_BULLETIN_VALIDATION_ENABLED = False
            result = fetch_bulletin('https://example.com/bulletin.pdf')
            self.assertIsNone(result)
        finally:
            da.Partner_BULLETIN_VALIDATION_ENABLED = original

    def test_list_recent_returns_empty_when_disabled(self):
        import backend.common.Partner_bulletin_adapter as da
        original = da.Partner_BULLETIN_VALIDATION_ENABLED
        try:
            da.Partner_BULLETIN_VALIDATION_ENABLED = False
            result = list_recent_bulletins(days=7)
            self.assertEqual(result, [])
        finally:
            da.Partner_BULLETIN_VALIDATION_ENABLED = original


class TestPdfExtraction(unittest.TestCase):
    def test_extract_pdf_text_raises_without_pdfplumber(self) -> None:
        # When pdfplumber is not available, should raise RuntimeError
        content = b'Danger Level: 3\nZone: Lahaul\n'
        try:
            import pdfplumber  # noqa: F401
            # pdfplumber is installed — non-PDF content raises PDFSyntaxError
            with self.assertRaises(Exception):
                _extract_pdf_text(content)
        except (RuntimeError, ModuleNotFoundError):
            with self.assertRaises(RuntimeError):
                _extract_pdf_text(content)

    def test_extract_pdf_text_empty_content(self) -> None:
        try:
            import pdfplumber  # noqa: F401
            # Empty bytes will raise PDFSyntaxError from pdfplumber
            with self.assertRaises(Exception):
                _extract_pdf_text(b'')
        except (RuntimeError, ModuleNotFoundError):
            with self.assertRaises(RuntimeError):
                _extract_pdf_text(b'')


class TestDistrictAndAltitudeParsing(unittest.TestCase):
    def test_parse_district(self) -> None:
        self.assertEqual(parse_district('District: Lahaul and Spiti\n'), 'Lahaul and Spiti')

    def test_parse_district_area(self) -> None:
        self.assertEqual(parse_district('Area: Kargil\n'), 'Kargil')

    def test_parse_district_no_match(self) -> None:
        self.assertIsNone(parse_district('Avalanche warning bulletin for today'))

    def test_parse_altitude_band_range(self) -> None:
        result = parse_altitude_band('Altitude: 3000 - 4000 m')
        self.assertIsNotNone(result)
        self.assertIn('3000', result)
        self.assertIn('4000', result)

    def test_parse_altitude_band_above(self) -> None:
        result = parse_altitude_band('Above: 3500 m')
        self.assertIsNotNone(result)
        self.assertIn('3500', result)

    def test_parse_altitude_band_no_match(self) -> None:
        self.assertIsNone(parse_altitude_band('No altitude info'))


class TestProvenanceHash(unittest.TestCase):
    def test_provenance_hash_computed(self) -> None:
        import backend.common.Partner_bulletin_adapter as da
        original = da.Partner_BULLETIN_VALIDATION_ENABLED
        try:
            da.Partner_BULLETIN_VALIDATION_ENABLED = True
            import hashlib
            content = b'Danger Level: 3\nZone: Lahaul\nDate: 15/01/2026\nDistrict: Lahaul  Altitude: 3000-4000 m  Danger Level: 3'
            expected_hash = hashlib.sha256(content).hexdigest()

            with unittest.mock.patch('urllib.request.urlopen') as mock_urlopen, \
                 unittest.mock.patch('backend.common.Partner_bulletin_adapter._extract_pdf_text', return_value=(content.decode('utf-8'), [])):
                mock_resp = unittest.mock.MagicMock()
                mock_resp.__enter__ = unittest.mock.Mock(return_value=mock_resp)
                mock_resp.__exit__ = unittest.mock.Mock(return_value=False)
                mock_resp.read = unittest.mock.Mock(return_value=content)
                mock_urlopen.return_value = mock_resp

                result = fetch_bulletin('https://Partner.gov.in/Partner_AWB_test.pdf')
                self.assertIsNotNone(result)
                self.assertIsNotNone(result.record)
                self.assertEqual(result.record.metadata['provenance_hash'], expected_hash)
                self.assertEqual(result.provenance_hash, expected_hash)
        finally:
            da.Partner_BULLETIN_VALIDATION_ENABLED = original


class TestListRecentBulletins(unittest.TestCase):
    def test_list_recent_bulletins_disabled_returns_empty(self) -> None:
        import backend.common.Partner_bulletin_adapter as da
        original = da.Partner_BULLETIN_VALIDATION_ENABLED
        try:
            da.Partner_BULLETIN_VALIDATION_ENABLED = False
            result = list_recent_bulletins(days=7)
            self.assertEqual(result, [])
        finally:
            da.Partner_BULLETIN_VALIDATION_ENABLED = original

    def test_list_recent_bulletins_finds_pdf_links(self) -> None:
        import backend.common.Partner_bulletin_adapter as da
        import unittest.mock
        original = da.Partner_BULLETIN_VALIDATION_ENABLED
        try:
            da.Partner_BULLETIN_VALIDATION_ENABLED = True
            html = b'<html><a href="/Partner_AWB_20260115.pdf">Bulletin 1</a></html>'
            content = b'Danger Level: 3\nZone: Lahaul\nDate: 15/01/2026\nDistrict: Lahaul  Altitude: 3000-4000 m  Danger Level: 3'
            import hashlib
            expected_hash = hashlib.sha256(content).hexdigest()
            registry = {'Partner_AWB_20260115': expected_hash}

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as reg_f:
                json.dump(registry, reg_f)
                reg_path = reg_f.name

            try:
                with unittest.mock.patch('urllib.request.urlopen') as mock_urlopen, \
                     unittest.mock.patch('backend.common.Partner_bulletin_adapter._extract_pdf_text', return_value=(content.decode('utf-8'), [])), \
                     unittest.mock.patch('backend.common.Partner_bulletin_adapter.Partner_PROVENANCE_REGISTRY_PATH', reg_path):
                    mock_resp_html = unittest.mock.MagicMock()
                    mock_resp_html.__enter__ = unittest.mock.Mock(return_value=mock_resp_html)
                    mock_resp_html.__exit__ = unittest.mock.Mock(return_value=False)
                    mock_resp_html.read = unittest.mock.Mock(return_value=html)

                    mock_resp_pdf = unittest.mock.MagicMock()
                    mock_resp_pdf.__enter__ = unittest.mock.Mock(return_value=mock_resp_pdf)
                    mock_resp_pdf.__exit__ = unittest.mock.Mock(return_value=False)
                    mock_resp_pdf.read = unittest.mock.Mock(return_value=content)

                    mock_urlopen.side_effect = [mock_resp_html, mock_resp_pdf]

                    records = list_recent_bulletins(days=365)
                    self.assertGreater(len(records), 0)
                    self.assertEqual(records[0].danger_level, 3)
            finally:
                Path(reg_path).unlink()
        finally:
            da.Partner_BULLETIN_VALIDATION_ENABLED = original


class TestMultiRowParsing(unittest.TestCase):
    def test_multi_row_bulletin_extracts_rows(self):
        text = (
            'Partner Avalanche Warning Bulletin\n'
            'Date: 16/04/2026\n'
            'Zone: Pir Panjal\n'
            'District: Baramulla  Altitude: 3000-4000 m  Danger Level: 3\n'
            'District: Kupwara  Altitude: 3500-4500 m  Danger Level: 4\n'
            'District: Bandipora  Altitude: 3000-4000 m  Danger Level: 2\n'
        )
        rows, partial = parse_bulletin_rows(text)
        self.assertGreaterEqual(len(rows), 1)

    def test_single_row_fallback(self):
        text = 'Date: 16/04/2026\nZone: Great Himalaya\nDanger Level: 3\nDistrict: Leh\nAltitude: 3500-4500 m'
        rows, partial = parse_bulletin_rows(text)
        # Line-by-line parser finds partial matches on separate lines; verify district and altitude are both captured
        all_rows = rows + partial
        districts = [r.district for r in all_rows if r.district]
        altitudes = [r.altitude_band for r in all_rows if r.altitude_band]
        self.assertIn('Leh', districts)
        self.assertIn('3500-4500 m', altitudes)

    def test_empty_text_returns_empty_rows(self):
        rows, partial = parse_bulletin_rows('')
        self.assertEqual(rows, [])
        self.assertEqual(partial, [])

    def test_bulletin_row_to_dict(self):
        row = PartnerBulletinRow(
            district='Baramulla',
            altitude_band='3000-4000 m',
            danger_level=3,
            danger_level_label='high',
        )
        d = row.to_dict()
        self.assertEqual(d['district'], 'Baramulla')
        self.assertEqual(d['danger_level'], 3)


class TestNoDateFallback(unittest.TestCase):
    def test_parse_returns_none_date_when_unparseable(self):
        text = 'Partner Avalanche Warning Bulletin\nZone: Great Himalaya\nDanger Level: 3'
        record = parse_bulletin_text(text, 'Partner_AWB_TEST')
        self.assertIsNone(record.issue_date)

    def test_parse_with_valid_date(self):
        text = 'Date: 16/04/2026\nZone: Great Himalaya\nDanger Level: 3'
        record = parse_bulletin_text(text, 'Partner_AWB_TEST')
        self.assertEqual(record.issue_date, date(2026, 4, 16))

    def test_to_dict_with_none_date(self):
        record = PartnerBulletinRecord(
            bulletin_id='TEST',
            issue_date=None,
            danger_level=3,
        )
        d = record.to_dict()
        self.assertIsNone(d['issue_date'])

    def test_record_includes_rows(self):
        text = 'Date: 16/04/2026\nDistrict: Baramulla  Altitude: 3000-4000 m  Danger Level: 3'
        record = parse_bulletin_text(text, 'Partner_AWB_TEST')
        self.assertGreaterEqual(len(record.rows), 1)
        d = record.to_dict()
        self.assertIn('rows', d)


class TestParseBulletinWithProvenance(unittest.TestCase):
    def test_complete_bulletin(self):
        text = 'Date: 16/04/2026\nDanger Level: 3\nDistrict: Baramulla  Altitude: 3000-4000 m  Danger Level: 3'
        # G-05: provenance verification requires a configured registry with matching hash
        registry = {'Partner_AWB_TEST': 'abc123'}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(registry, f)
            reg_path = f.name
        try:
            with patch('backend.common.Partner_bulletin_adapter.Partner_PROVENANCE_REGISTRY_PATH', reg_path):
                result = parse_bulletin_with_provenance(
                    text, 'Partner_AWB_TEST',
                    source_url='https://Partner.gov.in/Partner_AWB_TEST.pdf',
                    provenance_hash='abc123',
                )
            self.assertIsNotNone(result.record)
            self.assertTrue(result.is_complete)
            self.assertGreaterEqual(result.complete_row_count, 1)
            self.assertIsNone(result.parse_error)
            self.assertEqual(result.provenance_hash, 'abc123')
        finally:
            Path(reg_path).unlink()

    def test_missing_issue_date(self):
        text = 'Danger Level: 3\nDistrict: Baramulla  Danger Level: 3'
        result = parse_bulletin_with_provenance(text, 'Partner_AWB_TEST')
        self.assertIsNotNone(result.record)
        self.assertFalse(result.is_complete)
        self.assertEqual(result.parse_error, 'issue_date_missing')

    def test_no_complete_rows(self):
        text = 'Date: 16/04/2026\nDanger Level: 3'
        result = parse_bulletin_with_provenance(text, 'Partner_AWB_TEST')
        self.assertIsNotNone(result.record)
        self.assertFalse(result.is_complete)
        self.assertEqual(result.parse_error, 'no_complete_rows')

    def test_to_dict_serialization(self):
        text = 'Date: 16/04/2026\nDanger Level: 3\nDistrict: Baramulla  Danger Level: 3'
        result = parse_bulletin_with_provenance(text, 'Partner_AWB_TEST', provenance_hash='abc')
        d = result.to_dict()
        self.assertIn('is_complete', d)
        self.assertIn('complete_row_count', d)
        self.assertIn('parse_error', d)
        self.assertIn('provenance_hash', d)


class TestPdfplumberRuntimeDependency(unittest.TestCase):
    """Regression: pdfplumber must be installed at the pinned version in the active runtime."""

    def test_pdfplumber_installed_and_pinned(self) -> None:
        try:
            import pdfplumber
        except ImportError:
            self.fail('pdfplumber is not installed in the active runtime. Run: pip install pdfplumber==0.11.9')
        self.assertEqual(
            pdfplumber.__version__,
            '0.11.9',
            f'pdfplumber version mismatch: expected 0.11.9, got {pdfplumber.__version__}',
        )


class TestProvenanceRegistry(unittest.TestCase):
    """Regression: provenance registry must exercise match/mismatch behavior."""

    def test_provenance_hash_match(self) -> None:
        registry = {'Partner_TEST_001': 'abc123def456'}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(registry, f)
            reg_path = f.name
        try:
            verified, msg = verify_provenance_hash('Partner_TEST_001', 'abc123def456', registry_path=reg_path)
            self.assertTrue(verified)
            self.assertEqual(msg, 'hash_verified')
        finally:
            Path(reg_path).unlink()

    def test_provenance_hash_mismatch(self) -> None:
        registry = {'Partner_TEST_001': 'abc123def456'}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(registry, f)
            reg_path = f.name
        try:
            verified, msg = verify_provenance_hash('Partner_TEST_001', 'wrong_hash', registry_path=reg_path)
            self.assertFalse(verified)
            self.assertIn('hash_mismatch', msg)
        finally:
            Path(reg_path).unlink()

    def test_provenance_no_registry_fails_closed(self) -> None:
        """G-05: No registry configured must fail closed, not silently pass."""
        verified, msg = verify_provenance_hash('Partner_TEST_001', 'abc123', registry_path='')
        self.assertFalse(verified)
        self.assertEqual(msg, 'registry_not_configured')

    def test_provenance_registry_not_found_fails_closed(self) -> None:
        """G-05: Registry file missing must fail closed."""
        verified, msg = verify_provenance_hash('Partner_TEST_001', 'abc123', registry_path='/nonexistent/path/registry.json')
        self.assertFalse(verified)
        self.assertEqual(msg, 'registry_not_found')

    def test_provenance_bulletin_not_in_registry_fails_closed(self) -> None:
        """G-05: Bulletin not in registry must fail closed."""
        registry = {'Partner_OTHER_001': 'abc123def456'}
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(registry, f)
            reg_path = f.name
        try:
            verified, msg = verify_provenance_hash('Partner_TEST_001', 'abc123', registry_path=reg_path)
            self.assertFalse(verified)
            self.assertEqual(msg, 'bulletin_not_in_registry')
        finally:
            Path(reg_path).unlink()

    def test_placeholder_entry_fails_closed(self) -> None:
        """G-05: Placeholder entries must not support trusted publication — fail closed."""
        registry = {
            'entries': [
                {
                    'bulletin_id': 'Partner_TEST_001',
                    'sha256': 'abc123def456',
                    'status': 'placeholder_awaiting_scientist_review',
                }
            ]
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(registry, f)
            reg_path = f.name
        try:
            verified, msg = verify_provenance_hash('Partner_TEST_001', 'abc123def456', registry_path=reg_path)
            self.assertFalse(verified)
            self.assertEqual(msg, 'placeholder_awaiting_review')
        finally:
            Path(reg_path).unlink()

    def test_configured_registry_file_exists(self) -> None:
        """The shipped registry file at config/Partner_provenance_registry.json must exist and be valid JSON."""
        reg_path = Path(__file__).resolve().parents[2] / 'config' / 'Partner_provenance_registry.json'
        self.assertTrue(reg_path.exists(), f'Provenance registry not found at {reg_path}')
        data = json.loads(reg_path.read_text())
        self.assertIsInstance(data, dict)
        self.assertGreater(len(data), 0, 'Registry must contain at least one entry')

    def test_placeholder_entry_returns_placeholder_awaiting_review(self) -> None:
        """G-05: A matching entry with status 'placeholder_awaiting_scientist_review' fails closed."""
        registry = {
            'entries': [
                {
                    'bulletin_id': 'Partner_TEST_001',
                    'sha256': 'abc123def456',
                    'status': 'placeholder_awaiting_scientist_review',
                }
            ]
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(registry, f)
            reg_path = f.name
        try:
            verified, msg = verify_provenance_hash('Partner_TEST_001', 'abc123def456', registry_path=reg_path)
            self.assertFalse(verified)
            self.assertEqual(msg, 'placeholder_awaiting_review')
        finally:
            Path(reg_path).unlink()

    def test_reviewed_entry_returns_verified(self) -> None:
        """A matching entry with status 'reviewed' returns 'hash_verified'."""
        registry = {
            'entries': [
                {
                    'bulletin_id': 'Partner_TEST_002',
                    'sha256': 'def789ghi012',
                    'status': 'reviewed',
                }
            ]
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(registry, f)
            reg_path = f.name
        try:
            verified, msg = verify_provenance_hash('Partner_TEST_002', 'def789ghi012', registry_path=reg_path)
            self.assertTrue(verified)
            self.assertEqual(msg, 'hash_verified')
        finally:
            Path(reg_path).unlink()

    def test_env_var_driven_path_resolution(self) -> None:
        """verify_provenance_hash resolves registry path from env var when registry_path is None."""
        import backend.common.Partner_bulletin_adapter as adapter_mod
        registry = {
            'entries': [
                {
                    'bulletin_id': 'Partner_TEST_003',
                    'sha256': 'xyz999abc888',
                    'status': 'reviewed',
                }
            ]
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(registry, f)
            reg_path = f.name
        try:
            with patch.object(adapter_mod, 'Partner_PROVENANCE_REGISTRY_PATH', reg_path):
                verified, msg = verify_provenance_hash('Partner_TEST_003', 'xyz999abc888')
                self.assertTrue(verified)
                self.assertEqual(msg, 'hash_verified')
        finally:
            Path(reg_path).unlink()

    def test_synthetic_fixture_produces_complete_rows(self):
        """G-04: Synthetic Partner fixture parses with complete rows and no parse error."""
        import tempfile
        fixture_path = Path(__file__).parent / 'fixtures' / 'synthetic_Partner_bulletin.txt'
        self.assertTrue(fixture_path.exists(), f'Synthetic fixture not found at {fixture_path}')
        text = fixture_path.read_text()
        # Compute hash of fixture for provenance registry
        import hashlib as _hashlib
        fixture_hash = _hashlib.sha256(text.encode('utf-8')).hexdigest()
        # Create temp provenance registry with fixture hash
        registry = {
            'entries': [
                {
                    'bulletin_id': 'Partner_AWB_SYNTHETIC_TEST',
                    'sha256': fixture_hash,
                    'status': 'reviewed',
                }
            ]
        }
        import backend.common.Partner_bulletin_adapter as adapter_mod
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(registry, f)
            reg_path = f.name
        try:
            with patch.object(adapter_mod, 'Partner_PROVENANCE_REGISTRY_PATH', reg_path):
                result = parse_bulletin_with_provenance(
                    text, 'Partner_AWB_SYNTHETIC_TEST',
                    source_url='https://example.com/Partner/synthetic.pdf',
                    provenance_hash=fixture_hash,
                )
            self.assertIsNotNone(result.record)
            self.assertTrue(result.is_complete, f'Fixture should parse as complete, got parse_error={result.parse_error}')
            self.assertIsNone(result.parse_error)
            self.assertGreaterEqual(result.complete_row_count, 5,
                                    f'Expected at least 5 complete rows, got {result.complete_row_count}')
            for row in result.record.rows:
                self.assertIsNotNone(row.district)
                self.assertIsNotNone(row.danger_level)
                self.assertIsNotNone(row.altitude_band)
        finally:
            Path(reg_path).unlink()


if __name__ == '__main__':
    unittest.main()
