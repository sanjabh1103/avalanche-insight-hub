from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import requests

from backend.common import snowpack_proxy
from backend.common.snowpack_proxy import fetch_batched_cell_snowpack_proxies_strict


class FakeResponse:
    def __init__(self, status_code: int, payload, *, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f'HTTP {self.status_code}', response=self)


def _daily_payload(*, temp_mean: float = -6.0, temp_min: float = -10.0, snowfall: float = 12.0, precipitation: float = 20.0):
    return {
        'daily': {
            'time': ['2026-04-20'],
            'temperature_2m_mean': [temp_mean],
            'temperature_2m_min': [temp_min],
            'snowfall_sum': [snowfall],
            'precipitation_sum': [precipitation],
        }
    }


class SnowpackProxyBatchTests(unittest.TestCase):
    def test_fetch_batched_cell_snowpack_proxies_strict_parses_multi_coordinate_payload(self) -> None:
        response = FakeResponse(200, [_daily_payload(), _daily_payload(temp_mean=-3.0, snowfall=8.0)])

        with patch.object(snowpack_proxy.requests, 'get', return_value=response) as get_mock:
            proxies = fetch_batched_cell_snowpack_proxies_strict(
                coordinates=[(46.8, 9.8), (46.9, 9.9)],
                as_of=datetime(2026, 4, 28, tzinfo=timezone.utc),
            )

        self.assertEqual(len(proxies), 2)
        self.assertTrue(all(proxy.method == 'seasonal_cumulative_v1' for proxy in proxies))
        self.assertEqual(proxies[0].season_start, '2025-11-01')
        params = get_mock.call_args.kwargs['params']
        self.assertEqual(params['latitude'], '46.8000,46.9000')
        self.assertEqual(params['longitude'], '9.8000,9.9000')

    def test_fetch_batched_cell_snowpack_proxies_strict_chunks_requests_at_fifty(self) -> None:
        first_batch = [_daily_payload() for _ in range(50)]
        second_batch = [_daily_payload(temp_mean=-2.0, snowfall=6.0)]

        with patch.object(
            snowpack_proxy.requests,
            'get',
            side_effect=[FakeResponse(200, first_batch), FakeResponse(200, second_batch)],
        ) as get_mock:
            proxies = fetch_batched_cell_snowpack_proxies_strict(
                coordinates=[(46.8 + idx * 0.001, 9.8 + idx * 0.001) for idx in range(51)],
                as_of=datetime(2026, 4, 28, tzinfo=timezone.utc),
            )

        self.assertEqual(len(proxies), 51)
        self.assertEqual(get_mock.call_count, 2)
        first_params = get_mock.call_args_list[0].kwargs['params']
        second_params = get_mock.call_args_list[1].kwargs['params']
        self.assertEqual(first_params['latitude'].count(','), 49)
        self.assertEqual(second_params['latitude'], '46.8500')

    def test_fetch_batched_cell_snowpack_proxies_strict_retries_rate_limits(self) -> None:
        transient = FakeResponse(429, {'error': 'rate limited'}, headers={'Retry-After': '0'})
        success = FakeResponse(200, [_daily_payload()])

        with patch.object(snowpack_proxy.requests, 'get', side_effect=[transient, success]) as get_mock:
            with patch.object(snowpack_proxy.time, 'sleep', return_value=None) as sleep_mock:
                proxies = fetch_batched_cell_snowpack_proxies_strict(
                    coordinates=[(46.8, 9.8)],
                    as_of=datetime(2026, 4, 28, tzinfo=timezone.utc),
                )

        self.assertEqual(len(proxies), 1)
        self.assertEqual(get_mock.call_count, 2)
        sleep_mock.assert_called_once()

    def test_fetch_batched_cell_snowpack_proxies_strict_fails_on_count_mismatch(self) -> None:
        with patch.object(snowpack_proxy.requests, 'get', return_value=FakeResponse(200, [_daily_payload()])):
            with self.assertRaisesRegex(RuntimeError, 'count mismatch'):
                fetch_batched_cell_snowpack_proxies_strict(
                    coordinates=[(46.8, 9.8), (46.9, 9.9)],
                    as_of=datetime(2026, 4, 28, tzinfo=timezone.utc),
                )

    def test_fetch_batched_cell_snowpack_proxies_strict_fails_on_missing_daily_payload(self) -> None:
        with patch.object(snowpack_proxy.requests, 'get', return_value=FakeResponse(200, [{}])):
            with self.assertRaisesRegex(RuntimeError, 'Missing daily seasonal weather payload'):
                fetch_batched_cell_snowpack_proxies_strict(
                    coordinates=[(46.8, 9.8)],
                    as_of=datetime(2026, 4, 28, tzinfo=timezone.utc),
                )


if __name__ == '__main__':
    unittest.main()
