"""Partner avalanche warning bulletin adapter.

Parses public Partner (Defence Geoinformatics and Research Establishment)
avalanche warning bulletins from Partner public URLs into validation label
rows for Himalayan zones.

Bulletins are published as PDFs at:
  https://Partner.gov.in/avalanche-warning-bulletin/Partner_AWB_*.pdf

This adapter is credential-free and parses publicly available documents.

Env flags:
  Partner_BULLETIN_VALIDATION_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

Partner_BULLETIN_VALIDATION_ENABLED = os.getenv(
    'Partner_BULLETIN_VALIDATION_ENABLED', 'false'
).lower() not in {'0', 'false', 'off', 'no'}

Partner_BULLETIN_BASE_URL = 'https://Partner.gov.in/avalanche-warning-bulletin'

Partner_PROVENANCE_REGISTRY_PATH = os.getenv(
    'Partner_PROVENANCE_REGISTRY_PATH',
    str(Path(__file__).resolve().parent.parent / 'config' / 'Partner_provenance_registry.json')
)

# --- P1: Correct danger semantics — separate Partner from EAWS ---

# Partner-specific danger level colors (canonical for this adapter).
# Partner uses color codes: Green, Yellow, Orange, Red, Black.
# These are NOT EAWS names — EAWS uses Low/Moderate/Considerable/High/Very High.
Partner_DANGER_LEVELS = {
    1: 'green',
    2: 'yellow',
    3: 'orange',
    4: 'red',
    5: 'black',
}

# EAWS comparison names (explicitly separate, never silently interchanged).
# Source: European Avalanche Danger Scale (avalanches.org/standards/avalanche-danger-scale).
EAWS_DANGER_LEVELS = {
    1: 'low',
    2: 'moderate',
    3: 'considerable',
    4: 'high',
    5: 'very_high',
}


@dataclass(frozen=True)
class PartnerDangerLevelV1:
    """Canonical Partner danger level semantics with explicit EAWS comparison.

    Numeric level is canonical (1-5). Partner color/action/snow_condition are
    the operational semantics used in Indian Himalayan bulletins. EAWS name
    is provided as an explicit comparison only — it must never be silently
    interchanged with Partner semantics.

    P1 exit gate: Levels 1-5 round-trip without ambiguous strings;
    Partner and EAWS cannot be silently interchanged.
    """

    numeric_level: int
    Partner_color: str
    Partner_snow_condition: str
    Partner_action: str
    eaws_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            'numeric_level': self.numeric_level,
            'Partner_color': self.Partner_color,
            'Partner_snow_condition': self.Partner_snow_condition,
            'Partner_action': self.Partner_action,
            'eaws_name': self.eaws_name,
        }


# Full Partner danger level semantics table.
# Source: Partner Avalanche Warning Bulletins (Partner.gov.in), observed legend text.
# Action text is summarized from the bulletin legend; exact wording may vary
# by bulletin revision. The snow_condition field is the Partner label, not EAWS.
Partner_DANGER_SEMANTICS: dict[int, PartnerDangerLevelV1] = {
    1: PartnerDangerLevelV1(
        numeric_level=1,
        Partner_color='green',
        Partner_snow_condition='Generally safe',
        Partner_action='Explore slopes; snowpack generally well bonded.',
        eaws_name='low',
    ),
    2: PartnerDangerLevelV1(
        numeric_level=2,
        Partner_color='yellow',
        Partner_snow_condition='Partly unsafe',
        Partner_action='Be careful on steep slopes; few avalanche paths loaded.',
        eaws_name='moderate',
    ),
    3: PartnerDangerLevelV1(
        numeric_level=3,
        Partner_color='orange',
        Partner_snow_condition='Unsafe condition',
        Partner_action='Evacuate from avalanche paths; prepare for spontaneous releases.',
        eaws_name='considerable',
    ),
    4: PartnerDangerLevelV1(
        numeric_level=4,
        Partner_color='red',
        Partner_snow_condition='Highly unsafe',
        Partner_action='Do not enter avalanche terrain; spontaneous avalanches likely.',
        eaws_name='high',
    ),
    5: PartnerDangerLevelV1(
        numeric_level=5,
        Partner_color='black',
        Partner_snow_condition='Extremely unsafe',
        Partner_action='Complete evacuation; all slopes loaded, widespread natural avalanches.',
        eaws_name='very_high',
    ),
}


def get_Partner_danger_semantics(level: int) -> PartnerDangerLevelV1 | None:
    """Return the canonical Partner danger level semantics for a numeric level.

    Returns None if level is not in 1-5 range.
    """
    return Partner_DANGER_SEMANTICS.get(level)


def get_eaws_comparison(level: int) -> str | None:
    """Return the EAWS comparison name for a numeric danger level.

    This is explicitly a comparison — it must never be used as the primary
    label for Partner bulletins. Use get_Partner_danger_semantics() for Partner labels.
    """
    return EAWS_DANGER_LEVELS.get(level)


# Backward-compatible alias — now Partner-specific (color names, not EAWS names).
# P1 fix: level 3 is 'orange' (Partner), NOT 'high' (which is EAWS level 4).
# level 4 is 'red' (Partner), NOT 'very_high' (which is EAWS level 5).
DANGER_LEVELS = Partner_DANGER_LEVELS


@dataclass
class PartnerBulletinRow:
    """A single district/altitude row within a Partner bulletin."""

    district: str | None = None
    altitude_band: str | None = None
    danger_level: int | None = None
    danger_level_label: str | None = None  # Partner color name (green/yellow/orange/red/black)
    Partner_color: str | None = None  # P1: explicit Partner color
    eaws_label: str | None = None  # P1: explicit EAWS comparison name
    snow_condition: str | None = None
    likelihood: str | None = None
    provenance_backed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            'district': self.district,
            'altitude_band': self.altitude_band,
            'danger_level': self.danger_level,
            'danger_level_label': self.danger_level_label,
            'Partner_color': self.Partner_color,
            'eaws_label': self.eaws_label,
            'snow_condition': self.snow_condition,
            'likelihood': self.likelihood,
            'provenance_backed': self.provenance_backed,
        }


@dataclass
class PartnerBulletinRecord:
    """Parsed Partner bulletin record."""

    bulletin_id: str
    issue_date: date | None = None
    valid_until: date | None = None
    danger_level: int | None = None
    danger_level_label: str | None = None  # Partner color name
    Partner_color: str | None = None  # P1: explicit Partner color
    eaws_label: str | None = None  # P1: explicit EAWS comparison name
    zone: str | None = None
    region_key: str | None = None
    source_url: str | None = None
    raw_text: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)
    rows: list[PartnerBulletinRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'bulletin_id': self.bulletin_id,
            'issue_date': self.issue_date.isoformat() if self.issue_date else None,
            'valid_until': self.valid_until.isoformat() if self.valid_until else None,
            'danger_level': self.danger_level,
            'danger_level_label': self.danger_level_label,
            'Partner_color': self.Partner_color,
            'eaws_label': self.eaws_label,
            'zone': self.zone,
            'region_key': self.region_key,
            'source_url': self.source_url,
            'provenance': 'Partner_public_bulletin',
            'metadata': self.metadata,
            'rows': [r.to_dict() for r in self.rows],
        }


@dataclass
class ParseResult:
    """Result of parsing a Partner bulletin with completeness and provenance tracking.

    Attributes:
        record: The parsed PartnerBulletinRecord, or None if parsing failed.
        is_complete: True if all required fields (issue_date, danger_level, rows) are present.
        complete_row_count: Number of rows with all fields populated.
        parse_error: Error message if parsing failed, else None.
        provenance_hash: SHA-256 hash of source content, or None if not available.
    """
    record: PartnerBulletinRecord | None
    is_complete: bool
    complete_row_count: int
    parse_error: str | None
    provenance_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            'record': self.record.to_dict() if self.record else None,
            'is_complete': self.is_complete,
            'complete_row_count': self.complete_row_count,
            'parse_error': self.parse_error,
            'provenance_hash': self.provenance_hash,
        }


def parse_danger_level(text: str) -> int | None:
    """Extract danger level (1-5) from bulletin text."""
    patterns = [
        r'danger\s*level[:\s]*(\d)',
        r'avalanche\s*warning\s*level[:\s]*(\d)',
        r'level[:\s]*(\d)\s*of\s*5',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            level = int(match.group(1))
            if 1 <= level <= 5:
                return level
    return None


def parse_zone(text: str) -> str | None:
    """Extract zone name from bulletin text."""
    patterns = [
        r'zone[:\s]*([A-Za-z\s]+?)(?:\n|$)',
        r'sector[:\s]*([A-Za-z\s]+?)(?:\n|$)',
        r'region[:\s]*([A-Za-z\s]+?)(?:\n|$)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_bulletin_date(text: str) -> date | None:
    """Extract issue date from bulletin text.

    Returns None if no valid date is found or if the date is invalid (e.g., 31-02-2026).
    """
    date_patterns = [
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
        r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            try:
                if len(groups[0]) == 4:
                    return date(int(groups[0]), int(groups[1]), int(groups[2]))
                else:
                    return date(int(groups[2]), int(groups[1]), int(groups[0]))
            except ValueError:
                # Invalid date (e.g., 31-02-2026) — try next pattern or return None
                continue
    return None


def parse_validity_window(text: str) -> tuple[date | None, date | None]:
    """Extract the validity window from bulletin text.

    Partner bulletins contain text like:
      "Valid from 30-04-2026 (1700 hrs IST) TO 01-05-2026 (1700 hrs IST)"

    Returns (valid_from, valid_until). Either may be None if parsing fails.
    """
    # Pattern: Valid from DD-MM-YYYY ... TO DD-MM-YYYY
    pattern = re.compile(
        r'valid\s+from\s+(\d{1,2})[/-](\d{1,2})[/-](\d{4})'
        r'.*?\bto\b\s+(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if m:
        d1, mo1, y1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        d2, mo2, y2 = int(m.group(4)), int(m.group(5)), int(m.group(6))
        try:
            valid_from = date(y1, mo1, d1)
            valid_until = date(y2, mo2, d2)
            if valid_from > valid_until:
                return None, None  # Reversed dates — invalid
            return valid_from, valid_until
        except ValueError:
            return None, None

    # Fallback: try YYYY-MM-DD format
    pattern_ymd = re.compile(
        r'valid\s+from\s+(\d{4})[/-](\d{1,2})[/-](\d{1,2})'
        r'.*?\bto\b\s+(\d{4})[/-](\d{1,2})[/-](\d{1,2})',
        re.IGNORECASE,
    )
    m = pattern_ymd.search(text)
    if m:
        y1, mo1, d1 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y2, mo2, d2 = int(m.group(4)), int(m.group(5)), int(m.group(6))
        try:
            valid_from = date(y1, mo1, d1)
            valid_until = date(y2, mo2, d2)
            if valid_from > valid_until:
                return None, None  # Reversed dates — invalid
            return valid_from, valid_until
        except ValueError:
            return None, None

    return None, None


def parse_snow_condition(text: str) -> str | None:
    """Extract snow condition from bulletin text."""
    patterns = [
        r'snow\s*condition[:\s]*([A-Za-z\s]+?)(?:\n|$)',
        r'snow\s*pack[:\s]*([A-Za-z\s]+?)(?:\n|$)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_likelihood(text: str) -> str | None:
    """Extract likelihood from bulletin text."""
    patterns = [
        r'likelihood[:\s]*([A-Za-z\s]+?)(?:\n|$)',
        r'probability[:\s]*([A-Za-z\s]+?)(?:\n|$)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_bulletin_rows(text: str) -> tuple[list[PartnerBulletinRow], list[PartnerBulletinRow]]:
    """Extract multiple district/altitude rows from a multi-row bulletin.

    Partner bulletins typically contain a table with one row per district/altitude
    band, each with its own danger level. This function scans for repeated
    district + altitude + danger level patterns.

    Returns (complete_rows, partial_rows) where complete rows have all three
    fields (district, altitude_band, danger_level) and partial rows are missing
    at least one field.
    """
    all_rows: list[PartnerBulletinRow] = []

    # Split into lines and look for structured table rows
    lines = text.split('\n')
    for i, line in enumerate(lines):
        district = None
        altitude = None
        danger = None

        # Try to extract district from this line
        for pat in [r'district[:\s]*([A-Za-z\s]+?)(?:\s{2,}|\t|$)', r'([A-Z][a-z]+\s+[A-Z][a-z]+)']:
            m = re.search(pat, line, re.IGNORECASE)
            if m:
                district = m.group(1).strip()
                break

        # Try to extract altitude band from this line
        for pat in [r'(\d{3,5}\s*[-\u2013to ]+\d{3,5}\s*m)', r'above\s*(\d{3,5}\s*m)']:
            m = re.search(pat, line, re.IGNORECASE)
            if m:
                altitude = m.group(1).strip()
                break

        # Try to extract danger level from this line
        m = re.search(r'danger\s*level[:\s]*(\d)', line, re.IGNORECASE)
        if m:
            level = int(m.group(1))
            if 1 <= level <= 5:
                danger = level
        else:
            m = re.search(r'\b([1-5])\b\s*(?:of\s*5)?\s*$', line)
            if m and (district or altitude):
                danger = int(m.group(1))

        # Adjacent-row assembly: if district found but no danger, look at next 1-2 lines
        if district and danger is None:
            for j in range(i + 1, min(i + 3, len(lines))):
                next_line = lines[j]
                m2 = re.search(r'danger\s*level[:\s]*(\d)', next_line, re.IGNORECASE)
                if m2:
                    level = int(m2.group(1))
                    if 1 <= level <= 5:
                        danger = level
                        break
                m2 = re.search(r'\b([1-5])\b\s*(?:of\s*5)?\s*$', next_line)
                if m2:
                    danger = int(m2.group(1))
                    break

        # Adjacent-row assembly: if danger found but no district, look at prev line
        if danger and not district and i > 0:
            prev_line = lines[i - 1]
            for pat in [r'district[:\s]*([A-Za-z\s]+?)(?:\s{2,}|\t|$)', r'([A-Z][a-z]+\s+[A-Z][a-z]+)']:
                m = re.search(pat, prev_line, re.IGNORECASE)
                if m:
                    district = m.group(1).strip()
                    break

        if district or altitude or danger:
            all_rows.append(PartnerBulletinRow(
                district=district,
                altitude_band=altitude,
                danger_level=danger,
                danger_level_label=DANGER_LEVELS.get(danger) if danger else None,
                Partner_color=DANGER_LEVELS.get(danger) if danger else None,
                eaws_label=EAWS_DANGER_LEVELS.get(danger) if danger else None,
                snow_condition=parse_snow_condition(line),
                likelihood=parse_likelihood(line),
            ))

    # If no structured rows found, fall back to single-row extraction
    if not all_rows:
        district = parse_district(text)
        altitude = parse_altitude_band(text)
        danger = parse_danger_level(text)
        if district or altitude or danger:
            all_rows.append(PartnerBulletinRow(
                district=district,
                altitude_band=altitude,
                danger_level=danger,
                danger_level_label=DANGER_LEVELS.get(danger) if danger else None,
                Partner_color=DANGER_LEVELS.get(danger) if danger else None,
                eaws_label=EAWS_DANGER_LEVELS.get(danger) if danger else None,
                snow_condition=parse_snow_condition(text),
                likelihood=parse_likelihood(text),
            ))

    # Separate complete and partial rows
    # A row is complete if it has district AND danger_level.
    # altitude_band is optional — multi-district bulletins may have a default altitude
    # that applies to all rows, and some bulletins don't specify altitude per district.
    complete_rows = [
        r for r in all_rows
        if r.district is not None and r.danger_level is not None
    ]
    partial_rows = [r for r in all_rows if r not in complete_rows]

    return complete_rows, partial_rows


def parse_bulletin_text(text: str, bulletin_id: str, source_url: str | None = None) -> PartnerBulletinRecord:
    """Parse raw bulletin text into a structured record.

    Returns a record with issue_date=None if date parsing fails (no date.today() fallback).
    """
    danger_level = parse_danger_level(text)
    zone = parse_zone(text)
    issue_date = parse_bulletin_date(text)
    valid_from, valid_until = parse_validity_window(text)
    complete_rows, partial_rows = parse_bulletin_rows(text)

    return PartnerBulletinRecord(
        bulletin_id=bulletin_id,
        issue_date=issue_date,
        valid_until=valid_until,
        danger_level=danger_level,
        danger_level_label=DANGER_LEVELS.get(danger_level) if danger_level else None,
        Partner_color=DANGER_LEVELS.get(danger_level) if danger_level else None,
        eaws_label=EAWS_DANGER_LEVELS.get(danger_level) if danger_level else None,
        zone=zone,
        source_url=source_url,
        raw_text=text[:500],
        rows=complete_rows,
        metadata={'partial_rows': [r.to_dict() for r in partial_rows]} if partial_rows else {},
    )


def _extract_pdf_text(content: bytes) -> tuple[str, list[list[list[str]]]]:
    """Extract text and tables from PDF bytes using pdfplumber.

    Returns (text, tables) where tables is a list of pages, each containing
    a list of tables, each table being a list of rows (list of cell strings).

    Raises RuntimeError if pdfplumber is not installed — no silent UTF-8 fallback
    for binary PDF content.
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            'pdfplumber is required for Partner bulletin parsing but is not installed. '
            'Run: pip install pdfplumber==0.11.4'
        )

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            texts = []
            all_tables: list[list[list[str]]] = []
            for page in pdf.pages:
                text = page.extract_text() or ''
                texts.append(text)
                page_tables = page.extract_tables() or []
                for table in page_tables:
                    if table and isinstance(table, list):
                        cleaned = [
                            [(str(cell).strip() if cell is not None else '') for cell in row]
                            for row in table
                            if isinstance(row, list)
                        ]
                        if cleaned:
                            all_tables.append(cleaned)
            return '\n'.join(texts), all_tables
    except Exception as exc:
        import sys
        print(f'[Partner_bulletin] pdfplumber open error: {exc}', file=sys.stderr)
        raise


