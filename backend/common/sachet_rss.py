"""F16: SACHET RSS Feed Ingestion — NDMA Sachet portal CAP alert parser.

The SACHET portal (https://sachet.ndma.gov.in) does not provide a standard
developer API key or public REST API endpoint for pushing alerts. Instead,
it publishes real-time disaster alerts via an open Common Alerting Protocol
(CAP) 1.2 standard XML/RSS feed.

This module provides free ingestion of geo-targeted disaster alerts from the
NDMA SACHET portal using:

  1. ``FetchAllAlertDetails`` — JSON endpoint listing all current alerts
  2. ``FetchXMLFile`` — CAP 1.2 XML endpoint for individual alert details

Usage::

    from backend.common.sachet_rss import ingest_sachet_alerts

    alerts = ingest_sachet_alerts()
    for alert in alerts[0]:
        print(alert.identifier, alert.event, alert.severity, alert.area_desc)

Cost: 100% Free — no API key required.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

SACHET_BASE_URL = os.getenv('SACHET_BASE_URL', 'https://sachet.ndma.gov.in')
SACHET_ALERT_LIST_URL = os.getenv(
    'SACHET_ALERT_LIST_URL',
    f'{SACHET_BASE_URL}/cap_public_website/FetchAllAlertDetails',
)
SACHET_CAP_XML_URL = os.getenv(
    'SACHET_CAP_XML_URL',
    f'{SACHET_BASE_URL}/cap_public_website/FetchXMLFile',
)
SACHET_RSS_ENABLED = os.getenv('SACHET_RSS_ENABLED', 'true').lower() not in {'0', 'false', 'off', 'no'}
SACHET_RSS_TIMEOUT = float(os.getenv('SACHET_RSS_TIMEOUT', '15.0'))
SACHET_RSS_MAX_ALERTS = int(os.getenv('SACHET_RSS_MAX_ALERTS', '50'))

CAP_NAMESPACE = 'urn:oasis:names:tc:emergency:cap:1.2'


@dataclass(frozen=True)
class SachetRssAlert:
    """A parsed SACHET RSS alert item."""
    identifier: str
    sender: str
    sent: str
    status: str
    msg_type: str
    scope: str
    language: str
    category: str
    event: str
    urgency: str
    severity: str
    certainty: str
    headline: str
    description: str
    instruction: str
    area_desc: str
    polygon: str | None
    effective: str | None
    onset: str | None
    expires: str | None
    web_url: str | None
    raw_xml: str | None = None
    disaster_type: str | None = None
    severity_level: str | None = None
    source_json: dict[str, Any] | None = None


@dataclass
class SachetRssConfig:
    """Configuration for SACHET RSS feed ingestion."""
    base_url: str = SACHET_BASE_URL
    alert_list_url: str = SACHET_ALERT_LIST_URL
    cap_xml_url: str = SACHET_CAP_XML_URL
    enabled: bool = SACHET_RSS_ENABLED
    timeout: float = SACHET_RSS_TIMEOUT
    max_alerts: int = SACHET_RSS_MAX_ALERTS


def _parse_cap_xml(xml_string: str) -> SachetRssAlert | None:
    """Parse a CAP 1.2 XML string into a SachetRssAlert.

    Rejects XML containing DOCTYPE/entity declarations to prevent
    entity-expansion attacks.

    Args:
        xml_string: CAP 1.2 XML string from the SACHET portal.

    Returns:
        SachetRssAlert if parsing succeeds, None otherwise.
    """
    if '<!DOCTYPE' in xml_string or '<!ENTITY' in xml_string:
        return None

    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        return None

    ns = {'cap': CAP_NAMESPACE}

    def _find_text(parent: ET.Element, tag: str) -> str:
        elem = parent.find(f'cap:{tag}', ns)
        if elem is None:
            elem = parent.find(tag)
        return (elem.text or '').strip() if elem is not None and elem.text else ''

    def _find_text_root(tag: str) -> str:
        return _find_text(root, tag)

    info = root.find('cap:info', ns)
    if info is None:
        info = root.find('info')
    if info is None:
        return None

    area = info.find('cap:area', ns)
    if area is None:
        area = info.find('area')

    polygon = None
    if area is not None:
        poly_elem = area.find('cap:polygon', ns)
        if poly_elem is None:
            poly_elem = area.find('polygon')
        if poly_elem is not None and poly_elem.text:
            polygon = poly_elem.text.strip()

    return SachetRssAlert(
        identifier=_find_text_root('identifier'),
        sender=_find_text_root('sender'),
        sent=_find_text_root('sent'),
        status=_find_text_root('status'),
        msg_type=_find_text_root('msgType'),
        scope=_find_text_root('scope'),
        language=_find_text(info, 'language'),
        category=_find_text(info, 'category'),
        event=_find_text(info, 'event'),
        urgency=_find_text(info, 'urgency'),
        severity=_find_text(info, 'severity'),
        certainty=_find_text(info, 'certainty'),
        headline=_find_text(info, 'headline'),
        description=_find_text(info, 'description'),
        instruction=_find_text(info, 'instruction'),
        area_desc=_find_text(area, 'areaDesc') if area is not None else '',
        polygon=polygon,
        effective=_find_text(info, 'effective') or None,
        onset=_find_text(info, 'onset') or None,
        expires=_find_text(info, 'expires') or None,
        web_url=_find_text(info, 'web') or None,
        raw_xml=xml_string,
    )


def fetch_alert_list(config: SachetRssConfig | None = None) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch the list of current alerts from the SACHET portal.

    Calls the ``FetchAllAlertDetails`` JSON endpoint which returns a list
    of active disaster alerts with metadata (no API key required).

    Args:
        config: RSS configuration (uses default if None).

    Returns:
        Tuple of (list of alert metadata dictionaries, error message or None).
    """
    cfg = config or SachetRssConfig()
    if not cfg.enabled:
        return [], 'rss_disabled'

    try:
        import requests as _requests
        resp = _requests.get(cfg.alert_list_url, timeout=cfg.timeout)
        if resp.status_code != 200:
            return [], f'http_{resp.status_code}'
        try:
            data = resp.json()
        except ValueError:
            return [], 'invalid_json_format'
        if isinstance(data, list):
            return data[:cfg.max_alerts], None
        return [], 'invalid_json_format'
    except Exception as exc:
        return [], f'request_failed: {exc}'


