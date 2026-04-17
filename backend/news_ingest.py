"""Autonomous news-based avalanche event ingestion.

Pipeline (runs daily via GitHub Actions):

1. Query newsdata.io for recent articles matching ``avalanche`` keyword.
2. For each article, ask Gemini 2.0 Flash to extract a structured event record
   (is_event, lat/lng, severity, event_date, confidence).
3. Drop anything that is not a real avalanche OR does not fall inside one of
   our 8 configured regional bboxes.
4. De-duplicate against previously ingested articles (newsdata ``article_id``
   stored under ``topo_profile.metadata.news_article_id`` by the edge function).
5. POST qualifying events to the ``ingest-event`` Supabase edge function so
   they go through the standard topo-snap + deposit-zone classifier pipeline.

All credentials are read from environment. Missing any of ``NEWSDATA_API_KEY``,
``GEMINI_API_KEY``, ``SUPABASE_URL``, ``SUPABASE_SERVICE_ROLE_KEY`` causes a
clean ``exit 0`` (graceful skip) so the workflow job never fails the pipeline.
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
GEMINI_ENDPOINT = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    'gemini-2.0-flash:generateContent'
)

NEWSDATA_KEY = os.getenv('NEWSDATA_API_KEY')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')
SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

NEWS_LOOKBACK_HOURS = int(os.getenv('NEWS_LOOKBACK_HOURS', '48'))
NEWS_MAX_ARTICLES = int(os.getenv('NEWS_MAX_ARTICLES', '50'))
NEWS_MIN_CONFIDENCE = float(os.getenv('NEWS_MIN_CONFIDENCE', '0.6'))
NEWS_QUERY = os.getenv('NEWS_QUERY', 'avalanche')


def _has_all_credentials() -> bool:
    missing = [
        name for name, value in (
            ('NEWSDATA_API_KEY', NEWSDATA_KEY),
            ('GEMINI_API_KEY', GEMINI_KEY),
            ('SUPABASE_URL', SUPABASE_URL),
            ('SUPABASE_SERVICE_ROLE_KEY', SUPABASE_SERVICE_ROLE_KEY),
        ) if not value
    ]
    if missing:
        print(f'[news_ingest] missing credentials: {missing}; skipping (this is safe).')
        return False
    return True


def fetch_newsdata_articles() -> list[dict[str, Any]]:
    params = {
        'apikey': NEWSDATA_KEY,
        'q': NEWS_QUERY,
        'language': 'en',
        'category': 'environment,top,world',
        'size': min(NEWS_MAX_ARTICLES, 50),
    }
    resp = requests.get(NEWSDATA_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    results = body.get('results') or []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_LOOKBACK_HOURS)
    filtered: list[dict[str, Any]] = []
    for article in results:
        pub = article.get('pubDate')
        try:
            pub_dt = datetime.fromisoformat(pub.replace(' ', 'T').replace('Z', '+00:00'))
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
        except Exception:
            pub_dt = datetime.now(timezone.utc)
        if pub_dt < cutoff:
            continue
        filtered.append(article)
    print(f'[news_ingest] newsdata returned {len(results)} articles; {len(filtered)} within {NEWS_LOOKBACK_HOURS}h window')
    return filtered


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
    "event itself)."
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
        resp = requests.post(
            f'{GEMINI_ENDPOINT}?key={GEMINI_KEY}',
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as exc:
        print(f'[news_ingest] gemini call failed: {exc}', file=sys.stderr)
        return None
    try:
        text = resp.json()['candidates'][0]['content']['parts'][0]['text']
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
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        rows = resp.json()
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
        'event_type': 'reported',
        'severity': int(record.get('severity') or 3),
        'confidence': float(record.get('confidence') or 0.6),
        'location_name': record.get('location_name') or region.name,
        'fusion_source': 'newsdata_gemini',
        'metadata': {
            'news_article_id': article.get('article_id'),
            'news_link': article.get('link'),
            'news_title': article.get('title'),
            'news_source': article.get('source_id'),
            'news_pub_date': article.get('pubDate'),
            'event_date_iso': record.get('event_date_iso'),
            'extractor': 'gemini-2.0-flash',
            'region_key': region.key,
        },
    }
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
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
