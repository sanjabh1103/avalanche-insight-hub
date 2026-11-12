"""Tests for F15: Edge Deployment Mode configuration."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from backend.common.config import Settings, load_settings


class EdgeConfigTests(unittest.TestCase):
    """Tests for edge mode configuration."""

    @patch.dict(os.environ, {
        'EDGE_MODE': 'true',
        'LOCAL_DB_URL': 'postgresql://avalanche:pass@localhost:5432/avalanche_insight',
        'LOCAL_MODEL_WEIGHTS_PATH': '/opt/model_weights',
        'EDGE_SAR_CACHE_DIR': '/opt/sar_cache',
        'SUPABASE_URL': '',
        'SUPABASE_SERVICE_ROLE_KEY': '',
    })
    def test_edge_mode_enabled(self) -> None:
        settings = load_settings()
        self.assertTrue(settings.edge_mode)
        self.assertEqual(settings.local_db_url, 'postgresql://avalanche:pass@localhost:5432/avalanche_insight')
        self.assertEqual(settings.local_model_weights_path, '/opt/model_weights')
        self.assertEqual(settings.edge_sar_cache_dir, '/opt/sar_cache')

    @patch.dict(os.environ, {'EDGE_MODE': 'false'})
    def test_edge_mode_disabled(self) -> None:
        settings = load_settings()
        self.assertFalse(settings.edge_mode)
        self.assertIsNone(settings.local_db_url)

    @patch.dict(os.environ, {}, clear=True)
    def test_edge_mode_default_false(self) -> None:
        settings = load_settings()
        self.assertFalse(settings.edge_mode)
        self.assertIsNone(settings.local_db_url)
        self.assertIsNone(settings.local_model_weights_path)
        self.assertIsNone(settings.edge_sar_cache_dir)

    @patch.dict(os.environ, {'EDGE_MODE': '1'})
    def test_edge_mode_truthy_one(self) -> None:
        settings = load_settings()
        self.assertTrue(settings.edge_mode)

    @patch.dict(os.environ, {'EDGE_MODE': 'off'})
    def test_edge_mode_falsy_off(self) -> None:
        settings = load_settings()
        self.assertFalse(settings.edge_mode)

    def test_settings_is_frozen(self) -> None:
        settings = Settings(
            supabase_url=None,
            supabase_service_role_key=None,
            artifact_root=__import__('pathlib').Path('/tmp'),
            samples_per_region=500,
            seed=42,
            forecast_horizon_hours=72,
            grid_size=20,
            hazard_type='avalanche',
            dry_run=False,
            edge_mode=True,
            local_db_url='postgresql://localhost/db',
            local_model_weights_path='/opt/weights',
            edge_sar_cache_dir='/opt/sar',
            pilot_grid_resolution_m=None,
            research_model_gate_enabled=True,
        )
        with self.assertRaises(AttributeError):
            settings.edge_mode = False  # type: ignore[misc]


if __name__ == '__main__':
    unittest.main()