def fetch_cap_xml(identifier: str, config: SachetRssConfig | None = None) -> str | None:
    """Fetch the full CAP 1.2 XML for a specific alert identifier.

    Calls the ``FetchXMLFile`` endpoint which returns the raw CAP 1.2 XML.

    Args:
        identifier: Alert identifier from the alert list.
        config: RSS configuration (uses default if None).

    Returns:
        CAP 1.2 XML string, or None if fetch fails.
    """
    cfg = config or SachetRssConfig()
    if not cfg.enabled:
        return None

    try:
        import requests as _requests
        resp = _requests.get(
            cfg.cap_xml_url,
            params={'identifier': identifier},
            timeout=cfg.timeout,
        )
        if resp.status_code != 200:
            return None
        return resp.text
    except Exception:
        return None


def ingest_sachet_alerts(
    config: SachetRssConfig | None = None,
    *,
    fetch_cap_xml_detail: bool = True,
) -> tuple[list[SachetRssAlert], str | None]:
    """Ingest current disaster alerts from the NDMA SACHET RSS feed.

    This is the main entry point for SACHET RSS feed ingestion. It:
    1. Fetches the alert list from ``FetchAllAlertDetails``
    2. Optionally fetches full CAP 1.2 XML for each alert
    3. Parses and returns structured alert objects

    No API key required — uses the free public RSS/CAP feed.

    Args:
        config: RSS configuration (uses default if None).
        fetch_cap_xml_detail: If True, fetch full CAP XML for each alert.
            If False, only uses metadata from the JSON list endpoint.

    Returns:
        Tuple of (list of SachetRssAlert objects, error message or None).
    """
    cfg = config or SachetRssConfig()
    if not cfg.enabled:
        return [], 'rss_disabled'

    raw_alerts, fetch_err = fetch_alert_list(cfg)
    if fetch_err is not None:
        return [], fetch_err
    if not raw_alerts:
        return [], None

    alerts: list[SachetRssAlert] = []

    for raw in raw_alerts:
        identifier = str(raw.get('identifier', ''))
        if not identifier:
            continue

        if fetch_cap_xml_detail:
            cap_xml = fetch_cap_xml(identifier, cfg)
            if cap_xml:
                parsed = _parse_cap_xml(cap_xml)
                if parsed:
                    alerts.append(parsed)
                    continue

        alerts.append(_alert_from_json(raw, identifier))

    return alerts, None


