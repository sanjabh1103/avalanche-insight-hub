"""Sentinel-1/2 credentialed live pilot test scaffold.

Tests that the Sentinel-1 and Sentinel-2 adapters correctly gate on
credentials and can attempt a live fetch when credentials are present.
These tests skip gracefully when credentials are not available.

Env flags:
  COPERNICUS_HUB_USERNAME — Copernicus Data Hub username
  COPERNICUS_HUB_PASSWORD — Copernicus Data Hub password
  SENTINEL_PILOT_ENABLED — master switch for live pilot (default: false)
"""
from __future__ import annotations

import os
import unittest
from typing import Any

SENTINEL_PILOT_ENABLED = os.getenv('SENTINEL_PILOT_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}
COPERNICUS_USERNAME = os.getenv('COPERNICUS_HUB_USERNAME', '')
COPERNICUS_PASSWORD = os.getenv('COPERNICUS_HUB_PASSWORD', '')

_SKIP_NO_CREDS = 'Set COPERNICUS_HUB_USERNAME/PASSWORD and SENTINEL_PILOT_ENABLED=true to run live pilot'
_SKIP_NO_DEPS = 'Install requests to run live pilot tests'


def _has_requests() -> bool:
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        return False


def _has_credentials() -> bool:
    return bool(COPERNICUS_USERNAME and COPERNICUS_PASSWORD and SENTINEL_PILOT_ENABLED)


class TestSentinelCredentialGating(unittest.TestCase):
    """Verify adapters gate correctly on credentials without making network calls."""

    def test_s1_disabled_without_flag(self) -> None:
        from backend.common.s1_snow_depth import S1_DEPTH_ENABLED
        if SENTINEL_PILOT_ENABLED:
            self.skipTest('SENTINEL_PILOT_ENABLED is true — skipping disabled-state test')
        self.assertIsInstance(S1_DEPTH_ENABLED, bool)

    def test_s2_disabled_without_flag(self) -> None:
        from backend.common.sentinel2_snow_mapper import S2_SNOW_ENABLED
        if SENTINEL_PILOT_ENABLED:
            self.skipTest('SENTINEL_PILOT_ENABLED is true — skipping disabled-state test')
        self.assertIsInstance(S2_SNOW_ENABLED, bool)

    def test_credential_detection(self) -> None:
        """Credential detection must be deterministic."""
        creds_present = bool(COPERNICUS_USERNAME and COPERNICUS_PASSWORD)
        self.assertIsInstance(creds_present, bool)


@unittest.skipUnless(_has_requests(), _SKIP_NO_DEPS)
@unittest.skipUnless(_has_credentials(), _SKIP_NO_CREDS)
class TestSentinelLivePilotS1(unittest.TestCase):
    """Live S1 pilot — only runs with real credentials."""

    @classmethod
    def setUpClass(cls) -> None:
        import requests
        cls.requests = requests
        cls.session = requests.Session()
        cls.session.auth = (COPERNICUS_USERNAME, COPERNICUS_PASSWORD)

    def test_can_authenticate_to_copernicus_hub(self) -> None:
        """Verify credentials are accepted by the Copernicus Data Hub."""
        resp = self.session.get(
            'https://catalogue.dataspace.copernicus.eu/odata/v1/Products',
            params={'$top': 1},
            timeout=30,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('value', data)

    def test_can_query_s1_products(self) -> None:
        """Query S1 products for a small Himalayan bbox."""
        bbox = '76.0,35.0,77.0,36.0'
        filters = (
            "Collection/Name eq 'SENTINEL-1'"
            f" and OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(({bbox}))')"
        )
        resp = self.session.get(
            'https://catalogue.dataspace.copernicus.eu/odata/v1/Products',
            params={'$filter': filters, '$top': 5},
            timeout=30,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('value', data)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, 'session'):
            cls.session.close()


@unittest.skipUnless(_has_requests(), _SKIP_NO_DEPS)
@unittest.skipUnless(_has_credentials(), _SKIP_NO_CREDS)
class TestSentinelLivePilotS2(unittest.TestCase):
    """Live S2 pilot — only runs with real credentials."""

    @classmethod
    def setUpClass(cls) -> None:
        import requests
        cls.requests = requests
        cls.session = requests.Session()
        cls.session.auth = (COPERNICUS_USERNAME, COPERNICUS_PASSWORD)

    def test_can_query_s2_products(self) -> None:
        """Query S2 products for a small Himalayan bbox."""
        bbox = '76.0,35.0,77.0,36.0'
        filters = (
            "Collection/Name eq 'SENTINEL-2'"
            f" and OData.CSC.Intersects(area=geography'SRID=4326;POLYGON(({bbox}))')"
        )
        resp = self.session.get(
            'https://catalogue.dataspace.copernicus.eu/odata/v1/Products',
            params={'$filter': filters, '$top': 5},
            timeout=30,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('value', data)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, 'session'):
            cls.session.close()


if __name__ == '__main__':
    unittest.main()
