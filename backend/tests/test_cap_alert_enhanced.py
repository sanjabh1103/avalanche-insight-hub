"""Tests for F16: CAP Alert Enhanced + Sachet Push."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from backend.common.cap_alert import (
    generate_cap_alert,
    generate_multi_language_cap,
    should_trigger_alert,
    validate_cap_xml,
)
from backend.common.sachet_push import (
    SachetAlert,
    SachetConfig,
    SachetPushResult,
    build_multi_language_alerts,
    disseminate_alert,
    push_gagan_alert,
    push_navic_alert,
    push_sachet_alert,
    push_sms_alert,
    render_alert_message,
    should_trigger_alert as sachet_should_trigger,
)
from backend.common.sachet_rss import (
    SachetRssAlert,
    SachetRssConfig,
    filter_alerts_by_bbox,
    filter_alerts_by_disaster_type,
    get_sachet_alert_summary,
)


class CapValidationTests(unittest.TestCase):
    """Tests for CAP XML structural validation."""

    def test_validate_valid_cap_xml(self) -> None:
        xml = generate_cap_alert(
            identifier='test-001',
            sender='test@system',
            region_name='Test Region',
            region_key='test_region',
            bbox=[-107.0, 39.0, -106.0, 40.0],
            forecast_date='2026-06-25',
            horizon_hours=72,
            max_danger_level=4,
            headline='Test Alert',
            description='Test description',
        )
        is_valid, error = validate_cap_xml(xml)
        self.assertTrue(is_valid, f'Validation failed: {error}')
        self.assertIsNone(error)

    def test_validate_invalid_xml(self) -> None:
        is_valid, error = validate_cap_xml('<not valid xml')
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)

    def test_validate_missing_identifier(self) -> None:
        xml = '<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><sender>test</sender><sent>2026-01-01T00:00:00+00:00</sent><status>Actual</status><msgType>Alert</msgType><scope>Public</scope><info><category>Met</category><event>Test</event><urgency>Expected</urgency><severity>Severe</severity><certainty>Likely</certainty></info></alert>'
        is_valid, error = validate_cap_xml(xml)
        self.assertFalse(is_valid)
        self.assertIn('identifier', error or '')

    def test_validate_missing_info_block(self) -> None:
        xml = '<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>test</identifier><sender>test</sender><sent>2026-01-01T00:00:00+00:00</sent><status>Actual</status><msgType>Alert</msgType><scope>Public</scope></alert>'
        is_valid, error = validate_cap_xml(xml)
        self.assertFalse(is_valid)
        self.assertIn('info', error or '')


class CapTriggerTests(unittest.TestCase):
    """Tests for alert trigger logic."""

    def test_should_trigger_at_level_4(self) -> None:
        self.assertTrue(should_trigger_alert(4))

    def test_should_trigger_at_level_5(self) -> None:
        self.assertTrue(should_trigger_alert(5))

    def test_should_not_trigger_at_level_3(self) -> None:
        self.assertFalse(should_trigger_alert(3))

    def test_should_not_trigger_at_level_1(self) -> None:
        self.assertFalse(should_trigger_alert(1))

    def test_custom_threshold(self) -> None:
        self.assertTrue(should_trigger_alert(3, threshold=3))
        self.assertFalse(should_trigger_alert(2, threshold=3))


class MultiLanguageCapTests(unittest.TestCase):
    """Tests for multi-language CAP generation."""

    def test_multi_language_cap_has_three_info_blocks(self) -> None:
        xml = generate_multi_language_cap(
            identifier='test-ml-001',
            sender='test@system',
            region_name='Test Region',
            region_key='test_region',
            bbox=[-107.0, 39.0, -106.0, 40.0],
            forecast_date='2026-06-25',
            horizon_hours=72,
            max_danger_level=4,
        )
        # Count info blocks
        from xml.etree import ElementTree as ET
        root = ET.fromstring(xml)
        ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
        info_blocks = root.findall('.//cap:info', ns)
        if not info_blocks:
            info_blocks = root.findall('.//info')
        self.assertEqual(len(info_blocks), 3)

    def test_multi_language_cap_validates(self) -> None:
        xml = generate_multi_language_cap(
            identifier='test-ml-002',
            sender='test@system',
            region_name='Test Region',
            region_key='test_region',
            bbox=[-107.0, 39.0, -106.0, 40.0],
            forecast_date='2026-06-25',
            horizon_hours=72,
            max_danger_level=5,
        )
        is_valid, error = validate_cap_xml(xml)
        self.assertTrue(is_valid, f'Validation failed: {error}')

    def test_multi_language_cap_specific_languages(self) -> None:
        xml = generate_multi_language_cap(
            identifier='test-ml-003',
            sender='test@system',
            region_name='Test Region',
            region_key='test_region',
            bbox=[-107.0, 39.0, -106.0, 40.0],
            forecast_date='2026-06-25',
            horizon_hours=72,
            max_danger_level=4,
            languages=['en-US'],
        )
        from xml.etree import ElementTree as ET
        root = ET.fromstring(xml)
        ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
        info_blocks = root.findall('.//cap:info', ns)
        if not info_blocks:
            info_blocks = root.findall('.//info')
        self.assertEqual(len(info_blocks), 1)

    def test_multi_language_cap_contains_hindi(self) -> None:
        xml = generate_multi_language_cap(
            identifier='test-ml-004',
            sender='test@system',
            region_name='Test Region',
            region_key='test_region',
            bbox=[-107.0, 39.0, -106.0, 40.0],
            forecast_date='2026-06-25',
            horizon_hours=72,
            max_danger_level=4,
            languages=['hi'],
        )
        self.assertIn('हिमस्खलन', xml)


class SachetPushTests(unittest.TestCase):
    """Tests for Sachet push scaffold."""

    def test_sachet_disabled_returns_error(self) -> None:
        config = SachetConfig(enabled=False, api_key='test', rss_enabled=False)
        alert = SachetAlert(
            title='Test', body='Test body', language='en',
            geo_target='0,0,0,0', danger_level=4, region_name='Test',
        )
        result = push_sachet_alert(alert, config)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'sachet_disabled')
        self.assertEqual(result.channel, 'sachet_api')

    def test_sachet_rss_mode_returns_success_without_api_key(self) -> None:
        config = SachetConfig(enabled=False, api_key='', rss_enabled=True)
        alert = SachetAlert(
            title='Test', body='Test body', language='en',
            geo_target='0,0,0,0', danger_level=4, region_name='Test',
        )
        result = push_sachet_alert(alert, config)
        self.assertTrue(result.success)
        self.assertEqual(result.channel, 'sachet_rss')
        self.assertIsNotNone(result.message_id)

    def test_sachet_no_api_key_no_rss_returns_error(self) -> None:
        config = SachetConfig(enabled=True, api_key='', rss_enabled=False)
        alert = SachetAlert(
            title='Test', body='Test body', language='en',
            geo_target='0,0,0,0', danger_level=4, region_name='Test',
        )
        result = push_sachet_alert(alert, config)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'no_api_key_configured')

    def test_sachet_with_api_key_returns_success(self) -> None:
        config = SachetConfig(enabled=True, api_key='test_key')
        alert = SachetAlert(
            title='Test', body='Test body', language='en',
            geo_target='0,0,0,0', danger_level=4, region_name='Test',
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 202
        mock_resp.headers = {'content-type': 'application/json'}
        mock_resp.json.return_value = {'message_id': 'test_msg_123'}
        with patch('requests.post', return_value=mock_resp):
            result = push_sachet_alert(alert, config)
        self.assertTrue(result.success)
        self.assertIsNotNone(result.message_id)

    def test_sms_push_returns_success(self) -> None:
        alert = SachetAlert(
            title='Test', body='Test body', language='hi',
            geo_target='0,0,0,0', danger_level=4, region_name='Test',
        )
        result = push_sms_alert(alert)
        self.assertTrue(result.success)
        self.assertEqual(result.channel, 'sms_stub')

    def test_gagan_push_returns_success(self) -> None:
        alert = SachetAlert(
            title='Test', body='Test body', language='ur',
            geo_target='0,0,0,0', danger_level=5, region_name='Test',
        )
        result = push_gagan_alert(alert)
        self.assertTrue(result.success)
        self.assertEqual(result.channel, 'gagan')

    def test_navic_push_returns_success(self) -> None:
        alert = SachetAlert(
            title='Test', body='Test body', language='en',
            geo_target='0,0,0,0', danger_level=4, region_name='Test',
        )
        result = push_navic_alert(alert)
        self.assertTrue(result.success)
        self.assertEqual(result.channel, 'navic')


class SachetAlertTemplatesTests(unittest.TestCase):
    """Tests for multi-language alert templates."""

    def test_render_english_alert(self) -> None:
        msg = render_alert_message(region_name='Pir Panjal', danger_level=4, language='en')
        self.assertIn('AVALANCHE WARNING', msg)
        self.assertIn('Pir Panjal', msg)
        self.assertIn('4', msg)

    def test_render_hindi_alert(self) -> None:
        msg = render_alert_message(region_name='Pir Panjal', danger_level=5, language='hi')
        self.assertIn('हिमस्खलन', msg)
        self.assertIn('Pir Panjal', msg)

    def test_render_urdu_alert(self) -> None:
        msg = render_alert_message(region_name='Karakoram', danger_level=4, language='ur')
        self.assertIn('برفانی تودے', msg)

    def test_render_fallback_to_english(self) -> None:
        msg = render_alert_message(region_name='Test', danger_level=3, language='fr')
        self.assertIn('AVALANCHE', msg)

    def test_build_multi_language_alerts(self) -> None:
        alerts = build_multi_language_alerts(
            region_name='Test Region',
            danger_level=4,
            bbox=[-107.0, 39.0, -106.0, 40.0],
        )
        self.assertEqual(len(alerts), 3)
        languages = {a.language for a in alerts}
        self.assertEqual(languages, {'en', 'hi', 'ur'})

    def test_disseminate_alert_below_threshold(self) -> None:
        results = disseminate_alert(
            region_name='Test',
            danger_level=3,
            bbox=[0, 0, 0, 0],
        )
        self.assertEqual(len(results), 0)

    def test_disseminate_alert_at_threshold(self) -> None:
        results = disseminate_alert(
            region_name='Test',
            danger_level=4,
            bbox=[0, 0, 0, 0],
        )
        # 3 languages * 4 channels = 12 results
        self.assertEqual(len(results), 12)

    def test_sachet_should_trigger(self) -> None:
        self.assertTrue(sachet_should_trigger(4))
        self.assertFalse(sachet_should_trigger(3))


class SachetRssTests(unittest.TestCase):
    """Tests for SACHET RSS feed ingestion."""

    def test_rss_config_defaults(self) -> None:
        cfg = SachetRssConfig()
        self.assertTrue(cfg.enabled)
        self.assertIn('sachet.ndma.gov.in', cfg.alert_list_url)
        self.assertIn('sachet.ndma.gov.in', cfg.cap_xml_url)

    def test_rss_config_disabled(self) -> None:
        cfg = SachetRssConfig(enabled=False)
        self.assertFalse(cfg.enabled)

    def test_filter_alerts_by_bbox_with_polygon(self) -> None:
        alert_in = SachetRssAlert(
            identifier='test-1', sender='IMD', sent='2026-06-29T12:00:00+05:30',
            status='Actual', msg_type='Alert', scope='Public',
            language='en-IN', category='Met', event='Thunderstorm',
            urgency='Expected', severity='Moderate', certainty='Likely',
            headline='Test', description='Test', instruction='',
            area_desc='Test area',
            polygon='18.3,77.2 18.4,77.3 18.5,77.4 18.3,77.2',
            effective=None, onset=None, expires=None, web_url=None,
        )
        alert_out = SachetRssAlert(
            identifier='test-2', sender='IMD', sent='2026-06-29T12:00:00+05:30',
            status='Actual', msg_type='Alert', scope='Public',
            language='en-IN', category='Met', event='Thunderstorm',
            urgency='Expected', severity='Moderate', certainty='Likely',
            headline='Test', description='Test', instruction='',
            area_desc='Far away',
            polygon='40.0,-100.0 41.0,-99.0 42.0,-98.0 40.0,-100.0',
            effective=None, onset=None, expires=None, web_url=None,
        )
        # bbox around India [west, south, east, north]
        filtered = filter_alerts_by_bbox([alert_in, alert_out], [68.0, 8.0, 97.0, 37.0])
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].identifier, 'test-1')

    def test_filter_alerts_by_bbox_no_polygon_included(self) -> None:
        alert_no_poly = SachetRssAlert(
            identifier='test-3', sender='IMD', sent='2026-06-29T12:00:00+05:30',
            status='Actual', msg_type='Alert', scope='Public',
            language='en-IN', category='Met', event='Avalanche',
            urgency='Expected', severity='Severe', certainty='Likely',
            headline='Test', description='Test', instruction='',
            area_desc='No polygon',
            polygon=None,
            effective=None, onset=None, expires=None, web_url=None,
        )
        filtered = filter_alerts_by_bbox([alert_no_poly], [68.0, 8.0, 97.0, 37.0])
        self.assertEqual(len(filtered), 1)

    def test_filter_alerts_by_disaster_type(self) -> None:
        alert_avalanche = SachetRssAlert(
            identifier='test-1', sender='Partner', sent='2026-06-29T12:00:00+05:30',
            status='Actual', msg_type='Alert', scope='Public',
            language='en-IN', category='Met', event='Avalanche Warning',
            urgency='Expected', severity='Severe', certainty='Likely',
            headline='Avalanche Warning', description='Test', instruction='',
            area_desc='Himalayas',
            polygon=None,
            effective=None, onset=None, expires=None, web_url=None,
            disaster_type='Avalanche',
        )
        alert_thunder = SachetRssAlert(
            identifier='test-2', sender='IMD', sent='2026-06-29T12:00:00+05:30',
            status='Actual', msg_type='Alert', scope='Public',
            language='en-IN', category='Met', event='Thunderstorm',
            urgency='Expected', severity='Moderate', certainty='Possible',
            headline='Thunderstorm', description='Test', instruction='',
            area_desc='Karnataka',
            polygon=None,
            effective=None, onset=None, expires=None, web_url=None,
            disaster_type='Thunderstorm',
        )
        filtered = filter_alerts_by_disaster_type([alert_avalanche, alert_thunder], ['avalanche'])
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].identifier, 'test-1')

    def test_get_sachet_alert_summary(self) -> None:
        alerts = [
            SachetRssAlert(
                identifier='test-1', sender='IMD', sent='2026-06-29T12:00:00+05:30',
                status='Actual', msg_type='Alert', scope='Public',
                language='en-IN', category='Met', event='Avalanche',
                urgency='Expected', severity='Severe', certainty='Likely',
                headline='Test', description='Test', instruction='',
                area_desc='Himalayas', polygon=None,
                effective=None, onset=None, expires=None, web_url=None,
            ),
            SachetRssAlert(
                identifier='test-2', sender='IMD', sent='2026-06-29T13:00:00+05:30',
                status='Actual', msg_type='Alert', scope='Public',
                language='en-IN', category='Met', event='Thunderstorm',
                urgency='Expected', severity='Moderate', certainty='Possible',
                headline='Test', description='Test', instruction='',
                area_desc='Karnataka', polygon=None,
                effective=None, onset=None, expires=None, web_url=None,
            ),
        ]
        summary = get_sachet_alert_summary(alerts)
        self.assertEqual(summary['alert_count'], 2)
        self.assertTrue(summary['ingested'])
        self.assertIsNone(summary['error'])
        self.assertEqual(summary['severity_breakdown']['Severe'], 1)
        self.assertEqual(summary['severity_breakdown']['Moderate'], 1)

    def test_get_sachet_alert_summary_empty(self) -> None:
        summary = get_sachet_alert_summary([])
        self.assertEqual(summary['alert_count'], 0)
        self.assertEqual(summary['severity_breakdown'], {})
        self.assertTrue(summary['ingested'])
        self.assertIsNone(summary['error'])

    def test_get_sachet_alert_summary_with_error(self) -> None:
        summary = get_sachet_alert_summary([], fetch_error='network_timeout')
        self.assertEqual(summary['alert_count'], 0)
        self.assertFalse(summary['ingested'])
        self.assertEqual(summary['error'], 'network_timeout')

    def test_parse_cap_xml_from_sachet(self) -> None:
        from backend.common.sachet_rss import _parse_cap_xml
        cap_xml = '''<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<cap:alert xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
    <cap:identifier>IN-1747910186993019</cap:identifier>
    <cap:sender>IMD-Bengaluru</cap:sender>
    <cap:sent>2025-05-22T16:05:54+05:30</cap:sent>
    <cap:status>Actual</cap:status>
    <cap:msgType>Alert</cap:msgType>
    <cap:scope>Public</cap:scope>
    <cap:info>
        <cap:language>en-IN</cap:language>
        <cap:category>Met</cap:category>
        <cap:event>Light Thunderstorm</cap:event>
        <cap:urgency>Unknown</cap:urgency>
        <cap:severity>Moderate</cap:severity>
        <cap:certainty>Possible</cap:certainty>
        <cap:effective>2025-05-22T16:00:00+05:30</cap:effective>
        <cap:expires>2025-05-22T19:00:00+05:30</cap:expires>
        <cap:headline>Thunderstorm warning for Bidar</cap:headline>
        <cap:description>Thunderstorm expected</cap:description>
        <cap:instruction>Follow SDMA guidelines</cap:instruction>
        <cap:area>
            <cap:areaDesc>Bidar district of Karnataka</cap:areaDesc>
            <cap:polygon>18.3,77.2 18.4,77.3 18.3,77.2</cap:polygon>
        </cap:area>
    </cap:info>
</cap:alert>'''
        alert = _parse_cap_xml(cap_xml)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.identifier, 'IN-1747910186993019')
        self.assertEqual(alert.sender, 'IMD-Bengaluru')
        self.assertEqual(alert.event, 'Light Thunderstorm')
        self.assertEqual(alert.severity, 'Moderate')
        self.assertEqual(alert.area_desc, 'Bidar district of Karnataka')
        self.assertIsNotNone(alert.polygon)

    def test_parse_cap_xml_invalid(self) -> None:
        from backend.common.sachet_rss import _parse_cap_xml
        alert = _parse_cap_xml('<not valid xml')
        self.assertIsNone(alert)

    def test_parse_cap_xml_rejects_doctype(self) -> None:
        from backend.common.sachet_rss import _parse_cap_xml
        xml_with_dtd = '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe "test">]><alert><info><event>&xxe;</event></info></alert>'
        alert = _parse_cap_xml(xml_with_dtd)
        self.assertIsNone(alert)

    def test_ingest_sachet_alerts_disabled(self) -> None:
        from backend.common.sachet_rss import ingest_sachet_alerts, SachetRssConfig
        alerts, error = ingest_sachet_alerts(SachetRssConfig(enabled=False))
        self.assertEqual(alerts, [])
        self.assertEqual(error, 'rss_disabled')

    def test_fetch_alert_list_http_error(self) -> None:
        from backend.common.sachet_rss import fetch_alert_list, SachetRssConfig
        cfg = SachetRssConfig(alert_list_url='https://sachet.ndma.gov.in/nonexistent-endpoint-that-returns-404')
        alerts, error = fetch_alert_list(cfg)
        self.assertEqual(alerts, [])
        self.assertIsNotNone(error)

    def test_fetch_alert_list_request_failed(self) -> None:
        from backend.common.sachet_rss import fetch_alert_list, SachetRssConfig
        cfg = SachetRssConfig(alert_list_url='https://nonexistent.invalid.example/feed')
        alerts, error = fetch_alert_list(cfg)
        self.assertEqual(alerts, [])
        self.assertIsNotNone(error)
        self.assertIn('request_failed', error)


if __name__ == '__main__':
    unittest.main()
