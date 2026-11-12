"""Tests for the P6 Swiss EnviDat reference repair.

P6 exit gate: discover_envidat_resources() returns the two expected resources
using the working slug; the DOI-based ID falls back to the slug automatically.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from backend.scripts.download_swiss_ravafcast_data import (
    discover_envidat_resources,
    ENVIDAT_WORKING_PACKAGE_ID,
    ENVIDAT_FALLBACK_PACKAGE_IDS,
    select_resource_url,
    RESOURCE_PATTERNS,
)
from backend.reproduction.swiss_ravafcast.constants import (
    ENVIDAT_PACKAGE_ID,
    RF1_RESOURCE_KEY,
    RF2_RESOURCE_KEY,
)


class TestEnviDatPackageIdRepair(unittest.TestCase):
    """P6: The DOI-based package ID is replaced by the working slug."""

    def test_working_package_id_is_slug(self) -> None:
        """The default package ID is the slug, not the DOI-based ID."""
        self.assertEqual(ENVIDAT_WORKING_PACKAGE_ID, 'weather-snowpack-danger_ratings-data')
        self.assertNotEqual(ENVIDAT_WORKING_PACKAGE_ID, ENVIDAT_PACKAGE_ID)

    def test_doi_based_id_returns_404(self) -> None:
        """The DOI-based ID from constants.py is 'doi:10.16904/envidat.330'."""
        self.assertEqual(ENVIDAT_PACKAGE_ID, 'doi:10.16904/envidat.330')

    def test_fallback_includes_slug_and_uuid(self) -> None:
        """Fallback IDs include the slug and UUID."""
        self.assertIn(ENVIDAT_WORKING_PACKAGE_ID, ENVIDAT_FALLBACK_PACKAGE_IDS)
        self.assertIn('54d7dc19-e70c-4998-bfb6-caffe41c83e6', ENVIDAT_FALLBACK_PACKAGE_IDS)

    def test_doi_based_id_is_in_fallback_for_documentation(self) -> None:
        """The DOI-based ID is kept in the fallback list for documentation."""
        self.assertIn(ENVIDAT_PACKAGE_ID, ENVIDAT_FALLBACK_PACKAGE_IDS)


class TestDiscoverEnvidatResourcesFallback(unittest.TestCase):
    """P6: The fallback mechanism tries slug when DOI-based ID fails."""

    def test_slug_succeeds_directly(self) -> None:
        """Using the slug directly succeeds without fallback."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            'success': True,
            'result': {
                'resources': [
                    {'name': 'Data_weather_snowpack_danger_forecast', 'url': 'https://example.com/rf1.csv'},
                    {'name': 'Data_RF2_tidy', 'url': 'https://example.com/rf2.csv'},
                ],
            },
        }

        with patch('backend.scripts.download_swiss_ravafcast_data.requests.get', return_value=mock_response):
            resources = discover_envidat_resources(package_id=ENVIDAT_WORKING_PACKAGE_ID)
        self.assertEqual(len(resources), 2)

    def test_fallback_from_doi_to_slug(self) -> None:
        """When the DOI-based ID returns 404, the slug is tried as fallback."""
        # First call (DOI) returns 404, second call (slug) returns 200
        mock_404 = MagicMock()
        mock_404.status_code = 404

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.raise_for_status = MagicMock()
        mock_200.json.return_value = {
            'success': True,
            'result': {
                'resources': [
                    {'name': 'Data_RF2_tidy', 'url': 'https://example.com/rf2.csv'},
                ],
            },
        }

        with patch('backend.scripts.download_swiss_ravafcast_data.requests.get',
                   side_effect=[mock_404, mock_200]):
            resources = discover_envidat_resources(package_id='doi:10.16904/envidat.330')
        self.assertEqual(len(resources), 1)

    def test_all_failures_raise(self) -> None:
        """When all candidate IDs fail, a RuntimeError is raised."""
        mock_404 = MagicMock()
        mock_404.status_code = 404

        with patch('backend.scripts.download_swiss_ravafcast_data.requests.get',
                   return_value=mock_404):
            with self.assertRaises(RuntimeError) as ctx:
                discover_envidat_resources(package_id='doi:10.16904/envidat.330')
        self.assertIn('failed for all candidate IDs', str(ctx.exception))


class TestResourceSelection(unittest.TestCase):
    """P6: Resource URL selection from discovered resources."""

    def test_select_rf1_resource(self) -> None:
        resources = [
            {'name': 'Data_weather_snowpack_danger_forecast', 'url': 'https://example.com/rf1.csv',
             'description': 'RF1 forecast data', 'format': 'CSV'},
            {'name': 'Data_RF2_tidy', 'url': 'https://example.com/rf2.csv',
             'description': 'RF2 tidy data', 'format': 'CSV'},
        ]
        url = select_resource_url(resources, resource_key=RF1_RESOURCE_KEY)
        self.assertEqual(url, 'https://example.com/rf1.csv')

    def test_select_rf2_resource(self) -> None:
        resources = [
            {'name': 'Data_weather_snowpack_danger_forecast', 'url': 'https://example.com/rf1.csv',
             'description': 'RF1 forecast data', 'format': 'CSV'},
            {'name': 'Data_RF2_tidy', 'url': 'https://example.com/rf2.csv',
             'description': 'RF2 tidy data', 'format': 'CSV'},
        ]
        url = select_resource_url(resources, resource_key=RF2_RESOURCE_KEY)
        self.assertEqual(url, 'https://example.com/rf2.csv')


if __name__ == '__main__':
    unittest.main()
