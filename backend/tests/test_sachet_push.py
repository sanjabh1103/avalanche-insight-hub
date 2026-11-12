"""Tests for SACHET push and SMS gateway integration."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch, MagicMock

from backend.common.sachet_push import (
    SachetAlert,
    SachetPushResult,
    push_sachet_alert,
    push_sms_alert,
    should_trigger_alert,
)


def _make_alert(danger_level: int = 4, language: str = 'en') -> SachetAlert:
    return SachetAlert(
        title='Avalanche Warning',
        body='Danger Level 4/5. Avoid avalanche-prone slopes.',
        language=language,
        geo_target='28.0,86.0,29.0,87.0',
        danger_level=danger_level,
        region_name='Khumbu Region',
    )


class ShouldTriggerAlertTests(unittest.TestCase):
    def test_triggers_at_threshold(self) -> None:
        self.assertTrue(should_trigger_alert(4, threshold=4))

    def test_does_not_trigger_below_threshold(self) -> None:
        self.assertFalse(should_trigger_alert(3, threshold=4))

    def test_triggers_above_threshold(self) -> None:
        self.assertTrue(should_trigger_alert(5, threshold=4))


class SmsGatewayTests(unittest.TestCase):
    def test_sms_stub_mode_when_no_auth_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with patch('backend.common.sachet_push.SMS_AUTH_KEY', ''):
                result = push_sms_alert(_make_alert())
        self.assertTrue(result.success)
        self.assertEqual(result.channel, 'sms_stub')

    def test_sms_no_recipients_when_auth_key_set_but_empty_recipients(self) -> None:
        with patch('backend.common.sachet_push.SMS_AUTH_KEY', 'test_key'):
            with patch('backend.common.sachet_push.SMS_RECIPIENTS', ''):
                result = push_sms_alert(_make_alert())
        self.assertTrue(result.success)
        self.assertEqual(result.channel, 'sms_no_recipients')

    def test_sms_sends_via_msg91_when_configured(self) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"type": "success", "message": "sent"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch('backend.common.sachet_push.SMS_AUTH_KEY', 'test_key'):
            with patch('backend.common.sachet_push.SMS_RECIPIENTS', '919999999999,918888888888'):
                with patch('urllib.request.urlopen', return_value=mock_response):
                    result = push_sms_alert(_make_alert(danger_level=5))
        self.assertTrue(result.success)
        self.assertEqual(result.channel, 'sms_msg91')

    def test_sms_returns_error_on_gateway_failure(self) -> None:
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"type": "error", "message": "invalid auth"}'
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch('backend.common.sachet_push.SMS_AUTH_KEY', 'bad_key'):
            with patch('backend.common.sachet_push.SMS_RECIPIENTS', '919999999999'):
                with patch('urllib.request.urlopen', return_value=mock_response):
                    result = push_sms_alert(_make_alert())
        self.assertFalse(result.success)
        self.assertEqual(result.channel, 'sms_msg91')
        self.assertIn('sms_gateway_error', result.error or '')


class SachetRssModeTests(unittest.TestCase):
    def test_rss_mode_returns_success_without_api_key(self) -> None:
        with patch('backend.common.sachet_push.SACHET_ENABLED', False):
            with patch('backend.common.sachet_push.SACHET_RSS_ENABLED', True):
                result = push_sachet_alert(_make_alert())
        self.assertTrue(result.success)
        self.assertEqual(result.channel, 'sachet_rss')


if __name__ == '__main__':
    unittest.main()
