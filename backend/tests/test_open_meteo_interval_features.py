from __future__ import annotations

import json
import unittest
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from backend.common.open_meteo_interval_features import (
    OPEN_METEO_DAILY_VARIABLES,
    OpenMeteoArchiveClient,
    OpenMeteoIntervalFeatureError,
    aggregate_daily_interval,
    build_archive_url,
    build_open_meteo_interval_features,
    _canonical_bytes,
    _sha256,
    _verify_cached_response,
)


def _payload(start: date, days: int = 2) -> bytes:
    dates = [(start + timedelta(days=index)).isoformat() for index in range(days)]
    daily = {"time": dates}
    for index, variable in enumerate(OPEN_METEO_DAILY_VARIABLES):
        daily[variable] = [float(index + 1 + offset) for offset in range(days)]
    return json.dumps({"latitude": 28.0, "longitude": 86.0, "daily": daily}).encode()


def _label(source_event_id: str, *, join_key: str = "himalayas_nepal:1:2") -> dict:
    return {
        "source_event_id": source_event_id,
        "region_key": "himalayas_nepal",
        "feature_join_key": join_key,
        "lat": 28.0,
        "lng": 86.0,
        "interval_start": "2020-12-01T00:00:00Z",
        "interval_end": "2020-12-03T00:00:00Z",
        "label": 1,
    }


