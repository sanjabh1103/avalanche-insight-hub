"""Autonomous news-based avalanche event ingestion.

Pipeline (runs daily via GitHub Actions):

1. Query newsdata.io for recent avalanche-related articles across a small
   multilingual keyword set.
2. For each article, ask Gemini Flash to extract a structured event record
   (is_event, lat/lng, severity, event_date, confidence).
3. Drop anything that is not a real avalanche OR does not fall inside one of
   our 8 configured regional bboxes.
4. De-duplicate against previously ingested articles (newsdata ``article_id``
   stored under ``topo_profile.metadata.news_article_id`` by the edge function).
5. POST qualifying events to the ``ingest-event`` Supabase edge function so
   they go through the standard topo-snap + deposit-zone classifier pipeline.

All credentials are read from environment. Missing any of ``NEWSDATA_API_KEY``,
``GEMINI_API_KEY``, ``SUPABASE_URL``/``VITE_SUPABASE_URL``, or
``SUPABASE_SERVICE_ROLE_KEY`` causes a clean ``exit 0`` (graceful skip) so the
workflow job never fails the pipeline.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import requests

from backend.common.regions import Region, load_regions

NEWSDATA_ENDPOINT = 'https://newsdata.io/api/1/latest'
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
GEMINI_ENDPOINT = (
    f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'
)

NEWSDATA_KEY = os.getenv('NEWSDATA_API_KEY')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')
SUPABASE_URL = (os.getenv('SUPABASE_URL') or os.getenv('VITE_SUPABASE_URL') or '').rstrip('/')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

NEWS_LOOKBACK_HOURS = int(os.getenv('NEWS_LOOKBACK_HOURS', '48'))
NEWS_MAX_ARTICLES = int(os.getenv('NEWS_MAX_ARTICLES', '10'))  # free-tier cap
NEWS_MIN_CONFIDENCE = float(os.getenv('NEWS_MIN_CONFIDENCE', '0.6'))
NEWS_REQUEST_RETRIES = int(os.getenv('NEWS_REQUEST_RETRIES', '3'))
NEWS_REQUEST_BACKOFF_SECONDS = float(os.getenv('NEWS_REQUEST_BACKOFF_SECONDS', '1.0'))
NEWS_QUERY_TERMS = tuple(
    term.strip() for term in os.getenv(
        'NEWS_QUERY_TERMS',
        'avalanche,avalanche snow,avalanches,avalanche neige,avalancha,lawine,Himalayan avalanche,Kashmir avalanche,Ladakh avalanche,Himachal avalanche,Uttarakhand avalanche,Sikkim avalanche,Nepal avalanche',
    ).split(',')
    if term.strip()
)
NEWS_LANGUAGES = tuple(
    lang.strip() for lang in os.getenv('NEWS_LANGUAGES', 'en,fr,es,de,hi').split(',')
    if lang.strip()
)


def _has_all_credentials() -> bool:
    missing = [
        name for name, value in (
            ('NEWSDATA_API_KEY', NEWSDATA_KEY),
            ('GEMINI_API_KEY', GEMINI_KEY),
            ('SUPABASE_URL/VITE_SUPABASE_URL', SUPABASE_URL),
            ('SUPABASE_SERVICE_ROLE_KEY', SUPABASE_SERVICE_ROLE_KEY),
        ) if not value
    ]
    if missing:
        print(f'[news_ingest] missing credentials: {missing}; skipping (this is safe).')
        return False
    return True


def _redact_url(url: str) -> str:
    return url.split('?', 1)[0]


def _request_json_with_backoff(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = NEWS_REQUEST_RETRIES,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(retries):
        response = None
        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f'{method} {_redact_url(url)} returned {response.status_code}', response=response)
            response.raise_for_status()
            return response.json()
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc
        except requests.HTTPError as exc:
            status_code = getattr(exc.response, 'status_code', None)
            if status_code is not None and 400 <= status_code < 500 and status_code != 429:
                raise
            last_error = exc
        except Exception as exc:
            last_error = exc
        if attempt < retries - 1:
            retry_after = 0.0
            if response is not None:
                retry_after_header = response.headers.get('Retry-After')
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header)
                    except ValueError:
                        retry_after = 0.0
            sleep_time = max(NEWS_REQUEST_BACKOFF_SECONDS * (2 ** attempt), retry_after)
            print(f'[news_ingest] retrying {method} {_redact_url(url)} in {sleep_time:.1f}s', file=sys.stderr)
            time.sleep(sleep_time)
    raise last_error or RuntimeError(f'Failed to fetch {_redact_url(url)} after {retries} attempts')


def _iter_search_configs() -> Iterable[tuple[str, str]]:
    for language in NEWS_LANGUAGES or ('en',):
        for query in NEWS_QUERY_TERMS or ('avalanche',):
            yield query, language


def _parse_pubdate(pub: Any) -> datetime:
    try:
        pub_dt = datetime.fromisoformat(str(pub).replace(' ', 'T').replace('Z', '+00:00'))
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        return pub_dt
    except Exception:
        return datetime.now(timezone.utc)


def _article_key(article: dict[str, Any]) -> str:
    return str(article.get('article_id') or article.get('link') or article.get('title') or '')


def fetch_newsdata_articles() -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_LOOKBACK_HOURS)
    budget = min(NEWS_MAX_ARTICLES, 10)
    collected: list[dict[str, Any]] = []
    seen_article_keys: set[str] = set()
    search_configs = list(_iter_search_configs())

    for query, language in search_configs:
        if len(collected) >= budget:
            break
        params = {
            'apikey': NEWSDATA_KEY,
            'q': query,
            'size': budget,
            'language': language,
        }
        try:
            body = _request_json_with_backoff('GET', NEWSDATA_ENDPOINT, params=params, timeout=30)
        except Exception as exc:
            print(f'[news_ingest] newsdata query failed for {query!r}/{language!r}: {exc}', file=sys.stderr)
            continue
        results = body.get('results') or []
        for article in results:
            key = _article_key(article)
            if not key or key in seen_article_keys:
                continue
            pub_dt = _parse_pubdate(article.get('pubDate'))
            if pub_dt < cutoff:
                continue
            seen_article_keys.add(key)
            collected.append(article)
            if len(collected) >= budget:
                break

    print(
        f'[news_ingest] newsdata returned {len(collected)} avalanche articles '
        f'within {NEWS_LOOKBACK_HOURS}h window using {len(search_configs)} query configs'
    )
    return collected


EXTRACTION_PROMPT = (
    "You extract structured avalanche event records from news articles. "
    "Return ONLY a JSON object with keys: "
    '{"is_avalanche_event": bool, "location_name": string|null, '
    '"lat": number|null, "lng": number|null, "severity": 1-5 integer, '
    '"event_date_iso": string|null, "confidence": 0-1 number, '
    '"summary": string}. '
    "is_avalanche_event=true only for a real snow avalanche that has already "
    "occurred (ignore forecasts/warnings/historical retrospectives). "
    "Set lat/lng to the best-known event location (decimal degrees). "
    "severity: 1=near-miss, 2=small/no casualties, 3=significant damage, "
    "4=multiple casualties, 5=major disaster. "
    "confidence reflects your certainty about extraction accuracy (not the "
    "event itself). "
    "You may receive articles in English, French, Spanish, German, Hindi, or other "
    "languages; extract from the original text directly and do not require "
    "English. "
    "Pay special attention to events in the Himalayan region (India, Nepal, "
    "Pakistan, Afghanistan, Bhutan). If the article mentions a Himalayan state "
    "or region (Kashmir, Ladakh, Himachal Pradesh, Uttarakhand, Sikkim, "
    "Arunachal Pradesh, Nepal, Bhutan), include the state/region name in "
    "location_name."
)


def extract_event_with_gemini(title: str, content: str) -> Optional[dict[str, Any]]:
    snippet = (content or '')[:4000]
    body = {
        'contents': [{
            'role': 'user',
            'parts': [{'text': f'{EXTRACTION_PROMPT}\n\nTITLE: {title}\n\nARTICLE:\n{snippet}'}],
        }],
        'generationConfig': {
            'temperature': 0.1,
            'responseMimeType': 'application/json',
        },
    }
    try:
        payload = _request_json_with_backoff(
            'POST',
            GEMINI_ENDPOINT,
            payload=body,
            headers={'x-goog-api-key': GEMINI_KEY},
            timeout=30,
        )
    except Exception as exc:
        print(f'[news_ingest] gemini call failed: {exc}', file=sys.stderr)
        return None
    try:
        text = payload['candidates'][0]['content']['parts'][0]['text']
        record = json.loads(text)
    except Exception as exc:
        print(f'[news_ingest] gemini parse failed: {exc}', file=sys.stderr)
        return None
    return record


def match_region(lat: float, lng: float, regions: list[Region]) -> Optional[Region]:
    for region in regions:
        south, west, north, east = region.bbox
        if south <= lat <= north and west <= lng <= east:
            return region
    return None


def load_existing_article_ids() -> set[str]:
    """Return article_ids that have already been ingested as gemini_news events."""
    url = f'{SUPABASE_URL}/rest/v1/avalanche_events'
    params = {
        'select': 'topo_profile',
        'source': 'eq.gemini_news',
        'order': 'created_at.desc',
        'limit': '500',
    }
    headers = {
        'apikey': SUPABASE_SERVICE_ROLE_KEY or '',
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY or ""}',
    }
    try:
        rows = _request_json_with_backoff('GET', url, params=params, headers=headers, timeout=30)
    except Exception as exc:
        print(f'[news_ingest] could not fetch existing gemini_news events: {exc}', file=sys.stderr)
        return set()
    ids: set[str] = set()
    for row in rows:
        profile = row.get('topo_profile') or {}
        metadata = (profile.get('metadata') or {})
        article_id = metadata.get('news_article_id')
        if isinstance(article_id, str):
            ids.add(article_id)
    return ids


def post_ingest_event(article: dict[str, Any], record: dict[str, Any], region: Region) -> bool:
    url = f'{SUPABASE_URL}/functions/v1/ingest-event'
    payload = {
        'lat': float(record['lat']),
        'lng': float(record['lng']),
        'description': record.get('summary') or article.get('title') or 'News-sourced avalanche event',
        'hazard_type': 'avalanche',
        'source': 'gemini_news',
        'event_type': 'unknown',
        'severity': int(record.get('severity') or 3),
        'confidence': float(record.get('confidence') or 0.6),
        'label_confidence': float(record.get('confidence') or 0.6),
        'source_model': GEMINI_MODEL,
        'geometry_type': 'point',
        'location_name': record.get('location_name') or region.name,
        'fusion_source': 'newsdata_gemini',
        'training_eligible': False,
        'label_role': 'display_only',
        'training_eligible_reason': 'machine_extracted_news_unreviewed',
        'metadata': {
            'news_article_id': article.get('article_id'),
            'news_link': article.get('link'),
            'news_title': article.get('title'),
            'news_source': article.get('source_id'),
            'news_pub_date': article.get('pubDate'),
            'event_date_iso': record.get('event_date_iso'),
            'extractor': GEMINI_MODEL,
            'region_key': region.key,
            'machine_candidate_reason': 'gemini_extracted_news_unreviewed',
            'corroboration_sources': ['gemini_news'],
        },
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
    }
    try:
        _request_json_with_backoff('POST', url, payload=payload, headers=headers, timeout=60)
    except Exception as exc:
        print(f'[news_ingest] ingest-event POST failed for {article.get("article_id")}: {exc}', file=sys.stderr)
        return False
    return True


def main() -> int:
    if not _has_all_credentials():
        return 0

    regions = load_regions()
    known_ids = load_existing_article_ids()
    print(f'[news_ingest] {len(known_ids)} existing gemini_news articles already ingested')

    articles = fetch_newsdata_articles()
    stats = {'fetched': len(articles), 'duplicates': 0, 'not_event': 0, 'out_of_region': 0, 'low_confidence': 0, 'ingested': 0, 'post_failed': 0}

    for article in articles:
        article_id = article.get('article_id') or article.get('link')
        if article_id and article_id in known_ids:
            stats['duplicates'] += 1
            continue
        record = extract_event_with_gemini(article.get('title') or '', article.get('content') or article.get('description') or '')
        if not record or not record.get('is_avalanche_event'):
            stats['not_event'] += 1
            continue
        lat, lng = record.get('lat'), record.get('lng')
        if lat is None or lng is None:
            stats['out_of_region'] += 1
            continue
        region = match_region(float(lat), float(lng), regions)
        if region is None:
            stats['out_of_region'] += 1
            continue
        if float(record.get('confidence') or 0.0) < NEWS_MIN_CONFIDENCE:
            stats['low_confidence'] += 1
            continue
        if post_ingest_event(article, record, region):
            stats['ingested'] += 1
        else:
            stats['post_failed'] += 1
        time.sleep(0.3)  # be polite to Gemini + Supabase

    print(f'[news_ingest] summary: {json.dumps(stats, indent=2)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
