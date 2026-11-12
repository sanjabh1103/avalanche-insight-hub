"""Partner coverage and quality audit module.

P5: Coverage and quality audit — computes class/season/region/level coverage
from collected PublicBulletinCandidateV1 entries.

P5 exit gate: A coverage report exists with class/season/region/level counts;
Level 5 is reported exactly as observed (never inflated or merged).
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from backend.common.Partner_public_candidate import (
    PublicBulletinCandidateV1,
    PARSE_COMPLETE,
    PARSE_PARTIAL,
)


# Himalayan regions mapped from district names
# Source: Partner bulletin region headers
# G6: Region map is versioned for reproducibility
REGION_MAP_VERSION = '2026-04-30-v1'
REGION_MAP: dict[str, str] = {
    # Jammu & Kashmir
    'poonch': 'Jammu & Kashmir',
    'rajouri': 'Jammu & Kashmir',
    'reasi': 'Jammu & Kashmir',
    'ramban': 'Jammu & Kashmir',
    'doda': 'Jammu & Kashmir',
    'kishtwar': 'Jammu & Kashmir',
    'udhampur': 'Jammu & Kashmir',
    'anantnag': 'Jammu & Kashmir',
    'baramulla': 'Jammu & Kashmir',
    'kupwara': 'Jammu & Kashmir',
    'bandipora': 'Jammu & Kashmir',
    'ganderbal': 'Jammu & Kashmir',
    # Ladakh
    'kargil': 'Ladakh',
    'leh': 'Ladakh',
    # Himachal Pradesh
    'chamba': 'Himachal Pradesh',
    'lahaul-spiti': 'Himachal Pradesh',
    'lahaul and spiti': 'Himachal Pradesh',
    'kullu': 'Himachal Pradesh',
    'kinnaur': 'Himachal Pradesh',
    'shimla': 'Himachal Pradesh',
    # Uttarakhand
    'uttarkashi': 'Uttarakhand',
    'chamoli': 'Uttarakhand',
    'rudraprayag': 'Uttarakhand',
    'pithoragarh': 'Uttarakhand',
    'bagheshwar': 'Uttarakhand',
    'bageshwar': 'Uttarakhand',
    # Sikkim
    'north sikkim': 'Sikkim',
    'east sikkim': 'Sikkim',
    'west sikkim': 'Sikkim',
    'south sikkim': 'Sikkim',
}


def get_region_for_district(district: str) -> str:
    """Map a district name to its Himalayan region."""
    key = district.lower().strip()
    if key in REGION_MAP:
        return REGION_MAP[key]
    # Try without hyphens
    key_alt = key.replace('-', ' ')
    if key_alt in REGION_MAP:
        return REGION_MAP[key_alt]
    return 'Unknown'


def get_winter_season(d: date) -> str:
    """Map a date to its winter season string.

    Partner winter seasons run from approximately November to May.
    Season 2025-26 covers Nov 2025 through May 2026.

    G6: Season policy is versioned for reproducibility.
    Policy version: SEASON_POLICY_VERSION
    """
    if d.month >= 11:
        return f'{d.year}-{str(d.year + 1)[-2:]}'
    elif d.month <= 5:
        return f'{d.year - 1}-{str(d.year)[-2:]}'
    else:
        return f'{d.year}-offseason'


# G6: Season policy version — documented for reproducibility
SEASON_POLICY_VERSION = '2026-04-30-v1'


@dataclass
class CoverageReport:
    """P5: Coverage report with class/season/region/level counts.

    Level 5 is reported exactly as observed — never inflated or merged.
    G6: Separate denominators for listed/fetched/parseable/complete/valid_rows/training_eligible.
    G6: Region map and season policy are versioned.
    """
    schema_version: str = 'Partner_coverage_audit_v1'
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # G6: Versioned policy references
    region_map_version: str = REGION_MAP_VERSION
    season_policy_version: str = SEASON_POLICY_VERSION

    # G6: Separate denominators
    total_listed: int | None = None  # Total bulletins listed in a verified archive snapshot
    total_fetched: int | None = None  # Total bulletins fetched (downloaded)
    denominator_source: str = 'candidate_inventory_only'
    archive_denominators_verified: bool = False
    total_candidates: int = 0  # Total candidates (fetched + classified)
    total_parseable: int = 0  # Candidates with parse_status in (complete, partial)
    total_complete: int = 0  # Candidates with parse_status=complete
    total_partial: int = 0  # Candidates with parse_status=partial
    total_rows: int = 0  # Total rows from parseable candidates
    total_valid_rows: int = 0  # G6: Rows that passed validation
    total_training_eligible: int = 0  # G6: Always 0 for public candidates

    # G6: Separate counts for invalid/duplicate/unknown rows
    unknown_district_rows: int = 0
    invalid_danger_level_rows: int = 0
    missing_required_fields_rows: int = 0
    duplicate_rows: int = 0

    # Coverage by danger level (1-5)
    level_counts: dict[int, int] = field(default_factory=dict)

    # Coverage by region
    region_counts: dict[str, int] = field(default_factory=dict)

    # Coverage by winter season
    season_counts: dict[str, int] = field(default_factory=dict)

    # Coverage by district
    district_counts: dict[str, int] = field(default_factory=dict)

    # Level 5 specifics — reported exactly as observed
    level_5_count: int = 0
    level_5_districts: list[str] = field(default_factory=list)
    level_5_seasons: list[str] = field(default_factory=list)

    # Quality metrics
    parse_success_rate: float = 0.0
    avg_rows_per_bulletin: float = 0.0

    # Class distribution (percentage by level)
    class_distribution: dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_coverage_report(
    candidates: list[PublicBulletinCandidateV1],
    *,
    total_listed: int | None = None,
    total_fetched: int | None = None,
    denominator_source: str = 'candidate_inventory_only',
) -> CoverageReport:
    """Build a coverage report from collected public candidates.

    P5 exit gate: Level 5 is reported exactly as observed (never inflated or merged).
    Only complete and partial candidates contribute to row-level coverage.
    """
    report = CoverageReport()
    report.total_candidates = len(candidates)
    report.total_complete = sum(1 for c in candidates if c.parse_status == PARSE_COMPLETE)
    report.total_partial = sum(1 for c in candidates if c.parse_status == PARSE_PARTIAL)
    report.total_parseable = report.total_complete + report.total_partial
    if total_listed is not None or total_fetched is not None:
        if not isinstance(total_listed, int) or not isinstance(total_fetched, int):
            raise ValueError('total_listed and total_fetched must both be integers when supplied')
        if total_listed < 0 or total_fetched < 0 or total_fetched > total_listed:
            raise ValueError('coverage denominators must satisfy 0 <= total_fetched <= total_listed')
        report.total_listed = total_listed
        report.total_fetched = total_fetched
        report.denominator_source = denominator_source
        report.archive_denominators_verified = denominator_source != 'candidate_inventory_only'
    # G6: training_eligible is always 0 for public candidates
    report.total_training_eligible = sum(1 for c in candidates if c.training_eligible)  # Always 0

    level_counter: Counter[int] = Counter()
    region_counter: Counter[str] = Counter()
    season_counter: Counter[str] = Counter()
    district_counter: Counter[str] = Counter()
    level_5_districts: set[str] = set()
    level_5_seasons: set[str] = set()

    parseable = [c for c in candidates if c.parse_status in (PARSE_COMPLETE, PARSE_PARTIAL)]

    # G6: Track seen (district, altitude_band) keys for duplicate detection
    # Duplicates are counted within the SAME candidate only, not across candidates
    for candidate in parseable:
        # Season from issue_date
        if candidate.issue_date:
            try:
                d = date.fromisoformat(candidate.issue_date)
                season = get_winter_season(d)
                season_counter[season] += 1
            except ValueError:
                pass

        # G6: Track duplicates within this candidate only
        seen_row_keys: set[tuple[str, str | None, int]] = set()

        # Row-level coverage
        for row in candidate.rows:
            report.total_rows += 1
            if not isinstance(row, dict):
                report.missing_required_fields_rows += 1
                continue
            district_raw = row.get('district')
            danger = row.get('danger_level')
            altitude = row.get('altitude_band')

            if not isinstance(district_raw, str) or not district_raw.strip() or danger is None:
                report.missing_required_fields_rows += 1
                continue
            district = district_raw.strip()

            # G6: Count duplicate rows within the same candidate
            altitude_key = altitude.strip() if isinstance(altitude, str) and altitude.strip() else None
            row_key = (district.lower(), altitude_key, danger)
            if row_key in seen_row_keys:
                report.duplicate_rows += 1
                continue  # Skip duplicates in coverage counts
            seen_row_keys.add(row_key)

            region = get_region_for_district(district)
            if region == 'Unknown':
                report.unknown_district_rows += 1
                continue

            if isinstance(danger, bool) or not isinstance(danger, int) or not (1 <= danger <= 5):
                report.invalid_danger_level_rows += 1
                continue  # Skip invalid danger levels

            # G6: Count valid rows
            report.total_valid_rows += 1

            district_counter[district] += 1
            region_counter[region] += 1

            level_counter[danger] += 1

            # Level 5 tracking — exact, never inflated
            if danger == 5:
                level_5_districts.add(district)
                if candidate.issue_date:
                    try:
                        d = date.fromisoformat(candidate.issue_date)
                        level_5_seasons.add(get_winter_season(d))
                    except ValueError:
                        pass

    # Populate report
    report.level_counts = dict(sorted(level_counter.items()))
    report.region_counts = dict(sorted(region_counter.items()))
    report.season_counts = dict(sorted(season_counter.items()))
    report.district_counts = dict(sorted(district_counter.items()))
    report.level_5_count = level_counter.get(5, 0)
    report.level_5_districts = sorted(level_5_districts)
    report.level_5_seasons = sorted(level_5_seasons)

    # Quality metrics
    if report.total_candidates > 0:
        report.parse_success_rate = (
            (report.total_complete + report.total_partial) / report.total_candidates
        )
    if parseable:
        report.avg_rows_per_bulletin = report.total_rows / len(parseable)

    # Class distribution (percentage)
    total_leveled = sum(level_counter.values())
    if total_leveled > 0:
        report.class_distribution = {
            level: count / total_leveled
            for level, count in sorted(level_counter.items())
        }

    return report


def save_coverage_report(report: CoverageReport, path: Path) -> None:
    """Save coverage report to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))


def load_coverage_report(path: Path) -> CoverageReport | None:
    """Load a previously saved coverage report fail-closed."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError('E030_malformed_evidence: coverage report must be a JSON object')
        # Reconstruct from dict
        report = CoverageReport()
        for key, value in data.items():
            if hasattr(report, key):
                setattr(report, key, value)
        # Convert level_counts keys back to int (JSON makes them strings)
        if report.level_counts:
            report.level_counts = {int(k): v for k, v in report.level_counts.items()}
        if report.class_distribution:
            report.class_distribution = {
                int(k): v for k, v in report.class_distribution.items()
            }
        return report
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        message = str(exc)
        if message.startswith('E030_malformed_evidence:'):
            raise ValueError(message) from exc
        raise ValueError(f'coverage report load failed: {exc}') from exc