def _alert_from_json(raw: dict[str, Any], identifier: str) -> SachetRssAlert:
    """Build a SachetRssAlert from the JSON list endpoint metadata."""
    return SachetRssAlert(
        identifier=identifier,
        sender=raw.get('sender', 'NDMA-SACHET'),
        sent=raw.get('effective_start_time', ''),
        status='Actual',
        msg_type='Alert',
        scope='Public',
        language=raw.get('actual_lang', 'en'),
        category='Met',
        event=raw.get('disaster_type', 'Unknown'),
        urgency=raw.get('urgency', 'Unknown'),
        severity=raw.get('severity', 'Unknown'),
        certainty=raw.get('severity_level', 'Possible'),
        headline=raw.get('warning_message', ''),
        description=raw.get('warning_message', ''),
        instruction='',
        area_desc=raw.get('area_description', ''),
        polygon=None,
        effective=raw.get('effective_start_time'),
        onset=None,
        expires=raw.get('effective_end_time'),
        web_url=None,
        raw_xml=None,
        disaster_type=raw.get('disaster_type'),
        severity_level=raw.get('severity_level'),
        source_json=raw,
    )


def filter_alerts_by_bbox(
    alerts: list[SachetRssAlert],
    bbox: list[float],
) -> list[SachetRssAlert]:
    """Filter alerts by geographic bounding box.

    Checks if the alert's polygon intersects the given bbox.
    Alerts without polygon data are included (fail-open for safety).

    Args:
        alerts: List of alerts to filter.
        bbox: [west, south, east, north] bounding box.

    Returns:
        Filtered list of alerts that intersect or are within the bbox.
    """
    if not bbox or len(bbox) != 4:
        return alerts

    west, south, east, north = bbox
    filtered: list[SachetRssAlert] = []

    for alert in alerts:
        if not alert.polygon:
            filtered.append(alert)
            continue

        coords = alert.polygon.split()
        for coord in coords:
            parts = coord.strip().split(',')
            if len(parts) != 2:
                continue
            try:
                lat = float(parts[0])
                lon = float(parts[1])
            except ValueError:
                continue

            if south <= lat <= north and west <= lon <= east:
                filtered.append(alert)
                break

    return filtered


def filter_alerts_by_disaster_type(
    alerts: list[SachetRssAlert],
    disaster_types: list[str],
) -> list[SachetRssAlert]:
    """Filter alerts by disaster type (case-insensitive substring match).

    Args:
        alerts: List of alerts to filter.
        disaster_types: List of disaster type keywords (e.g. ['avalanche', 'snow']).

    Returns:
        Filtered list of alerts matching any of the disaster types.
    """
    if not disaster_types:
        return alerts

    keywords = [dt.lower() for dt in disaster_types]
    return [
        alert for alert in alerts
        if any(kw in (alert.event or '').lower() or kw in (alert.disaster_type or '').lower()
               for kw in keywords)
    ]


def get_sachet_alert_summary(
    alerts: list[SachetRssAlert],
    *,
    fetch_error: str | None = None,
    config: SachetRssConfig | None = None,
) -> dict[str, Any]:
    """Build a summary metadata dict for ingestion results.

    Args:
        alerts: List of ingested alerts.
        fetch_error: Error message if the feed fetch failed, None if successful.
        config: RSS configuration used for ingestion (uses default if None).

    Returns:
        Summary dictionary with counts, timestamps, and severity breakdown.
    """
    cfg = config or SachetRssConfig()
    severity_counts: dict[str, int] = {}
    for alert in alerts:
        sev = alert.severity or 'Unknown'
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        'enabled': cfg.enabled,
        'ingested': fetch_error is None,
        'alert_count': len(alerts),
        'severity_breakdown': severity_counts,
        'latest_sent': max((a.sent for a in alerts if a.sent), default=''),
        'source': 'sachet_rss_feed',
        'feed_url': cfg.alert_list_url,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'error': fetch_error,
    }