def parse_district(text: str) -> str | None:
    """Extract district name from bulletin text."""
    patterns = [
        r'district[:\s]*([A-Za-z\s]+?)(?:\n|$)',
        r'area[:\s]*([A-Za-z\s]+?)(?:\n|$)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_altitude_band(text: str) -> str | None:
    """Extract altitude band from bulletin text."""
    patterns = [
        r'altitude[:\s]*(\d{3,5}\s*[-–to ]+\d{3,5}\s*m)',
        r'elevation[:\s]*(\d{3,5}\s*[-–to ]+\d{3,5}\s*m)',
        r'above[:\s]*(\d{3,5}\s*m)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def verify_provenance_hash(
    bulletin_id: str,
    provenance_hash: str,
    registry_path: str | None = None,
) -> tuple[bool, str]:
    """Verify a bulletin's provenance hash against a registry.

    Supports two registry formats:
    - New format: {"entries": [{"bulletin_id": ..., "sha256": ..., "status": ...}]}
    - Legacy format: {bulletin_id: sha256_hash}

    Returns (verified, message). Only an exact SHA-256 hash match against
    a reviewed registry entry returns (True, 'hash_verified').

    All other cases return (False, reason) — fail closed, not open:
    - No registry configured: (False, 'registry_not_configured')
    - Registry file missing: (False, 'registry_not_found')
    - Bulletin not in registry: (False, 'bulletin_not_in_registry')
    - Placeholder entry: (False, 'placeholder_awaiting_review')
    - Hash mismatch: (False, 'hash_mismatch: ...')
    - Registry error: (False, 'registry_error: ...')
    """
    # G-05: Explicit empty string means "not configured" (fail closed).
    # None means "use default path".
    if registry_path is not None and registry_path == '':
        return False, 'registry_not_configured'
    reg_path = registry_path or Partner_PROVENANCE_REGISTRY_PATH
    if not reg_path:
        return False, 'registry_not_configured'
    try:
        reg_file = Path(reg_path)
        if not reg_file.exists():
            return False, 'registry_not_found'
        registry = json.loads(reg_file.read_text())

        # New format: entries list with status
        if isinstance(registry, dict) and 'entries' in registry:
            entries = registry['entries']
            for entry in entries:
                if entry.get('bulletin_id') == bulletin_id:
                    status = entry.get('status', 'reviewed')
                    if status == 'placeholder_awaiting_scientist_review':
                        return False, 'placeholder_awaiting_review'
                    expected_hash = entry.get('sha256', '')
                    if expected_hash == provenance_hash:
                        return True, 'hash_verified'
                    return False, f'hash_mismatch: expected {expected_hash[:12]}... got {provenance_hash[:12]}...'
            return False, 'bulletin_not_in_registry'

        # Legacy format: flat dict {bulletin_id: hash}
        expected_hash = registry.get(bulletin_id)
        if expected_hash is None:
            return False, 'bulletin_not_in_registry'
        if expected_hash == provenance_hash:
            return True, 'hash_verified'
        return False, f'hash_mismatch: expected {expected_hash[:12]}... got {provenance_hash[:12]}...'
    except Exception as exc:
        return False, f'registry_error: {exc}'


# Region header patterns for side-by-side tables
REGION_HEADER_RE = re.compile(
    r'^\s*\([A-E]\)\s+(.+?)\s*$',
    re.IGNORECASE,
)
# SN pattern: "1.", "2.", etc.
SN_RE = re.compile(r'^\s*(\d+)\.\s*$')
# Altitude pattern: "Above 3000 m", "3000-4000 m", etc.
ALTITUDE_CELL_RE = re.compile(
    r'(above\s+\d{3,5}\s*m|\d{3,5}\s*[-\u2013to ]+\d{3,5}\s*m)',
    re.IGNORECASE,
)
# District name: alphabetic text, not a number, not a header keyword
DISTRICT_KEYWORDS = {
    'districts', 'district', 'area', 'region', 'zone', 'sector',
    'danger', 'level', 'altitude', 'elevation', 'height', 'band',
    'snow', 'condition', 'likelihood', 'probability', 'avalanche',
    'sn', 'preferred', 'action', 'interpretation', 'degree',
}

# G2: Known Partner districts — used for validation and malformed row filtering
# Source: Partner bulletin region headers and district names from live bulletins
KNOWN_DISTRICTS: set[str] = {
    # Jammu & Kashmir
    'poonch', 'rajouri', 'reasi', 'ramban', 'doda', 'kishtwar',
    'udhampur', 'anantnag', 'baramulla', 'kupwara', 'bandipora',
    'ganderbal', 'gurez', 'gulmarg',
    # Ladakh
    'kargil', 'leh',
    # Himachal Pradesh
    'chamba', 'lahaul-spiti', 'lahaul and spiti', 'lahaul', 'kullu', 'kinnaur',
    'shimla',
    # Uttarakhand
    'uttarkashi', 'chamoli', 'rudraprayag', 'pithoragarh',
    'bagheshwar', 'bageshwar',
    # Sikkim
    'north sikkim', 'east sikkim', 'west sikkim', 'south sikkim',
}


def _is_valid_district(name: str) -> bool:
    """G2: Validate a district name against known districts and malformed patterns.

    Rejects:
    - Newline fragments (e.g., 'G\\nS\\ni\\H\\i')
    - Single characters
    - Strings shorter than 3 chars
    - Strings with only digits/symbols
    - Strings not in KNOWN_DISTRICTS (with fuzzy matching for hyphens)

    Note: Keyword rejection (e.g., 'Avalanche', 'Warning') is handled separately
    in _extract_entry_from_cells() via DISTRICT_KEYWORDS, not in this function.
    """
    if not name or not isinstance(name, str):
        return False
    cleaned = name.strip()
    if not cleaned:
        return False
    # Reject newline fragments
    if '\n' in cleaned:
        return False
    # Reject very short strings (single chars, two chars)
    if len(cleaned) < 3:
        return False
    # Reject strings that are mostly non-alphabetic
    alpha_count = sum(1 for c in cleaned if c.isalpha())
    if alpha_count < 2:
        return False
    # Check against known districts (case-insensitive)
    lower = cleaned.lower()
    if lower in KNOWN_DISTRICTS:
        return True
    # Try with hyphen replacement
    lower_alt = lower.replace('-', ' ')
    if lower_alt in KNOWN_DISTRICTS:
        return True
    # Try with hyphen insertion (e.g., "lahaulspiti" -> "lahaul-spiti")
    for d in KNOWN_DISTRICTS:
        if lower.replace('-', '').replace(' ', '') == d.replace('-', '').replace(' ', ''):
            return True
    # Not a known district — reject
    return False


def _is_region_header_row(row: list[str]) -> str | None:
    """Check if a row is a region header like '(A) UT of Jammu & Kashmir'.

    Returns the region name if matched, else None.
    """
    for cell in row:
        cell = str(cell).strip() if cell else ''
        if not cell:
            continue
        m = REGION_HEADER_RE.match(cell)
        if m:
            return m.group(1).strip()
    return None


def _extract_entry_from_cells(
    cells: list[str],
    region: str | None,
) -> PartnerBulletinRow | None:
    """Extract a single district entry from a half-row of cells.

    Scans cells for SN, district name, danger level (1-5), and altitude band.
    Returns None if no district or danger level is found.
    """
    sn_found = False
    district: str | None = None
    danger: int | None = None
    altitude: str | None = None

    for cell in cells:
        val = str(cell).strip() if cell else ''
        if not val:
            continue

        # Check for SN pattern
        sn_m = SN_RE.match(val)
        if sn_m and not sn_found:
            sn_found = True
            continue

        # Check for danger level (single digit 1-5)
        if not danger and re.match(r'^[1-5]$', val):
            danger = int(val)
            continue

        # Check for altitude band
        if not altitude:
            alt_m = ALTITUDE_CELL_RE.search(val)
            if alt_m:
                altitude = alt_m.group(1).strip()
                continue

        # Check for district name (alphabetic, not a keyword, not a number)
        if not district:
            # Skip if it's a number or SN
            if re.match(r'^\d+\.?$', val):
                continue
            # Skip if it's a keyword
            if val.lower().strip() in DISTRICT_KEYWORDS:
                continue
            # Skip if it contains only digits/symbols
            if not re.search(r'[A-Za-z]', val):
                continue
            # Skip region headers
            if REGION_HEADER_RE.match(val):
                continue
            # This looks like a district name
            # N9: Strip whitespace to prevent matching failures
            district = val.strip() if val else val

    if district and danger is not None:
        return PartnerBulletinRow(
            district=district,
            altitude_band=altitude,  # None means "all altitudes" — never inferred
            danger_level=danger,
            danger_level_label=DANGER_LEVELS.get(danger),
            Partner_color=DANGER_LEVELS.get(danger),
            eaws_label=EAWS_DANGER_LEVELS.get(danger),
            snow_condition=None,
            likelihood=None,
        )
    return None


def assemble_side_by_side_rows(tables: list[list[list[str]]]) -> list[PartnerBulletinRow]:
    """Parse side-by-side district tables from Partner bulletins.

    Partner bulletins use a two-column layout:
      Left half:  SN | District | Danger Level | Altitude
      Right half: SN | District | Danger Level | Altitude

    Each half is associated with a region header like:
      (A) UT of Jammu & Kashmir    (B) UT of Ladakh

    P3: This function handles the live bulletin layout where column
    positions shift between rows due to merged cells and wrapping.
    """
    rows: list[PartnerBulletinRow] = []

    for table in tables:
        if not table or len(table) < 2:
            continue

        # Track current region for left and right halves
        left_region: str | None = None
        right_region: str | None = None

        for raw_row in table:
            if not raw_row or not any(str(c).strip() for c in raw_row):
                continue

            cells = [(str(c).strip() if c is not None else '') for c in raw_row]
            n_cols = len(cells)

            # Check for region headers
            region_text = _is_region_header_row(cells)
            if region_text:
                # Determine if this is a left or right header by position
                # Left headers are in the first half, right in the second half
                mid = n_cols // 2
                left_has_text = any(c.strip() for c in cells[:mid])
                right_has_text = any(c.strip() for c in cells[mid:])
                if left_has_text and not right_has_text:
                    left_region = region_text
                elif right_has_text and not left_has_text:
                    right_region = region_text
                elif left_has_text and right_has_text:
                    # Both sides have headers — find which side has the (A) pattern
                    for i, cell in enumerate(cells):
                        if REGION_HEADER_RE.match(cell):
                            if i < mid:
                                left_region = region_text
                            else:
                                right_region = region_text
                continue

            # Skip header rows (SN, Districts, Danger Level, etc.)
            non_empty = [c.lower() for c in cells if c.strip()]
            if not non_empty:
                continue
            header_matches = sum(1 for c in non_empty if any(kw in c for kw in DISTRICT_KEYWORDS))
            if header_matches >= max(2, len(non_empty) // 2):
                continue

            # Split into left and right halves
            mid = n_cols // 2
            left_cells = cells[:mid]
            right_cells = cells[mid:]

            # Extract left entry
            left_entry = _extract_entry_from_cells(left_cells, left_region)
            if left_entry:
                rows.append(left_entry)

            # Extract right entry
            right_entry = _extract_entry_from_cells(right_cells, right_region)
            if right_entry:
                rows.append(right_entry)

    return rows


def assemble_table_rows(tables: list[list[list[str]]]) -> list[PartnerBulletinRow]:
    """Assemble PartnerBulletinRow objects from pdfplumber-extracted table cells.

    Partner bulletin tables typically have columns like:
    District | Altitude | Danger Level | Snow Condition | Likelihood

    G-04: Handles repeated headers, wrapped cells, column shifts, and multi-row records.
    """
    rows: list[PartnerBulletinRow] = []

    # Keywords that indicate a header row (not data)
    HEADER_KEYWORDS = {'district', 'area', 'region', 'altitude', 'elevation',
                        'danger', 'level', 'snow', 'condition', 'likelihood',
                        'probability', 'zone', 'sector', 'height', 'band'}

    def _is_header_row(row: list[str]) -> bool:
        """Check if a row is a header (repeated or initial) by keyword density."""
        non_empty = [str(c).strip().lower() for c in row if str(c).strip()]
        if not non_empty:
            return False
        header_matches = sum(1 for c in non_empty if any(kw in c for kw in HEADER_KEYWORDS))
        return header_matches >= max(2, len(non_empty) // 2)

    def _extract_danger_level(val: str) -> int | None:
        """Extract danger level 1-5 from a cell value.

        P1: Numeric digit is canonical. Roman numerals are unambiguous.
        Word matching uses BOTH Partner colors and EAWS names, but only when
        the full cell matches (not substring) to avoid ambiguity.
        'high' maps to EAWS level 4, NOT Partner level 3 (which is 'orange').
        """
        val = str(val).strip()
        # Direct digit (canonical)
        m = re.search(r'(\d)', val)
        if m:
            level = int(m.group(1))
            if 1 <= level <= 5:
                return level
        # Roman numeral (check longest first to avoid false matches)
        roman_map = [('iii', 3), ('ii', 2), ('iv', 4), ('v', 5), ('i', 1)]
        val_lower = val.lower().strip()
        for roman, num in roman_map:
            if val_lower == roman or val_lower.startswith(roman + ' '):
                return num
        # Word match — P1: separate Partner colors from EAWS names
        # Partner color words (canonical for Partner bulletins)
        Partner_word_map = {
            'green': 1, 'yellow': 2, 'orange': 3, 'red': 4, 'black': 5,
        }
        # EAWS name words (comparison only, but accepted for parsing robustness)
        eaws_word_map = {
            'low': 1, 'moderate': 2, 'considerable': 3, 'high': 4, 'very high': 5,
            'extreme': 5,  # EAWS 'extreme' is not standard but seen in some mappings
        }
        # Check Partner colors first (canonical for Partner bulletins)
        for word, num in Partner_word_map.items():
            if val_lower == word or val_lower.startswith(word + ' '):
                return num
        # Then check EAWS names — 'high' = 4, NOT 3
        for word, num in eaws_word_map.items():
            if val_lower == word or val_lower.startswith(word + ' '):
                return num
        return None

    for table in tables:
        if not table or len(table) < 2:
            continue

        # Identify column indices from header row
        header = [str(cell).strip().lower() for cell in table[0]] if table[0] else []
        col_map: dict[str, int] = {}
        for i, h in enumerate(header):
            if 'district' in h or 'area' in h or 'region' in h or 'zone' in h or 'sector' in h:
                col_map['district'] = i
            elif 'altitude' in h or 'elevation' in h or 'height' in h or 'band' in h:
                col_map['altitude'] = i
            elif 'danger' in h or 'level' in h:
                col_map['danger'] = i
            elif 'snow' in h or 'condition' in h:
                col_map['snow'] = i
            elif 'likelihood' in h or 'probability' in h:
                col_map['likelihood'] = i

        # If no headers detected, try positional mapping for typical Partner layout
        if not col_map:
            n_cols = len(header) if header else 0
            if n_cols >= 3:
                col_map = {'district': 0, 'altitude': 1, 'danger': 2}
            elif n_cols == 2:
                col_map = {'district': 0, 'danger': 1}
            else:
                continue

        # Parse data rows — skip repeated headers
        last_district: str | None = None
        for raw_row in table[1:]:
            if not raw_row or not any(str(c).strip() for c in raw_row):
                continue

            # G-04: Skip repeated header rows within the table
            if _is_header_row(raw_row):
                continue

            district = None
            altitude = None
            danger = None
            snow_condition = None
            likelihood = None

            if 'district' in col_map and col_map['district'] < len(raw_row):
                val = str(raw_row[col_map['district']]).strip()
                if val and val.lower() not in ('district', 'area', 'region', 'zone', 'sector', ''):
                    district = val

            if 'altitude' in col_map and col_map['altitude'] < len(raw_row):
                val = str(raw_row[col_map['altitude']]).strip()
                if val:
                    altitude = val

            if 'danger' in col_map and col_map['danger'] < len(raw_row):
                val = str(raw_row[col_map['danger']]).strip()
                danger = _extract_danger_level(val)

            if 'snow' in col_map and col_map['snow'] < len(raw_row):
                val = str(raw_row[col_map['snow']]).strip()
                if val:
                    snow_condition = val

            if 'likelihood' in col_map and col_map['likelihood'] < len(raw_row):
                val = str(raw_row[col_map['likelihood']]).strip()
                if val:
                    likelihood = val

            # G-04: Handle wrapped cells — if district is empty but we have a
            # previous district, this is a continuation row for a different
            # altitude band within the same district
            if not district and last_district and (altitude or danger):
                district = last_district

            if district:
                last_district = district

            if district or altitude or danger:
                rows.append(PartnerBulletinRow(
                    district=district,
                    altitude_band=altitude,
                    danger_level=danger,
                    danger_level_label=DANGER_LEVELS.get(danger) if danger else None,
                    Partner_color=DANGER_LEVELS.get(danger) if danger else None,
                    eaws_label=EAWS_DANGER_LEVELS.get(danger) if danger else None,
                    snow_condition=snow_condition,
                    likelihood=likelihood,
                ))

    return rows


def _bulletin_row_identity(row: PartnerBulletinRow) -> tuple[str, str | None, int | None]:
    """Return the stable identity used to detect repeated extraction rows."""
    district = row.district.strip().casefold() if row.district else ''
    altitude = row.altitude_band.strip() if row.altitude_band else None
    return district, altitude, row.danger_level


def parse_bulletin_with_provenance(
    text: str,
    bulletin_id: str,
    source_url: str | None = None,
    provenance_hash: str | None = None,
    tables: list[list[list[str]]] | None = None,
) -> ParseResult:
    """Parse bulletin text and return a ParseResult with completeness validation.

    Rejects malformed extractions where issue_date is None or no complete rows are found.
    When tables are provided from extract_tables(), they are used to supplement
    text-based row parsing for more robust extraction.
    """
    record = parse_bulletin_text(text, bulletin_id, source_url=source_url)
    if provenance_hash:
        record.metadata['provenance_hash'] = provenance_hash
    if tables:
        record.metadata['table_count'] = len(tables)
        record.metadata['table_row_count'] = sum(len(t) for t in tables)

    # P3: Use side-by-side parser as primary, then fall back to legacy table parser
    side_by_side_rows = assemble_side_by_side_rows(tables) if tables else []
    # G-04: Assemble rows from pdfplumber table cells when available
    table_rows = assemble_table_rows(tables) if tables else []

    # Merge: prefer side-by-side rows, then table rows, then text rows
    text_complete = [
        r for r in record.rows
        if r.district is not None and r.danger_level is not None
    ]
    table_complete = [
        r for r in table_rows
        if r.district is not None and r.danger_level is not None
    ]
    side_by_side_complete = [
        r for r in side_by_side_rows
        if r.district is not None and r.danger_level is not None
    ]

    if side_by_side_complete and len(side_by_side_complete) >= len(table_complete):
        # Use side-by-side rows as primary source
        # Deduplicate by (district, altitude_band) to avoid merging rows with different altitude bands
        seen_keys = {_bulletin_row_identity(r) for r in side_by_side_complete}
        extra_rows = [r for r in table_complete if _bulletin_row_identity(r) not in seen_keys]
        extra_text = [r for r in text_complete if _bulletin_row_identity(r) not in seen_keys]
        all_complete = side_by_side_complete + extra_rows + extra_text
        record.metadata['row_source'] = 'side_by_side_assembled'
    elif table_complete and len(table_complete) >= len(text_complete):
        # Use table rows as primary source, merge text-only rows as supplement
        # Deduplicate by (district, altitude_band) to avoid merging rows with different altitude bands
        seen_keys = {_bulletin_row_identity(r) for r in table_complete}
        extra_text_rows = [r for r in text_complete if _bulletin_row_identity(r) not in seen_keys]
        all_complete = table_complete + extra_text_rows
        record.metadata['row_source'] = 'table_assembled'
    else:
        all_complete = text_complete
        if table_rows or side_by_side_rows:
            record.metadata['row_source'] = 'text_with_table_supplement'
        else:
            record.metadata['row_source'] = 'text_only'

    complete_rows = all_complete

    # G2: Filter malformed rows — validate districts and danger levels
    valid_rows = []
    malformed_rows = []
    for r in complete_rows:
        if r.district and _is_valid_district(r.district):
            # Validate danger level is 1-5
            if r.danger_level is not None and 1 <= r.danger_level <= 5:
                valid_rows.append(r)
            else:
                malformed_rows.append(r)
        else:
            malformed_rows.append(r)

    if malformed_rows:
        record.metadata['malformed_row_count'] = len(malformed_rows)
        record.metadata['malformed_districts'] = [
            r.district for r in malformed_rows if r.district
        ]

    # The PDF table and text parsers can observe the same row more than once.
    # Keep one deterministic row and mark the parse blocked rather than
    # silently presenting duplicated observations as extra evidence.
    deduplicated_rows: list[PartnerBulletinRow] = []
    seen_row_keys: set[tuple[str, str | None, int | None]] = set()
    duplicate_keys: list[dict[str, Any]] = []
    for row in valid_rows:
        key = _bulletin_row_identity(row)
        if key in seen_row_keys:
            duplicate_keys.append({
                'district': row.district,
                'altitude_band': row.altitude_band,
                'danger_level': row.danger_level,
            })
            continue
        seen_row_keys.add(key)
        deduplicated_rows.append(row)

    complete_rows = deduplicated_rows
    if duplicate_keys:
        record.metadata['duplicate_row_count'] = len(duplicate_keys)
        record.metadata['duplicate_row_keys'] = duplicate_keys
    # P3: Update record.rows with the merged complete rows
    record.rows = complete_rows

    # Mark rows as provenance-backed only when hash is verified against registry
    has_provenance = source_url is not None and provenance_hash is not None
    provenance_verified = False
    if has_provenance:
        provenance_verified, verify_msg = verify_provenance_hash(bulletin_id, provenance_hash)
        record.metadata['provenance_verified'] = provenance_verified
        record.metadata['provenance_verify_msg'] = verify_msg
    for r in complete_rows:
        r.provenance_backed = provenance_verified

    # Require all complete rows to be provenance-backed
    all_provenance_backed = all(r.provenance_backed for r in complete_rows) if complete_rows else False

    is_complete = (
        record.issue_date is not None
        and len(complete_rows) > 0
        and not duplicate_keys
        and all_provenance_backed
    )

    parse_error: str | None = None
    if record.issue_date is None:
        parse_error = 'issue_date_missing'
    elif len(complete_rows) == 0:
        parse_error = 'no_complete_rows'
    elif duplicate_keys:
        parse_error = 'duplicate_rows'
    elif not all_provenance_backed:
        parse_error = 'rows_missing_provenance'

    return ParseResult(
        record=record,
        is_complete=is_complete,
        complete_row_count=len(complete_rows),
        parse_error=parse_error,
        provenance_hash=provenance_hash,
    )


def fetch_bulletin(bulletin_url: str) -> ParseResult | None:
    """Fetch and parse a Partner bulletin from a URL.

    Returns None if Partner_BULLETIN_VALIDATION_ENABLED is false or fetch fails.
    Returns ParseResult with parse_error set if the bulletin is malformed.
    """
    if not Partner_BULLETIN_VALIDATION_ENABLED:
        return None

    try:
        req = urllib.request.Request(bulletin_url, headers={'User-Agent': 'AvalancheInsightHub/1.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()
    except Exception:
        return None

    # Extract bulletin ID from URL
    bulletin_id = bulletin_url.rsplit('/', 1)[-1].replace('.pdf', '')

    # Extract text and tables from PDF using pdfplumber
    text, tables = _extract_pdf_text(content)

    # Compute provenance hash
    provenance_hash = hashlib.sha256(content).hexdigest()

    # Verify provenance hash against registry if configured
    verified, verify_msg = verify_provenance_hash(bulletin_id, provenance_hash)

    result = parse_bulletin_with_provenance(
        text, bulletin_id, source_url=bulletin_url, provenance_hash=provenance_hash,
        tables=tables,
    )
    result.record.metadata['provenance_verified'] = verified
    result.record.metadata['provenance_verify_msg'] = verify_msg
    return result


def list_recent_bulletins(
    *,
    days: int = 7,
    zones: list[str] | None = None,
) -> list[PartnerBulletinRecord]:
    """List recent Partner bulletins by scraping the bulletin index page.

    Returns empty when disabled.
    """
    if not Partner_BULLETIN_VALIDATION_ENABLED:
        return []

    try:
        req = urllib.request.Request(
            Partner_BULLETIN_BASE_URL,
            headers={'User-Agent': 'AvalancheInsightHub/1.0'},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return []

    # Find PDF links matching Partner bulletin pattern
    pdf_links = re.findall(
        r'href="([^"]*Partner_AWB_[^"]+\.pdf)"',
        html,
        re.IGNORECASE,
    )

    records: list[PartnerBulletinRecord] = []
    cutoff = date.today().toordinal() - days

    for link in pdf_links:
        url = link if link.startswith('http') else f'https://Partner.gov.in{link}'
        result = fetch_bulletin(url)
        if result is None or result.record is None:
            continue
        if not result.is_complete:
            import sys
            bulletin_id = result.record.bulletin_id if result.record else 'unknown'
            print(f'[Partner_bulletin] Skipped incomplete bulletin {bulletin_id}: {result.parse_error}', file=sys.stderr)
            continue
        record = result.record
        if record.issue_date is None or record.issue_date.toordinal() < cutoff:
            continue
        if zones and record.zone and record.zone.lower() not in {z.lower() for z in zones}:
            continue
        records.append(record)

    return records
