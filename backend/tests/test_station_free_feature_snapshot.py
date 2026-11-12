from __future__ import annotations

import copy
import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.common.station_free_feature_snapshot import (
    StationFreeFeatureSnapshotError,
    build_station_free_feature_snapshot,
    load_station_free_feature_snapshot,
    write_station_free_feature_snapshot,
)


def _source_manifest(**overrides):
    manifest = {
        "source_key": "era5_land",
        "source_family": "open_weather_reanalysis",
        "source_snapshot_id": "era5-land-snapshot-v1",
        "source_manifest_sha256": "a" * 64,
        "source_content_sha256": "b" * 64,
        "license": "Copernicus licence review",
        "license_status": "pending",
        "license_review_id": "review-era5-land",
        "station_data_used": False,
    }
    manifest.update(overrides)
    return manifest


def _feature(index=0, **overrides):
    row = {
        "feature_id": f"era5-feature-{index}",
        "region_key": "himalayas_nepal",
        "lat": 28.0 + index * 0.01,
        "lng": 86.0 + index * 0.01,
        "feature_valid_from": "2020-12-01T00:00:00Z",
        "feature_valid_until": "2020-12-02T00:00:00Z",
        "feature_cutoff_at": "2020-12-01T00:00:00Z",
        "features": {
            "temperature_2m": -8.0,
            "snowfall": 2.5,
            "precipitation": 3.0,
            "relative_humidity_2m": 74.0,
            "windspeed_10m": 18.0,
        },
        "training_eligible": False,
        "core_training_eligible": False,
        "production_scoring_eligible": False,
    }
    row.update(overrides)
    return row


class StationFreeFeatureSnapshotTests(unittest.TestCase):
    def test_builds_hashable_station_free_rows_with_explicit_window(self) -> None:
        rows, manifest = build_station_free_feature_snapshot(
            [_feature()],
            region_keys=["himalayas_nepal"],
            source_manifest=_source_manifest(),
        )

        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["feature_join_key"].startswith("himalayas_nepal:"))
        self.assertEqual(rows[0]["feature_valid_until"], "2020-12-02T00:00:00Z")
        self.assertFalse(rows[0]["training_eligible"])
        self.assertFalse(rows[0]["production_scoring_eligible"])
        self.assertFalse(manifest["station_data_used"])
        self.assertTrue(manifest["feature_snapshot_ready"])
        self.assertFalse(manifest["training_eligible"])
        self.assertEqual(manifest["feature_row_count"], 1)

    def test_preserves_source_cutoff_review_metadata(self) -> None:
        _, manifest = build_station_free_feature_snapshot(
            [_feature()],
            region_keys=["himalayas_nepal"],
            source_manifest=_source_manifest(
                cutoff_policy="valid_time_shadow",
                cutoff_policy_review_status="pending_scientist_approval",
            ),
        )

        source = manifest["source_manifests"]["era5_land"]
        self.assertEqual(source["cutoff_policy"], "valid_time_shadow")
        self.assertEqual(
            source["cutoff_policy_review_status"],
            "pending_scientist_approval",
        )

    def test_write_and_load_recheck_hashes_and_order(self) -> None:
        rows, manifest = build_station_free_feature_snapshot(
            [_feature(1), _feature(0)],
            region_keys=["himalayas_nepal"],
            source_manifest=_source_manifest(),
        )
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "features"
            write_station_free_feature_snapshot(output, rows, manifest)
            loaded_rows, loaded_manifest = load_station_free_feature_snapshot(
                output / "snapshot_manifest.json"
            )

        self.assertEqual(loaded_rows, rows)
        self.assertEqual(loaded_manifest["feature_rows_sha256"], manifest["feature_rows_sha256"])
        self.assertEqual(loaded_manifest["manifest_hash"], manifest["manifest_hash"])

    def test_rejects_leakage_station_data_and_duplicate_features(self) -> None:
        with self.assertRaisesRegex(StationFreeFeatureSnapshotError, "cutoff"):
            build_station_free_feature_snapshot(
                [_feature(feature_cutoff_at="2020-12-01T00:00:01Z")],
                region_keys=["himalayas_nepal"],
                source_manifest=_source_manifest(),
            )

        with self.assertRaisesRegex(StationFreeFeatureSnapshotError, "station"):
            build_station_free_feature_snapshot(
                [_feature(station_id="station-1")],
                region_keys=["himalayas_nepal"],
                source_manifest=_source_manifest(),
            )

        duplicate = _feature()
        with self.assertRaisesRegex(StationFreeFeatureSnapshotError, "duplicate"):
            build_station_free_feature_snapshot(
                [duplicate, copy.deepcopy(duplicate)],
                region_keys=["himalayas_nepal"],
                source_manifest=_source_manifest(),
            )

    def test_rejects_source_manifest_with_station_data_or_invalid_hash(self) -> None:
        with self.assertRaisesRegex(StationFreeFeatureSnapshotError, "station_data_used"):
            build_station_free_feature_snapshot(
                [_feature()],
                region_keys=["himalayas_nepal"],
                source_manifest=_source_manifest(station_data_used=True),
            )

        with self.assertRaisesRegex(StationFreeFeatureSnapshotError, "SHA-256"):
            build_station_free_feature_snapshot(
                [_feature()],
                region_keys=["himalayas_nepal"],
                source_manifest=_source_manifest(source_content_sha256="not-a-hash"),
            )


if __name__ == "__main__":
    unittest.main()
