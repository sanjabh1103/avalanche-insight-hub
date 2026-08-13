"""Citizen-Science: Community-Reported Avalanche Observations.

Backend module for anonymous community-reported avalanche observations.
Reports are validated, rate-limited by IP, stored in Supabase, and fed into
the F19 continuous learning loop as weak labels (confidence 0.3).

Env flags:
  CITIZEN_SCIENCE_ENABLED — master switch (default: false)
  CITIZEN_RATE_LIMIT_PER_HOUR — max reports per IP per hour (default: 5)
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from collections import defaultdict

CITIZEN_SCIENCE_ENABLED = os.getenv('CITIZEN_SCIENCE_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}
CITIZEN_RATE_LIMIT_PER_HOUR = int(os.getenv('CITIZEN_RATE_LIMIT_PER_HOUR', '5'))

# Weak label confidence for citizen reports in continuous learning
CITIZEN_LABEL_CONFIDENCE = 0.3
CITIZEN_LABEL_SOURCE = 'citizen'


@dataclass(frozen=True)
class CitizenReport:
    """A community-reported avalanche observation."""
    report_id: str
    lat: float
    lng: float
    timestamp: datetime
    description: str
    photo_url: str | None = None
    reporter_id: str | None = None  # None = anonymous
    confidence: float = CITIZEN_LABEL_CONFIDENCE
    status: str = 'pending'  # pending, validated, rejected
    hazard_type: str = 'avalanche'
    estimated_size: str | None = None  # small, medium, large
    weather_conditions: str | None = None


class RateLimiter:
    """Simple in-memory rate limiter keyed by IP."""

    def __init__(self, max_per_hour: int = CITIZEN_RATE_LIMIT_PER_HOUR) -> None:
        self.max_per_hour = max_per_hour
        self._timestamps: dict[str, list[float]] = defaultdict(list)

    def check(self, ip: str) -> bool:
        """Check if IP is within rate limit.

        Args:
            ip: Client IP address

        Returns:
            True if allowed, False if rate limited
        """
        now = time.time()
        cutoff = now - 3600  # 1 hour ago

        # Clean old entries
        self._timestamps[ip] = [t for t in self._timestamps[ip] if t > cutoff]

        if len(self._timestamps[ip]) >= self.max_per_hour:
            return False

        self._timestamps[ip].append(now)
        return True

    def remaining(self, ip: str) -> int:
        """Get remaining requests for IP."""
        now = time.time()
        cutoff = now - 3600
        self._timestamps[ip] = [t for t in self._timestamps[ip] if t > cutoff]
        return max(0, self.max_per_hour - len(self._timestamps[ip]))


def validate_report(
    *,
    lat: float,
    lng: float,
    description: str,
) -> tuple[bool, str]:
    """Validate citizen report fields.

    Args:
        lat: Latitude
        lng: Longitude
        description: Description text

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not (-90 <= lat <= 90):
        return False, 'Latitude must be between -90 and 90'
    if not (-180 <= lng <= 180):
        return False, 'Longitude must be between -180 and 180'
    if not description or len(description.strip()) < 10:
        return False, 'Description must be at least 10 characters'
    if len(description) > 2000:
        return False, 'Description must be under 2000 characters'
    return True, ''


def create_report(
    *,
    lat: float,
    lng: float,
    description: str,
    photo_url: str | None = None,
    reporter_id: str | None = None,
    estimated_size: str | None = None,
    weather_conditions: str | None = None,
    hazard_type: str = 'avalanche',
) -> CitizenReport:
    """Create and validate a citizen report.

    Args:
        lat: Latitude
        lng: Longitude
        description: Description text
        photo_url: Optional photo URL
        reporter_id: Optional reporter ID (None = anonymous)
        estimated_size: Optional size estimate
        weather_conditions: Optional weather description
        hazard_type: Hazard type (default: avalanche)

    Returns:
        CitizenReport

    Raises:
        ValueError: If validation fails
    """
    is_valid, error = validate_report(lat=lat, lng=lng, description=description)
    if not is_valid:
        raise ValueError(error)

    report_id = f'cr_{int(time.time() * 1000)}_{abs(hash((lat, lng, description))) % 10000}'

    return CitizenReport(
        report_id=report_id,
        lat=lat,
        lng=lng,
        timestamp=datetime.now(timezone.utc),
        description=description.strip(),
        photo_url=photo_url,
        reporter_id=reporter_id,
        confidence=CITIZEN_LABEL_CONFIDENCE,
        status='pending',
        hazard_type=hazard_type,
        estimated_size=estimated_size,
        weather_conditions=weather_conditions,
    )


