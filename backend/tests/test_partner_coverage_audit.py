"""Tests for Partner_coverage_audit.py — P5: Coverage and quality audit.

P5 exit gate: A coverage report exists with class/season/region/level counts;
Level 5 is reported exactly as observed (never inflated or merged).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from backend.common.Partner_coverage_audit import (
    CoverageReport,
    build_coverage_report,
    save_coverage_report,
    load_coverage_report,
    get_region_for_district,
    get_winter_season,
)
from backend.common.Partner_public_candidate import (
    PublicBulletinCandidateV1,
    build_candidate_from_parse_result,
    PARSE_COMPLETE,
    PARSE_PARTIAL,
    PARSE_FAILED,
)


class TestRegionMapping(unittest.TestCase):
    """District to region mapping."""

    def test_jammu_kashmir_districts(self) -> None:
        self.assertEqual(get_region_for_district('Poonch'), 'Jammu & Kashmir')
        self.assertEqual(get_region_for_district('Baramulla'), 'Jammu & Kashmir')
        self.assertEqual(get_region_for_district('Ramban'), 'Jammu & Kashmir')

    def test_ladakh_districts(self) -> None:
        self.assertEqual(get_region_for_district('Kargil'), 'Ladakh')
        self.assertEqual(get_region_for_district('Leh'), 'Ladakh')

    def test_himachal_districts(self) -> None:
        self.assertEqual(get_region_for_district('Chamba'), 'Himachal Pradesh')
        self.assertEqual(get_region_for_district('Lahaul-Spiti'), 'Himachal Pradesh')
        self.assertEqual(get_region_for_district('Kullu'), 'Himachal Pradesh')

    def test_uttarakhand_districts(self) -> None:
        self.assertEqual(get_region_for_district('Uttarkashi'), 'Uttarakhand')
        self.assertEqual(get_region_for_district('Chamoli'), 'Uttarakhand')

    def test_sikkim_districts(self) -> None:
        self.assertEqual(get_region_for_district('North Sikkim'), 'Sikkim')
        self.assertEqual(get_region_for_district('East Sikkim'), 'Sikkim')

    def test_unknown_district(self) -> None:
        self.assertEqual(get_region_for_district('Unknown Place'), 'Unknown')


class TestWinterSeason(unittest.TestCase):
    """Date to winter season mapping."""

    def test_winter_month(self) -> None:
        self.assertEqual(get_winter_season(date(2026, 1, 15)), '2025-26')
        self.assertEqual(get_winter_season(date(2026, 4, 30)), '2025-26')

    def test_late_year(self) -> None:
        self.assertEqual(get_winter_season(date(2025, 11, 1)), '2025-26')
        self.assertEqual(get_winter_season(date(2025, 12, 15)), '2025-26')

    def test_offseason(self) -> None:
        self.assertEqual(get_winter_season(date(2026, 7, 15)), '2026-offseason')


class TestBuildCoverageReport(unittest.TestCase):
    """P5: Coverage report building."""

    def setUp(self) -> None:
        self.candidates = [
            build_candidate_from_parse_result(
                bulletin_id='B1', source_url='url1', pdf_bytes=b'c1',
                parse_status=PARSE_COMPLETE,
                issue_date=date(2026, 4, 30),
                valid_from=date(2026, 4, 30),
                valid_until=date(2026, 5, 1),
                rows=[
                    {'district': 'Poonch', 'danger_level': 1},
                    {'district': 'Kargil', 'danger_level': 3, 'altitude_band': 'Above 3100 m'},
                    {'district': 'Baramulla', 'danger_level': 2, 'altitude_band': 'Above 3000 m'},
                ],
            ),
            build_candidate_from_parse_result(
                bulletin_id='B2', source_url='url2', pdf_bytes=b'c2',
                parse_status=PARSE_COMPLETE,
                issue_date=date(2026, 5, 1),
                rows=[
                    {'district': 'Poonch', 'danger_level': 1},
                    {'district': 'Kargil', 'danger_level': 4, 'altitude_band': 'Above 3100 m'},
                ],
            ),
        ]

    def test_total_counts(self) -> None:
        report = build_coverage_report(self.candidates)
        self.assertEqual(report.total_candidates, 2)
        self.assertEqual(report.total_complete, 2)
        self.assertEqual(report.total_rows, 5)
        self.assertIsNone(report.total_listed)
        self.assertIsNone(report.total_fetched)
        self.assertFalse(report.archive_denominators_verified)

    def test_missing_and_unknown_rows_are_not_valid(self) -> None:
        candidate = build_candidate_from_parse_result(
            bulletin_id='invalid', source_url='url', pdf_bytes=b'invalid',
            parse_status=PARSE_COMPLETE,
            rows=[
                {'district': '', 'danger_level': None},
                {'district': 'Unknown Place', 'danger_level': 1},
                {'district': 'Poonch', 'danger_level': 9},
                {'district': 'Poonch', 'danger_level': 1},
            ],
        )
        report = build_coverage_report([candidate])
        self.assertEqual(report.total_valid_rows, 1)
        self.assertEqual(report.missing_required_fields_rows, 1)
        self.assertEqual(report.unknown_district_rows, 1)
        self.assertEqual(report.invalid_danger_level_rows, 1)

    def test_row_identity_includes_danger_level(self) -> None:
        candidate = build_candidate_from_parse_result(
            bulletin_id='levels', source_url='url', pdf_bytes=b'levels',
            parse_status=PARSE_COMPLETE,
            rows=[
                {'district': 'Poonch', 'altitude_band': 'Above 3000 m', 'danger_level': 1},
                {'district': 'Poonch', 'altitude_band': 'Above 3000 m', 'danger_level': 2},
            ],
        )
        report = build_coverage_report([candidate])
        self.assertEqual(report.total_valid_rows, 2)
        self.assertEqual(report.duplicate_rows, 0)

    def test_explicit_archive_denominators_are_preserved(self) -> None:
        report = build_coverage_report(
            self.candidates,
            total_listed=12,
            total_fetched=2,
            denominator_source='archive_snapshot_v1',
        )
        self.assertEqual(report.total_listed, 12)
        self.assertEqual(report.total_fetched, 2)
        self.assertTrue(report.archive_denominators_verified)
        self.assertEqual(report.denominator_source, 'archive_snapshot_v1')

    def test_level_counts(self) -> None:
        report = build_coverage_report(self.candidates)
        self.assertEqual(report.level_counts[1], 2)  # Poonch x2
        self.assertEqual(report.level_counts[2], 1)  # Baramulla
        self.assertEqual(report.level_counts[3], 1)  # Kargil
        self.assertEqual(report.level_counts[4], 1)  # Kargil
        self.assertEqual(report.level_counts.get(5, 0), 0)  # No Level 5

    def test_region_counts(self) -> None:
        report = build_coverage_report(self.candidates)
        self.assertEqual(report.region_counts['Jammu & Kashmir'], 3)  # Poonch x2 + Baramulla
        self.assertEqual(report.region_counts['Ladakh'], 2)  # Kargil x2

    def test_season_counts(self) -> None:
        report = build_coverage_report(self.candidates)
        self.assertEqual(report.season_counts['2025-26'], 2)

    def test_district_counts(self) -> None:
        report = build_coverage_report(self.candidates)
        self.assertEqual(report.district_counts['Poonch'], 2)
        self.assertEqual(report.district_counts['Kargil'], 2)
        self.assertEqual(report.district_counts['Baramulla'], 1)

    def test_class_distribution(self) -> None:
        report = build_coverage_report(self.candidates)
        total = sum(report.level_counts.values())
        self.assertAlmostEqual(sum(report.class_distribution.values()), 1.0)
        self.assertAlmostEqual(report.class_distribution[1], 2 / total)

    def test_level_5_reported_exactly_as_observed(self) -> None:
        """P5 exit gate: Level 5 is reported exactly as observed, never inflated."""
        # Add a candidate with Level 5
        candidates = self.candidates + [
            build_candidate_from_parse_result(
                bulletin_id='B3', source_url='url3', pdf_bytes=b'c3',
                parse_status=PARSE_COMPLETE,
                issue_date=date(2026, 2, 15),
                rows=[
                    {'district': 'Kargil', 'danger_level': 5, 'altitude_band': 'Above 3100 m'},
                ],
            ),
        ]
        report = build_coverage_report(candidates)
        self.assertEqual(report.level_5_count, 1)  # Exactly 1, not inflated
        self.assertIn('Kargil', report.level_5_districts)
        self.assertIn('2025-26', report.level_5_seasons)

    def test_level_5_not_merged(self) -> None:
        """P5: Level 5 is never merged with Level 4."""
        candidates = [
            build_candidate_from_parse_result(
                bulletin_id='B1', source_url='url1', pdf_bytes=b'c1',
                parse_status=PARSE_COMPLETE,
                issue_date=date(2026, 2, 15),
                rows=[
                    {'district': 'Kargil', 'danger_level': 4},
                    {'district': 'Leh', 'danger_level': 5},
                ],
            ),
        ]
        report = build_coverage_report(candidates)
        self.assertEqual(report.level_counts[4], 1)
        self.assertEqual(report.level_counts[5], 1)
        self.assertEqual(report.level_5_count, 1)  # Not merged into 4

    def test_parse_success_rate(self) -> None:
        candidates = self.candidates + [
            build_candidate_from_parse_result(
                bulletin_id='B3', source_url='url3', pdf_bytes=b'c3',
                parse_status=PARSE_FAILED,
            ),
        ]
        report = build_coverage_report(candidates)
        self.assertAlmostEqual(report.parse_success_rate, 2 / 3)

    def test_avg_rows_per_bulletin(self) -> None:
        report = build_coverage_report(self.candidates)
        self.assertAlmostEqual(report.avg_rows_per_bulletin, 2.5)  # 5 rows / 2 bulletins

    def test_empty_candidates(self) -> None:
        report = build_coverage_report([])
        self.assertEqual(report.total_candidates, 0)
        self.assertEqual(report.total_rows, 0)
        self.assertEqual(report.level_5_count, 0)


class TestG6CoverageDenominators(unittest.TestCase):
    """G6: Coverage report has separate denominators and versioned policies."""

    def test_g6_report_has_versioned_region_map(self) -> None:
        """G6: Coverage report must reference the region map version."""
        from backend.common.Partner_coverage_audit import CoverageReport, REGION_MAP_VERSION
        report = CoverageReport()
        self.assertEqual(report.region_map_version, REGION_MAP_VERSION)

    def test_g6_report_has_versioned_season_policy(self) -> None:
        """G6: Coverage report must reference the season policy version."""
        from backend.common.Partner_coverage_audit import CoverageReport, SEASON_POLICY_VERSION
        report = CoverageReport()
        self.assertEqual(report.season_policy_version, SEASON_POLICY_VERSION)

    def test_g6_report_has_separate_denominators(self) -> None:
        """G6: Report must have listed/fetched/parseable/complete/valid_rows/training_eligible."""
        from backend.common.Partner_coverage_audit import CoverageReport
        report = CoverageReport()
        # All denominator fields must exist
        self.assertTrue(hasattr(report, 'total_listed'))
        self.assertTrue(hasattr(report, 'total_fetched'))
        self.assertTrue(hasattr(report, 'total_parseable'))
        self.assertTrue(hasattr(report, 'total_valid_rows'))
        self.assertTrue(hasattr(report, 'total_training_eligible'))

    def test_g6_report_has_invalid_duplicate_counts(self) -> None:
        """G6: Report must count unknown/invalid/duplicate rows separately."""
        from backend.common.Partner_coverage_audit import CoverageReport
        report = CoverageReport()
        self.assertTrue(hasattr(report, 'unknown_district_rows'))
        self.assertTrue(hasattr(report, 'invalid_danger_level_rows'))
        self.assertTrue(hasattr(report, 'duplicate_rows'))

    def test_g6_training_eligible_always_zero_for_public(self) -> None:
        """G6: total_training_eligible must be 0 for public candidates."""
        from backend.common.Partner_coverage_audit import build_coverage_report
        from backend.common.Partner_public_candidate import build_candidate_from_parse_result, PARSE_COMPLETE
        candidates = [
            build_candidate_from_parse_result(
                bulletin_id='TEST', source_url='url', pdf_bytes=b'test',
                parse_status=PARSE_COMPLETE,
            ),
        ]
        report = build_coverage_report(candidates)
        self.assertEqual(report.total_training_eligible, 0)


class TestSaveLoadCoverageReport(unittest.TestCase):
    """P5: Report persistence."""

    def test_save_and_load(self) -> None:
        candidates = [
            build_candidate_from_parse_result(
                bulletin_id='B1', source_url='url1', pdf_bytes=b'c1',
                parse_status=PARSE_COMPLETE,
                issue_date=date(2026, 4, 30),
                rows=[{'district': 'Poonch', 'danger_level': 1}],
            ),
        ]
        report = build_coverage_report(candidates)
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            path = Path(f.name)
        try:
            save_coverage_report(report, path)
            loaded = load_coverage_report(path)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.total_candidates, 1)
            self.assertEqual(loaded.level_counts[1], 1)
        finally:
            path.unlink()

    def test_non_object_json_returns_structured_blocker(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as handle:
            path = Path(handle.name)
        try:
            path.write_text('[]', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, r'^E030_malformed_evidence:'):
                load_coverage_report(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    unittest.main()
