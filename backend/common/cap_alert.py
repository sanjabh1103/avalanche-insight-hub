"""WMO CAP 1.2 XML alert scaffold for avalanche forecast products.

Generates OASIS Common Alerting Protocol (CAP) 1.2 XML from forecast
artifacts. This is a scaffold — it produces valid XML structure but
does not submit to any national emergency pathway. Validation against
the CAP 1.2 XSD should be done before production use.

Reference: https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2.html
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

CAP_NAMESPACE = 'urn:oasis:names:tc:emergency:cap:1.2'
CAP_VERSION = '1.2'

EAWS_DANGER_TO_CAP_SEVERITY = {
    1: 'Minor',
    2: 'Minor',
    3: 'Moderate',
    4: 'Severe',
    5: 'Extreme',
}

EAWS_DANGER_TO_CAP_CERTAINTY = {
    1: 'Possible',
    2: 'Possible',
    3: 'Likely',
    4: 'Likely',
    5: 'Observed',
}


def generate_cap_alert(
    *,
    identifier: str,
    sender: str,
    sent: datetime | None = None,
    status: str = 'Actual',
    message_type: str = 'Alert',
    scope: str = 'Public',
    region_name: str,
    region_key: str,
    bbox: list[float],
    forecast_date: str,
    horizon_hours: int,
    max_danger_level: int,
    headline: str,
    description: str,
    instruction: str | None = None,
    web_url: str | None = None,
    effective: datetime | None = None,
    expires: datetime | None = None,
) -> str:
    """Generate a CAP 1.2 XML alert string from forecast parameters.

    Args:
        identifier: Unique alert identifier (e.g., forecast_run_id).
        sender: Sender identifier (e.g., 'avalanche-insight-hub@system').
        sent: Issue timestamp (defaults to now UTC).
        status: CAP status (Actual, Exercise, System, Test, Draft).
        message_type: CAP message type (Alert, Update, Cancel, Ack, Error).
        scope: CAP scope (Public, Restricted, Private).
        region_name: Human-readable region name.
        region_key: Machine region key.
        bbox: [west, south, east, north] bounding box.
        forecast_date: ISO date string for the forecast.
        horizon_hours: Forecast horizon in hours.
        max_danger_level: EAWS danger level 1-5.
        headline: Short headline for the alert.
        description: Detailed description of the avalanche risk.
        instruction: Recommended actions (optional).
        web_url: URL to the full forecast workspace (optional).
        effective: Effective time (defaults to sent).
        expires: Expiry time (defaults to sent + horizon_hours).

    Returns:
        CAP 1.2 XML string.
    """
    sent = sent or datetime.now(timezone.utc)
    effective = effective or sent
    expires = expires or sent.replace() if False else sent

    from datetime import timedelta
    expires = expires or (sent + timedelta(hours=horizon_hours))

    severity = EAWS_DANGER_TO_CAP_SEVERITY.get(max_danger_level, 'Moderate')
    certainty = EAWS_DANGER_TO_CAP_CERTAINTY.get(max_danger_level, 'Possible')

    area_desc = f'{region_name} ({region_key}) — bbox: {bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}'

    info = ET.Element('info', xmlns=CAP_NAMESPACE)
    ET.SubElement(info, 'language').text = 'en-US'
    ET.SubElement(info, 'category').text = 'Met'
    ET.SubElement(info, 'event').text = 'Avalanche Warning'
    ET.SubElement(info, 'urgency').text = 'Expected'
    ET.SubElement(info, 'severity').text = severity
    ET.SubElement(info, 'certainty').text = certainty
    ET.SubElement(info, 'effective').text = effective.isoformat()
    ET.SubElement(info, 'expires').text = expires.isoformat()
    ET.SubElement(info, 'senderName').text = 'Avalanche Insight Hub'
    ET.SubElement(info, 'headline').text = headline
    ET.SubElement(info, 'description').text = description
    if instruction:
        ET.SubElement(info, 'instruction').text = instruction
    ET.SubElement(info, 'web').text = web_url or ''
    ET.SubElement(info, 'parameter', name='forecastDate').text = forecast_date
    ET.SubElement(info, 'parameter', name='horizonHours').text = str(horizon_hours)
    ET.SubElement(info, 'parameter', name='eawsDangerLevel').text = str(max_danger_level)
    ET.SubElement(info, 'parameter', name='regionKey').text = region_key

    area = ET.SubElement(info, 'area')
    ET.SubElement(area, 'areaDesc').text = area_desc
    polygon = f'{bbox[1]},{bbox[0]} {bbox[1]},{bbox[2]} {bbox[3]},{bbox[2]} {bbox[3]},{bbox[0]} {bbox[1]},{bbox[0]}'
    ET.SubElement(area, 'polygon').text = polygon

    alert = ET.Element('alert', xmlns=CAP_NAMESPACE)
    ET.SubElement(alert, 'identifier').text = identifier
    ET.SubElement(alert, 'sender').text = sender
    ET.SubElement(alert, 'sent').text = sent.isoformat()
    ET.SubElement(alert, 'status').text = status
    ET.SubElement(alert, 'msgType').text = message_type
    ET.SubElement(alert, 'scope').text = scope
    alert.append(info)

    ET.indent(alert, space='  ')
    return ET.tostring(alert, encoding='unicode', xml_declaration=True)


def generate_cap_from_forecast_run(
    forecast_run: dict[str, Any],
    *,
    sender: str = 'avalanche-insight-hub@system',
    web_url: str | None = None,
) -> str:
    """Generate CAP XML from a forecast run dictionary.

    Args:
        forecast_run: Dictionary with keys matching forecast_runs table columns.
        sender: CAP sender identifier.
        web_url: URL to the public forecast workspace.

    Returns:
        CAP 1.2 XML string.
    """
    model_metadata = forecast_run.get('model_metadata') or {}
    weather_summary = forecast_run.get('weather_summary') or {}
    bulletins = forecast_run.get('forecast_bulletins') or {}

    max_danger = 1
    for bulletin in bulletins.values() if isinstance(bulletins, dict) else []:
        if isinstance(bulletin, dict):
            level = bulletin.get('danger_level') or bulletin.get('maxDangerLevel')
            if isinstance(level, (int, float)) and level > max_danger:
                max_danger = int(level)

    region_name = forecast_run.get('region_name') or forecast_run.get('region_key', 'unknown')
    region_key = forecast_run.get('region_key', 'unknown')
    bbox = forecast_run.get('bbox', [0, 0, 0, 0])
    forecast_date = str(forecast_run.get('forecast_date', ''))
    horizon_hours = int(forecast_run.get('horizon_hours', 72))

    headline = f'Avalanche Warning — {region_name} — EAWS Level {max_danger}'
    description = (
        f'Batch-first avalanche forecast for {region_name} ({region_key}). '
        f'Forecast date: {forecast_date}. Horizon: {horizon_hours}h. '
        f'Maximum EAWS danger level: {max_danger}. '
        f'Model: {model_metadata.get("model_version", "unknown")}. '
        f'This is a decision-support tool, not an official warning.'
    )
    instruction = (
        'Consult local avalanche bulletins for official warnings. '
        'This forecast is generated by a batch-first ML pipeline and '
        'should be used as supplementary decision support only.'
    )

    return generate_cap_alert(
        identifier=str(forecast_run.get('id', 'unknown')),
        sender=sender,
        region_name=region_name,
        region_key=region_key,
        bbox=bbox,
        forecast_date=forecast_date,
        horizon_hours=horizon_hours,
        max_danger_level=max_danger,
        headline=headline,
        description=description,
        instruction=instruction,
        web_url=web_url,
    )
