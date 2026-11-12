"""Tests for the build_open_meteo_interval_feature_snapshot acquisition script.

These tests verify the strict 100% expected-input coverage gate, the
season-exclusion metadata, and the cache/resume integration at the script
level.  They use injected fetch functions to avoid real network calls.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from backend.common.open_meteo_interval_features import OPEN_METEO_DAILY_VARIABLES
from backend.scripts.build_open_meteo_interval_feature_snapshot import (
    _compute_coverage,
    _season_id,
    _write_bundle_manifest,
    build_parser,
    main,
)


def _payload(start: date, days: int = 2) -> bytes:
    dates = [(start + timedelta(days=index)).isoformat() for index in range(days)]
    daily = {"time": dates}
    for index, variable in enumerate(OPEN_METEO_DAILY_VARIABLES):
        daily[variable] = [float(index + 1 + offset) for offset in range(days)]
    return json.dumps({"latitude": 28.0, "longitude": 86.0, "daily": daily}).encode()


def _make_label_manifest(tmpdir: Path, labels: list[dict]) -> Path:
    """Write a minimal label manifest + events JSONL and return the manifest path."""
    events_path = tmpdir / "events.jsonl"
    events_path.write_text(
        "\n".join(json.dumps(label) for label in labels) + "\n",
        encoding="utf-8",
    )
    import hashlib
    payload = events_path.read_bytes()
    manifest = {
        "events_path": "events.jsonl",
        "event_rows_sha256": hashlib.sha256(payload).hexdigest(),
        "review_status": "reviewed_interval_staging",
        "training_eligible": False,
        "production_scoring_eligible": False,
    }
    manifest_path = tmpdir / "snapshot_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _label(source_event_id: str, *, join_key: str = "himalayas_nepal:1:2",
           start: str = "2020-12-01T00:00:00Z", end: str = "2020-12-03T00:00:00Z") -> dict:
    return {
        "source_event_id": source_event_id,
        "region_key": "himalayas_nepal",
        "feature_join_key": join_key,
        "lat": 28.0,
        "lng": 86.0,
        "interval_start": start,
        "interval_end": end,
        "label": 1,
    }


class ComputeCoverageTests(unittest.TestCase):
    def test_complete_coverage_passes(self) -> None:
        labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:3")]
        feature_rows = [
            {
                "feature_join_key": "himalayas_nepal:1:2",
                "feature_valid_from": "2020-12-01T00:00:00Z",
                "feature_valid_until": "2020-12-03T00:00:00Z",
            },
            {
                "feature_join_key": "himalayas_nepal:1:3",
                "feature_valid_from": "2020-12-01T00:00:00Z",
                "feature_valid_until": "2020-12-03T00:00:00Z",
            },
        ]
        report = _compute_coverage(labels, feature_rows, spatial_bin_km=5.0)
        self.assertTrue(report["passed"])
        # Event-level accounting
        self.assertEqual(report["raw_expected_label_count"], 2)
        self.assertEqual(report["covered_raw_label_count"], 2)
        self.assertEqual(report["missing_raw_label_count"], 0)
        self.assertEqual(report["raw_label_coverage_fraction"], 1.0)
        # Unique key-level accounting
        self.assertEqual(report["unique_expected_feature_key_count"], 2)
        self.assertEqual(report["covered_unique_feature_key_count"], 2)
        self.assertEqual(report["unique_feature_key_coverage_fraction"], 1.0)
        # Legacy backward-compatible fields
        self.assertEqual(report["expected_label_count"], 2)
        self.assertEqual(report["covered_label_count"], 2)
        self.assertEqual(report["coverage_fraction"], 1.0)

    def test_partial_coverage_fails_with_missing_labels(self) -> None:
        labels = [_label("event-a"), _label("event-b", join_key="himalayas_nepal:1:3")]
        feature_rows = [
            {
                "feature_join_key": "himalayas_nepal:1:2",
                "feature_valid_from": "2020-12-01T00:00:00Z",
                "feature_valid_until": "2020-12-03T00:00:00Z",
            },
        ]
        report = _compute_coverage(labels, feature_rows, spatial_bin_km=5.0)
        self.assertFalse(report["passed"])
        # Event-level: event-b is uncovered
        self.assertEqual(report["raw_expected_label_count"], 2)
        self.assertEqual(report["covered_raw_label_count"], 1)
        self.assertEqual(report["missing_raw_label_count"], 1)
        self.assertIn("event-b", report["missing_event_ids"])
        # Unique key-level: key 1:3 is missing
        self.assertEqual(report["unique_expected_feature_key_count"], 2)
        self.assertEqual(report["covered_unique_feature_key_count"], 1)
        # Legacy
        self.assertEqual(report["missing_labels"][0]["source_event_id"], "event-b")

    def test_duplicate_keys_track_event_level_coverage(self) -> None:
        """Multiple events sharing the same feature key must all be covered by one feature row."""
        labels = [
            _label("event-a", join_key="himalayas_nepal:1:2"),
            _label("event-b", join_key="himalayas_nepal:1:2"),  # same key, same interval
            _label("event-c", join_key="himalayas_nepal:1:3"),
        ]
        feature_rows = [
            {
                "feature_join_key": "himalayas_nepal:1:2",
                "feature_valid_from": "2020-12-01T00:00:00Z",
                "feature_valid_until": "2020-12-03T00:00:00Z",
            },
            {
                "feature_join_key": "himalayas_nepal:1:3",
                "feature_valid_from": "2020-12-01T00:00:00Z",
                "feature_valid_until": "2020-12-03T00:00:00Z",
            },
        ]
        report = _compute_coverage(labels, feature_rows, spatial_bin_km=5.0)
        self.assertTrue(report["passed"])
        # 3 raw events, 2 unique keys
        self.assertEqual(report["raw_expected_label_count"], 3)
        self.assertEqual(report["covered_raw_label_count"], 3)
        self.assertEqual(report["unique_expected_feature_key_count"], 2)
        self.assertEqual(report["covered_unique_feature_key_count"], 2)
        # Multiplicity: key 1:2 has 2 events, key 1:3 has 1 event
        self.assertEqual(report["key_multiplicity"]["min"], 1)
        self.assertEqual(report["key_multiplicity"]["max"], 2)
        self.assertEqual(report["key_multiplicity"]["mean"], 1.5)

    def test_duplicate_keys_partial_coverage_fails_at_event_level(self) -> None:
        """If one of two events sharing a key is missing the feature row, both fail."""
        labels = [
            _label("event-a", join_key="himalayas_nepal:1:2"),
            _label("event-b", join_key="himalayas_nepal:1:2"),
        ]
        feature_rows = []  # No feature rows at all
        report = _compute_coverage(labels, feature_rows, spatial_bin_km=5.0)
        self.assertFalse(report["passed"])
        self.assertEqual(report["raw_expected_label_count"], 2)
        self.assertEqual(report["covered_raw_label_count"], 0)
        self.assertEqual(report["missing_raw_label_count"], 2)
        self.assertIn("event-a", report["missing_event_ids"])
        self.assertIn("event-b", report["missing_event_ids"])
        self.assertEqual(report["unique_expected_feature_key_count"], 1)
        self.assertEqual(report["covered_unique_feature_key_count"], 0)

    def test_event_without_id_fails_gate(self) -> None:
        """An event missing its source_event_id must fail the gate."""
        label = _label("event-a")
        del label["source_event_id"]
        report = _compute_coverage([label], [], spatial_bin_km=5.0)
        self.assertFalse(report["passed"])
        self.assertEqual(report["events_without_id_count"], 1)

    def test_non_positive_labels_are_ignored(self) -> None:
        label = _label("event-a")
        label["label"] = 0
        report = _compute_coverage([label], [], spatial_bin_km=5.0)
        self.assertTrue(report["passed"])
        self.assertEqual(report["raw_expected_label_count"], 0)
        self.assertEqual(report["unique_expected_feature_key_count"], 0)

    def test_duplicate_event_ids_fail_gate(self) -> None:
        """Duplicate event IDs must be rejected, not silently overwritten."""
        labels = [
            _label("event-dup", join_key="himalayas_nepal:1:2"),
            _label("event-dup", join_key="himalayas_nepal:1:3"),  # same ID, different key
        ]
        feature_rows = [
            {
                "feature_join_key": "himalayas_nepal:1:2",
                "feature_valid_from": "2020-12-01T00:00:00Z",
                "feature_valid_until": "2020-12-03T00:00:00Z",
            },
            {
                "feature_join_key": "himalayas_nepal:1:3",
                "feature_valid_from": "2020-12-01T00:00:00Z",
                "feature_valid_until": "2020-12-03T00:00:00Z",
            },
        ]
        report = _compute_coverage(labels, feature_rows, spatial_bin_km=5.0)
        self.assertFalse(report["passed"])
        self.assertEqual(report["duplicate_event_id_count"], 1)
        self.assertIn("event-dup", report["duplicate_event_ids"])
        # Only the first occurrence is counted in raw_expected
        self.assertEqual(report["raw_expected_label_count"], 1)


class SeasonExclusionTests(unittest.TestCase):
    def test_season_id_for_november_is_current_year(self) -> None:
        row = _label("event-a", start="2020-11-15T00:00:00Z", end="2020-11-16T00:00:00Z")
        self.assertEqual(_season_id(row), "2020-2021")

    def test_season_id_for_october_is_previous_year(self) -> None:
        row = _label("event-a", start="2020-10-15T00:00:00Z", end="2020-10-16T00:00:00Z")
        self.assertEqual(_season_id(row), "2019-2020")


class BuildParserTests(unittest.TestCase):
    def test_parser_accepts_exclude_season(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "--label-manifest", "/tmp/manifest.json",
            "--output-dir", "/tmp/output",
            "--region-key", "himalayas_nepal",
            "--exclude-season", "2025-2026",
            "--model", "era5",
            "--max-request-days", "90",
            "--request-timeout-seconds", "30",
            "--strict-coverage",
        ])
        self.assertEqual(args.excluded_seasons, ["2025-2026"])
        self.assertEqual(args.model, "era5")
        self.assertEqual(args.max_request_days, 90)
        self.assertEqual(args.request_timeout_seconds, 30.0)
        self.assertTrue(args.strict_coverage)

    def test_parser_accepts_no_strict_coverage(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "--label-manifest", "/tmp/manifest.json",
            "--output-dir", "/tmp/output",
            "--region-key", "himalayas_nepal",
            "--no-strict-coverage",
        ])
        self.assertFalse(args.strict_coverage)

    def test_parser_defaults_strict_coverage_to_true(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "--label-manifest", "/tmp/manifest.json",
            "--output-dir", "/tmp/output",
            "--region-key", "himalayas_nepal",
        ])
        self.assertTrue(args.strict_coverage)


class MainScriptTests(unittest.TestCase):
    def test_complete_run_passes_coverage_gate(self) -> None:
        """A run where every label gets a feature row should exit 0."""
        import backend.common.open_meteo_interval_features as omif

        original_fetch_daily = omif.OpenMeteoArchiveClient.fetch_daily

        def mock_fetch_daily(self, lat, lng, start, end, *, model="era5_land"):
            url = omif.build_archive_url(lat, lng, start, end, model=model)
            days = (end - start).days + 1
            raw = _payload(start, days=days)
            import hashlib
            payload = json.loads(raw.decode("utf-8"))
            return {
                "url": url,
                "latitude": payload.get("latitude", lat),
                "longitude": payload.get("longitude", lng),
                "model": model,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "request_attempts": 1,
                "raw_payload_sha256": hashlib.sha256(raw).hexdigest(),
                "payload": payload,
            }

        omif.OpenMeteoArchiveClient.fetch_daily = mock_fetch_daily
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                manifest_path = _make_label_manifest(tmpdir_path, [_label("event-a")])
                output_dir = tmpdir_path / "output"

                exit_code = main([
                    "--label-manifest", str(manifest_path),
                    "--output-dir", str(output_dir),
                    "--region-key", "himalayas_nepal",
                    "--model", "era5",
                    "--max-request-days", "90",
                    "--request-timeout-seconds", "30",
                ])

                self.assertEqual(exit_code, 0)
                provenance = json.loads(
                    (output_dir / "source_provenance.json").read_text()
                )
                self.assertTrue(provenance["coverage_gate_passed"])
                self.assertEqual(provenance["coverage_gate"]["coverage_fraction"], 1.0)
        finally:
            omif.OpenMeteoArchiveClient.fetch_daily = original_fetch_daily

    def test_exclude_season_preserves_excluded_labels(self) -> None:
        """Excluded labels should be preserved in provenance with exclusion metadata."""
        import backend.common.open_meteo_interval_features as omif

        original_fetch_daily = omif.OpenMeteoArchiveClient.fetch_daily

        def mock_fetch_daily(self, lat, lng, start, end, *, model="era5_land"):
            url = omif.build_archive_url(lat, lng, start, end, model=model)
            days = (end - start).days + 1
            raw = _payload(start, days=days)
            import hashlib
            payload = json.loads(raw.decode("utf-8"))
            return {
                "url": url,
                "latitude": payload.get("latitude", lat),
                "longitude": payload.get("longitude", lng),
                "model": model,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "request_attempts": 1,
                "raw_payload_sha256": hashlib.sha256(raw).hexdigest(),
                "payload": payload,
            }

        omif.OpenMeteoArchiveClient.fetch_daily = mock_fetch_daily
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                # One label in 2020-2021 season, one in 2025-2026 season
                labels = [
                    _label("event-2020", start="2020-12-01T00:00:00Z", end="2020-12-03T00:00:00Z"),
                    _label("event-2025", start="2025-11-03T00:00:00Z", end="2025-11-04T00:00:00Z",
                           join_key="himalayas_nepal:1:3"),
                ]
                manifest_path = _make_label_manifest(tmpdir_path, labels)
                output_dir = tmpdir_path / "output"

                exit_code = main([
                    "--label-manifest", str(manifest_path),
                    "--output-dir", str(output_dir),
                    "--region-key", "himalayas_nepal",
                    "--model", "era5",
                    "--exclude-season", "2025-2026",
                    "--max-request-days", "90",
                    "--request-timeout-seconds", "30",
                ])

                self.assertEqual(exit_code, 0)
                provenance = json.loads(
                    (output_dir / "source_provenance.json").read_text()
                )
                self.assertEqual(provenance["excluded_label_count"], 1)
                self.assertEqual(provenance["label_row_count"], 1)
                excluded = provenance["excluded_labels"][0]
                self.assertFalse(excluded["included_in_primary_snapshot"])
                self.assertEqual(excluded["exclusion_reason"], "partial_or_sparse_current_season")
                self.assertEqual(excluded["source_event_id"], "event-2025")
        finally:
            omif.OpenMeteoArchiveClient.fetch_daily = original_fetch_daily

    def test_bundle_manifest_is_written_and_links_all_hashes(self) -> None:
        """The bundle manifest must link all artifact hashes for external verification."""
        import backend.common.open_meteo_interval_features as omif

        original_fetch_daily = omif.OpenMeteoArchiveClient.fetch_daily

        def mock_fetch_daily(self, lat, lng, start, end, *, model="era5_land"):
            url = omif.build_archive_url(lat, lng, start, end, model=model)
            days = (end - start).days + 1
            raw = _payload(start, days=days)
            import hashlib
            payload = json.loads(raw.decode("utf-8"))
            return {
                "url": url,
                "latitude": payload.get("latitude", lat),
                "longitude": payload.get("longitude", lng),
                "model": model,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "request_attempts": 1,
                "raw_payload_sha256": hashlib.sha256(raw).hexdigest(),
                "payload": payload,
            }

        omif.OpenMeteoArchiveClient.fetch_daily = mock_fetch_daily
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                manifest_path = _make_label_manifest(tmpdir_path, [_label("event-a")])
                output_dir = tmpdir_path / "output"

                exit_code = main([
                    "--label-manifest", str(manifest_path),
                    "--output-dir", str(output_dir),
                    "--region-key", "himalayas_nepal",
                    "--model", "era5",
                    "--max-request-days", "90",
                    "--request-timeout-seconds", "30",
                ])

                self.assertEqual(exit_code, 0)
                bundle_path = output_dir / "bundle_manifest.json"
                self.assertTrue(bundle_path.is_file())
                bundle = json.loads(bundle_path.read_text())

                # Verify all component hashes are present
                components = bundle["component_hashes"]
                self.assertIn("label_manifest", components)
                self.assertIn("features_jsonl", components)
                self.assertIn("snapshot_manifest", components)
                self.assertIn("source_provenance", components)
                self.assertIn("cache_manifest", components)
                self.assertIn("excluded_event_record", components)
                self.assertIn("coverage_gate", components)

                # Verify hashes are non-null for existing files
                self.assertIsNotNone(components["features_jsonl"]["sha256"])
                self.assertIsNotNone(components["snapshot_manifest"]["sha256"])
                self.assertIsNotNone(components["source_provenance"]["sha256"])

                # Verify bundle hash is present and is a valid SHA-256
                self.assertIn("bundle_sha256", bundle)
                self.assertEqual(len(bundle["bundle_sha256"]), 64)

                # Verify summary fields
                self.assertFalse(bundle["training_eligible"])
                self.assertFalse(bundle["production_scoring_eligible"])
                self.assertEqual(bundle["coverage_scope"], "label_linked_interval_features")
                self.assertFalse(bundle["operational_grid_coverage"])
        finally:
            omif.OpenMeteoArchiveClient.fetch_daily = original_fetch_daily

    def test_bundle_manifest_hash_changes_on_tamper(self) -> None:
        """Tampering with an artifact file must change the bundle hash."""
        import hashlib
        import backend.common.open_meteo_interval_features as omif
        from backend.scripts.build_open_meteo_interval_feature_snapshot import _sha256_file

        original_fetch_daily = omif.OpenMeteoArchiveClient.fetch_daily

        def mock_fetch_daily(self, lat, lng, start, end, *, model="era5_land"):
            url = omif.build_archive_url(lat, lng, start, end, model=model)
            days = (end - start).days + 1
            raw = _payload(start, days=days)
            payload = json.loads(raw.decode("utf-8"))
            return {
                "url": url,
                "latitude": payload.get("latitude", lat),
                "longitude": payload.get("longitude", lng),
                "model": model,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "request_attempts": 1,
                "raw_payload_sha256": hashlib.sha256(raw).hexdigest(),
                "payload": payload,
            }

        omif.OpenMeteoArchiveClient.fetch_daily = mock_fetch_daily
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                manifest_path = _make_label_manifest(tmpdir_path, [_label("event-a")])
                output_dir = tmpdir_path / "output"

                main([
                    "--label-manifest", str(manifest_path),
                    "--output-dir", str(output_dir),
                    "--region-key", "himalayas_nepal",
                    "--model", "era5",
                ])

                bundle = json.loads((output_dir / "bundle_manifest.json").read_text())
                original_features_hash = bundle["component_hashes"]["features_jsonl"]["sha256"]

                # Tamper: append a line to features.jsonl
                with open(output_dir / "features.jsonl", "a") as f:
                    f.write('{"tampered": true}\n')

                # Recompute the file hash
                tampered_features_hash = _sha256_file(output_dir / "features.jsonl")

                # The file hash must have changed
                self.assertNotEqual(original_features_hash, tampered_features_hash)

                # The bundle manifest's recorded hash no longer matches the file
                self.assertNotEqual(
                    bundle["component_hashes"]["features_jsonl"]["sha256"],
                    tampered_features_hash,
                )
        finally:
            omif.OpenMeteoArchiveClient.fetch_daily = original_fetch_daily


if __name__ == "__main__":
    unittest.main()
