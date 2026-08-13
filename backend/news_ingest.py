"""Autonomous news-based avalanche event ingestion.

Pipeline (runs daily via GitHub Actions):

1. Query newsdata.io for recent avalanche-related articles across a small
   multilingual keyword set.
2. For each article, ask Gemini Flash to extract a structured event record
   (is_event, lat/lng, severity, event_date, confidence).
3. Drop anything that is not a real avalanche OR does not fall inside one of
   our 8 configured regional bboxes.
4. De-duplicate against previously ingested articles (newsdata ``article_id``
   stored under ``topo_profile.metadata.news_article_id``).
5. Insert qualifying events directly via the Supabase REST API into
   ``avalanche_events`` with ``source='gemini_news'`` and
   ``training_eligible=False`` so a scientist can review before promotion.
   NOTE: This bypasses the ``ingest-event`` edge function and its topo-snap /
   deposit-zone enrichment. Events are marked ``label_role='display_only'``
   until a scientist validates them.

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
GOOGLE_NEWS_RSS_ENDPOINT = 'https://news.google.com/rss/search?q=avalanche+Himalaya&hl=en-IN&gl=IN&ceid=IN:en'
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
NEWS_MIN_CONFIDENCE = float(os.getenv('NEWS_MIN_CONFIDENCE', '0.4'))
NEWS_REQUEST_RETRIES = int(os.getenv('NEWS_REQUEST_RETRIES', '3'))
NEWS_REQUEST_BACKOFF_SECONDS = float(os.getenv('NEWS_REQUEST_BACKOFF_SECONDS', '1.0'))
NEWS_RSS_MIN_INTERVAL_S = float(os.getenv('NEWS_RSS_MIN_INTERVAL_S', '2.0'))
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

_last_rss_fetch_time = 0.0


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
        for cred in missing:
            print(f'::warning::news_ingest skipped — missing GitHub secret: {cred}. Set it in repo Settings → Secrets and Variables → Actions.')
        return False
    return True


def _has_rss_fallback_credentials() -> bool:
    """Check if we can run RSS-only mode (no NewsData key needed)."""
    missing = [
        name for name, value in (
            ('GEMINI_API_KEY', GEMINI_KEY),
            ('SUPABASE_URL/VITE_SUPABASE_URL', SUPABASE_URL),
            ('SUPABASE_SERVICE_ROLE_KEY', SUPABASE_SERVICE_ROLE_KEY),
        ) if not value
    ]
    if missing:
        print(f'[news_ingest] RSS fallback missing credentials: {missing}; skipping.')
        for cred in missing:
            print(f'::warning::news_ingest RSS fallback skipped — missing GitHub secret: {cred}. Set it in repo Settings → Secrets and Variables → Actions.')
        return False
    if not NEWSDATA_KEY:
        print('[news_ingest] NEWSDATA_API_KEY not set — using Google News RSS fallback (free, no key).')
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
    "is_avalanche_event=true for ANY article describing a real avalanche-related "
    "incident, including: avalanches that have occurred, avalanche rescue "
    "operations, avalanche casualties (soldiers, civilians, climbers), "
    "avalanche-triggered road closures or highway blockages, avalanche damage "
    "to infrastructure, and avalanche incidents reported as news. "
    "Only set is_avalanche_event=false for: pure seasonal forecast summaries "
    "with no specific incident, general safety advisories with no event, "
    "non-avalanche news (floods, landslides without avalanche), or articles "
    "about historical anniversaries with no new event. "
    "Set lat/lng to the best-known event location (decimal degrees). If exact "
    "coordinates are not given, infer approximate lat/lng from the location "
    "name, city, or region mentioned in the article. "
    "severity: 1=near-miss, 2=small/no casualties, 3=significant damage, "
    "4=multiple casualties, 5=major disaster. "
    "confidence reflects your certainty about extraction accuracy (not the "
    "event itself). Set confidence >= 0.5 if you can identify the event type "
    "and approximate location, even if exact coordinates are uncertain. "
    "You may receive articles in English, French, Spanish, German, Hindi, or other "
    "languages; extract from the original text directly and do not require "
    "English. "
    "Pay special attention to events in the Himalayan region (India, Nepal, "
    "Pakistan, Afghanistan, Bhutan). If the article mentions a Himalayan state "
    "or region (Kashmir, Ladakh, Himachal Pradesh, Uttarakhand, Sikkim, "
    "Arunachal Pradesh, Nepal, Bhutan), include the state/region name in "
    "location_name."
)


def extract_event_with_gemini(title: str, content: str, source_id: str = '') -> Optional[dict[str, Any]]:
    snippet = (content or '')[:4000]
    source_context = f'\nSOURCE: {source_id}' if source_id else ''
    body = {
        'contents': [{
            'role': 'user',
            'parts': [{'text': f'{EXTRACTION_PROMPT}\n\nTITLE: {title}\n\nARTICLE:\n{snippet}{source_context}'}],
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
    print(f'[news_ingest] gemini result: is_event={record.get("is_avalanche_event")} '
          f'confidence={record.get("confidence")} location={record.get("location_name")} '
          f'lat={record.get("lat")} lng={record.get("lng")} severity={record.get("severity")}')
    return record


def match_region(lat: float, lng: float, regions: list[Region]) -> Optional[Region]:
    for region in regions:
        south, west, north, east = region.bbox
        if south <= lat <= north and west <= lng <= east:
            return region
    return None


_LOCATION_NAME_MAP: dict[str, str] = {
    'kashmir': 'Pir Panjal (NW Himalaya)',
    'srinagar': 'Pir Panjal (NW Himalaya)',
    'gulmarg': 'Pir Panjal (NW Himalaya)',
    'poonch': 'Pir Panjal (NW Himalaya)',
    'rajouri': 'Pir Panjal (NW Himalaya)',
    'baramulla': 'Pir Panjal (NW Himalaya)',
    'kupwara': 'Pir Panjal (NW Himalaya)',
    'ladakh': 'Karakoram & Ladakh',
    'leh': 'Karakoram & Ladakh',
    'kargil': 'Karakoram & Ladakh',
    'drass': 'Karakoram & Ladakh',
    'zanskar': 'Karakoram & Ladakh',
    'nubra': 'Karakoram & Ladakh',
    'siachen': 'Karakoram & Ladakh',
    'himachal': 'Great Himalaya (NW Himalaya)',
    'manali': 'Great Himalaya (NW Himalaya)',
    'kullu': 'Great Himalaya (NW Himalaya)',
    'lahaul': 'Great Himalaya (NW Himalaya)',
    'spiti': 'Great Himalaya (NW Himalaya)',
    'chamba': 'Great Himalaya (NW Himalaya)',
    'uttarakhand': 'Great Himalaya (NW Himalaya)',
    'uttarkashi': 'Great Himalaya (NW Himalaya)',
    'chamoli': 'Great Himalaya (NW Himalaya)',
    'rudraprayag': 'Great Himalaya (NW Himalaya)',
    'joshimath': 'Great Himalaya (NW Himalaya)',
    'nepal': 'Himalayas (Nepal)',
    'khumbu': 'Himalayas (Nepal)',
    'everest': 'Himalayas (Nepal)',
    'annapurna': 'Himalayas (Nepal)',
    'mustang': 'Himalayas (Nepal)',
    'colorado': 'Colorado Rockies',
    'rockies': 'Colorado Rockies',
    'swiss': 'Swiss Alps',
    'switzerland': 'Swiss Alps',
    'alps': 'Swiss Alps',
    'french alps': 'French Alps',
    'chamonix': 'French Alps',
    'mont blanc': 'French Alps',
    'cascades': 'Cascades (WA)',
    'washington': 'Cascades (WA)',
    'norway': 'Scandinavia (Norway)',
    'japan': 'Japanese Alps',
    'himalaya': 'Himalayas (Nepal)',
    'himalayas': 'Himalayas (Nepal)',
    'patagonia': 'Andes (Patagonia)',
    'andes': 'Andes (Patagonia)',
}


def match_location_name_to_region(location_name: str, regions: list[Region]) -> Optional[tuple[Region, float, float]]:
    """Match a location_name string to a known region and return (region, lat, lng) using region center."""
    if not location_name:
        return None
    lower = location_name.lower()
    for keyword, region_name in _LOCATION_NAME_MAP.items():
        if keyword in lower:
            for region in regions:
                if region.name == region_name:
                    return region, region.center[0], region.center[1]
    return None


def load_existing_article_ids() -> set[str] | None:
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
        return None
    ids: set[str] = set()
    for row in rows:
        profile = row.get('topo_profile') or {}
        metadata = (profile.get('metadata') or {})
        article_id = metadata.get('news_article_id')
        if isinstance(article_id, str):
            ids.add(article_id)
    return ids


def _count_gemini_news_rows() -> int | None:
    """Count existing gemini_news rows. Returns None on error."""
    url = f'{SUPABASE_URL}/rest/v1/avalanche_events'
    params = {'source': 'eq.gemini_news', 'select': 'id'}
    headers = {
        'apikey': SUPABASE_SERVICE_ROLE_KEY or '',
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY or ""}',
        'Prefer': 'count=exact',
    }
    try:
        resp = _request_json_with_backoff('GET', url, params=params, headers=headers, timeout=15)
        return len(resp) if isinstance(resp, list) else None
    except Exception:
        return None


GEMINI_NEWS_ROW_BUDGET = int(os.getenv('GEMINI_NEWS_ROW_BUDGET', '500'))


def post_ingest_event(article: dict[str, Any], record: dict[str, Any], region: Region) -> bool:
    """Insert event directly via Supabase REST API (no edge function needed)."""
    lat = float(record['lat'])
    lng = float(record['lng'])
    url = f'{SUPABASE_URL}/rest/v1/avalanche_events'
    metadata = {
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
    }
    event_date = record.get('event_date_iso') or ''
    payload = {
        'location': f'POINT({lng} {lat})',
        'description': (record.get('summary') or article.get('title') or 'News-sourced avalanche event')[:500],
        'hazard_type': 'avalanche',
        'source': 'gemini_news',
        'event_type': 'unknown',
        'severity': max(1, min(5, int(record.get('severity') or 3))),
        'confidence': max(0.0, min(1.0, float(record.get('confidence') or 0.6))),
        'label_confidence': max(0.0, min(1.0, float(record.get('confidence') or 0.6))),
        'source_model': GEMINI_MODEL,
        'geometry_type': 'point',
        'fusion_source': 'newsdata_gemini',
        'training_eligible': False,
        'label_role': 'display_only',
        'training_eligible_reason': 'machine_extracted_news_unreviewed',
        'topo_profile': {
            'metadata': metadata,
            'location_name': record.get('location_name') or region.name,
        },
    }
    if event_date:
        try:
            from datetime import datetime as _dt
            payload['timestamp'] = _dt.fromisoformat(event_date.replace('Z', '+00:00')).isoformat()
        except Exception:
            pass
    headers = {
        'Content-Type': 'application/json',
        'apikey': SUPABASE_SERVICE_ROLE_KEY or '',
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY or ""}',
        'Prefer': 'return=representation',
    }
    try:
        result = _request_json_with_backoff('POST', url, payload=payload, headers=headers, timeout=60)
        if isinstance(result, list) and result:
            row_id = result[0].get('id', '?')
            src = article.get('source_id') or ''
            print(f'[news_ingest] inserted event id={row_id} for {src}')
        return True
    except Exception as exc:
        print(f'[news_ingest] REST insert failed for {article.get("article_id")}: {exc}', file=sys.stderr)
        return False


def fetch_google_news_rss() -> list[dict[str, Any]]:
    """Fetch avalanche-related articles from Google News RSS (free, no API key).

    Returns a list of article dicts with keys: title, link, pubDate, description.
    Falls back to an empty list on any error.
    """
    global _last_rss_fetch_time
    elapsed = time.monotonic() - _last_rss_fetch_time
    if elapsed < NEWS_RSS_MIN_INTERVAL_S:
        time.sleep(NEWS_RSS_MIN_INTERVAL_S - elapsed)
    _last_rss_fetch_time = time.monotonic()
    try:
        import xml.etree.ElementTree as ET
        resp = requests.get(GOOGLE_NEWS_RSS_ENDPOINT, timeout=15, headers={'User-Agent': 'AvalancheInsightHub/1.0'})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = root.findall('.//item')
        articles = []
        for item in items[:NEWS_MAX_ARTICLES]:
            title = (item.findtext('title') or '').strip()
            link = (item.findtext('link') or '').strip()
            pub_date = (item.findtext('pubDate') or '').strip()
            desc = (item.findtext('description') or '').strip()
            if title:
                articles.append({
                    'article_id': link or title,
                    'title': title,
                    'link': link,
                    'pubDate': pub_date,
                    'description': desc,
                    'content': desc,
                })
        print(f'[news_ingest] Google News RSS: fetched {len(articles)} articles')
        return articles
    except Exception as exc:
        print(f'[news_ingest] Google News RSS fetch failed: {exc}', file=sys.stderr)
        return []


def _run_retention_cleanup() -> None:
    """Call Supabase RPC to delete oldest gemini_news rows beyond budget."""
    url = f'{SUPABASE_URL}/rest/v1/rpc/cleanup_gemini_news_rows'
    headers = {
        'Content-Type': 'application/json',
        'apikey': SUPABASE_SERVICE_ROLE_KEY or '',
        'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY or ""}',
    }
    try:
        result = _request_json_with_backoff(
            'POST', url, payload={'p_row_budget': GEMINI_NEWS_ROW_BUDGET},
            headers=headers, timeout=30,
        )
        deleted = result if isinstance(result, int) else 0
        if deleted:
            print(f'[news_ingest] retention cleanup: deleted {deleted} old gemini_news rows')
    except Exception as exc:
        print(f'[news_ingest] retention cleanup skipped: {exc}', file=sys.stderr)


def main() -> int:
    if not _has_all_credentials():
        if not _has_rss_fallback_credentials():
            return 0
        regions = load_regions()
        known_ids = load_existing_article_ids()
        if known_ids is None:
            print('[news_ingest] dedupe check failed — aborting to prevent duplicate inserts')
            return 0
        print(f'[news_ingest] {len(known_ids)} existing gemini_news articles already ingested')

        existing_count = _count_gemini_news_rows()
        if existing_count is not None and existing_count >= GEMINI_NEWS_ROW_BUDGET:
            print(f'[news_ingest] row budget reached: {existing_count} >= {GEMINI_NEWS_ROW_BUDGET} — running cleanup then skipping ingestion')
            _run_retention_cleanup()
            return 0

        articles = fetch_google_news_rss()
        stats = {'fetched': len(articles), 'duplicates': 0, 'not_event': 0, 'out_of_region': 0, 'low_confidence': 0, 'ingested': 0, 'post_failed': 0, 'source': 'google_news_rss'}

        for article in articles:
            article_id = article.get('article_id') or article.get('link')
            if article_id and article_id in known_ids:
                stats['duplicates'] += 1
                continue
            record = extract_event_with_gemini(
                article.get('title') or '',
                article.get('content') or article.get('description') or '',
                source_id=article.get('source_id') or article.get('source') or '',
            )
            if not record or not record.get('is_avalanche_event'):
                stats['not_event'] += 1
                continue
            lat, lng = record.get('lat'), record.get('lng')
            region = None
            if lat is not None and lng is not None:
                region = match_region(float(lat), float(lng), regions)
            if region is None:
                loc_match = match_location_name_to_region(record.get('location_name') or '', regions)
                if loc_match:
                    region, lat, lng = loc_match
                    record['lat'] = lat
                    record['lng'] = lng
                    print(f'[news_ingest] location-name fallback: "{record.get("location_name")}" -> {region.name}')
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
            time.sleep(0.3)

        print(f'[news_ingest] summary: {json.dumps(stats, indent=2)}')
        _run_retention_cleanup()
        return 0

    regions = load_regions()
    known_ids = load_existing_article_ids()
    if known_ids is None:
        print('[news_ingest] dedupe check failed — aborting to prevent duplicate inserts')
        return 0
    print(f'[news_ingest] {len(known_ids)} existing gemini_news articles already ingested')

    existing_count = _count_gemini_news_rows()
    if existing_count is not None and existing_count >= GEMINI_NEWS_ROW_BUDGET:
        print(f'[news_ingest] row budget reached: {existing_count} >= {GEMINI_NEWS_ROW_BUDGET} — running cleanup then skipping ingestion')
        _run_retention_cleanup()
        return 0

    articles = fetch_newsdata_articles()
    stats = {'fetched': len(articles), 'duplicates': 0, 'not_event': 0, 'out_of_region': 0, 'low_confidence': 0, 'ingested': 0, 'post_failed': 0, 'source': 'newsdata'}

    for article in articles:
        article_id = article.get('article_id') or article.get('link')
        if article_id and article_id in known_ids:
            stats['duplicates'] += 1
            continue
        record = extract_event_with_gemini(
            article.get('title') or '',
            article.get('content') or article.get('description') or '',
            source_id=article.get('source_id') or article.get('source') or '',
        )
        if not record or not record.get('is_avalanche_event'):
            stats['not_event'] += 1
            continue
        lat, lng = record.get('lat'), record.get('lng')
        region = None
        if lat is not None and lng is not None:
            region = match_region(float(lat), float(lng), regions)
        if region is None:
            loc_match = match_location_name_to_region(record.get('location_name') or '', regions)
            if loc_match:
                region, lat, lng = loc_match
                record['lat'] = lat
                record['lng'] = lng
                print(f'[news_ingest] location-name fallback: "{record.get("location_name")}" -> {region.name}')
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
    _run_retention_cleanup()
    return 0


if __name__ == '__main__':
    sys.exit(main())