def report_to_weak_label(report: CitizenReport) -> dict[str, Any]:
    """Convert a citizen report to a weak label for continuous learning.

    Args:
        report: Validated citizen report

    Returns:
        Dict with label fields for continuous_learning.py
    """
    return {
        'label_source': CITIZEN_LABEL_SOURCE,
        'confidence': CITIZEN_LABEL_CONFIDENCE,
        'lat': report.lat,
        'lng': report.lng,
        'timestamp': report.timestamp.isoformat(),
        'description': report.description,
        'report_id': report.report_id,
        'hazard_type': report.hazard_type,
    }


def report_to_supabase_row(report: CitizenReport) -> dict[str, Any]:
    """Convert a citizen report to a Supabase row dict.

    Args:
        report: Citizen report

    Returns:
        Dict matching citizen_reports table schema
    """
    return {
        'report_id': report.report_id,
        'lat': report.lat,
        'lng': report.lng,
        'timestamp': report.timestamp.isoformat(),
        'description': report.description,
        'photo_url': report.photo_url,
        'reporter_id': report.reporter_id,
        'confidence': report.confidence,
        'status': report.status,
        'hazard_type': report.hazard_type,
        'estimated_size': report.estimated_size,
        'weather_conditions': report.weather_conditions,
    }


def reports_to_geojson(reports: list[CitizenReport]) -> dict[str, Any]:
    """Convert reports to GeoJSON for map overlay.

    Args:
        reports: List of citizen reports

    Returns:
        GeoJSON FeatureCollection
    """
    features: list[dict[str, Any]] = []
    for report in reports:
        features.append({
            'type': 'Feature',
            'geometry': {
                'type': 'Point',
                'coordinates': [report.lng, report.lat],
            },
            'properties': {
                'report_id': report.report_id,
                'timestamp': report.timestamp.isoformat(),
                'description': report.description,
                'confidence': report.confidence,
                'status': report.status,
                'hazard_type': report.hazard_type,
                'has_photo': report.photo_url is not None,
                'estimated_size': report.estimated_size,
                'source': 'citizen',
            },
        })

    return {
        'type': 'FeatureCollection',
        'features': features,
    }


class CitizenScienceManager:
    """Manages citizen report ingestion, validation, and weak label generation."""

    def __init__(
        self,
        *,
        rate_limit_per_hour: int = CITIZEN_RATE_LIMIT_PER_HOUR,
    ) -> None:
        self.rate_limiter = RateLimiter(max_per_hour=rate_limit_per_hour)
        self.reports: list[CitizenReport] = []

    def submit_report(
        self,
        *,
        ip: str,
        lat: float,
        lng: float,
        description: str,
        photo_url: str | None = None,
        reporter_id: str | None = None,
        estimated_size: str | None = None,
        weather_conditions: str | None = None,
        hazard_type: str = 'avalanche',
    ) -> tuple[CitizenReport | None, str]:
        """Submit a citizen report with rate limiting.

        Args:
            ip: Client IP for rate limiting
            lat, lng, description, etc.: Report fields

        Returns:
            Tuple of (report_or_none, message)
        """
        if not self.rate_limiter.check(ip):
            remaining = self.rate_limiter.remaining(ip)
            return None, f'Rate limit exceeded. Try again later. (Remaining: {remaining})'

        try:
            report = create_report(
                lat=lat,
                lng=lng,
                description=description,
                photo_url=photo_url,
                reporter_id=reporter_id,
                estimated_size=estimated_size,
                weather_conditions=weather_conditions,
                hazard_type=hazard_type,
            )
        except ValueError as exc:
            return None, str(exc)

        self.reports.append(report)
        return report, 'Report submitted successfully'

    def get_weak_labels(self) -> list[dict[str, Any]]:
        """Get all reports as weak labels for continuous learning.

        Returns:
            List of weak label dicts
        """
        return [report_to_weak_label(r) for r in self.reports if r.status != 'rejected']

    def get_status(self) -> dict[str, Any]:
        """Get manager status."""
        return {
            'enabled': CITIZEN_SCIENCE_ENABLED,
            'rate_limit_per_hour': self.rate_limiter.max_per_hour,
            'total_reports': len(self.reports),
            'pending_reports': sum(1 for r in self.reports if r.status == 'pending'),
            'validated_reports': sum(1 for r in self.reports if r.status == 'validated'),
        }
