from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.common.runout import build_runout_polygons, runout_polygon_for_cell


class RunoutPolygonTests(unittest.TestCase):
    @patch('backend.common.runout.RUN_PHYSICS_RUNOUT', False)
    def test_build_runout_polygons_skips_unavailable_cells_with_missing_probability(self) -> None:
        rows = [
            {
                'row': 9,
                'col': 9,
                'lat': 39.90,
                'lng': -106.90,
                'lat_end': 39.91,
                'lng_end': -106.89,
                'risk_score': 4,
                'probability': None,
                'runout_seed': True,
                'status': 'unavailable_terrain',
                'terrain_inputs': {},
            },
            {
                'row': 1,
                'col': 1,
                'lat': 39.10,
                'lng': -106.10,
                'lat_end': 39.11,
                'lng_end': -106.09,
                'risk_score': 4,
                'probability': 0.91,
                'runout_seed': False,
                'status': 'ready',
                'terrain_inputs': {'slope_deg': 33.0, 'aspect_deg': 180.0},
            },
            {
                'row': 2,
                'col': 2,
                'lat': 39.20,
                'lng': -106.20,
                'lat_end': 39.21,
                'lng_end': -106.19,
                'risk_score': 4,
                'probability': 0.71,
                'runout_seed': False,
                'status': 'ready',
                'terrain_inputs': {'slope_deg': 31.0, 'aspect_deg': 90.0},
            },
        ]

        polygons = build_runout_polygons('colorado_rockies', rows)

        self.assertEqual([(polygon['row'], polygon['col']) for polygon in polygons], [(1, 1), (2, 2)])

    @patch('backend.common.runout.RUN_PHYSICS_RUNOUT', False)
    def test_build_runout_polygons_allows_runout_seed_when_probability_missing(self) -> None:
        rows = [
            {
                'row': 4,
                'col': 5,
                'lat': 39.40,
                'lng': -106.40,
                'lat_end': 39.41,
                'lng_end': -106.39,
                'risk_score': 5,
                'probability': None,
                'runout_seed': True,
                'status': 'ready',
                'terrain_inputs': {'slope_deg': 37.0, 'aspect_deg': 225.0},
            }
        ]

        polygons = build_runout_polygons('colorado_rockies', rows)

        self.assertEqual(len(polygons), 1)
        self.assertEqual(polygons[0]['row'], 4)
        self.assertEqual(polygons[0]['col'], 5)
        self.assertIn(polygons[0]['method'], {'analytical_alpha_beta', 'rectangular_footprint'})

    @patch('backend.common.runout.RUN_PHYSICS_RUNOUT', False)
    def test_build_runout_polygons_ignores_malformed_probability_without_raising(self) -> None:
        rows = [
            {
                'row': 7,
                'col': 7,
                'lat': 39.70,
                'lng': -106.70,
                'lat_end': 39.71,
                'lng_end': -106.69,
                'risk_score': 1,
                'probability': 'not-a-number',
                'runout_seed': False,
                'status': 'ready',
                'terrain_inputs': {'slope_deg': 28.0, 'aspect_deg': 15.0},
            }
        ]

        polygons = build_runout_polygons('colorado_rockies', rows)

        self.assertEqual(polygons, [])

    @patch('backend.common.runout.RUN_PHYSICS_RUNOUT', False)
    def test_runout_polygon_for_cell_uses_neutral_probability_fallback(self) -> None:
        cell = {
            'row': 3,
            'col': 4,
            'lat': 39.30,
            'lng': -106.30,
            'lat_end': 39.31,
            'lng_end': -106.29,
            'risk_score': 4,
            'probability': None,
            'terrain_inputs': {'slope_deg': 35.0, 'aspect_deg': 135.0},
        }

        polygon = runout_polygon_for_cell(region_key='colorado_rockies', cell=cell)

        self.assertEqual(polygon.row, 3)
        self.assertEqual(polygon.col, 4)
        self.assertTrue(len(polygon.polygon) >= 4)


if __name__ == '__main__':
    unittest.main()
