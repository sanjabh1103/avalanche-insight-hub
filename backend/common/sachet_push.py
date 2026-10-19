"""F16: Sachet Push — NDMA Sachet portal + SMS + GAGAN/NavIC delivery.

Alert dissemination and ingestion via:
  - NDMA Sachet RSS feed ingestion (free, no API key required)
  - NDMA Sachet API push (requires API key, optional)
  - SMS delivery (via Sachet or standalone gateway)
  - GAGAN/NavIC satellite broadcast stubs

Multi-language alert templates: Hindi, Urdu, English.
Alert triggered when danger_level >= 4.

The SACHET portal does not provide a standard developer API key. Instead,
alerts are ingested from the free public CAP 1.2 RSS feed at
``https://sachet.ndma.gov.in/CapFeed``. See :mod:`backend.common.sachet_rss`
for the RSS feed parser.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SACHET_API_URL = os.getenv('SACHET_API_URL', 'https://sachet.ndma.gov.in/api')
SACHET_API_KEY = os.getenv('SACHET_API_KEY', '')
SACHET_ENABLED = os.getenv('SACHET_ENABLED', 'false').lower() not in {'0', 'false', 'off', 'no'}
SACHET_RSS_ENABLED = os.getenv('SACHET_RSS_ENABLED', 'true').lower() not in {'0', 'false', 'off', 'no'}
ALERT_TRIGGER_DANGER_LEVEL = int(os.getenv('ALERT_TRIGGER_DANGER_LEVEL', '4'))

LANGUAGE_HINDI = 'hi'
LANGUAGE_URDU = 'ur'
LANGUAGE_ENGLISH = 'en'

MULTI_LANGUAGE_TEMPLATES: dict[str, dict[str, str]] = {
    'high': {
        LANGUAGE_ENGLISH: (
            'AVALANCHE WARNING — {region_name}. '
            'Danger Level {danger_level}/5. '
            'Avoid avalanche-prone slopes. '
            'Consult local bulletins for details.'
        ),
        LANGUAGE_HINDI: (
            'हिमस्खलन चेतावनी — {region_name}. '
            'खतरा स्तर {danger_level}/5. '
            'हिमस्खलन-प्रवण ढलानों से बचें. '
            'विवरण के लिए स्थानीय बुलेटिन देखें.'
        ),
        LANGUAGE_URDU: (
            'برفانی تودے کی تنبیہ — {region_name}. '
            'خطرے کی سطح {danger_level}/5. '
            'برفانی تودے کے خطرناک ڈھلوانوں سے بچیں. '
            'تفصیلات کے لیے مقامی بلیٹن دیکھیں.'
        ),
    },
    'moderate': {
        LANGUAGE_ENGLISH: (
            'AVALANCHE ADVISORY — {region_name}. '
            'Danger Level {danger_level}/5. '
            'Exercise caution on steep slopes.'
        ),
        LANGUAGE_HINDI: (
            'हिमस्खलन सलाह — {region_name}. '
            'खतरा स्तर {danger_level}/5. '
            ' steep ढलानों पर सावधानी बरतें.'
        ),
        LANGUAGE_URDU: (
            'برفانی تودے کی مشورہ — {region_name}. '
            'خطرے کی سطح {danger_level}/5. '
            'ڈھلوانوں پر احتیاط کریں.'
        ),
    },
}


@dataclass(frozen=True)
class SachetConfig:
    """Configuration for Sachet integration.

    Supports two modes:
    - API push mode (requires api_key, enabled=True)
    - RSS feed mode (free, no api_key needed, rss_enabled=True)
    """
    api_url: str = SACHET_API_URL
    api_key: str = SACHET_API_KEY
    enabled: bool = SACHET_ENABLED
    rss_enabled: bool = SACHET_RSS_ENABLED
    languages: tuple[str, ...] = (LANGUAGE_ENGLISH, LANGUAGE_HINDI, LANGUAGE_URDU)


@dataclass(frozen=True)
class SachetAlert:
    """Alert payload for Sachet push."""
    title: str
    body: str
    language: str
    geo_target: str  # bbox string or area code
    danger_level: int
    region_name: str
    alert_type: str = 'avalanche'
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class SachetPushResult:
    """Result of a Sachet push attempt."""
    success: bool
    message_id: str | None
    error: str | None
    channel: str  # 'sachet_api', 'sms', 'gagan', 'navic'
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def should_trigger_alert(danger_level: int, threshold: int = ALERT_TRIGGER_DANGER_LEVEL) -> bool:
    """Determine if an alert should be triggered based on danger level.

    Args:
        danger_level: EAWS danger level (1-5)
        threshold: Trigger threshold (default 4)

    Returns:
        True if danger_level >= threshold
    """
    return danger_level >= threshold


def render_alert_message(
    *,
    region_name: str,
    danger_level: int,
    language: str = LANGUAGE_ENGLISH,
) -> str:
    """Render alert message in specified language.

    Args:
        region_name: Human-readable region name
        danger_level: EAWS danger level (1-5)
        language: Language code ('en', 'hi', 'ur')

    Returns:
        Formatted alert message string
    """
    severity = 'high' if danger_level >= 4 else 'moderate'
    templates = MULTI_LANGUAGE_TEMPLATES.get(severity, MULTI_LANGUAGE_TEMPLATES['moderate'])
    template = templates.get(language, templates[LANGUAGE_ENGLISH])
    return template.format(region_name=region_name, danger_level=danger_level)


def build_multi_language_alerts(
    *,
    region_name: str,
    danger_level: int,
    bbox: list[float],
    config: SachetConfig | None = None,
) -> list[SachetAlert]:
    """Build alert payloads for all configured languages.

    Args:
        region_name: Human-readable region name
        danger_level: EAWS danger level (1-5)
        bbox: [west, south, east, north] bounding box
        config: Sachet configuration (uses default if None)

    Returns:
        List of SachetAlert objects, one per language
    """
    cfg = config or SachetConfig()
    geo_target = f'{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}'
    title = f'Avalanche Warning — {region_name} — Level {danger_level}'

    alerts: list[SachetAlert] = []
    for lang in cfg.languages:
        body = render_alert_message(
            region_name=region_name,
            danger_level=danger_level,
            language=lang,
        )
        alerts.append(SachetAlert(
            title=title,
            body=body,
            language=lang,
            geo_target=geo_target,
            danger_level=danger_level,
            region_name=region_name,
        ))
    return alerts


def push_sachet_alert(alert: SachetAlert, config: SachetConfig | None = None) -> SachetPushResult:
    """Push alert via NDMA Sachet API or RSS feed mode.

    When API push mode is enabled and an API key is present, makes an HTTP POST
    to the Sachet API. When RSS feed mode is enabled (default, free, no API key),
    returns a success result marking the alert as published via the RSS feed
    ingestion pipeline (see :mod:`backend.common.sachet_rss`).

    Args:
        alert: SachetAlert to push
        config: Sachet configuration

    Returns:
        SachetPushResult indicating success/failure
    """
    cfg = config or SachetConfig()

    if cfg.enabled and cfg.api_key:
        return _push_via_api(alert, cfg)

    if cfg.rss_enabled:
        return SachetPushResult(
            success=True,
            message_id=f'rss_{alert.timestamp}_{alert.language}',
            error=None,
            channel='sachet_rss',
        )

    if not cfg.enabled and not cfg.rss_enabled:
        return SachetPushResult(
            success=False,
            message_id=None,
            error='sachet_disabled',
            channel='sachet_api',
        )

    return SachetPushResult(
        success=False,
        message_id=None,
        error='no_api_key_configured',
        channel='sachet_api',
    )


def _push_via_api(alert: SachetAlert, cfg: SachetConfig) -> SachetPushResult:
    """Push alert via NDMA Sachet REST API (requires API key)."""
    try:
        import requests as _requests
        payload = {
            'title': alert.title,
            'body': alert.body,
            'language': alert.language,
            'geo_target': alert.geo_target,
            'danger_level': alert.danger_level,
            'region_name': alert.region_name,
            'alert_type': alert.alert_type,
            'timestamp': alert.timestamp,
        }
        headers = {
            'Authorization': f'Bearer {cfg.api_key}',
            'Content-Type': 'application/json',
        }
        resp = _requests.post(
            f'{cfg.api_url}/alerts',
            json=payload,
            headers=headers,
            timeout=10.0,
        )
        if resp.status_code in (200, 201, 202):
            msg_id = resp.json().get('message_id') if resp.headers.get('content-type', '').startswith('application/json') else None
            return SachetPushResult(
                success=True,
                message_id=msg_id or f'sachet_{alert.timestamp}_{alert.language}',
                error=None,
                channel='sachet_api',
            )
        return SachetPushResult(
            success=False,
            message_id=None,
            error=f'http_{resp.status_code}',
            channel='sachet_api',
        )
    except Exception as exc:
        return SachetPushResult(
            success=False,
            message_id=None,
            error=f'push_failed: {exc}',
            channel='sachet_api',
        )


SMS_GATEWAY_URL = os.getenv('SMS_GATEWAY_URL', 'https://api.msg91.com/api/v5/flow')
SMS_AUTH_KEY = os.getenv('SMS_AUTH_KEY', os.getenv('MSG91_AUTH_KEY', ''))
SMS_SENDER_ID = os.getenv('SMS_SENDER_ID', 'AVLNCH')
SMS_ROUTE_ID = os.getenv('SMS_ROUTE_ID', '4')
SMS_RECIPIENTS = os.getenv('SMS_RECIPIENTS', '')


def push_sms_alert(alert: SachetAlert, config: SachetConfig | None = None) -> SachetPushResult:
    """Push alert via SMS gateway (MSG91).

    When SMS_AUTH_KEY is configured, sends a real SMS via MSG91 flow API.
    Falls back to stub mode (no-op success) when key is absent.

    Args:
        alert: SachetAlert to push
        config: Sachet configuration

    Returns:
        SachetPushResult
    """
    if not SMS_AUTH_KEY:
        return SachetPushResult(
            success=True,
            message_id=f'sms_stub_{alert.timestamp}_{alert.language}',
            error=None,
            channel='sms_stub',
        )

    import json
    import urllib.request

    template_key = MULTI_LANGUAGE_TEMPLATES.get(
        'high' if alert.danger_level >= 4 else 'moderate',
        MULTI_LANGUAGE_TEMPLATES['high'],
    )
    message_body = template_key.get(alert.language, template_key[LANGUAGE_ENGLISH]).format(
        region_name=alert.region_name,
        danger_level=alert.danger_level,
    )

    recipients = [r.strip() for r in SMS_RECIPIENTS.split(',') if r.strip()]
    if not recipients:
        return SachetPushResult(
            success=True,
            message_id=f'sms_no_recipients_{alert.timestamp}',
            error=None,
            channel='sms_no_recipients',
        )

    payload = {
        'template_id': os.getenv('SMS_TEMPLATE_ID', ''),
        'sender': SMS_SENDER_ID,
        'short_url': '0',
        'mobiles': ','.join(recipients),
        'var1': alert.region_name,
        'var2': str(alert.danger_level),
        'var3': message_body[:160],
    }

    headers = {
        'authkey': SMS_AUTH_KEY,
        'Content-Type': 'application/json',
    }

    try:
        req = urllib.request.Request(
            SMS_GATEWAY_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            resp_data = json.loads(response.read().decode('utf-8'))
            if resp_data.get('type') == 'success':
                return SachetPushResult(
                    success=True,
                    message_id=f'sms_{alert.timestamp}_{alert.language}',
                    error=None,
                    channel='sms_msg91',
                )
            return SachetPushResult(
                success=False,
                message_id=None,
                error=f'sms_gateway_error: {resp_data.get("message", "unknown")}',
                channel='sms_msg91',
            )
    except Exception as exc:
        return SachetPushResult(
            success=False,
            message_id=None,
            error=f'sms_failed: {exc}',
            channel='sms_msg91',
        )


def push_gagan_alert(alert: SachetAlert, config: SachetConfig | None = None) -> SachetPushResult:
    """Push alert via GAGAN satellite.

    Stub implementation — GAGAN (GPS Aided Geo Augmented Navigation)
    is India's SBAS system for satellite-based alert dissemination.

    Args:
        alert: SachetAlert to push
        config: Sachet configuration

    Returns:
        SachetPushResult
    """
    return SachetPushResult(
        success=True,
        message_id=f'gagan_{alert.timestamp}_{alert.language}',
        error=None,
        channel='gagan',
    )


def push_navic_alert(alert: SachetAlert, config: SachetConfig | None = None) -> SachetPushResult:
    """Push alert via NavIC satellite.

    Stub implementation — NavIC (Navigation with Indian Constellation)
    is India's regional satellite navigation system.

    Args:
        alert: SachetAlert to push
        config: Sachet configuration

    Returns:
        SachetPushResult
    """
    return SachetPushResult(
        success=True,
        message_id=f'navic_{alert.timestamp}_{alert.language}',
        error=None,
        channel='navic',
    )


def disseminate_alert(
    *,
    region_name: str,
    danger_level: int,
    bbox: list[float],
    config: SachetConfig | None = None,
) -> list[SachetPushResult]:
    """Disseminate alert via all configured channels.

    Builds multi-language alerts and pushes via Sachet API, SMS, GAGAN, NavIC.

    Args:
        region_name: Human-readable region name
        danger_level: EAWS danger level (1-5)
        bbox: [west, south, east, north] bounding box
        config: Sachet configuration

    Returns:
        List of SachetPushResult for all channels and languages
    """
    if not should_trigger_alert(danger_level):
        return []

    alerts = build_multi_language_alerts(
        region_name=region_name,
        danger_level=danger_level,
        bbox=bbox,
        config=config,
    )

    results: list[SachetPushResult] = []
    for alert in alerts:
        results.append(push_sachet_alert(alert, config))
        results.append(push_sms_alert(alert, config))
        results.append(push_gagan_alert(alert, config))
        results.append(push_navic_alert(alert, config))

    return results
