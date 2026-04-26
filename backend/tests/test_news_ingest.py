from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import requests

from backend import news_ingest


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object], *, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload)

    def json(self) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f'HTTP {self.status_code}', response=self)


class NewsIngestTests(unittest.TestCase):
    def test_extract_event_with_gemini_retries_transient_failures(self) -> None:
        success_payload = {
            'candidates': [{
                'content': {
                    'parts': [{
                        'text': json.dumps({
                            'is_avalanche_event': True,
                            'location_name': 'Test Pass',
                            'lat': 46.0,
                            'lng': -121.0,
                            'severity': 3,
                            'event_date_iso': '2026-04-23T00:00:00Z',
                            'confidence': 0.88,
                            'summary': 'Avalanche reported near the pass.',
                        }),
                    }],
                },
            }],
        }

        transient = FakeResponse(429, {'error': 'rate limited'}, headers={'Retry-After': '0'})
        success = FakeResponse(200, success_payload)

        with patch.object(news_ingest.requests, 'request', side_effect=[transient, success]) as request_mock:
            with patch.object(news_ingest.time, 'sleep', return_value=None) as sleep_mock:
                record = news_ingest.extract_event_with_gemini('Avalanche near pass', 'Strong slide reported by rescuers.')

        self.assertIsNotNone(record)
        assert record is not None
        self.assertTrue(record['is_avalanche_event'])
        self.assertEqual(record['location_name'], 'Test Pass')
        self.assertEqual(request_mock.call_count, 2)
        sleep_mock.assert_called_once()

    def test_fetch_newsdata_articles_deduplicates_across_multilingual_searches(self) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        first_batch = {
            'results': [
                {'article_id': 'a1', 'link': 'https://example.com/a1', 'pubDate': now_iso, 'title': 'Avalanche one'},
                {'article_id': 'dup', 'link': 'https://example.com/dup', 'pubDate': now_iso, 'title': 'Duplicate'},
            ]
        }
        second_batch = {
            'results': [
                {'article_id': 'dup', 'link': 'https://example.com/dup', 'pubDate': now_iso, 'title': 'Duplicate'},
                {'article_id': 'a2', 'link': 'https://example.com/a2', 'pubDate': now_iso, 'title': 'Avalanche two'},
            ]
        }

        with patch.object(news_ingest, 'NEWS_QUERY_TERMS', ('avalanche', 'avalancha')):
            with patch.object(news_ingest, 'NEWS_LANGUAGES', ('en', 'es')):
                with patch.object(news_ingest, 'NEWS_MAX_ARTICLES', 3):
                    with patch.object(news_ingest, '_request_json_with_backoff', side_effect=[first_batch, second_batch]) as request_mock:
                        articles = news_ingest.fetch_newsdata_articles()

        self.assertEqual([article['article_id'] for article in articles], ['a1', 'dup', 'a2'])
        self.assertEqual(request_mock.call_count, 2)

    def test_post_ingest_event_includes_autonomous_label_fields(self) -> None:
        article = {
            'article_id': 'article-1',
            'link': 'https://example.com/article-1',
            'title': 'Avalanche near pass',
            'source_id': 'example-news',
            'pubDate': '2026-04-24T00:00:00Z',
        }
        record = {
            'lat': 46.0,
            'lng': -121.0,
            'summary': 'Avalanche reported',
            'severity': 3,
            'confidence': 0.82,
            'location_name': 'Test Pass',
            'event_date_iso': '2026-04-24T00:00:00Z',
        }

        class RegionStub:
            key = 'cascades'
            name = 'Cascades'

        with patch.object(news_ingest, '_request_json_with_backoff', return_value={'ok': True}) as request_mock:
            ok = news_ingest.post_ingest_event(article, record, RegionStub())

        self.assertTrue(ok)
        _, kwargs = request_mock.call_args
        payload = kwargs['payload']
        self.assertEqual(payload['label_confidence'], 0.82)
        self.assertEqual(payload['source_model'], news_ingest.GEMINI_MODEL)
        self.assertEqual(payload['geometry_type'], 'point')


if __name__ == '__main__':
    unittest.main()
