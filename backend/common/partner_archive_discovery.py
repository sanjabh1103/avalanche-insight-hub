"""Partner/Partner public archive discovery module.

Discovers and classifies every row in the public Partner Avalanche Warning
Bulletin archive at:
  https://Partner.gov.in/Partner/en/documents/avalanche-warning-bulletin-archive

The archive uses Drupal pagination with ?page=N (0-indexed).

P2 exit gate: Archive accounting satisfies listed = candidate + excluded + malformed;
no "254 bulletins" claim remains. Every row is classified.

This module is credential-free and reads publicly available archive pages.
It does NOT fetch PDFs — it only discovers and classifies archive entries.
Use Partner_bulletin_adapter.fetch_bulletin() to fetch individual PDFs.

Env flags:
  Partner_ARCHIVE_DISCOVERY_ENABLED — master switch (default: false)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import tempfile
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

Partner_ARCHIVE_DISCOVERY_ENABLED = os.getenv(
    'Partner_ARCHIVE_DISCOVERY_ENABLED', 'false'
).lower() not in {'0', 'false', 'off', 'no'}

Partner_ARCHIVE_BASE_URL = 'https://Partner.gov.in/Partner/en/documents/avalanche-warning-bulletin-archive'

# Entry kinds
KIND_BULLETIN = 'bulletin'
KIND_CLOSING_LETTER = 'closing_letter'
KIND_BLANK = 'blank'
KIND_MALFORMED_DATE = 'malformed_date'
KIND_INVALID_DOCUMENT = 'invalid_document'
KIND_NONSTANDARD_FILENAME = 'nonstandard_filename'
KIND_PAGE_NOT_FOUND = 'page_not_found'

# Discovery statuses
STATUS_DISCOVERED = 'discovered'
STATUS_EXCLUDED = 'excluded'
STATUS_MALFORMED = 'malformed'
STATUS_FAILED = 'failed'

# Discovery lifecycle states. A page inventory is not complete merely because
# the parser returned entries; the fetch route and stop reason are part of the
# evidence contract.
DISCOVERY_NOT_RUN = 'not_run'
DISCOVERY_DISABLED = 'disabled'
DISCOVERY_COMPLETE = 'complete'
DISCOVERY_INCOMPLETE = 'incomplete'

# Standard Partner AWB filename pattern
Partner_AWB_FILENAME_RE = re.compile(
    r'Partner_AWB_(\d{1,2})-([A-Za-z]{3})-(\d{4})\.pdf',
    re.IGNORECASE,
)

# Closing letter patterns
CLOSING_LETTER_RE = re.compile(
    r'closing|operational.*forecasting.*services|end.*of.*season',
    re.IGNORECASE,
)

# Date patterns in archive table
DATE_DMY_RE = re.compile(r'(\d{1,2})-(\d{1,2})-(\d{4})')
DATE_YMD_RE = re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})')


@dataclass(frozen=True)
class PartnerArchiveEntryV1:
    """A single classified entry from the Partner archive.

    P2 contract: archive serial, title, posted date, source URL,
    entry kind, and discovery status.
    """

    serial: int  # S.No from the archive table
    title: str  # Title from the archive table
    posted_date: str | None  # Date string as posted (raw, not parsed)
    source_url: str | None  # PDF link URL
    entry_kind: str  # One of KIND_* constants
    discovery_status: str  # One of STATUS_* constants
    page_number: int  # Archive page where this entry was found
    file_size: str | None = None  # Type/Size column content
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    notes: str | None = None  # Additional classification notes

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_bulletin(self) -> bool:
        return self.entry_kind == KIND_BULLETIN

    @property
    def is_excluded(self) -> bool:
        return self.discovery_status == STATUS_EXCLUDED

    @property
    def is_malformed(self) -> bool:
        return self.discovery_status == STATUS_MALFORMED


def parse_archive_date(date_str: str) -> date | None:
    """Parse a date string from the archive table.

    Handles DD-MM-YYYY and YYYY-MM-DD formats.
    Returns None for malformed dates (e.g., '20-03-0026').
    """
    if not date_str:
        return None
    date_str = date_str.strip()

    # Try DD-MM-YYYY
    m = DATE_DMY_RE.match(date_str)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        # Reject malformed years (e.g., 0026 instead of 2026)
        if y < 2000:
            return None
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    # Try YYYY-MM-DD
    m = DATE_YMD_RE.match(date_str)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    return None


def classify_entry(
    serial: int,
    title: str,
    date_str: str,
    url: str | None,
    file_size: str | None,
    page_number: int,
) -> PartnerArchiveEntryV1:
    """Classify a single archive row into an entry kind.

    Classification rules (checked in order):
    1. blank: No title and no URL
    2. closing_letter: Title matches closing/season-end pattern
    3. malformed_date: Date doesn't parse to a valid date
    4. page_not_found: URL or title indicates a page-not-found error
    5. nonstandard_filename: URL is a PDF but doesn't match Partner_AWB pattern
    6. invalid_document: URL is not a PDF
    7. bulletin: Standard Partner AWB PDF with valid filename
    """
    title = title.strip() if title else ''
    date_str = date_str.strip() if date_str else ''
    url = url.strip() if url else ''
    file_size = file_size.strip() if file_size else ''

    # 1. Blank entry
    if not title and not url:
        return PartnerArchiveEntryV1(
            serial=serial, title='', posted_date=date_str, source_url=None,
            entry_kind=KIND_BLANK, discovery_status=STATUS_EXCLUDED,
            page_number=page_number, file_size=file_size,
            notes='No title and no URL',
        )

    # 2. Closing letter
    if CLOSING_LETTER_RE.search(title):
        return PartnerArchiveEntryV1(
            serial=serial, title=title, posted_date=date_str, source_url=url or None,
            entry_kind=KIND_CLOSING_LETTER, discovery_status=STATUS_EXCLUDED,
            page_number=page_number, file_size=file_size,
            notes='Closing/season-end letter, not a bulletin',
        )

    # 3. Malformed date
    parsed_date = parse_archive_date(date_str)
    if date_str and parsed_date is None:
        return PartnerArchiveEntryV1(
            serial=serial, title=title, posted_date=date_str, source_url=url or None,
            entry_kind=KIND_MALFORMED_DATE, discovery_status=STATUS_MALFORMED,
            page_number=page_number, file_size=file_size,
            notes=f'Date does not parse: {date_str}',
        )

    # 4. Page not found
    if 'page not found' in title.lower() or 'not found' in title.lower():
        return PartnerArchiveEntryV1(
            serial=serial, title=title, posted_date=date_str, source_url=url or None,
            entry_kind=KIND_PAGE_NOT_FOUND, discovery_status=STATUS_EXCLUDED,
            page_number=page_number, file_size=file_size,
            notes='Page-not-found document',
        )

    # 5-7. URL-based classification
    if not url:
        # Has title but no URL — could be a header or formatting artifact
        return PartnerArchiveEntryV1(
            serial=serial, title=title, posted_date=date_str, source_url=None,
            entry_kind=KIND_INVALID_DOCUMENT, discovery_status=STATUS_EXCLUDED,
            page_number=page_number, file_size=file_size,
            notes='No URL associated with entry',
        )

    # Check if URL is a PDF
    if not url.lower().endswith('.pdf'):
        return PartnerArchiveEntryV1(
            serial=serial, title=title, posted_date=date_str, source_url=url,
            entry_kind=KIND_INVALID_DOCUMENT, discovery_status=STATUS_EXCLUDED,
            page_number=page_number, file_size=file_size,
            notes='URL is not a PDF',
        )

    # Check filename pattern
    filename = url.rsplit('/', 1)[-1] if '/' in url else url
    if not Partner_AWB_FILENAME_RE.match(filename):
        return PartnerArchiveEntryV1(
            serial=serial, title=title, posted_date=date_str, source_url=url,
            entry_kind=KIND_NONSTANDARD_FILENAME, discovery_status=STATUS_EXCLUDED,
            page_number=page_number, file_size=file_size,
            notes=f'Non-standard filename: {filename}',
        )

    # Standard bulletin
    return PartnerArchiveEntryV1(
        serial=serial, title=title, posted_date=date_str, source_url=url,
        entry_kind=KIND_BULLETIN, discovery_status=STATUS_DISCOVERED,
        page_number=page_number, file_size=file_size,
        notes=None,
    )


def _fetch_archive_page(page_num: int, timeout: int = 15, max_retries: int = 3) -> tuple[str | None, str | None, str | None]:
    """Fetch a single archive page and return (HTML content, SHA-256 hash, error reason).

    G3: Returns page hash for source snapshot verification.
    Returns (None, None, error_reason) on network error.
    P3: Retries with exponential backoff (1s, 2s before the final attempt
    when max_retries=3) for transient failures.
    """
    import time
    url = f'{Partner_ARCHIVE_BASE_URL}?page={page_num}'
    last_error: str | None = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'AvalancheInsightHub/1.0'})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                content = resp.read().decode('utf-8', errors='ignore')
                page_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
                return content, page_hash, None
        except Exception as exc:
            last_error = str(exc)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 1s, 2s before the final attempt
    return None, None, f'{last_error} (after {max_retries} retries)'


def parse_archive_page_html(html: str, page_num: int) -> list[PartnerArchiveEntryV1]:
    """Parse a single archive page's HTML and return classified entries.

    The Partner archive uses a Drupal table with columns:
    S.No | Title | Date | Type/Size | Link to Content
    """
    entries: list[PartnerArchiveEntryV1] = []

    # Find all table rows with PDF links or content
    # Pattern: rows like "1 | Title | DD-MM-YYYY | size | View"
    # The HTML has links like href="/Partner/sites/default/files/avalanche_warning_bulletin/..."

    # Extract rows from the table — look for serial numbers and associated data
    # The Drupal table has a specific structure we need to parse

    # Find all PDF links and their context
    pdf_link_pattern = re.compile(
        r'href="([^"]*avalanche_warning_bulletin[^"]*\.pdf)"',
        re.IGNORECASE,
    )

    # Find all table rows — Drupal renders as <tr> with <td> cells
    # But the exact structure varies. We'll use a robust approach:
    # 1. Find all links in the page
    # 2. Find all date-like strings
    # 3. Find all serial numbers

    # Extract all links with their surrounding text
    link_blocks = re.findall(
        r'<td[^>]*>.*?</td>',
        html,
        re.DOTALL | re.IGNORECASE,
    )

    # Alternative: parse the table rows directly
    row_pattern = re.compile(
        r'<tr[^>]*>(.*?)</tr>',
        re.DOTALL | re.IGNORECASE,
    )
    rows = row_pattern.findall(html)

    for row_html in rows:
        # Skip header rows
        if '<th' in row_html.lower():
            continue

        # Extract cells
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.DOTALL | re.IGNORECASE)
        if len(cells) < 3:
            continue

        # Clean HTML from cells
        def clean_html(s: str) -> str:
            s = re.sub(r'<[^>]+>', ' ', s)
            s = re.sub(r'\s+', ' ', s)
            return s.strip()

        # Try to extract serial, title, date, size, URL
        serial_str = clean_html(cells[0])
        try:
            serial = int(serial_str)
        except ValueError:
            continue  # Not a data row

        # Find the link URL in the row
        url_match = pdf_link_pattern.search(row_html)
        url = url_match.group(1) if url_match else None
        if url and not url.startswith('http'):
            url = f'https://Partner.gov.in{url}'

        # Title is usually in the cell with the link or the second cell
        title = clean_html(cells[1]) if len(cells) > 1 else ''

        # Date is usually in the third cell
        date_str = clean_html(cells[2]) if len(cells) > 2 else ''

        # File size is usually in the fourth cell
        file_size = clean_html(cells[3]) if len(cells) > 3 else None

        entry = classify_entry(
            serial=serial,
            title=title,
            date_str=date_str,
            url=url,
            file_size=file_size,
            page_number=page_num,
        )
        entries.append(entry)

    return entries


def discover_archive(
    *,
    max_pages: int = 30,
    timeout: int = 15,
    start_page: int = 0,
) -> list[PartnerArchiveEntryV1]:
    """Discover all entries in the Partner archive by paginating through pages.

    Stops when:
    - A page returns no entries (end of archive)
    - max_pages is reached
    - Network error on consecutive pages

    P2 exit gate: listed = candidate + excluded + malformed
    """
    global _last_page_hashes, _last_fetch_failures, _last_discovery_state
    if not Partner_ARCHIVE_DISCOVERY_ENABLED:
        with _state_lock:
            _last_page_hashes = {}
            _last_fetch_failures = []
            _last_discovery_state = {
                'status': DISCOVERY_DISABLED,
                'stop_reason': 'disabled',
                'start_page': start_page,
                'max_pages': max_pages,
                'pages_attempted': 0,
                'pages_fetched': 0,
                'entry_fingerprint': _fingerprint_entries([]),
            }
        return []

    all_entries: list[PartnerArchiveEntryV1] = []
    consecutive_errors = 0
    # G3: Track page hashes and fetch failures
    page_hashes: dict[int, str] = {}
    fetch_failures: list[dict[str, Any]] = []
    pages_attempted = 0
    pages_fetched = 0
    stop_reason = 'max_pages_reached'

    for page_num in range(start_page, start_page + max_pages):
        pages_attempted += 1
        html, page_hash, error_reason = _fetch_archive_page(page_num, timeout=timeout)
        if html is None:
            consecutive_errors += 1
            # G3: Record fetch failure
            fetch_failures.append({
                'page_num': page_num,
                'error': error_reason or 'unknown',
                'timestamp': datetime.now(timezone.utc).isoformat(),
            })
            if consecutive_errors >= 3:
                stop_reason = 'consecutive_errors'
                break
            continue

        consecutive_errors = 0
        pages_fetched += 1
        # G3: Record page hash
        if page_hash:
            page_hashes[page_num] = page_hash

        page_entries = parse_archive_page_html(html, page_num)
        if not page_entries:
            # Empty page — end of archive
            stop_reason = 'empty_page'
            break

        all_entries.extend(page_entries)

    status = (
        DISCOVERY_COMPLETE
        if stop_reason == 'empty_page' and not fetch_failures
        else DISCOVERY_INCOMPLETE
    )
    # G3: Store page hashes, failures, and stop metadata atomically for the
    # manifest. The entry fingerprint prevents stale state from another run
    # being attached to a manually supplied entry list.
    with _state_lock:
        _last_page_hashes = page_hashes
        _last_fetch_failures = fetch_failures
        _last_discovery_state = {
            'status': status,
            'stop_reason': stop_reason,
            'start_page': start_page,
            'max_pages': max_pages,
            'pages_attempted': pages_attempted,
            'pages_fetched': pages_fetched,
            'entry_fingerprint': _fingerprint_entries(all_entries),
        }

    return all_entries


# G3: Module-level state for page hashes and fetch failures
# P5: Lock for thread-safe access to module-level globals
_state_lock = threading.Lock()
_last_page_hashes: dict[int, str] = {}
_last_fetch_failures: list[dict[str, Any]] = []
_last_discovery_state: dict[str, Any] = {
    'status': DISCOVERY_NOT_RUN,
    'stop_reason': 'not_run',
    'start_page': None,
    'max_pages': None,
    'pages_attempted': 0,
    'pages_fetched': 0,
    'entry_fingerprint': None,
}


def _fingerprint_entries(entries: list[PartnerArchiveEntryV1]) -> str:
    payload = [entry.to_dict() for entry in entries]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    ).hexdigest()


def build_archive_manifest(entries: list[PartnerArchiveEntryV1]) -> dict[str, Any]:
    """Build a summary manifest from discovered archive entries.

    P2 exit gate: Archive accounting satisfies listed = candidate + excluded + malformed.
    """
    bulletins = [e for e in entries if e.entry_kind == KIND_BULLETIN]
    excluded = [e for e in entries if e.discovery_status == STATUS_EXCLUDED]
    malformed = [e for e in entries if e.discovery_status == STATUS_MALFORMED]
    discovered = [e for e in entries if e.discovery_status == STATUS_DISCOVERED]

    # Count by kind
    kind_counts: dict[str, int] = {}
    for e in entries:
        kind_counts[e.entry_kind] = kind_counts.get(e.entry_kind, 0) + 1

    current_fingerprint = _fingerprint_entries(entries)
    with _state_lock:
        state = dict(_last_discovery_state)
        page_hashes = dict(_last_page_hashes)
        fetch_failures = list(_last_fetch_failures)
    if state.get('entry_fingerprint') != current_fingerprint:
        state = {
            'status': DISCOVERY_NOT_RUN,
            'stop_reason': 'entry_list_not_from_discovery_run',
            'start_page': None,
            'max_pages': None,
            'pages_attempted': 0,
            'pages_fetched': 0,
        }
        page_hashes = {}
        fetch_failures = []

    return {
        'schema_version': 'Partner_archive_discovery_v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'total_listed': len(entries),
        'total_candidate': len(discovered),
        'total_excluded': len(excluded),
        'total_malformed': len(malformed),
        'accounting_check': len(entries) == len(discovered) + len(excluded) + len(malformed),
        'discovery_status': state['status'],
        'discovery_complete': state['status'] == DISCOVERY_COMPLETE,
        'stop_reason': state['stop_reason'],
        'start_page': state.get('start_page'),
        'max_pages': state.get('max_pages'),
        'pages_attempted': state.get('pages_attempted', 0),
        'pages_fetched': state.get('pages_fetched', 0),
        # G3: Page hashes for source snapshot verification
        'page_hashes': page_hashes,
        'page_hash_count': len(page_hashes),
        # G3: Fetch failure records
        'fetch_failures': fetch_failures,
        'fetch_failure_count': len(fetch_failures),
        'kind_counts': kind_counts,
        'bulletin_count': len(bulletins),
        'bulletin_serials': [e.serial for e in bulletins],
        'entries': [e.to_dict() for e in entries],
    }


def save_archive_manifest(manifest: dict[str, Any], path: Path) -> None:
    """Atomically save a self-hashed archive manifest to a JSON file."""
    if not isinstance(manifest, dict):
        raise ValueError('archive manifest must be a JSON object')
    payload = dict(manifest)
    payload['manifest_hash_scope'] = 'canonical_json.manifest_sha256_null'
    payload['manifest_sha256'] = None
    hash_bytes = (
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + '\n'
    ).encode('utf-8')
    payload['manifest_sha256'] = hashlib.sha256(hash_bytes).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp', delete=False) as handle:
        temporary_path = Path(handle.name)
        handle.write(encoded)
    os.replace(temporary_path, path)


def load_archive_manifest(path: Path) -> dict[str, Any] | None:
    """Load a previously saved archive manifest for resumption fail-closed."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'archive manifest load failed: {exc}') from exc
    if not isinstance(payload, dict):
        raise ValueError('archive manifest must be a JSON object')
    expected = payload.get('manifest_sha256')
    if expected is not None:
        if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
            raise ValueError('archive manifest hash is missing or invalid')
        normalized = dict(payload)
        normalized['manifest_sha256'] = None
        actual = hashlib.sha256(
            (json.dumps(normalized, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
        ).hexdigest()
        if actual != expected:
            raise ValueError(f'archive manifest hash mismatch: {path}')
    return payload