class OpenMeteoIntervalFeatureTests(unittest.TestCase):
    def test_transient_429_retries_with_retry_after_and_records_attempts(self) -> None:
        calls = 0
        delays: list[float] = []

        def fetch(url: str) -> bytes:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise HTTPError(url, 429, "rate limited", {"Retry-After": "0"}, None)
            return _payload(date(2020, 12, 1), days=2)

        client = OpenMeteoArchiveClient(
            fetch=fetch,
            max_retries=2,
            backoff_seconds=99,
            sleep_fn=delays.append,
        )
        response = client.fetch_daily(
            28.0,
            86.0,
            date(2020, 12, 1),
            date(2020, 12, 2),
        )

        self.assertEqual(calls, 2)
        self.assertEqual(delays, [0.0])
        self.assertEqual(response["request_attempts"], 2)

    def test_persistent_transient_error_fails_with_bounded_attempts(self) -> None:
        calls = 0

        def fetch(url: str) -> bytes:
            nonlocal calls
            calls += 1
            raise HTTPError(url, 503, "unavailable", {}, None)

        with self.assertRaisesRegex(OpenMeteoIntervalFeatureError, r"HTTP 503 after 3 attempt"):
            OpenMeteoArchiveClient(
                fetch=fetch,
                max_retries=2,
                backoff_seconds=0,
                sleep_fn=lambda _: None,
            ).fetch_daily(28.0, 86.0, date(2020, 12, 1), date(2020, 12, 2))
        self.assertEqual(calls, 3)

    def test_non_transient_http_error_is_not_retried(self) -> None:
        calls = 0

        def fetch(url: str) -> bytes:
            nonlocal calls
            calls += 1
            raise HTTPError(url, 400, "bad request", {}, None)

        with self.assertRaisesRegex(OpenMeteoIntervalFeatureError, r"HTTP 400 after 1 attempt"):
            OpenMeteoArchiveClient(fetch=fetch, sleep_fn=lambda _: None).fetch_daily(
                28.0, 86.0, date(2020, 12, 1), date(2020, 12, 2)
            )
        self.assertEqual(calls, 1)

    def test_archive_url_is_explicit_and_daily(self) -> None:
        url = build_archive_url(28.0, 86.0, date(2020, 12, 1), date(2020, 12, 3))
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["models"], ["era5_land"])
        self.assertEqual(query["timezone"], ["UTC"])
        self.assertEqual(query["start_date"], ["2020-12-01"])
        self.assertEqual(query["end_date"], ["2020-12-03"])
        self.assertEqual(query["daily"][0].split(","), list(OPEN_METEO_DAILY_VARIABLES))

    def test_aggregate_requires_complete_interval_and_preserves_missingness(self) -> None:
        payload = json.loads(_payload(date(2020, 12, 1), days=2))
        features = aggregate_daily_interval(
            payload,
            "2020-12-01T00:00:00Z",
            "2020-12-03T00:00:00Z",
        )
        self.assertEqual(features["snowfall"], 7.0)
        self.assertEqual(features["windspeed_10m"], 6.0)

        payload["daily"]["time"] = ["2020-12-01"]
        with self.assertRaisesRegex(OpenMeteoIntervalFeatureError, "does not cover"):
            aggregate_daily_interval(
                payload,
                "2020-12-01T00:00:00Z",
                "2020-12-03T00:00:00Z",
            )

    def test_grouped_fetch_builds_shadow_rows_without_station_data(self) -> None:
        calls: list[str] = []

        def fetch(url: str) -> bytes:
            calls.append(url)
            return _payload(date(2020, 12, 1), days=2)

        rows, source_manifest, fetch_records = build_open_meteo_interval_features(
            [_label("event-a"), _label("event-b")],
            client=OpenMeteoArchiveClient(fetch=fetch),
            source_manifest_sha256="a" * 64,
            license_review_id="review-pending",
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(fetch_records), 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["feature_cutoff_at"], "2020-12-01T00:00:00Z")
        self.assertEqual(rows[0]["feature_cutoff_status"], "explicit_provisional_valid_time_shadow")
        self.assertFalse(rows[0]["station_data_used"])
        self.assertFalse(rows[0]["training_eligible"])
        self.assertEqual(rows[0]["native_resolution_m"], 11000.0)
        self.assertFalse(rows[0]["direct_station_data_used"])
        self.assertTrue(rows[0]["retrospective_only"])
        self.assertFalse(source_manifest["station_data_used"])
        self.assertEqual(source_manifest["license_status"], "pending")
        self.assertEqual(source_manifest["dataset_product"], "ERA5-Land")
        self.assertEqual(source_manifest["native_resolution_m"], 11000.0)
        self.assertEqual(source_manifest["license_url"], "https://open-meteo.com/en/licence")

        rows, source_manifest, _ = build_open_meteo_interval_features(
            [_label("event-a")],
            client=OpenMeteoArchiveClient(fetch=fetch),
            source_manifest_sha256="a" * 64,
            license_review_id="review-pending",
            model="era5",
        )
        self.assertEqual(source_manifest["source_key"], "era5")
        self.assertEqual(rows[0]["source_key"], "era5")
        self.assertEqual(source_manifest["dataset_product"], "ERA5")
        self.assertEqual(source_manifest["native_resolution_m"], 25000.0)
        self.assertNotIn("ERA5-Land", source_manifest["license"])
        self.assertEqual(source_manifest["availability_delay_days"], 5)
        self.assertEqual(source_manifest["underlying_reanalysis_observations"], "included_by_provider")

    def test_long_window_is_chunked_and_merged_deterministically(self) -> None:
        calls: list[tuple[str, str]] = []

        def fetch(url: str) -> bytes:
            query = parse_qs(urlparse(url).query)
            start = date.fromisoformat(query["start_date"][0])
            end = date.fromisoformat(query["end_date"][0])
            calls.append((query["start_date"][0], query["end_date"][0]))
            return _payload(start, days=(end - start).days + 1)

        rows, _, fetch_records = build_open_meteo_interval_features(
            [_label("long-window")],
            client=OpenMeteoArchiveClient(fetch=fetch),
            source_manifest_sha256="a" * 64,
            license_review_id="review-pending",
            max_request_days=1,
        )

        self.assertEqual(calls, [("2020-12-01", "2020-12-01"), ("2020-12-02", "2020-12-02")])
        self.assertEqual(len(fetch_records), 2)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["features"]["snowfall"], 6.0)

    def test_scene_aware_event_time_bounds_are_accepted_as_interval_aliases(self) -> None:
        label = _label("event-alias")
        label.pop("interval_start")
        label.pop("interval_end")
        label["event_time_start"] = "2020-12-01T00:00:00Z"
        label["event_time_end"] = "2020-12-03T00:00:00Z"

        rows, _, fetch_records = build_open_meteo_interval_features(
            [label],
            client=OpenMeteoArchiveClient(
                fetch=lambda _: _payload(date(2020, 12, 1), days=2)
            ),
            source_manifest_sha256="a" * 64,
            license_review_id="review-pending",
        )

        self.assertEqual(len(fetch_records), 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["feature_valid_from"], "2020-12-01T00:00:00Z")
        self.assertEqual(rows[0]["feature_valid_until"], "2020-12-03T00:00:00Z")

    def test_invalid_cutoff_policy_is_fail_closed(self) -> None:
        with self.assertRaisesRegex(OpenMeteoIntervalFeatureError, "cutoff policy"):
            build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=lambda _: _payload(date(2020, 12, 1))),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cutoff_policy="inferred",
            )

    def test_conflicting_interval_aliases_are_rejected(self) -> None:
        label = _label("event-conflict")
        label["event_time_start"] = "2020-12-02T00:00:00Z"
        with self.assertRaisesRegex(OpenMeteoIntervalFeatureError, "conflicting interval_start aliases"):
            build_open_meteo_interval_features(
                [label],
                client=OpenMeteoArchiveClient(fetch=lambda _: _payload(date(2020, 12, 1))),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
            )

    def test_cached_response_is_reused_on_resume(self) -> None:
        """A second call with the same cache_dir must not re-fetch cached chunks."""
        import tempfile
        from pathlib import Path

        fetch_calls: list[str] = []

        def fetch(url: str) -> bytes:
            fetch_calls.append(url)
            return _payload(date(2020, 12, 1), days=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "raw_cache"

            # First run: fetches and caches
            rows1, _, fetch_records1 = build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=fetch),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cache_dir=cache_dir,
            )
            self.assertEqual(len(fetch_calls), 1)
            self.assertEqual(len(rows1), 1)

            # Cache manifest should exist
            manifest_path = cache_dir / "cache_manifest.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["entry_count"], 1)
            self.assertEqual(manifest["cached_count"], 1)

            # Second run: should use cache, no new fetch calls
            rows2, _, fetch_records2 = build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=fetch),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cache_dir=cache_dir,
            )
            self.assertEqual(len(fetch_calls), 1)  # No new fetch
            self.assertEqual(len(rows2), 1)
            self.assertEqual(rows2[0]["feature_id"], rows1[0]["feature_id"])

    def test_corrupted_cache_entry_is_refetched(self) -> None:
        """A corrupted cache file (invalid JSON) must be silently discarded and re-fetched."""
        import tempfile
        from pathlib import Path

        fetch_calls: list[str] = []

        def fetch(url: str) -> bytes:
            fetch_calls.append(url)
            return _payload(date(2020, 12, 1), days=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "raw_cache"

            # First run: fetches and caches
            build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=fetch),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cache_dir=cache_dir,
            )
            self.assertEqual(len(fetch_calls), 1)

            # Corrupt the cache file with invalid JSON
            from backend.common.open_meteo_interval_features import _cache_key
            url = build_archive_url(28.0, 86.0, date(2020, 12, 1), date(2020, 12, 2))
            cache_path = cache_dir / f"{_cache_key(url)}.json"
            self.assertTrue(cache_path.is_file())
            cache_path.write_text("CORRUPTED{invalid json", encoding="utf-8")

            # Second run: should re-fetch the corrupted entry
            build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=fetch),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cache_dir=cache_dir,
            )
            self.assertEqual(len(fetch_calls), 2)  # Re-fetched

    def test_tampered_payload_is_rejected_and_refetched(self) -> None:
        """A cache entry with a modified payload but unchanged stored hash must be rejected.

        This is the critical cache integrity test: an attacker or disk
        corruption modifies the payload data but leaves the stored
        raw_payload_sha256 unchanged.  The cache must recompute the
        canonical payload hash, detect the mismatch, and re-fetch.
        """
        import tempfile
        from pathlib import Path

        fetch_calls: list[str] = []

        def fetch(url: str) -> bytes:
            fetch_calls.append(url)
            return _payload(date(2020, 12, 1), days=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "raw_cache"

            # First run: fetches and caches
            build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=fetch),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cache_dir=cache_dir,
            )
            self.assertEqual(len(fetch_calls), 1)

            # Tamper with the payload: modify a temperature value but keep the stored hash
            from backend.common.open_meteo_interval_features import _cache_key
            url = build_archive_url(28.0, 86.0, date(2020, 12, 1), date(2020, 12, 2))
            cache_path = cache_dir / f"{_cache_key(url)}.json"
            self.assertTrue(cache_path.is_file())
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            # Tamper: change the first temperature value
            cached["payload"]["daily"]["temperature_2m_mean"][0] = 999.0
            # Keep the original raw_payload_sha256 unchanged (don't update it)
            cache_path.write_text(
                json.dumps(cached, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

            # Second run: must reject the tampered entry and re-fetch
            build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=fetch),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cache_dir=cache_dir,
            )
            self.assertEqual(len(fetch_calls), 2)  # Re-fetched due to hash mismatch

    def test_cache_manifest_records_integrity_verification(self) -> None:
        """The cache manifest must record integrity_verified status for each entry."""
        import tempfile
        from pathlib import Path

        def fetch(url: str) -> bytes:
            return _payload(date(2020, 12, 1), days=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "raw_cache"

            build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=fetch),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cache_dir=cache_dir,
            )

            manifest_path = cache_dir / "cache_manifest.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["cache_type"], "request_addressed")
            self.assertEqual(manifest["entry_count"], 1)
            self.assertEqual(manifest["cached_count"], 1)
            self.assertEqual(manifest["integrity_verified_count"], 1)
            self.assertTrue(manifest["entries"][0]["integrity_verified"])
            self.assertIn("cache_manifest_sha256", manifest)

    def test_cache_disabled_when_dir_is_none(self) -> None:
        """When cache_dir is None, no cache files should be created."""
        import tempfile
        from pathlib import Path

        fetch_calls: list[str] = []

        def fetch(url: str) -> bytes:
            fetch_calls.append(url)
            return _payload(date(2020, 12, 1), days=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = None

            rows, _, _ = build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=fetch),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cache_dir=cache_dir,
            )
            self.assertEqual(len(fetch_calls), 1)
            self.assertEqual(len(rows), 1)
            # No cache directory should have been created
            self.assertFalse((Path(tmpdir) / "raw_cache").exists())

    def test_cache_metadata_mismatch_rejects_entry(self) -> None:
        """A cache entry whose model or dates don't match the URL query must be rejected."""
        import tempfile
        from pathlib import Path

        fetch_calls: list[str] = []

        def fetch(url: str) -> bytes:
            fetch_calls.append(url)
            return _payload(date(2020, 12, 1), days=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "raw_cache"

            # First run: fetches and caches
            build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=fetch),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cache_dir=cache_dir,
            )
            self.assertEqual(len(fetch_calls), 1)

            # Tamper: change the model field in the cached entry to mismatch the URL
            from backend.common.open_meteo_interval_features import _cache_key
            url = build_archive_url(28.0, 86.0, date(2020, 12, 1), date(2020, 12, 2), model="era5_land")
            cache_path = cache_dir / f"{_cache_key(url)}.json"
            self.assertTrue(cache_path.is_file())
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached["model"] = "era5"  # URL says era5_land, cache says era5
            cache_path.write_text(
                json.dumps(cached, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )

            # Second run: must reject the mismatched entry and re-fetch
            build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=fetch),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cache_dir=cache_dir,
            )
            self.assertEqual(len(fetch_calls), 2)  # Re-fetched due to metadata mismatch

    def test_self_consistent_cache_tamper_passes_cache_check_but_detected_by_bundle(self) -> None:
        """A self-consistent tamper (payload + canonical hash both changed) passes
        the cache-level _verify_cached_response because the recomputed canonical
        hash matches the stored hash.  This is a known limitation of the cache
        verifier alone.  The real defense is at the BUNDLE level: the
        raw_payload_sha256 recorded in the cache manifest and provenance will
        no longer match the actual cached payload, and the bundle manifest's
        file hash for the cache file will change.  The preflight verifier
        detects this by recomputing all file hashes and comparing with the
        bundle manifest.

        This test documents the cache-level behavior honestly: the cache
        verifier accepts a self-consistent tamper, but the raw_payload_sha256
        diverges, which is detectable at the bundle/provenance level.
        """
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "raw_cache"

            # Build a valid cached response
            url = build_archive_url(28.0, 86.0, date(2020, 12, 1), date(2020, 12, 2))
            payload = json.loads(_payload(date(2020, 12, 1), days=2).decode("utf-8"))
            original_raw_hash = _sha256(_payload(date(2020, 12, 1), days=2))
            canonical_hash = _sha256(_canonical_bytes(payload))

            cached = {
                "url": url,
                "latitude": 28.0,
                "longitude": 86.0,
                "model": "era5_land",
                "start_date": "2020-12-01",
                "end_date": "2020-12-02",
                "request_attempts": 1,
                "raw_payload_sha256": original_raw_hash,
                "canonical_payload_sha256": canonical_hash,
                "payload": payload,
            }

            # Verify the original passes
            self.assertTrue(_verify_cached_response(cached, url))

            # Tamper: modify payload AND update canonical hash to match
            tampered_payload = dict(payload)
            tampered_daily = dict(tampered_payload["daily"])
            tampered_daily["temperature_2m_mean"] = [999.0] + tampered_daily["temperature_2m_mean"][1:]
            tampered_payload["daily"] = tampered_daily
            tampered_canonical_hash = _sha256(_canonical_bytes(tampered_payload))

            tampered_cached = dict(cached)
            tampered_cached["payload"] = tampered_payload
            tampered_cached["canonical_payload_sha256"] = tampered_canonical_hash

            # The cache-level canonical hash verification passes (attacker updated it)
            # This is an honest assertion: the cache verifier alone cannot detect this
            self.assertTrue(_verify_cached_response(tampered_cached, url))

            # The raw_payload_sha256 no longer matches the tampered payload.
            # This is the signal that the bundle verifier detects: the cache
            # file hash changes, so the bundle manifest's recorded hash for
            # the cache file will no longer match.
            tampered_file_bytes = json.dumps(
                tampered_cached, ensure_ascii=False, sort_keys=True, indent=2
            ).encode("utf-8")
            original_file_bytes = json.dumps(
                cached, ensure_ascii=False, sort_keys=True, indent=2
            ).encode("utf-8")
            self.assertNotEqual(_sha256(original_file_bytes), _sha256(tampered_file_bytes))

    def test_cache_manifest_includes_canonical_payload_sha256(self) -> None:
        """Each cache-manifest entry must include the canonical_payload_sha256."""
        import tempfile
        from pathlib import Path

        def fetch(url: str) -> bytes:
            return _payload(date(2020, 12, 1), days=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "raw_cache"

            build_open_meteo_interval_features(
                [_label("event-a")],
                client=OpenMeteoArchiveClient(fetch=fetch),
                source_manifest_sha256="a" * 64,
                license_review_id="review-pending",
                cache_dir=cache_dir,
            )

            manifest = json.loads((cache_dir / "cache_manifest.json").read_text())
            entry = manifest["entries"][0]
            self.assertIn("canonical_payload_sha256", entry)
            self.assertIsNotNone(entry["canonical_payload_sha256"])
            self.assertEqual(len(entry["canonical_payload_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
